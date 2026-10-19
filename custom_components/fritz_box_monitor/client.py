"""Client to talk to a FRITZ!Box cable modem.

The integration never talks to the modem itself; all device access goes
through this module, mirroring the library role from the Home Assistant
integration tutorial (step 1).

The client speaks the web UI protocol of FRITZ!OS cable boxes:

- authentication via ``login_sid.lua?version=2`` (PBKDF2
  challenge-response; the username is optional and may be empty for
  boxes configured for password-only login)
- data via the JSON endpoints of ``data.lua`` (``page=docInfo`` for the
  DOCSIS channel statistics)

Device identity and connection status are read from the ``doc`` section
of the docInfo page. Those keys are the least verified part of the
protocol; adjust them together with
tests/components/fritz_box_monitor/fixtures/doc_info.json once real
responses have been recorded from a box.
"""

from dataclasses import dataclass
import hashlib
import json
from typing import Any, cast
import xml.etree.ElementTree as ET

from aiohttp import ClientError, ClientSession

_ZERO_SID = "0" * 16


@dataclass(frozen=True)
class DocsisChannel:
    """A single DOCSIS channel of the cable modem.

    ``snr`` and the error counters are only exposed for downstream
    channels and are ``None`` for upstream channels.
    """

    channel_id: int
    docsis_version: str
    frequency: int  # Hz
    power: float  # dBuV
    modulation: str
    snr: float | None = None  # dB
    correctable_errors: int | None = None
    uncorrectable_errors: int | None = None


@dataclass(frozen=True)
class CableModemStatus:
    """Status snapshot of the FRITZ!Box cable modem."""

    serial_number: str
    model: str
    firmware: str
    connection_status: str
    downstream: tuple[DocsisChannel, ...]
    upstream: tuple[DocsisChannel, ...]


@dataclass(frozen=True)
class _SessionInfo:
    """Parsed SessionInfo response of login_sid.lua."""

    sid: str
    challenge: str
    block_time: int


class FritzBoxMonitorError(Exception):
    """Base error of the FRITZ!Box Monitor client."""


class FritzBoxMonitorConnectionError(FritzBoxMonitorError):
    """The cable modem could not be reached."""


class FritzBoxMonitorAuthError(FritzBoxMonitorError):
    """Authentication against the cable modem failed."""


class FritzBoxMonitorLoginBlockedError(FritzBoxMonitorAuthError):
    """The FRITZ!Box has temporarily blocked login attempts."""

    def __init__(self, block_time: int) -> None:
        """Initialize with the remaining block time in seconds."""
        super().__init__(f"Login blocked for {block_time} seconds")
        self.block_time = block_time


def _parse_session_info(text: str) -> _SessionInfo:
    """Parse a login_sid.lua XML response."""
    root = ET.fromstring(text)
    return _SessionInfo(
        sid=root.findtext("SID") or "",
        challenge=root.findtext("Challenge") or "",
        block_time=int(root.findtext("BlockTime") or 0),
    )


def _check_session_info(info: _SessionInfo) -> _SessionInfo:
    """Raise when the box reports a login block."""
    if info.block_time > 0:
        raise FritzBoxMonitorLoginBlockedError(info.block_time)
    return info


def _calculate_pbkdf2_response(challenge: str, password: str) -> str:
    """Calculate the login response for a v2 challenge.

    See the AVM technical note on the session id: the challenge has the
    form version$iterations$salt1$iterations2$salt2 and the response is
    salt2$hash2 with hash2 = PBKDF2-HMAC-SHA256(PBKDF2-HMAC-SHA256(
    password, salt1, iterations), salt2, iterations2).
    """
    _, iterations1, salt1, iterations2, salt2 = challenge.split("$")
    hash1 = hashlib.pbkdf2_hmac(
        "sha256", password.encode(), bytes.fromhex(salt1), int(iterations1)
    )
    hash2 = hashlib.pbkdf2_hmac(
        "sha256", hash1, bytes.fromhex(salt2), int(iterations2)
    )
    return f"{salt2}${hash2.hex()}"


def _parse_channels(container: dict[str, Any]) -> tuple[DocsisChannel, ...]:
    """Parse the channels of one direction (down-/upstream).

    DOCSIS 3.0 channels come first, each version sorted by channel id.
    Signal-to-noise ratio and error counters only exist downstream.
    """
    channels: list[DocsisChannel] = []
    for version_key, docsis_version in (
        ("docsis30", "3.0"),
        ("docsis31", "3.1"),
    ):
        for channel_id in sorted(container.get(version_key, {}), key=int):
            entry = container[version_key][channel_id]
            channels.append(
                DocsisChannel(
                    channel_id=int(channel_id),
                    docsis_version=docsis_version,
                    frequency=int(entry["frequency"]),
                    power=float(entry["powerLevel"]),
                    modulation=str(entry["modulation"]),
                    snr=float(entry["mse"]) if "mse" in entry else None,
                    correctable_errors=(
                        int(entry["corrErrors"])
                        if "corrErrors" in entry
                        else None
                    ),
                    uncorrectable_errors=(
                        int(entry["nonCorrErrors"])
                        if "nonCorrErrors" in entry
                        else None
                    ),
                )
            )
    return tuple(channels)


class FritzBoxMonitorClient:
    """Talk to a FRITZ!Box cable modem over its web UI."""

    def __init__(
        self,
        host: str,
        session: ClientSession,
        *,
        username: str = "",
        password: str = "",
    ) -> None:
        """Initialize the client."""
        self.host = host
        self.session = session
        self._username = username
        self._password = password
        self._sid: str | None = None

    async def get_status(self) -> CableModemStatus:
        """Return the current status of the cable modem.

        Raise FritzBoxMonitorConnectionError when the modem cannot be
        reached, FritzBoxMonitorAuthError when login fails and
        FritzBoxMonitorLoginBlockedError when the box has blocked login
        attempts for a cooldown period.
        """
        sid = self._sid or await self._async_login()
        try:
            doc = await self._async_fetch_doc_info(sid)
        except FritzBoxMonitorConnectionError:
            # The box rejects requests with an expired session id:
            # re-login once and retry before giving up.
            sid = await self._async_login()
            doc = await self._async_fetch_doc_info(sid)

        data = doc["data"]
        device = data["doc"]
        return CableModemStatus(
            serial_number=str(device["serialNumber"]),
            model=str(device["modelName"]),
            firmware=str(device["fwVersion"]),
            connection_status=str(device["connectionStatus"]),
            downstream=_parse_channels(data["channelDs"]),
            upstream=_parse_channels(data["channelUs"]),
        )

    async def _async_login(self) -> str:
        """Login and cache the session id."""
        info = await self._async_get_session_info()
        if info.sid and info.sid != _ZERO_SID:
            # The box handed out a session without a login; reuse it.
            self._sid = info.sid
            return info.sid

        response = _calculate_pbkdf2_response(info.challenge, self._password)
        info = await self._async_submit_login(response)
        if not info.sid or info.sid == _ZERO_SID:
            raise FritzBoxMonitorAuthError(
                "The FRITZ!Box rejected the login credentials"
            )
        self._sid = info.sid
        return info.sid

    async def _async_get_session_info(self) -> _SessionInfo:
        """Request the login challenge."""
        text = await self._async_request(
            "GET",
            f"http://{self.host}/login_sid.lua",
            params={"version": "2"},
        )
        return _check_session_info(_parse_session_info(text))

    async def _async_submit_login(self, response: str) -> _SessionInfo:
        """Submit the login response for the challenge."""
        text = await self._async_request(
            "POST",
            f"http://{self.host}/login_sid.lua",
            params={"version": "2"},
            data={"username": self._username, "response": response},
        )
        return _check_session_info(_parse_session_info(text))

    async def _async_fetch_doc_info(self, sid: str) -> dict[str, Any]:
        """Fetch the docInfo page as JSON."""
        text = await self._async_request(
            "POST",
            f"http://{self.host}/data.lua",
            data={"sid": sid, "page": "docInfo"},
        )
        return cast(dict[str, Any], json.loads(text))

    async def _async_request(
        self, method: str, url: str, **kwargs: Any
    ) -> str:
        """Perform a request against the FRITZ!Box web UI."""
        try:
            async with self.session.request(method, url, **kwargs) as resp:
                resp.raise_for_status()
                return await resp.text()
        except (TimeoutError, ClientError) as err:
            raise FritzBoxMonitorConnectionError(
                f"Error communicating with the FRITZ!Box: {err}"
            ) from err
