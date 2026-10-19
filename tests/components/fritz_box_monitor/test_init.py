"""Tests for the FRITZ!Box Monitor integration setup, retry and unload."""

from datetime import timedelta
from typing import Any
from unittest.mock import AsyncMock

from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import UpdateFailed
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.fritz_box_monitor.client import (
    CableModemStatus,
    FritzBoxMonitorAuthError,
    FritzBoxMonitorConnectionError,
    FritzBoxMonitorLoginBlockedError,
)
from custom_components.fritz_box_monitor.const import (
    CONF_UPDATE_INTERVAL,
    DEFAULT_UPDATE_INTERVAL_SECONDS,
    DOMAIN,
)
from custom_components.fritz_box_monitor.coordinator import (
    FritzBoxMonitorCoordinator,
)

from .const import (
    FAKE_BASE_URL,
    FAKE_BLOCK_TIME,
    FAKE_HOST,
    FAKE_MAC,
    FAKE_PASSWORD,
    FAKE_USERNAME,
)


def _coordinator(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    client: Any,
) -> FritzBoxMonitorCoordinator:
    """Return a coordinator around a mocked client."""
    return FritzBoxMonitorCoordinator(
        hass,
        mock_config_entry,
        client,
        timedelta(seconds=DEFAULT_UPDATE_INTERVAL_SECONDS),
    )


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


async def test_coordinator_maps_connection_errors_to_update_failed(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Connection errors surface as UpdateFailed."""
    client: Any = AsyncMock()
    client.get_status.side_effect = FritzBoxMonitorConnectionError("offline")
    coordinator = _coordinator(hass, mock_config_entry, client)

    with pytest.raises(UpdateFailed):
        await coordinator._async_update_data()


async def test_coordinator_maps_auth_errors_to_config_entry_auth_failed(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Wrong credentials raise ConfigEntryAuthFailed and start reauth."""
    mock_config_entry.add_to_hass(hass)
    client: Any = AsyncMock()
    client.get_status.side_effect = FritzBoxMonitorAuthError("denied")
    coordinator = _coordinator(hass, mock_config_entry, client)

    with pytest.raises(ConfigEntryAuthFailed):
        await coordinator._async_update_data()

    await hass.async_block_till_done()
    progress = hass.config_entries.flow.async_progress_by_handler(DOMAIN)
    assert any(
        flow["context"].get("source") == config_entries.SOURCE_REAUTH
        for flow in progress
    )


async def test_coordinator_maps_blocked_errors_to_update_failed(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """A temporary login block stays retryable (no reauth)."""
    client: Any = AsyncMock()
    client.get_status.side_effect = FritzBoxMonitorLoginBlockedError(
        FAKE_BLOCK_TIME
    )
    coordinator = _coordinator(hass, mock_config_entry, client)

    with pytest.raises(UpdateFailed):
        await coordinator._async_update_data()

    assert (
        hass.config_entries.flow.async_progress_by_handler(DOMAIN) == []
    )


async def test_coordinator_update_interval(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """The coordinator polls at the configured interval."""
    client: Any = AsyncMock()
    coordinator = _coordinator(hass, mock_config_entry, client)

    assert coordinator.update_interval == timedelta(
        seconds=DEFAULT_UPDATE_INTERVAL_SECONDS
    )


async def test_setup_honors_update_interval_option(
    hass: HomeAssistant,
    mock_fritz_box: None,
) -> None:
    """The poll interval from the entry options wins over the default."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_HOST: FAKE_HOST,
            CONF_USERNAME: FAKE_USERNAME,
            CONF_PASSWORD: FAKE_PASSWORD,
        },
        options={CONF_UPDATE_INTERVAL: 60},
    )
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    coordinator = entry.runtime_data
    assert coordinator.update_interval == timedelta(seconds=60)
