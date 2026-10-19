"""Client to talk to a FRITZ!Box cable modem.

The integration never talks to the modem itself; all device access goes
through this module, mirroring the library role from the Home Assistant
integration tutorial (step 1).

The client speaks the web UI protocol of FRITZ!OS cable boxes over
HTTPS (certificate errors are ignored; the box uses a self-signed
certificate):

- authentication via ``login_sid.lua?version=2`` (PBKDF2
  challenge-response; the username is optional and may be empty for
  boxes configured for password-only login)
- data via the JSON endpoints of ``data.lua`` (``page=docOv`` for the
  connection state, link rates and device identity; ``page=docInfo``
  for the DOCSIS channel statistics)
- the FRITZ!OS version via the generic REST endpoint
  ``/api/v0/generic/uimodlogic`` (newer FRITZ!OS releases only; a box
  without it simply reports no version)

The cable modem MAC address (from docOv) is the only stable hardware
identifier the web UI exposes; it keys the config entry and device.
"""

from dataclasses import dataclass
import hashlib
from itertools import chain
import json
from typing import Any, cast
import xml.etree.ElementTree as ET

from aiohttp import ClientError, ClientSession

_ZERO_SID = "0" * 16

_DOCSIS_VERSIONS = (("docsis30", "3.0"), ("docsis31", "3.1"))

# nspver is "<namespace>.<major>.<minor>".
_NSPVER_PARTS = 3


@dataclass(frozen=True)
class DocsisChannel:
    """A single DOCSIS channel of the cable modem.

    ``snr`` and the error counters are only exposed for downstream
    channels and are ``None`` for upstream channels. DOCSIS 3.0 reports
    the signal quality as negative MSE, which is normalized to a
    positive SNR here; 3.1 reports MER directly.
    """

    channel_id: int
    docsis_version: str
    frequency: float  # MHz; midpoint of the band for 3.1 blocks
    power: float  # dBuV
    modulation: str
    snr: float | None = None  # dB
    correctable_errors: int | None = None
    uncorrectable_errors: int | None = None


@dataclass(frozen=True)
class CableModemStatus:
    """Status snapshot of the FRITZ!Box cable modem."""

    mac: str
    model: str
    connection_status: str
    os_version: str | None  # FRITZ!OS version; None when unavailable
    ds_rate: float  # Mbit/s
    us_rate: float  # Mbit/s
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


def _parse_rate(raw: str) -> float:
    """Parse a rate like "1126,4 Mbit/s" or "1126.4 Mbit/s" into Mbit/s."""
    return float(raw.split(" ", 1)[0].replace(",", "."))


def _parse_frequency(raw: str) -> float:
    """Parse a frequency in MHz; ranges become the band midpoint."""
    if " - " in raw:
        start, end = raw.split(" - ", 1)
        return round((float(start) + float(end)) / 2, 3)
    return float(raw)


def _parse_snr(entry: dict[str, Any], downstream: bool) -> float | None:
    """Normalize the reported signal quality to a positive dB value.

    DOCSIS 3.0 reports MSE (negative dB), 3.1 reports MER (positive
    dB). Only downstream channels report a value.
    """
    if not downstream:
        return None
    if "mse" in entry:
        return -float(entry["mse"])
    if "mer" in entry:
        return float(entry["mer"])
    return None


def _parse_channels(
    raw_channels: list[dict[str, Any]],
    docsis_version: str,
    downstream: bool,
) -> tuple[DocsisChannel, ...]:
    """Parse the channel list of one DOCSIS version and direction."""
    return tuple(
        DocsisChannel(
            channel_id=int(entry["channelID"]),
            docsis_version=docsis_version,
            frequency=_parse_frequency(str(entry["frequency"])),
            power=float(entry["powerLevel"]),
            modulation=str(entry["modulation"]),
            snr=_parse_snr(entry, downstream),
            correctable_errors=entry.get("corrErrors"),
            uncorrectable_errors=entry.get("nonCorrErrors"),
        )
        for entry in raw_channels
    )


def _parse_direction(
    container: dict[str, Any], downstream: bool
) -> tuple[DocsisChannel, ...]:
    """DOCSIS 3.0 channels first, then 3.1, in reported order."""
    return tuple(
        chain.from_iterable(
            _parse_channels(container.get(version_key, []), version, downstream)
            for version_key, version in _DOCSIS_VERSIONS
        )
    )


def _parse_nspver(raw: str) -> str:
    """Derive the FRITZ!OS version from the UI namespace version.

    nspver has the form "<namespace>.<major>.<minor>", e.g. "252.08.25"
    for FRITZ!OS 8.25. Fall back to the raw value on surprises.
    """
    parts = raw.split(".")
    if len(parts) >= _NSPVER_PARTS:
        try:
            return f"{int(parts[1])}.{parts[2]}"
        except ValueError:
            return raw
    return raw


def _parse_status(
    doc_ov: dict[str, Any],
    doc_info: dict[str, Any],
    os_version: str | None,
) -> CableModemStatus:
    """Build the status snapshot from the docOv and docInfo pages."""
    # The connection fields live one level below the page data.
    data_ov = doc_ov["data"]["connectionData"]
    data_info = doc_info["data"]

    # The MAC is the second infoLeft entry (locale-independent position;
    # the first holds the DOCSIS software version).
    mac = str(data_ov["infoLeft"]["details"][1]["value"])
    line = data_ov["line"][0]

    return CableModemStatus(
        mac=mac,
        model=str(data_ov["modell"]),
        connection_status=str(line["state"]),
        os_version=os_version,
        ds_rate=_parse_rate(str(data_ov["dsRate"])),
        us_rate=_parse_rate(str(data_ov["usRate"])),
        downstream=_parse_direction(data_info["channelDs"], downstream=True),
        upstream=_parse_direction(data_info["channelUs"], downstream=False),
    )


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
        doc_ov = await self._async_fetch_page_with_retry("docOv")
        doc_info = await self._async_fetch_page_with_retry("docInfo")
        os_version = None
        if self._sid is not None:
            os_version = await self._async_fetch_os_version(self._sid)
        return _parse_status(doc_ov, doc_info, os_version)

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
            f"https://{self.host}/login_sid.lua",
            params={"version": "2"},
        )
        return _check_session_info(_parse_session_info(text))

    async def _async_submit_login(self, response: str) -> _SessionInfo:
        """Submit the login response for the challenge."""
        text = await self._async_request(
            "POST",
            f"https://{self.host}/login_sid.lua",
            params={"version": "2"},
            data={"username": self._username, "response": response},
        )
        return _check_session_info(_parse_session_info(text))

    async def _async_fetch_page_with_retry(self, page: str) -> dict[str, Any]:
        """Fetch a data.lua page, re-login once when rejected."""
        sid = self._sid or await self._async_login()
        try:
            return await self._async_fetch_doc(sid, page)
        except FritzBoxMonitorConnectionError:
            # The box rejects requests with an expired session id:
            # re-login once and retry before giving up.
            sid = await self._async_login()
            return await self._async_fetch_doc(sid, page)

    async def _async_fetch_os_version(self, sid: str) -> str | None:
        """Fetch the FRITZ!OS version; None when unavailable.

        The generic REST endpoints of the web UI only exist on newer
        FRITZ!OS releases, and they authenticate via an AVM-SID header
        instead of the form field. A box without this API loses only
        the version, never functionality.
        """
        try:
            text = await self._async_request(
                "GET",
                f"https://{self.host}/api/v0/generic/uimodlogic",
                headers={"Authorization": f"AVM-SID {sid}"},
            )
            return _parse_nspver(str(json.loads(text)["nspver"]))
        except (FritzBoxMonitorConnectionError, ValueError, KeyError):
            return None

    async def _async_fetch_doc(self, sid: str, page: str) -> dict[str, Any]:
        """Fetch a data.lua page as JSON, mirroring the web UI request."""
        text = await self._async_request(
            "POST",
            f"https://{self.host}/data.lua",
            data={
                "xhr": "1",
                "sid": sid,
                "lang": "en",
                "page": page,
                "xhrId": "all",
            },
        )
        return cast(dict[str, Any], json.loads(text))

    async def _async_request(
        self, method: str, url: str, **kwargs: Any
    ) -> str:
        """Perform a request against the FRITZ!Box web UI.

        Certificate errors are ignored: the box uses a self-signed
        certificate.
        """
        try:
            async with self.session.request(
                method, url, ssl=False, **kwargs
            ) as resp:
                resp.raise_for_status()
                return await resp.text()
        except (TimeoutError, ClientError) as err:
            raise FritzBoxMonitorConnectionError(
                f"Error communicating with the FRITZ!Box: {err}"
            ) from err
