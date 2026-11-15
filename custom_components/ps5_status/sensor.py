"""Power state (on / rest mode / off) and the game being played."""
from __future__ import annotations

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import Ps5ConfigEntry
from .const import POWER_STATES
from .entity import Ps5Entity


async def async_setup_entry(hass: HomeAssistant, entry: Ps5ConfigEntry, add: AddConfigEntryEntitiesCallback) -> None:
    c = entry.runtime_data
    add([Ps5PowerSensor(c), Ps5GameSensor(c)])


class Ps5PowerSensor(Ps5Entity, SensorEntity):
    _attr_translation_key = "power"
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = POWER_STATES

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "power")

    @property
    def native_value(self) -> str:
        return self.coordinator.data.power

    @property
    def icon(self) -> str:
        return {"on": "mdi:sony-playstation", "rest": "mdi:power-sleep"}.get(self.coordinator.data.power, "mdi:power-off")


class Ps5GameSensor(Ps5Entity, SensorEntity):
    _attr_translation_key = "now_playing"
    _attr_icon = "mdi:gamepad-variant"

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "now_playing")

    @property
    def native_value(self) -> str | None:
        return self.coordinator.data.game
