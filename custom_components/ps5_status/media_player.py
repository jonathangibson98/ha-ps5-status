"""The PS5 as a media player: off, rest mode (standby), on, or playing a game with its title and picture."""
from __future__ import annotations

from homeassistant.components.media_player import MediaPlayerEntity, MediaPlayerState, MediaType
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import Ps5ConfigEntry
from .const import POWER_ON, POWER_REST
from .entity import Ps5Entity


async def async_setup_entry(hass: HomeAssistant, entry: Ps5ConfigEntry, add: AddConfigEntryEntitiesCallback) -> None:
    add([Ps5MediaPlayer(entry.runtime_data)])


class Ps5MediaPlayer(Ps5Entity, MediaPlayerEntity):
    _attr_name = None  # the device name: media_player.playstation_5
    _attr_media_image_remotely_accessible = False  # Home Assistant fetches the art, so dashboards never call Sony

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "media_player")

    @property
    def state(self) -> MediaPlayerState:
        d = self.coordinator.data
        if d.power == POWER_REST:
            return MediaPlayerState.STANDBY
        if d.power != POWER_ON:
            return MediaPlayerState.OFF
        return MediaPlayerState.PLAYING if d.game else MediaPlayerState.ON

    @property
    def media_content_type(self) -> MediaType | None:
        return MediaType.GAME if self.coordinator.data.game else None

    @property
    def media_title(self) -> str | None:
        return self.coordinator.data.game

    @property
    def media_image_url(self) -> str | None:
        return self.coordinator.data.game_image

    @property
    def app_name(self) -> str | None:
        return self.coordinator.data.game

    @property
    def extra_state_attributes(self) -> dict:
        d = self.coordinator.data
        return {"power": d.power, "game_source": "PlayStation Network" if self.coordinator.psn_entity else None,
                "ip_address": self._host}
