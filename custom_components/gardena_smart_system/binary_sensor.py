"""Support for Gardena Smart System binary sensors."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, PUMP_MODEL_KEYWORDS
from .coordinator import GardenaSmartSystemCoordinator
from .entities import GardenaOnlineEntity, GardenaEntity

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Gardena Smart System binary sensors."""
    coordinator: GardenaSmartSystemCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities = []

    for location in coordinator.locations.values():
        for device in location.devices.values():
            entities.append(GardenaOnlineBinarySensor(coordinator, device))

            # Pump running binary sensor (uses BFF data)
            if any(kw in (device.model_type or "").lower() for kw in PUMP_MODEL_KEYWORDS):
                entities.append(GardenaPumpRunningSensor(coordinator, device))

    entities.append(GardenaWebSocketConnectedSensor(coordinator, entry.entry_id))

    async_add_entities(entities)


class GardenaOnlineBinarySensor(GardenaOnlineEntity, BinarySensorEntity):
    """Representation of a Gardena device online status sensor."""

    def __init__(self, coordinator: GardenaSmartSystemCoordinator, device) -> None:
        """Initialize the online status sensor."""
        super().__init__(coordinator, device)
        self._attr_name = f"{device.name} Online"


class GardenaWebSocketConnectedSensor(GardenaEntity, BinarySensorEntity):
    """Binary sensor indicating whether the Gardena WebSocket is connected."""

    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY

    def __init__(self, coordinator: GardenaSmartSystemCoordinator, entry_id: str) -> None:
        """Initialize the WebSocket connectivity sensor."""
        from .models import GardenaDevice
        dummy_device = GardenaDevice(
            id=f"websocket_status_{entry_id}",
            name="WebSocket Status",
            model_type="WebSocket Client",
            serial="websocket",
            services={},
            location_id=""
        )
        super().__init__(coordinator, dummy_device, "WEBSOCKET")
        self._attr_name = "Gardena WebSocket Connected"
        self._attr_unique_id = f"gardena_websocket_connected_{entry_id}"

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return True

    @property
    def is_on(self) -> bool:
        """Return True if WebSocket is connected."""
        if self.coordinator.websocket_client:
            return self.coordinator.websocket_client.is_connected
        return False

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return entity specific state attributes."""
        attrs = super().extra_state_attributes
        if self.coordinator.websocket_client:
            attrs.update({
                "reconnect_attempts": self.coordinator.websocket_client.reconnect_attempts,
            })
        return attrs


class GardenaPumpRunningSensor(GardenaEntity, BinarySensorEntity):
    """Binary sensor: True when the pressure pump motor is running."""

    _attr_device_class = BinarySensorDeviceClass.RUNNING

    def __init__(self, coordinator: GardenaSmartSystemCoordinator, device) -> None:
        super().__init__(coordinator, device, "VALVE")
        self._device_id = device.id
        self._attr_name = f"{device.name} Pumpe läuft"
        self._attr_unique_id = f"{device.id}_pump_bff_running"
        self._attr_icon = "mdi:pump"

    @property
    def available(self) -> bool:
        """Available only when BFF data has been fetched."""
        return super().available and self.coordinator.get_pump_bff_data(self._device_id) is not None

    @property
    def is_on(self) -> bool:
        """Return True if pump_on_off == 'on'."""
        bff = self.coordinator.get_pump_bff_data(self._device_id)
        return bff.pump_on_off == "on" if bff else False

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        attrs = super().extra_state_attributes
        bff = self.coordinator.get_pump_bff_data(self._device_id)
        if bff:
            if bff.pump_state is not None:
                attrs["pump_state"] = bff.pump_state
            if bff.mode is not None:
                attrs["mode"] = bff.mode
        return attrs

