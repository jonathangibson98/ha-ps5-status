"""Shared base for PS5 Status entities."""
from __future__ import annotations

from homeassistant.const import CONF_HOST
from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import Ps5Coordinator


class Ps5Entity(CoordinatorEntity[Ps5Coordinator]):
    _attr_has_entity_name = True

    def __init__(self, coordinator: Ps5Coordinator, key: str) -> None:
        super().__init__(coordinator)
        entry = coordinator.config_entry
        uid = entry.unique_id or entry.entry_id
        self._attr_unique_id = f"{uid}_{key}"
        hid = coordinator.host_id or ""
        mac = ":".join(hid[i:i + 2] for i in range(0, 12, 2)).lower() if len(hid) == 12 else None
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, uid)},
            connections={(CONNECTION_NETWORK_MAC, mac)} if mac else set(),
            name=entry.title,
            manufacturer="Sony Interactive Entertainment",
            model="PlayStation 5",
            sw_version=coordinator.data.system_version if coordinator.data else None,
            configuration_url=None,
        )
        self._host = entry.data[CONF_HOST]
