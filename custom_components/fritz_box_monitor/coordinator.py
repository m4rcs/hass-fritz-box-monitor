"""Data update coordinator for the FRITZ!Box Monitor integration."""

from datetime import timedelta
import logging
from typing import override

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed,
)

from .client import (
    CableModemStatus,
    FritzBoxMonitorAuthError,
    FritzBoxMonitorClient,
    FritzBoxMonitorError,
    FritzBoxMonitorLoginBlockedError,
)
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

# Typed config entry: its runtime_data holds the coordinator, so the
# platforms get a typed coordinator for free.
type FritzBoxMonitorConfigEntry = ConfigEntry[FritzBoxMonitorCoordinator]


class FritzBoxMonitorCoordinator(DataUpdateCoordinator[CableModemStatus]):
    """Fetch the status of the cable modem on a fixed schedule."""

    config_entry: FritzBoxMonitorConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: FritzBoxMonitorConfigEntry,
        client: FritzBoxMonitorClient,
        update_interval: timedelta,
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            config_entry=config_entry,
            name=DOMAIN,
            update_interval=update_interval,
        )
        self.client = client

    @override
    async def _async_update_data(self) -> CableModemStatus:
        """Fetch the latest status from the cable modem."""
        try:
            return await self.client.get_status()
        except FritzBoxMonitorLoginBlockedError as err:
            # A blocked login expires on its own; keep retrying.
            raise UpdateFailed(
                translation_domain=DOMAIN,
                translation_key="update_failed",
            ) from err
        except FritzBoxMonitorAuthError as err:
            # Wrong credentials: point the user at the reauth flow. The
            # explicit start also covers scheduled background refreshes.
            self.config_entry.async_start_reauth(self.hass)
            raise ConfigEntryAuthFailed(str(err)) from err
        except FritzBoxMonitorError as err:
            raise UpdateFailed(
                translation_domain=DOMAIN,
                translation_key="update_failed",
            ) from err
