"""Tests for the FRITZ!Box Monitor sensor platform."""

from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.helpers.device_registry import DeviceEntry
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from syrupy.assertion import SnapshotAssertion

from custom_components.fritz_box_monitor.const import DOMAIN
from custom_components.fritz_box_monitor.sensor import SENSORS

from .const import FAKE_SERIAL


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
    """The platform creates one entity per sensor description."""
    registry = er.async_get(hass)
    entries = er.async_entries_for_config_entry(
        registry, loaded_entry.entry_id
    )

    assert len(entries) == len(SENSORS)
    assert {entry.unique_id for entry in entries} == {
        f"{FAKE_SERIAL}_{description.key}" for description in SENSORS
    }


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
    assert device.identifiers == {(DOMAIN, FAKE_SERIAL)}
    assert device.manufacturer == "AVM"
    assert device.model == "FRITZ!Box 6591 Cable"
    assert device.serial_number == FAKE_SERIAL
    assert device.sw_version == "7.29"
    assert device.name == "FRITZ!Box Monitor"


async def test_sensor_snapshot(
    hass: HomeAssistant,
    loaded_entry: MockConfigEntry,
    snapshot: SnapshotAssertion,
) -> None:
    """The sensor state matches the snapshot."""
    registry = er.async_get(hass)
    entries = er.async_entries_for_config_entry(
        registry, loaded_entry.entry_id
    )
    entity_id = entries[0].entity_id

    state = hass.states.get(entity_id)
    assert state is not None
    assert state.state == "online"
    assert state == snapshot
