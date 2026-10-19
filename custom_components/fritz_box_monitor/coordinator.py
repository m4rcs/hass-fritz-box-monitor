"""Data update coordinator for the FRITZ!Box Monitor integration."""

import logging
from typing import override

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed,
)

from .client import CableModemStatus, FritzBoxMonitorClient, FritzBoxMonitorError
from .const import DOMAIN, UPDATE_INTERVAL

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
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            config_entry=config_entry,
            name=DOMAIN,
            update_interval=UPDATE_INTERVAL,
        )
        self.client = client

    @override
    async def _async_update_data(self) -> CableModemStatus:
        """Fetch the latest status from the cable modem."""
        try:
            return await self.client.get_status()
        except FritzBoxMonitorError as err:
            raise UpdateFailed(
                translation_domain=DOMAIN,
                translation_key="update_failed",
            ) from err
