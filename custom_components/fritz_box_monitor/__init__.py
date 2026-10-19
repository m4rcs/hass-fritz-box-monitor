"""The FRITZ!Box Monitor integration.

Monitors the connection of an AVM FRITZ!Box cable modem and exposes its
cable (DOCSIS) line statistics as sensors.
"""

from datetime import timedelta

from homeassistant.const import (
    CONF_HOST,
    CONF_PASSWORD,
    CONF_USERNAME,
    Platform,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .client import FritzBoxMonitorClient
from .const import (
    CONF_UPDATE_INTERVAL,
    DEFAULT_UPDATE_INTERVAL_SECONDS,
)
from .coordinator import FritzBoxMonitorConfigEntry, FritzBoxMonitorCoordinator

_PLATFORMS: list[Platform] = [Platform.SENSOR]


async def async_setup_entry(
    hass: HomeAssistant, entry: FritzBoxMonitorConfigEntry
) -> bool:
    """Set up FRITZ!Box Monitor from a config entry."""
    client = FritzBoxMonitorClient(
        entry.data[CONF_HOST],
        session=async_get_clientsession(hass),
        username=entry.data[CONF_USERNAME],
        password=entry.data[CONF_PASSWORD],
    )

    interval = timedelta(
        seconds=entry.options.get(
            CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL_SECONDS
        )
    )
    coordinator = FritzBoxMonitorCoordinator(hass, entry, client, interval)

    # Fetch the first data before any entity exists. When the modem is
    # offline this raises ConfigEntryNotReady and Home Assistant retries
    # the setup later (test-before-setup rule).
    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, _PLATFORMS)

    return True


async def async_unload_entry(
    hass: HomeAssistant, entry: FritzBoxMonitorConfigEntry
) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, _PLATFORMS)
