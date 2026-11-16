"""Setup screens and entities, with the PS5 and the PSN media player faked."""
from datetime import timedelta
from unittest.mock import patch

from homeassistant import config_entries
from homeassistant.const import CONF_HOST
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_fire_time_changed

from custom_components.ps5_status.const import CONF_PSN_ENTITY, DOMAIN
from custom_components.ps5_status.ddp import parse_reply

AWAKE = parse_reply(b"HTTP/1.1 200 Ok\nhost-id:001122AABBCC\nhost-type:PS5\nhost-name:PS5-512\nsystem-version:09400000\n", "192.168.86.40")
REST = parse_reply(b"HTTP/1.1 620 Server Standby\nhost-id:001122AABBCC\nhost-type:PS5\nhost-name:PS5-512\n", "192.168.86.40")
PSN = "media_player.playstation_5_console"
ART = "https://image.api.playstation.com/vulcan/ap/rnd/nhl26.png"


async def test_setup_flow_discovered(hass):
    hass.states.async_set(PSN, "on", {"friendly_name": "PlayStation 5 Console"})
    with patch("custom_components.ps5_status.config_flow.async_discover", return_value=[AWAKE]), \
         patch("custom_components.ps5_status.config_flow.async_query", return_value=AWAKE), \
         patch("custom_components.ps5_status.coordinator.async_query", return_value=AWAKE):
        r = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
        assert r["type"] is FlowResultType.FORM and r["step_id"] == "user"
        r = await hass.config_entries.flow.async_configure(r["flow_id"], {CONF_HOST: "192.168.86.40"})
        assert r["step_id"] == "psn"
        r = await hass.config_entries.flow.async_configure(r["flow_id"], {})  # power only, PSN added later
        assert r["type"] is FlowResultType.CREATE_ENTRY and r["title"] == "PS5-512"
        assert r["data"] == {CONF_HOST: "192.168.86.40"} and r["options"]["accounts"] == []
        assert r["result"].unique_id == "001122AABBCC"
        # the same console again is refused
        r = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
        assert r["step_id"] == "manual"  # nothing new found, so it asks for an IP
        r = await hass.config_entries.flow.async_configure(r["flow_id"], {CONF_HOST: "192.168.86.40"})
        assert r["type"] is FlowResultType.ABORT and r["reason"] == "already_configured"


async def test_manual_no_answer(hass):
    with patch("custom_components.ps5_status.config_flow.async_discover", return_value=[]), \
         patch("custom_components.ps5_status.config_flow.async_query", return_value=None):
        r = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
        r = await hass.config_entries.flow.async_configure(r["flow_id"], {CONF_HOST: "192.168.86.99"})
        assert r["type"] is FlowResultType.FORM and r["errors"] == {"base": "no_answer"}


async def test_entities_follow_console(hass):
    hass.states.async_set(PSN, "playing", {"media_title": "NHL 26", "entity_picture": ART})
    entry = MockConfigEntry(domain=DOMAIN, unique_id="001122AABBCC", title="PS5-512",
                            data={CONF_HOST: "192.168.86.40"}, options={CONF_PSN_ENTITY: PSN, "scan_interval": 5, "off_after": 3})
    entry.add_to_hass(hass)
    answer = {"r": AWAKE}

    async def fake_query(host, *a, **k):
        return answer["r"]

    with patch("custom_components.ps5_status.coordinator.async_query", side_effect=fake_query):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        def st(e):
            return hass.states.get(e)
        mp = st("media_player.ps5_512")
        assert mp.state == "playing" and mp.attributes["media_title"] == "NHL 26"
        assert mp.attributes["entity_picture"].startswith("/api/media_player_proxy/media_player.ps5_512")
        assert st("sensor.ps5_512_power").state == "on"
        assert st("sensor.ps5_512_now_playing").state == "NHL 26"
        assert st("binary_sensor.ps5_512_awake").state == "on"
        assert st("binary_sensor.ps5_512_playing_a_game").state == "on"
        img = st("image.ps5_512_game_picture")
        assert img.state != "unavailable"

        # game changes on PSN: picked up straight away, without waiting for the next check
        hass.states.async_set(PSN, "playing", {"media_title": "EA FC 26", "entity_picture": ART + "?fc"})
        await hass.async_block_till_done()
        assert st("sensor.ps5_512_now_playing").state == "EA FC 26"

        # back on the home screen
        hass.states.async_set(PSN, "on", {})
        await hass.async_block_till_done()
        assert st("media_player.ps5_512").state == "on" and st("binary_sensor.ps5_512_playing_a_game").state == "off"
        assert st("image.ps5_512_game_picture").state == "unavailable"

        # rest mode
        hass.states.async_set(PSN, "playing", {"media_title": "NHL 26", "entity_picture": ART})
        answer["r"] = REST
        async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=6))
        await hass.async_block_till_done()
        assert st("media_player.ps5_512").state == "standby" and st("sensor.ps5_512_power").state == "rest"
        assert st("binary_sensor.ps5_512_awake").state == "off"
        assert st("sensor.ps5_512_now_playing").state == "unknown"  # nothing playing in rest mode, even if PSN lags

        # off: one missed answer doesn't count, three in a row do
        answer["r"] = None
        now = dt_util.utcnow()
        for i in range(1, 4):
            async_fire_time_changed(hass, now + timedelta(seconds=6 * i + 1))
            await hass.async_block_till_done()
            if i < 3:
                assert st("sensor.ps5_512_power").state == "rest"
        assert st("sensor.ps5_512_power").state == "off" and st("media_player.ps5_512").state == "off"

        # power only: no PSN entity picked
        hass.config_entries.async_update_entry(entry, options={**entry.options, CONF_PSN_ENTITY: ""})
        await hass.async_block_till_done()
        answer["r"] = AWAKE
        async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=30))
        await hass.async_block_till_done()
        assert st("media_player.ps5_512").state == "on" and st("sensor.ps5_512_now_playing").state == "unknown"

        assert await hass.config_entries.async_unload(entry.entry_id)


async def test_options(hass):
    entry = MockConfigEntry(domain=DOMAIN, unique_id="001122AABBCC", title="PS5-512",
                            data={CONF_HOST: "192.168.86.40"}, options={CONF_PSN_ENTITY: "", "scan_interval": 5, "off_after": 3})
    entry.add_to_hass(hass)
    hass.states.async_set(PSN, "on", {})
    with patch("custom_components.ps5_status.coordinator.async_query", return_value=AWAKE):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        r = await hass.config_entries.options.async_init(entry.entry_id)
        assert r["type"] is FlowResultType.MENU and r["menu_options"] == ["add_account", "settings", "link"]
        r = await hass.config_entries.options.async_configure(r["flow_id"], {"next_step_id": "settings"})
        r = await hass.config_entries.options.async_configure(r["flow_id"], {CONF_PSN_ENTITY: PSN, "scan_interval": 10,
                                                                             "psn_interval": 30, "off_after": 2})
        assert r["type"] is FlowResultType.CREATE_ENTRY
        await hass.async_block_till_done()
        assert entry.options[CONF_PSN_ENTITY] == PSN and entry.runtime_data.update_interval == timedelta(seconds=10)
        assert entry.runtime_data.psn_entity == PSN


class FakeSource:
    """Stands in for any media player (not PSN): only its picture fetch is needed."""

    def __init__(self):
        self.calls = 0

    async def async_get_media_image(self):
        self.calls += 1
        return b"\x89PNG-game-art", "image/png"


async def test_any_media_player_source_and_picture(hass):
    from homeassistant.components.image import async_get_image

    src = "media_player.living_room_tv"
    hass.states.async_set(src, "playing", {"app_name": "Astro Bot", "entity_picture": "/api/media_player_proxy/media_player.living_room_tv?token=x&cache=1"})
    entry = MockConfigEntry(domain=DOMAIN, unique_id="001122AABBCC", title="PS5-512",
                            data={CONF_HOST: "192.168.86.40"}, options={CONF_PSN_ENTITY: src, "scan_interval": 5, "off_after": 3})
    entry.add_to_hass(hass)
    fake = FakeSource()
    with patch("custom_components.ps5_status.coordinator.async_query", return_value=AWAKE), \
         patch("custom_components.ps5_status.coordinator.Ps5Coordinator.source_entity", return_value=fake):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        assert hass.states.get("sensor.ps5_512_now_playing").state == "Astro Bot"  # app_name when there's no media_title
        image = await async_get_image(hass, "image.ps5_512_game_picture")
        assert image.content == b"\x89PNG-game-art" and image.content_type == "image/png"
        player = hass.data["media_player"].get_entity("media_player.ps5_512")
        assert await player.async_get_media_image() == (b"\x89PNG-game-art", "image/png")
        # no turn-on until linked
        assert hass.states.get("media_player.ps5_512").attributes["supported_features"] == 0
        assert hass.states.get("button.ps5_512_turn_on") is None


async def test_link_then_turn_on(hass):
    hass.states.async_set(PSN, "on", {})
    psn_entry = MockConfigEntry(domain="playstation_network", unique_id="1234567890123456789", title="JonG98")
    psn_entry.add_to_hass(hass)
    entry = MockConfigEntry(domain=DOMAIN, unique_id="001122AABBCC", title="PS5-512",
                            data={CONF_HOST: "192.168.86.40"}, options={CONF_PSN_ENTITY: PSN, "scan_interval": 5, "off_after": 3})
    entry.add_to_hass(hass)
    answer = {"r": REST}

    async def fake_query(host, *a, **k):
        return answer["r"]

    with patch("custom_components.ps5_status.coordinator.async_query", side_effect=fake_query):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        r = await hass.config_entries.options.async_init(entry.entry_id)
        r = await hass.config_entries.options.async_configure(r["flow_id"], {"next_step_id": "link"})
        assert r["step_id"] == "link"
        # a wrong code
        from custom_components.ps5_status.remoteplay import RemotePlayError
        with patch("custom_components.ps5_status.config_flow.async_register", side_effect=RemotePlayError("The PS5 refused the code.")):
            r = await hass.config_entries.options.async_configure(r["flow_id"], {"account_id": "1234567890123456789", "pin": "11112222"})
        assert r["errors"] == {"base": "link_failed"} and r["description_placeholders"]["error"] == "The PS5 refused the code."
        with patch("custom_components.ps5_status.config_flow.async_register",
                   return_value={"PS5-RegistKey": "3361613562383339", "PS5-Nickname": "PS5-512"}) as reg:
            r = await hass.config_entries.options.async_configure(r["flow_id"], {"account_id": "1234567890123456789", "pin": "12345678"})
        assert r["type"] is FlowResultType.CREATE_ENTRY
        assert reg.call_args.args == ("192.168.86.40", "1234567890123456789", "12345678")
        await hass.async_block_till_done()
        assert entry.data["regist_key"] == "3361613562383339"
        assert hass.states.get("media_player.ps5_512").attributes["supported_features"] == 128  # TURN_ON

        woke = []

        async def fake_wake(host, key, *a, **k):
            woke.append((host, key))
            answer["r"] = AWAKE

        with patch("custom_components.ps5_status.media_player.async_wake", side_effect=fake_wake), \
             patch("custom_components.ps5_status.media_player.asyncio.sleep", return_value=None):
            await hass.services.async_call("media_player", "turn_on", {"entity_id": "media_player.ps5_512"}, blocking=True)
            await hass.async_block_till_done()
            assert woke == [("192.168.86.40", "3361613562383339")]
            assert hass.states.get("sensor.ps5_512_power").state == "on"
            answer["r"] = REST
            await hass.services.async_call("button", "press", {"entity_id": "button.ps5_512_turn_on"}, blocking=True)
            await hass.async_block_till_done()
            assert len(woke) == 2

        # unlink
        r = await hass.config_entries.options.async_init(entry.entry_id)
        assert "unlink" in r["menu_options"]
        r = await hass.config_entries.options.async_configure(r["flow_id"], {"next_step_id": "unlink"})
        await hass.async_block_till_done()
        assert "regist_key" not in entry.data and hass.states.get("media_player.ps5_512").attributes["supported_features"] == 0
