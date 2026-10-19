"""Client to talk to a FRITZ!Box cable modem.

The integration never talks to the modem itself; all device access goes
through this module, mirroring the library role from the Home Assistant
integration tutorial (step 1).

The client speaks the web UI protocol of FRITZ!OS cable boxes:

- authentication via ``login_sid.lua?version=2`` (PBKDF2 challenge-response)
- data via the JSON endpoints of ``data.lua`` (``page=docInfo`` for the
  DOCSIS channel statistics)

The interface below keeps the properties Home Assistant expects from a
device library: an async API that never blocks the event loop, a
caller-provided aiohttp session, and its own exceptions so the
integration can tell a connection problem apart from anything else.

TODO: implement the client; tests/components/fritz_box_monitor/
test_client.py drives the implementation (TDD).
"""

from dataclasses import dataclass

from aiohttp import ClientSession


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


class FritzBoxMonitorError(Exception):
    """Base error of the FRITZ!Box Monitor client."""


class FritzBoxMonitorConnectionError(FritzBoxMonitorError):
    """The cable modem could not be reached."""


class FritzBoxMonitorAuthError(FritzBoxMonitorError):
    """Authentication against the cable modem failed."""


class FritzBoxMonitorClient:
    """Talk to a FRITZ!Box cable modem."""

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

    async def get_status(self) -> CableModemStatus:
        """Return the current status of the cable modem.

        TODO: implement (see the module docstring). Raise
        FritzBoxMonitorConnectionError when the modem cannot be reached
        and FritzBoxMonitorAuthError when login fails.
        """
        raise NotImplementedError
