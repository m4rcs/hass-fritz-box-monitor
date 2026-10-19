"""Sensor platform for the FRITZ!Box Monitor integration."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import override

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.typing import StateType

from .client import CableModemStatus
from .coordinator import FritzBoxMonitorConfigEntry, FritzBoxMonitorCoordinator
from .entity import FritzBoxMonitorEntity


@dataclass(frozen=True, kw_only=True)
class FritzBoxMonitorSensorEntityDescription(SensorEntityDescription):
    """Describe a FRITZ!Box Monitor sensor."""

    value_fn: Callable[[CableModemStatus], StateType]


def _extreme(values: list[float], *, highest: bool) -> float | None:
    """Return the highest or lowest value, or None without channels."""
    if not values:
        return None
    return max(values) if highest else min(values)


def _downstream_power(
    status: CableModemStatus, *, highest: bool
) -> float | None:
    """Min or max downstream power level in dBuV."""
    return _extreme(
        [channel.power for channel in status.downstream], highest=highest
    )


def _upstream_power(
    status: CableModemStatus, *, highest: bool
) -> float | None:
    """Min or max upstream power level in dBuV."""
    return _extreme(
        [channel.power for channel in status.upstream], highest=highest
    )


def _downstream_snr(
    status: CableModemStatus, *, highest: bool
) -> float | None:
    """Min or max downstream signal-to-noise ratio in dB."""
    return _extreme(
        [
            channel.snr
            for channel in status.downstream
            if channel.snr is not None
        ],
        highest=highest,
    )


SENSORS: tuple[FritzBoxMonitorSensorEntityDescription, ...] = (
    FritzBoxMonitorSensorEntityDescription(
        key="connection_status",
        translation_key="connection_status",
        icon="mdi:lan-connect",
        value_fn=lambda status: status.connection_status,
    ),
    FritzBoxMonitorSensorEntityDescription(
        key="ds_channel_count",
        translation_key="ds_channel_count",
        icon="mdi:arrow-down-bold",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda status: len(status.downstream),
    ),
    FritzBoxMonitorSensorEntityDescription(
        key="us_channel_count",
        translation_key="us_channel_count",
        icon="mdi:arrow-up-bold",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda status: len(status.upstream),
    ),
    FritzBoxMonitorSensorEntityDescription(
        key="ds_power_min",
        translation_key="ds_power_min",
        icon="mdi:arrow-down-bold",
        native_unit_of_measurement="dBuV",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda status: _downstream_power(status, highest=False),
    ),
    FritzBoxMonitorSensorEntityDescription(
        key="ds_power_max",
        translation_key="ds_power_max",
        icon="mdi:arrow-down-bold",
        native_unit_of_measurement="dBuV",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda status: _downstream_power(status, highest=True),
    ),
    FritzBoxMonitorSensorEntityDescription(
        key="us_power_min",
        translation_key="us_power_min",
        icon="mdi:arrow-up-bold",
        native_unit_of_measurement="dBuV",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda status: _upstream_power(status, highest=False),
    ),
    FritzBoxMonitorSensorEntityDescription(
        key="us_power_max",
        translation_key="us_power_max",
        icon="mdi:arrow-up-bold",
        native_unit_of_measurement="dBuV",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda status: _upstream_power(status, highest=True),
    ),
    FritzBoxMonitorSensorEntityDescription(
        key="ds_snr_min",
        translation_key="ds_snr_min",
        icon="mdi:signal",
        native_unit_of_measurement="dB",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda status: _downstream_snr(status, highest=False),
    ),
    FritzBoxMonitorSensorEntityDescription(
        key="ds_snr_max",
        translation_key="ds_snr_max",
        icon="mdi:signal",
        native_unit_of_measurement="dB",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda status: _downstream_snr(status, highest=True),
    ),
    FritzBoxMonitorSensorEntityDescription(
        key="ds_correctable_errors",
        translation_key="ds_correctable_errors",
        icon="mdi:counter",
        state_class=SensorStateClass.TOTAL,
        value_fn=lambda status: sum(
            channel.correctable_errors or 0
            for channel in status.downstream
        ),
    ),
    FritzBoxMonitorSensorEntityDescription(
        key="ds_uncorrectable_errors",
        translation_key="ds_uncorrectable_errors",
        icon="mdi:counter",
        state_class=SensorStateClass.TOTAL,
        value_fn=lambda status: sum(
            channel.uncorrectable_errors or 0
            for channel in status.downstream
        ),
    ),
    FritzBoxMonitorSensorEntityDescription(
        key="ds_rate",
        translation_key="ds_rate",
        icon="mdi:transfer-down",
        device_class=SensorDeviceClass.DATA_RATE,
        native_unit_of_measurement="Mbit/s",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda status: status.ds_rate,
    ),
    FritzBoxMonitorSensorEntityDescription(
        key="us_rate",
        translation_key="us_rate",
        icon="mdi:transfer-up",
        device_class=SensorDeviceClass.DATA_RATE,
        native_unit_of_measurement="Mbit/s",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda status: status.us_rate,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: FritzBoxMonitorConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the FRITZ!Box Monitor sensors."""
    coordinator = entry.runtime_data

    async_add_entities(
        FritzBoxMonitorSensor(coordinator, description)
        for description in SENSORS
    )


class FritzBoxMonitorSensor(FritzBoxMonitorEntity, SensorEntity):
    """A sensor of the FRITZ!Box cable modem."""

    entity_description: FritzBoxMonitorSensorEntityDescription

    def __init__(
        self,
        coordinator: FritzBoxMonitorCoordinator,
        description: FritzBoxMonitorSensorEntityDescription,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.data.mac}_{description.key}"

    @override
    @property
    def native_value(self) -> StateType:
        """Return the value of the sensor."""
        return self.entity_description.value_fn(self.coordinator.data)
