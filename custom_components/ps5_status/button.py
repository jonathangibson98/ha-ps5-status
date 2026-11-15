"""A Turn on button, for dashboards and automations (only once the PS5 is linked for turning on)."""
from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import Ps5ConfigEntry
from .entity import Ps5Entity
from .media_player import wake_and_watch


async def async_setup_entry(hass: HomeAssistant, entry: Ps5ConfigEntry, add: AddConfigEntryEntitiesCallback) -> None:
    if entry.runtime_data.regist_key:
        add([Ps5TurnOnButton(entry.runtime_data)])


class Ps5TurnOnButton(Ps5Entity, ButtonEntity):
    _attr_translation_key = "turn_on"
    _attr_icon = "mdi:power"

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "turn_on")

    async def async_press(self) -> None:
        self.hass.async_create_background_task(wake_and_watch(self.coordinator), "ps5_status wake")
