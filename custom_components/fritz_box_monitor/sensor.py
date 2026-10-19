"""Sensor platform for the FRITZ!Box Monitor integration."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import override

from homeassistant.components.sensor import SensorEntity, SensorEntityDescription
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .client import CableModemStatus
from .coordinator import FritzBoxMonitorConfigEntry, FritzBoxMonitorCoordinator
from .entity import FritzBoxMonitorEntity


@dataclass(frozen=True, kw_only=True)
class FritzBoxMonitorSensorEntityDescription(SensorEntityDescription):
    """Describe a FRITZ!Box Monitor sensor."""

    value_fn: Callable[[CableModemStatus], float | int | str]


SENSORS: tuple[FritzBoxMonitorSensorEntityDescription, ...] = (
    # TODO: replace this placeholder with the real cable modem metrics:
    # downstream/upstream signal-to-noise ratio and power levels,
    # correctable/uncorrectable error counters, connection state, ...
    # Give measurement sensors a device_class, a unit and
    # SensorStateClass.MEASUREMENT so they convert and statistics work.
    FritzBoxMonitorSensorEntityDescription(
        key="connection_status",
        translation_key="connection_status",
        icon="mdi:lan-connect",
        value_fn=lambda status: status.connection_status,
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
        self._attr_unique_id = (
            f"{coordinator.data.serial_number}_{description.key}"
        )

    @override
    @property
    def native_value(self) -> float | int | str:
        """Return the value of the sensor."""
        return self.entity_description.value_fn(self.coordinator.data)
