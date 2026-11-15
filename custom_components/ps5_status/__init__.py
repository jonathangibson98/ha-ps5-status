"""PS5 Status: a PS5's real power state (on, rest mode, off) from the local network, plus the game and its picture
from the PlayStation Network integration, as one device."""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .coordinator import Ps5Coordinator

PLATFORMS = [Platform.BINARY_SENSOR, Platform.BUTTON, Platform.IMAGE, Platform.MEDIA_PLAYER, Platform.SENSOR]

type Ps5ConfigEntry = ConfigEntry[Ps5Coordinator]


async def async_setup_entry(hass: HomeAssistant, entry: Ps5ConfigEntry) -> bool:
    coordinator = Ps5Coordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    entry.async_on_unload(entry.add_update_listener(_reload))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def _reload(hass: HomeAssistant, entry: Ps5ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: Ps5ConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
