"""On while the console is awake (not in rest mode or off): handy for automations."""
from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import Ps5ConfigEntry
from .const import POWER_ON
from .entity import Ps5Entity


async def async_setup_entry(hass: HomeAssistant, entry: Ps5ConfigEntry, add: AddConfigEntryEntitiesCallback) -> None:
    c = entry.runtime_data
    add([Ps5AwakeSensor(c), Ps5PlayingSensor(c)])


class Ps5AwakeSensor(Ps5Entity, BinarySensorEntity):
    _attr_translation_key = "awake"
    _attr_device_class = BinarySensorDeviceClass.POWER

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "awake")

    @property
    def is_on(self) -> bool:
        return self.coordinator.data.power == POWER_ON


class Ps5PlayingSensor(Ps5Entity, BinarySensorEntity):
    _attr_translation_key = "playing"
    _attr_device_class = BinarySensorDeviceClass.RUNNING

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "playing")

    @property
    def is_on(self) -> bool:
        return bool(self.coordinator.data.game)
