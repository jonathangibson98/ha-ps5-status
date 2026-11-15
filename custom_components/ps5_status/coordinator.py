"""Polls the console over the local network and merges in the game from the PlayStation Network integration."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, STATE_PLAYING
from homeassistant.core import Event, EventStateChangedData, HomeAssistant, callback
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import (
    CONF_OFF_AFTER,
    CONF_REGIST_KEY,
    CONF_PSN_ENTITY,
    CONF_SCAN_INTERVAL,
    DEFAULT_OFF_AFTER,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    POWER_OFF,
    POWER_ON,
    POWER_REST,
)
from .ddp import DdpReply, async_query

_LOGGER = logging.getLogger(__name__)


@dataclass
class Ps5Data:
    """Everything the entities show."""

    power: str
    host_name: str | None = None
    host_id: str | None = None
    system_version: str | None = None
    game: str | None = None
    game_image: str | None = None  # changes whenever the source's picture changes; the picture is fetched through HA
    psn_available: bool = False


class Ps5Coordinator(DataUpdateCoordinator[Ps5Data]):
    """One per console."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        opts = {**entry.data, **entry.options}
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN} {entry.data[CONF_HOST]}",
            update_interval=timedelta(seconds=int(opts.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL))),
            always_update=False,
        )
        self.host: str = entry.data[CONF_HOST]
        self.psn_entity: str | None = opts.get(CONF_PSN_ENTITY) or None
        self.off_after = int(opts.get(CONF_OFF_AFTER, DEFAULT_OFF_AFTER))
        self._misses = 0
        self._last: DdpReply | None = None
        self.host_id: str | None = entry.unique_id
        self.regist_key: str | None = entry.data.get(CONF_REGIST_KEY) or None

    async def _async_setup(self) -> None:
        if self.psn_entity:
            # the game changes on PSN's schedule, not ours: refresh as soon as that entity changes
            self.config_entry.async_on_unload(
                async_track_state_change_event(self.hass, [self.psn_entity], self._psn_changed)
            )

    @callback
    def _psn_changed(self, _event: Event[EventStateChangedData]) -> None:
        if self.data is not None:
            self.async_set_updated_data(self._merge(self.data.power, self._last))

    async def _async_update_data(self) -> Ps5Data:
        reply = await async_query(self.host)
        if reply is not None:
            self._misses = 0
            self._last = reply
            power = POWER_ON if reply.awake else POWER_REST if reply.standby else POWER_ON
        else:
            self._misses += 1
            previous = self.data.power if self.data else POWER_OFF
            # one dropped UDP packet shouldn't flip the console off
            power = POWER_OFF if self._misses >= self.off_after else previous
        return self._merge(power, self._last)

    def _merge(self, power: str, reply: DdpReply | None) -> Ps5Data:
        game, image, psn_ok = self._psn_game() if power == POWER_ON else (None, None, self._psn_ok())
        return Ps5Data(
            power=power,
            host_name=reply.host_name if reply else None,
            host_id=(reply.host_id if reply else None) or self.host_id,
            system_version=reply.system_version if reply else None,
            game=game,
            game_image=image,
            psn_available=psn_ok,
        )

    def _psn_ok(self) -> bool:
        if not self.psn_entity:
            return False
        st = self.hass.states.get(self.psn_entity)
        return st is not None and st.state not in ("unavailable", "unknown")

    def _psn_game(self) -> tuple[str | None, str | None, bool]:
        """(title, picture token, source usable) from the chosen media player: PlayStation Network's console player,
        or any other media player (a TV, a universal player...)."""
        if not self.psn_entity:
            return None, None, False
        st = self.hass.states.get(self.psn_entity)
        if st is None or st.state in ("unavailable", "unknown"):
            return None, None, False
        title = st.attributes.get("media_title") or st.attributes.get("app_name")
        if st.state != STATE_PLAYING and not title:
            return None, None, True
        pic = st.attributes.get("entity_picture")
        return title or None, (pic if title and isinstance(pic, str) and pic else None), True

    def source_entity(self):
        """The chosen media player's entity object, to fetch its picture through Home Assistant."""
        component = self.hass.data.get("media_player")
        if not self.psn_entity or component is None or not hasattr(component, "get_entity"):
            return None
        return component.get_entity(self.psn_entity)

    async def async_source_image(self) -> tuple[bytes | None, str | None]:
        """The game picture, fetched the way the source media player's own card fetches it."""
        entity = self.source_entity()
        if entity is None or not self.data or not self.data.game_image:
            return None, None
        try:
            return await entity.async_get_media_image()
        except Exception:  # noqa: BLE001 - a picture that can't be fetched just isn't shown
            _LOGGER.debug("Couldn't fetch the picture from %s", self.psn_entity, exc_info=True)
            return None, None
