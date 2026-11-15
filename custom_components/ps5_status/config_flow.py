"""Setup: find the PS5 on the network (or type its IP), then pick the PlayStation Network media player for the game."""
from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_HOST
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import (
    CONF_ACCOUNT_ID,
    CONF_OFF_AFTER,
    CONF_PIN,
    CONF_REGIST_KEY,
    CONF_PSN_ENTITY,
    CONF_SCAN_INTERVAL,
    DEFAULT_OFF_AFTER,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
)
from .ddp import async_discover, async_query
from .remoteplay import RemotePlayError, async_register

MANUAL = "manual"


def _psn_selector() -> selector.EntitySelector:
    """Any media player: PlayStation Network's console player is the usual one, but a TV or universal player works."""
    return selector.EntitySelector(selector.EntitySelectorConfig(domain="media_player"))


class Ps5StatusConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self) -> None:
        self._found: dict[str, Any] = {}
        self._host: str | None = None
        self._name: str = "PlayStation 5"

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            if user_input[CONF_HOST] == MANUAL:
                return await self.async_step_manual()
            return await self._use(user_input[CONF_HOST])
        consoles = [r for r in await async_discover() if (r.host_type or "PS5").upper() == "PS5"]
        configured = {e.unique_id for e in self._async_current_entries()}
        self._found = {r.address: r for r in consoles if (r.host_id or r.address) not in configured}
        if not self._found:
            return await self.async_step_manual()
        options = [selector.SelectOptionDict(value=a, label=f"{r.host_name or 'PS5'} ({a})" + (" - rest mode" if r.standby else ""))
                   for a, r in self._found.items()]
        options.append(selector.SelectOptionDict(value=MANUAL, label="Type an IP address"))
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({vol.Required(CONF_HOST): selector.SelectSelector(
                selector.SelectSelectorConfig(options=options, mode=selector.SelectSelectorMode.LIST))}),
        )

    async def async_step_manual(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            host = user_input[CONF_HOST].strip()
            if await async_query(host, timeout=3.0) is None:
                errors["base"] = "no_answer"
            else:
                return await self._use(host)
        return self.async_show_form(
            step_id="manual",
            data_schema=vol.Schema({vol.Required(CONF_HOST, default=(user_input or {}).get(CONF_HOST, "")): str}),
            errors=errors,
        )

    async def _use(self, host: str) -> ConfigFlowResult:
        reply = self._found.get(host) or await async_query(host, timeout=3.0)
        if reply is None:
            return self.async_abort(reason="no_answer")
        await self.async_set_unique_id(reply.host_id or host)
        self._abort_if_unique_id_configured(updates={CONF_HOST: host})
        self._host, self._name = host, reply.host_name or "PlayStation 5"
        return await self.async_step_psn()

    async def async_step_psn(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(
                title=self._name,
                data={CONF_HOST: self._host},
                options={CONF_PSN_ENTITY: user_input.get(CONF_PSN_ENTITY) or "",
                         CONF_SCAN_INTERVAL: DEFAULT_SCAN_INTERVAL, CONF_OFF_AFTER: DEFAULT_OFF_AFTER},
            )
        guess = next((s.entity_id for s in self.hass.states.async_all("media_player")
                      if s.entity_id.startswith("media_player.") and "playstation" in s.entity_id and "ps5" in s.entity_id), None)
        return self.async_show_form(
            step_id="psn",
            data_schema=vol.Schema({vol.Optional(CONF_PSN_ENTITY, description={"suggested_value": guess}): _psn_selector()}),
            description_placeholders={"name": self._name},
        )

    @staticmethod
    @callback
    def async_get_options_flow(entry: ConfigEntry) -> Ps5StatusOptionsFlow:
        return Ps5StatusOptionsFlow()


class Ps5StatusOptionsFlow(OptionsFlow):
    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        menu = ["settings", "link"]
        if self.config_entry.data.get(CONF_REGIST_KEY):
            menu.append("unlink")
        return self.async_show_menu(step_id="init", menu_options=menu)

    async def async_step_link(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Link like the PS Remote Play app does, so Home Assistant can turn the PS5 on."""
        errors: dict[str, str] = {}
        placeholders = {"error": ""}
        accounts = {e.unique_id: e.title for e in self.hass.config_entries.async_entries("playstation_network")
                    if e.unique_id and str(e.unique_id).isdigit()}
        if user_input is not None:
            account = str(user_input.get(CONF_ACCOUNT_ID) or "").strip()
            if not account.isdigit():
                errors[CONF_ACCOUNT_ID] = "bad_account"
            else:
                try:
                    info = await async_register(self.config_entry.data[CONF_HOST], account, user_input.get(CONF_PIN, ""))
                except RemotePlayError as err:
                    errors["base"], placeholders["error"] = "link_failed", str(err)
                except OSError as err:
                    errors["base"], placeholders["error"] = "link_failed", f"Network problem: {err}"
                else:
                    self.hass.config_entries.async_update_entry(
                        self.config_entry, data={**self.config_entry.data, CONF_REGIST_KEY: info["PS5-RegistKey"],
                                                 CONF_ACCOUNT_ID: account})
                    return self.async_create_entry(data=dict(self.config_entry.options))
        if accounts:
            account_field = selector.SelectSelector(selector.SelectSelectorConfig(
                options=[selector.SelectOptionDict(value=k, label=f"{v} ({k})") for k, v in accounts.items()],
                custom_value=True, mode=selector.SelectSelectorMode.DROPDOWN))
            default = (user_input or {}).get(CONF_ACCOUNT_ID) or next(iter(accounts))
        else:
            account_field = selector.TextSelector()
            default = (user_input or {}).get(CONF_ACCOUNT_ID, "")
        return self.async_show_form(
            step_id="link",
            data_schema=vol.Schema({
                vol.Required(CONF_ACCOUNT_ID, default=default): account_field,
                vol.Required(CONF_PIN): selector.TextSelector(selector.TextSelectorConfig(type=selector.TextSelectorType.NUMBER)),
            }),
            errors=errors,
            description_placeholders=placeholders,
        )

    async def async_step_unlink(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        data = {k: v for k, v in self.config_entry.data.items() if k not in (CONF_REGIST_KEY, CONF_ACCOUNT_ID)}
        self.hass.config_entries.async_update_entry(self.config_entry, data=data)
        return self.async_create_entry(data=dict(self.config_entry.options))

    async def async_step_settings(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data={**user_input, CONF_PSN_ENTITY: user_input.get(CONF_PSN_ENTITY) or ""})
        o = self.config_entry.options
        return self.async_show_form(
            step_id="settings",
            data_schema=vol.Schema({
                vol.Optional(CONF_PSN_ENTITY, description={"suggested_value": o.get(CONF_PSN_ENTITY) or None}): _psn_selector(),
                vol.Required(CONF_SCAN_INTERVAL, default=o.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)):
                    selector.NumberSelector(selector.NumberSelectorConfig(min=2, max=120, step=1, unit_of_measurement="s",
                                                                          mode=selector.NumberSelectorMode.BOX)),
                vol.Required(CONF_OFF_AFTER, default=o.get(CONF_OFF_AFTER, DEFAULT_OFF_AFTER)):
                    selector.NumberSelector(selector.NumberSelectorConfig(min=1, max=20, step=1,
                                                                          mode=selector.NumberSelectorMode.BOX)),
            }),
        )
