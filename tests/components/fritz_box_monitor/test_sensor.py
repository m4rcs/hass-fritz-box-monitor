"""Tests for the FRITZ!Box Monitor sensor platform."""

from typing import Any

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
    """The platform creates aggregates plus one sensor per channel metric."""
    coordinator = loaded_entry.runtime_data
    registry = er.async_get(hass)
    entries = er.async_entries_for_config_entry(
        registry, loaded_entry.entry_id
    )

    expected_unique_ids = {
        f"{FAKE_MAC}_{description.key}" for description in SENSORS
    }
    for direction, channels in (
        ("ds", coordinator.data.downstream),
        ("us", coordinator.data.upstream),
    ):
        for channel in channels:
            base = f"{FAKE_MAC}_{direction}_channel_{channel.channel_id}"
            expected_unique_ids.add(base)
            if direction == "ds":
                expected_unique_ids.add(f"{base}_snr")
                if channel.correctable_errors is not None:
                    expected_unique_ids.add(f"{base}_correctable")
                if channel.uncorrectable_errors is not None:
                    expected_unique_ids.add(f"{base}_uncorrectable")

    assert len(entries) == len(expected_unique_ids)
    assert {entry.unique_id for entry in entries} == expected_unique_ids


async def test_channel_sensors_are_diagnostic(
    hass: HomeAssistant, loaded_entry: MockConfigEntry
) -> None:
    """All channel metric sensors carry the diagnostic category."""
    registry = er.async_get(hass)
    entries = er.async_entries_for_config_entry(
        registry, loaded_entry.entry_id
    )

    channel_entries = [
        entry
        for entry in entries
        if "_channel_" in entry.unique_id
        and not entry.unique_id.endswith("_channel_count")
    ]
    assert len(channel_entries) == len(entries) - len(SENSORS)
    assert all(
        entry.entity_category == EntityCategory.DIAGNOSTIC
        for entry in channel_entries
    )


async def test_channel_metric_sensors(
    hass: HomeAssistant, loaded_entry: MockConfigEntry
) -> None:
    """SNR and error counters are exposed per channel where reported."""
    registry = er.async_get(hass)
    entries = er.async_entries_for_config_entry(
        registry, loaded_entry.entry_id
    )

    def _state(unique_id: str) -> Any:
        entry = next(
            (entry for entry in entries if entry.unique_id == unique_id),
            None,
        )
        if entry is None:
            return None
        return hass.states.get(entry.entity_id)

    snr8 = _state(f"{FAKE_MAC}_ds_channel_8_snr")
    assert snr8 is not None
    assert snr8.state == "39.0"
    assert snr8.attributes["unit_of_measurement"] == "dB"

    correctable8 = _state(f"{FAKE_MAC}_ds_channel_8_correctable")
    assert correctable8 is not None
    assert correctable8.state == "986"

    uncorrectable21 = _state(f"{FAKE_MAC}_ds_channel_21_uncorrectable")
    assert uncorrectable21 is not None
    assert uncorrectable21.state == "1120"

    snr193 = _state(f"{FAKE_MAC}_ds_channel_193_snr")
    assert snr193 is not None
    assert snr193.state == "43.0"

    # DOCSIS 3.1 blocks report no correctable counter: no entity exists.
    assert _state(f"{FAKE_MAC}_ds_channel_193_correctable") is None
    # Upstream reports power only.
    assert _state(f"{FAKE_MAC}_us_channel_1_snr") is None


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
    assert state.attributes["channel_id"] == 8
    assert state.attributes["docsis_version"] == "3.0"
    assert state.attributes["frequency_mhz"] == 618.0
    assert state.attributes["frequency"] == "618.000"
    assert state.attributes["modulation"] == "256QAM"
    assert state.attributes["snr_db"] == 39.0
    assert state.attributes["correctable_errors"] == 986
    assert state.attributes["uncorrectable_errors"] == 0
    assert state.attributes["latency"] == 0.32


async def test_docsis31_channel_sensor_carries_extra_fields(
    hass: HomeAssistant, loaded_entry: MockConfigEntry
) -> None:
    """A 3.1 block exposes its OFDM-specific fields and the band range."""
    registry = er.async_get(hass)
    entries = er.async_entries_for_config_entry(
        registry, loaded_entry.entry_id
    )
    channel_entry = next(
        entry
        for entry in entries
        if entry.unique_id == f"{FAKE_MAC}_ds_channel_193"
    )

    state = hass.states.get(channel_entry.entity_id)
    assert state is not None
    assert state.state == "17.1"
    assert state.attributes["frequency_mhz"] == 229.975
    assert state.attributes["frequency"] == "134.975 - 324.975"
    assert state.attributes["snr_db"] == 43.0
    assert state.attributes["plc"] == "264"
    assert state.attributes["fft"] == "4K"
    assert "correctable_errors" not in state.attributes


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
