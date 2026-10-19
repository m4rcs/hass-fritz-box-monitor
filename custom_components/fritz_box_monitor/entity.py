"""Base entity for the FRITZ!Box Monitor integration."""

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, NAME
from .coordinator import FritzBoxMonitorCoordinator


class FritzBoxMonitorEntity(CoordinatorEntity[FritzBoxMonitorCoordinator]):
    """Base class for FRITZ!Box Monitor entities."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: FritzBoxMonitorCoordinator) -> None:
        """Initialize the entity."""
        super().__init__(coordinator)
        status = coordinator.data

        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, status.mac)},
            manufacturer="AVM",
            model=status.model,
            name=NAME,
            serial_number=status.mac,
        )
        if status.os_version is not None:
            self._attr_device_info["sw_version"] = status.os_version
