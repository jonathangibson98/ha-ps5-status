"""The game's picture, as an image entity for picture cards and wallpapers."""
from __future__ import annotations

from homeassistant.components.image import ImageEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from . import Ps5ConfigEntry
from .entity import Ps5Entity


async def async_setup_entry(hass: HomeAssistant, entry: Ps5ConfigEntry, add: AddConfigEntryEntitiesCallback) -> None:
    add([Ps5GameImage(hass, entry.runtime_data)])


class Ps5GameImage(Ps5Entity, ImageEntity):
    _attr_translation_key = "game_image"

    def __init__(self, hass: HomeAssistant, coordinator) -> None:
        Ps5Entity.__init__(self, coordinator, "game_image")
        ImageEntity.__init__(self, hass)
        self._attr_image_url = coordinator.data.game_image
        self._attr_image_last_updated = dt_util.utcnow()

    @callback
    def _handle_coordinator_update(self) -> None:
        url = self.coordinator.data.game_image
        if url != self._attr_image_url:
            self._attr_image_url = url
            self._cached_image = None
            self._attr_image_last_updated = dt_util.utcnow()
        super()._handle_coordinator_update()

    @property
    def available(self) -> bool:
        return super().available and bool(self.coordinator.data.game_image)
