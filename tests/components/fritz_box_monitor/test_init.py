"""Tests for the FRITZ!Box Monitor integration setup, retry and unload."""

from typing import Any
from unittest.mock import AsyncMock

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import UpdateFailed
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.fritz_box_monitor.client import (
    CableModemStatus,
    FritzBoxMonitorAuthError,
)
from custom_components.fritz_box_monitor.const import UPDATE_INTERVAL
from custom_components.fritz_box_monitor.coordinator import (
    FritzBoxMonitorCoordinator,
)

from .const import FAKE_BASE_URL, FAKE_MAC


def _coordinator(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    client: Any,
) -> FritzBoxMonitorCoordinator:
    """Return a coordinator around a mocked client."""
    return FritzBoxMonitorCoordinator(hass, mock_config_entry, client)


async def test_setup_success(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_fritz_box: None,
) -> None:
    """A reachable modem leads to a loaded entry with fetched data."""
    mock_config_entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    assert mock_config_entry.state is ConfigEntryState.LOADED

    coordinator = mock_config_entry.runtime_data
    assert isinstance(coordinator, FritzBoxMonitorCoordinator)
    assert isinstance(coordinator.data, CableModemStatus)
    assert coordinator.data.mac == FAKE_MAC


async def test_setup_failure_sets_up_retry(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    aioclient_mock: Any,
) -> None:
    """A modem that cannot be reached leaves the entry in setup retry."""
    aioclient_mock.get(
        f"{FAKE_BASE_URL}/login_sid.lua?version=2", exc=TimeoutError()
    )
    mock_config_entry.add_to_hass(hass)

    assert not await hass.config_entries.async_setup(
        mock_config_entry.entry_id
    )
    await hass.async_block_till_done()

    assert mock_config_entry.state is ConfigEntryState.SETUP_RETRY


async def test_unload(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_fritz_box: None,
) -> None:
    """Unloading removes the platforms and resets the entry state."""
    mock_config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    assert mock_config_entry.state is ConfigEntryState.LOADED

    assert await hass.config_entries.async_unload(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    assert mock_config_entry.state is ConfigEntryState.NOT_LOADED


async def test_coordinator_maps_client_errors_to_update_failed(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Client errors surface as UpdateFailed."""
    client: Any = AsyncMock()
    client.get_status.side_effect = FritzBoxMonitorAuthError("denied")
    coordinator = _coordinator(hass, mock_config_entry, client)

    with pytest.raises(UpdateFailed):
        await coordinator._async_update_data()


async def test_coordinator_update_interval(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """The coordinator polls at the configured interval."""
    client: Any = AsyncMock()
    coordinator = _coordinator(hass, mock_config_entry, client)

    assert coordinator.update_interval == UPDATE_INTERVAL
