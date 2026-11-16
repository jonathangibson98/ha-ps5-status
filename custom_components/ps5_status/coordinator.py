"""Polls the console over the local network for power, and PlayStation Network for the game and who's playing.

The game comes from PS5 Status's own PSN sign-ins (no PlayStation Network integration needed). The old way, picking
any media player as the game source, still works for setups that use it.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta
import logging
import time

import aiohttp

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, STATE_PLAYING
from homeassistant.core import Event, EventStateChangedData, HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import (
    CONF_ACCOUNTS,
    CONF_NAME,
    CONF_NPSSO,
    CONF_OFF_AFTER,
    CONF_PSN_ENTITY,
    CONF_PSN_INTERVAL,
    CONF_REGIST_KEY,
    CONF_SCAN_INTERVAL,
    DEFAULT_OFF_AFTER,
    DEFAULT_PSN_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    POWER_OFF,
    POWER_ON,
    POWER_REST,
)
from .ddp import DdpReply, async_query
from .psn import Presence, PsnAccount, PsnAuthError, PsnError

_LOGGER = logging.getLogger(__name__)


@dataclass
class Ps5Data:
    """Everything the entities show."""

    power: str
    host_name: str | None = None
    host_id: str | None = None
    system_version: str | None = None
    game: str | None = None
    game_id: str | None = None
    game_image: str | None = None  # a URL (built-in PSN) or the source player's picture token; changes with the picture
    whos_playing: str | None = None
    players: list[str] = field(default_factory=list)   # everyone signed in on this PS5 right now
    psn_available: bool = False
    psn_problem: str | None = None


@dataclass
class _Player:
    name: str
    account: PsnAccount
    presence: Presence | None = None
    problem: str | None = None


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
        self.psn_interval = int(opts.get(CONF_PSN_INTERVAL, DEFAULT_PSN_INTERVAL))
        self._misses = 0
        self._last: DdpReply | None = None
        self.host_id: str | None = entry.unique_id
        self.regist_key: str | None = entry.data.get(CONF_REGIST_KEY) or None
        session = async_get_clientsession(hass)
        self.players: list[_Player] = [
            _Player(a.get(CONF_NAME) or "Player", PsnAccount(session, a[CONF_NPSSO]))
            for a in opts.get(CONF_ACCOUNTS) or [] if a.get(CONF_NPSSO)
        ]
        self._psn_checked = 0.0
        self._was_on = False
        self._image_cache: tuple[str, bytes, str] | None = None

    @property
    def uses_builtin_psn(self) -> bool:
        return bool(self.players)

    async def _async_setup(self) -> None:
        for p in self.players:
            try:
                await p.account.async_login()
            except PsnAuthError as err:
                p.problem = f"{p.name}: NPSSO token refused, add it again ({err})"
                _LOGGER.warning("PS5 Status: %s", p.problem)
            except PsnError as err:
                p.problem = f"{p.name}: PSN didn't answer ({err})"
                _LOGGER.debug("PS5 Status: %s", p.problem)
        if self.psn_entity and not self.players:
            # the game changes on the source's schedule, not ours: refresh as soon as that entity changes
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
            power = POWER_REST if reply.standby and not reply.awake else POWER_ON
        else:
            self._misses += 1
            previous = self.data.power if self.data else POWER_OFF
            # one dropped UDP packet shouldn't flip the console off
            power = POWER_OFF if self._misses >= self.off_after else previous

        if self.players:
            if power == POWER_ON:
                due = time.monotonic() - self._psn_checked >= self.psn_interval
                if due or not self._was_on:  # just woke up: check PSN right away
                    await self._check_psn()
            else:
                for p in self.players:
                    p.presence = None
                self._psn_checked = 0.0
        self._was_on = power == POWER_ON
        return self._merge(power, self._last)

    async def _check_psn(self) -> None:
        self._psn_checked = time.monotonic()
        for p in self.players:
            try:
                p.presence = await p.account.async_presence()
                p.problem = None
            except PsnAuthError as err:
                p.presence, p.problem = None, f"{p.name}: NPSSO token expired, add it again ({err})"
                _LOGGER.warning("PS5 Status: %s", p.problem)
            except PsnError as err:
                # keep the last answer: PSN hiccups shouldn't blank the game
                p.problem = f"{p.name}: {err}"
                _LOGGER.debug("PS5 Status: PSN check failed for %s", p.name, exc_info=True)

    def _merge(self, power: str, reply: DdpReply | None) -> Ps5Data:
        base = {
            "power": power,
            "host_name": reply.host_name if reply else None,
            "host_id": (reply.host_id if reply else None) or self.host_id,
            "system_version": reply.system_version if reply else None,
        }
        if self.players:
            return Ps5Data(**base, **self._builtin(power))
        game, image, psn_ok = self._psn_game() if power == POWER_ON else (None, None, self._psn_ok())
        return Ps5Data(**base, game=game, game_image=image, psn_available=psn_ok)

    def _builtin(self, power: str) -> dict:
        problems = [p.problem for p in self.players if p.problem]
        ok = any(p.problem is None for p in self.players)
        if power != POWER_ON:
            return {"psn_available": ok, "psn_problem": "; ".join(problems) or None}
        on_ps5 = [p for p in self.players if p.presence and p.presence.on_ps5]
        gaming = [p for p in on_ps5 if p.presence.title]
        who = (gaming or on_ps5 or [None])[0]
        pres = who.presence if who else None
        return {
            "game": pres.title if pres else None,
            "game_id": pres.title_id if pres else None,
            "game_image": pres.image if pres and pres.title else None,
            "whos_playing": who.name if who else None,
            "players": [p.name for p in on_ps5],
            "psn_available": ok,
            "psn_problem": "; ".join(problems) or None,
        }

    # ----- the old way: a media player as the game source -----

    def _psn_ok(self) -> bool:
        if not self.psn_entity:
            return False
        st = self.hass.states.get(self.psn_entity)
        return st is not None and st.state not in ("unavailable", "unknown")

    def _psn_game(self) -> tuple[str | None, str | None, bool]:
        """(title, picture token, source usable) from the chosen media player."""
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
        """The game picture: downloaded from Sony (built-in PSN) or fetched the way the source player's card does."""
        if not self.data or not self.data.game_image:
            return None, None
        url = self.data.game_image
        if self.players and url.startswith("http"):
            if self._image_cache and self._image_cache[0] == url:
                return self._image_cache[1], self._image_cache[2]
            try:
                async with async_get_clientsession(self.hass).get(url, timeout=aiohttp.ClientTimeout(total=15)) as r:
                    if r.status != 200:
                        return None, None
                    data, ctype = await r.read(), r.headers.get("Content-Type", "image/png").split(";")[0]
            except (aiohttp.ClientError, TimeoutError):
                _LOGGER.debug("Couldn't download the game picture %s", url, exc_info=True)
                return None, None
            self._image_cache = (url, data, ctype)
            return data, ctype
        entity = self.source_entity()
        if entity is None:
            return None, None
        try:
            return await entity.async_get_media_image()
        except Exception:  # noqa: BLE001 - a picture that can't be fetched just isn't shown
            _LOGGER.debug("Couldn't fetch the picture from %s", self.psn_entity, exc_info=True)
            return None, None
