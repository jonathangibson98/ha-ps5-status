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
    ents = [Ps5PowerSensor(c), Ps5GameSensor(c)]
    if c.uses_builtin_psn:
        ents.append(Ps5PlayerSensor(c))
    add(ents)


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


class Ps5PlayerSensor(Ps5Entity, SensorEntity):
    """Which of your PSN accounts is on the console (only with PS5 Status's own PSN sign-ins)."""

    _attr_translation_key = "whos_playing"
    _attr_icon = "mdi:account-circle"

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "whos_playing")

    @property
    def native_value(self) -> str | None:
        return self.coordinator.data.whos_playing

    @property
    def extra_state_attributes(self) -> dict:
        return {"players": self.coordinator.data.players}
