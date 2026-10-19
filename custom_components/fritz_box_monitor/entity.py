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

        # TODO: verify manufacturer/model values once the client reports
        # the real device information.
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, status.serial_number)},
            manufacturer="AVM",
            model=status.model,
            name=NAME,
            serial_number=status.serial_number,
            sw_version=status.firmware,
        )
