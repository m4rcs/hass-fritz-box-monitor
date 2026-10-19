"""Client to talk to a FRITZ!Box cable modem.

The integration never talks to the modem itself; all device access goes
through this module, mirroring the library role from the Home Assistant
integration tutorial (step 1).

TODO: decide how to reach the modem and implement the client. Candidate
approaches:

- TR-064/TR-069 SOAP API via a small aiohttp client (no extra dependency)
- the data.lua endpoints of the FRITZ!Box web UI for DOCSIS details
- delegate to a dedicated PyPI library once one is chosen, and list it
  in the ``requirements`` key of manifest.json

Whatever the approach, the interface below keeps the properties Home
Assistant expects from a device library: an async API that never blocks
the event loop, a caller-provided aiohttp session, and its own
exceptions so the integration can tell a connection problem apart from
anything else.
"""

from dataclasses import dataclass

from aiohttp import ClientSession


@dataclass
class CableModemStatus:
    """Status snapshot of the FRITZ!Box cable modem.

    TODO: replace the placeholder fields with the real data the modem
    exposes (DOCSIS channel stats, signal-to-noise ratio, power levels,
    error counters, connection state, ...).
    """

    serial_number: str
    model: str
    firmware: str
    connection_status: str


class FritzBoxMonitorError(Exception):
    """Base error of the FRITZ!Box Monitor client."""


class FritzBoxMonitorConnectionError(FritzBoxMonitorError):
    """The cable modem could not be reached."""


class FritzBoxMonitorAuthError(FritzBoxMonitorError):
    """Authentication against the cable modem failed."""


class FritzBoxMonitorClient:
    """Talk to a FRITZ!Box cable modem."""

    def __init__(self, host: str, session: ClientSession) -> None:
        """Initialize the client."""
        self.host = host
        self.session = session

    async def get_status(self) -> CableModemStatus:
        """Return the current status of the cable modem.

        TODO: implement (see the module docstring). Raise
        FritzBoxMonitorConnectionError when the modem cannot be reached
        and FritzBoxMonitorAuthError when login fails.
        """
        raise NotImplementedError
