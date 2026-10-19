"""Tests for the FRITZ!Box Monitor sensor platform."""

from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.helpers.device_registry import DeviceEntry
from homeassistant.helpers.entity_registry import EntityCategory
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from syrupy.assertion import SnapshotAssertion

from custom_components.fritz_box_monitor.const import DOMAIN
from custom_components.fritz_box_monitor.sensor import SENSORS

from .const import FAKE_MAC


@pytest.fixture
async def loaded_entry(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_fritz_box: None,
) -> MockConfigEntry:
    """Return a set-up config entry for the integration."""
    mock_config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    return mock_config_entry


async def test_sensors_created(
    hass: HomeAssistant, loaded_entry: MockConfigEntry
) -> None:
    """The platform creates aggregates plus one entity per channel."""
    coordinator = loaded_entry.runtime_data
    registry = er.async_get(hass)
    entries = er.async_entries_for_config_entry(
        registry, loaded_entry.entry_id
    )

    expected_count = (
        len(SENSORS) + len(coordinator.data.downstream) + len(coordinator.data.upstream)
    )
    assert len(entries) == expected_count

    expected_unique_ids = {
        f"{FAKE_MAC}_{description.key}" for description in SENSORS
    } | {
        f"{FAKE_MAC}_{direction}_channel_{channel.channel_id}"
        for direction, channels in (
            ("ds", coordinator.data.downstream),
            ("us", coordinator.data.upstream),
        )
        for channel in channels
    }
    assert {entry.unique_id for entry in entries} == expected_unique_ids


async def test_channel_sensors_are_diagnostic(
    hass: HomeAssistant, loaded_entry: MockConfigEntry
) -> None:
    """Channel entities carry the diagnostic category."""
    registry = er.async_get(hass)
    entries = er.async_entries_for_config_entry(
        registry, loaded_entry.entry_id
    )

    coordinator = loaded_entry.runtime_data
    channel_unique_ids = {
        f"{FAKE_MAC}_ds_channel_{channel.channel_id}"
        for channel in coordinator.data.downstream
    } | {
        f"{FAKE_MAC}_us_channel_{channel.channel_id}"
        for channel in coordinator.data.upstream
    }
    channel_entries = [
        entry for entry in entries if entry.unique_id in channel_unique_ids
    ]
    assert len(channel_entries) == len(channel_unique_ids)
    assert all(
        entry.entity_category == EntityCategory.DIAGNOSTIC
        for entry in channel_entries
    )


async def test_channel_sensor_carries_attributes(
    hass: HomeAssistant, loaded_entry: MockConfigEntry
) -> None:
    """A downstream channel exposes power as state and data as attributes."""
    registry = er.async_get(hass)
    entries = er.async_entries_for_config_entry(
        registry, loaded_entry.entry_id
    )
    channel_entry = next(
        entry
        for entry in entries
        if entry.unique_id == f"{FAKE_MAC}_ds_channel_8"
    )

    state = hass.states.get(channel_entry.entity_id)
    assert state is not None
    assert state.state == "16.0"
    assert state.attributes["docsis_version"] == "3.0"
    assert state.attributes["frequency_mhz"] == 618.0
    assert state.attributes["modulation"] == "256QAM"
    assert state.attributes["snr_db"] == 39.0
    assert state.attributes["correctable_errors"] == 986
    assert state.attributes["uncorrectable_errors"] == 0


async def test_device_registry(
    hass: HomeAssistant, loaded_entry: MockConfigEntry
) -> None:
    """The entities belong to a device carrying the modem identity."""
    registry = er.async_get(hass)
    entries = er.async_entries_for_config_entry(
        registry, loaded_entry.entry_id
    )
    device_id = entries[0].device_id
    assert device_id is not None
    device = dr.async_get(hass).async_get(device_id)
    assert isinstance(device, DeviceEntry)
    assert device.identifiers == {(DOMAIN, FAKE_MAC)}
    assert device.manufacturer == "AVM"
    assert device.model == "FRITZ!Box 6660 Cable"
    assert device.serial_number == FAKE_MAC
    assert device.sw_version == "8.25"
    assert device.name == "FRITZ!Box Monitor"


async def test_sensor_snapshot(
    hass: HomeAssistant,
    loaded_entry: MockConfigEntry,
    snapshot: SnapshotAssertion,
) -> None:
    """All sensor states match the snapshots."""
    registry = er.async_get(hass)
    entries = er.async_entries_for_config_entry(
        registry, loaded_entry.entry_id
    )
    states = [hass.states.get(entry.entity_id) for entry in entries]
    assert all(state is not None for state in states)

    connection_status = next(
        state
        for state in states
        if state is not None and state.entity_id.endswith("connection_status")
    )
    assert connection_status.state == "ready"

    for state in states:
        assert state == snapshot
