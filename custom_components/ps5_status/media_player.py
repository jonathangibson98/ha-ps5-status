"""The PS5 as a media player: off, rest mode (standby), on, or playing a game with its title and picture.
Turns the console on once it's linked through Remote Play (in the integration's options)."""
from __future__ import annotations

import asyncio

from homeassistant.components.media_player import (
    MediaPlayerEntity,
    MediaPlayerEntityFeature,
    MediaPlayerState,
    MediaType,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import Ps5ConfigEntry
from .const import POWER_ON, POWER_REST
from .entity import Ps5Entity
from .remoteplay import async_wake


async def async_setup_entry(hass: HomeAssistant, entry: Ps5ConfigEntry, add: AddConfigEntryEntitiesCallback) -> None:
    add([Ps5MediaPlayer(entry.runtime_data)])


async def wake_and_watch(coordinator) -> None:
    """Send the wake-up, then check more often while the console comes up (it takes 10-20 seconds)."""
    await async_wake(coordinator.host, coordinator.regist_key)
    for delay in (3, 7, 10, 10):
        await asyncio.sleep(delay)
        await coordinator.async_request_refresh()
        if coordinator.data and coordinator.data.power == POWER_ON:
            break


class Ps5MediaPlayer(Ps5Entity, MediaPlayerEntity):
    _attr_name = None  # the device name: media_player.playstation_5
    _attr_media_image_remotely_accessible = False  # Home Assistant fetches the art, so dashboards never call Sony

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "media_player")

    @property
    def supported_features(self) -> MediaPlayerEntityFeature:
        return MediaPlayerEntityFeature.TURN_ON if self.coordinator.regist_key else MediaPlayerEntityFeature(0)

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
        # only used to notice the picture changed; the picture itself comes from async_get_media_image
        return self.coordinator.data.game_image

    async def async_get_media_image(self) -> tuple[bytes | None, str | None]:
        return await self.coordinator.async_source_image()

    @property
    def app_name(self) -> str | None:
        return self.coordinator.data.game

    async def async_turn_on(self) -> None:
        if self.coordinator.regist_key:
            self.hass.async_create_background_task(wake_and_watch(self.coordinator), "ps5_status wake")

    @property
    def extra_state_attributes(self) -> dict:
        d = self.coordinator.data
        return {"power": d.power, "game_source": self.coordinator.psn_entity or None,
                "can_turn_on": bool(self.coordinator.regist_key), "ip_address": self._host}
