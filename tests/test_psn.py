"""Built-in PSN: who's playing and the game, with no PlayStation Network integration."""
from unittest.mock import patch

from homeassistant import config_entries
from homeassistant.const import CONF_HOST
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ps5_status.const import DOMAIN
from custom_components.ps5_status.ddp import parse_reply
from custom_components.ps5_status.psn import Presence, PsnAuthError, parse_presence

AWAKE = parse_reply(b"HTTP/1.1 200 Ok\nhost-id:0C7043751C7E\nhost-type:PS5\nhost-name:PS5-512\nsystem-version:09400000\n", "192.168.86.40")
REST = parse_reply(b"HTTP/1.1 620 Server Standby\nhost-id:0C7043751C7E\nhost-type:PS5\nhost-name:PS5-512\n", "192.168.86.40")
ART = "https://image.api.playstation.com/vulcan/roblox.png"
TOKEN = "a" * 64


def test_parse_presence():
    p = parse_presence({"basicPresence": {
        "availability": "availableToPlay",
        "primaryPlatformInfo": {"onlineStatus": "online", "platform": "PS5"},
        "gameTitleInfoList": [{"npTitleId": "PPSA01", "titleName": "Roblox", "format": "PS5", "launchPlatform": "PS5",
                               "conceptIconUrl": ART}]}})
    assert p.on_ps5 and p.title == "Roblox" and p.image == ART and p.title_id == "PPSA01"
    off = parse_presence({"basicPresence": {"primaryPlatformInfo": {"onlineStatus": "offline", "platform": "PS5"}}})
    assert not off.on_ps5 and off.title is None


async def test_setup_with_npsso(hass):
    async def fake_login(self):
        self.account_id, self.online_id = "1234567890123456789", "JonG98"

    with patch("custom_components.ps5_status.config_flow.async_discover", return_value=[AWAKE]), \
         patch("custom_components.ps5_status.config_flow.async_query", return_value=AWAKE), \
         patch("custom_components.ps5_status.coordinator.async_query", return_value=AWAKE), \
         patch("custom_components.ps5_status.psn.PsnAccount.async_login", fake_login), \
         patch("custom_components.ps5_status.psn.PsnAccount.async_presence", return_value=Presence()):
        r = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
        r = await hass.config_entries.flow.async_configure(r["flow_id"], {CONF_HOST: "192.168.86.40"})
        bad = await hass.config_entries.flow.async_configure(r["flow_id"], {"name": "Jon", "npsso": "short"})
        assert bad["errors"] == {"npsso": "bad_npsso"}
        r = await hass.config_entries.flow.async_configure(r["flow_id"], {"name": "", "npsso": '{"npsso":"%s"}' % TOKEN})
        assert r["type"] is FlowResultType.CREATE_ENTRY
        acct = r["options"]["accounts"][0]
        assert acct["name"] == "JonG98" and acct["npsso"] == TOKEN and acct["account_id"] == "1234567890123456789"


async def test_refused_npsso(hass):
    with patch("custom_components.ps5_status.config_flow.async_discover", return_value=[AWAKE]), \
         patch("custom_components.ps5_status.config_flow.async_query", return_value=AWAKE), \
         patch("custom_components.ps5_status.psn.PsnAccount.async_login", side_effect=PsnAuthError("nope")):
        r = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
        r = await hass.config_entries.flow.async_configure(r["flow_id"], {CONF_HOST: "192.168.86.40"})
        r = await hass.config_entries.flow.async_configure(r["flow_id"], {"name": "Jon", "npsso": TOKEN})
        assert r["errors"] == {"npsso": "bad_npsso"}


async def test_whos_playing(hass):
    from datetime import timedelta
    from homeassistant.util import dt as dt_util
    from pytest_homeassistant_custom_component.common import async_fire_time_changed

    presences = {
        "J" * 64: Presence(online=True, platform="PS5"),  # Jon on the home screen
        "V" * 64: Presence(online=True, platform="PS5", title="Roblox", title_id="PPSA01", image=ART),
    }

    async def fake_presence(self, account_id="me"):
        return presences[self.npsso]

    async def fake_login(self):
        return None

    entry = MockConfigEntry(domain=DOMAIN, unique_id="0C7043751C7E", title="PS5-512", data={CONF_HOST: "192.168.86.40"},
                            options={"accounts": [{"name": "Jon", "npsso": "J" * 64}, {"name": "Von", "npsso": "V" * 64}],
                                     "psn_entity": "", "scan_interval": 5, "psn_interval": 30, "off_after": 1})
    entry.add_to_hass(hass)
    answer = {"r": AWAKE}

    async def fake_query(host, *a, **k):
        return answer["r"]

    with patch("custom_components.ps5_status.coordinator.async_query", side_effect=fake_query), \
         patch("custom_components.ps5_status.psn.PsnAccount.async_login", fake_login), \
         patch("custom_components.ps5_status.psn.PsnAccount.async_presence", fake_presence):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        mp = hass.states.get("media_player.ps5_512")
        assert mp.state == "playing" and mp.attributes["media_title"] == "Roblox"
        assert mp.attributes["whos_playing"] == "Von" and mp.attributes["media_artist"] == "Von"
        assert mp.attributes["players"] == ["Jon", "Von"]
        assert mp.attributes["entity_picture"].startswith("/api/media_player_proxy/media_player.ps5_512")
        assert hass.states.get("sensor.ps5_512_who_s_playing").state == "Von"

        # console goes to rest mode: nobody's playing, even though PSN still says Roblox
        answer["r"] = REST
        async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=6))
        await hass.async_block_till_done()
        mp = hass.states.get("media_player.ps5_512")
        assert mp.state == "standby" and mp.attributes.get("media_title") is None
        assert mp.attributes["whos_playing"] is None
        assert await hass.config_entries.async_unload(entry.entry_id)


async def test_picture_downloaded_from_sony(hass, aioclient_mock):
    aioclient_mock.get(ART, content=b"\x89PNG-roblox", headers={"Content-Type": "image/png"})

    async def fake_login(self):
        return None

    entry = MockConfigEntry(domain=DOMAIN, unique_id="0C7043751C7E", title="PS5-512", data={CONF_HOST: "192.168.86.40"},
                            options={"accounts": [{"name": "Von", "npsso": "V" * 64}], "scan_interval": 5})
    entry.add_to_hass(hass)
    with patch("custom_components.ps5_status.coordinator.async_query", return_value=AWAKE), \
         patch("custom_components.ps5_status.psn.PsnAccount.async_login", fake_login), \
         patch("custom_components.ps5_status.psn.PsnAccount.async_presence",
               return_value=Presence(online=True, platform="PS5", title="Roblox", image=ART)):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        player = hass.data["media_player"].get_entity("media_player.ps5_512")
        assert await player.async_get_media_image() == (b"\x89PNG-roblox", "image/png")
        assert await player.async_get_media_image() == (b"\x89PNG-roblox", "image/png")
        assert aioclient_mock.call_count == 1  # cached until the game changes


async def test_add_friend_and_track(hass):
    async def fake_login(self):
        return None

    async def fake_friends(self):
        return [("2222222222222222222", "VonTheGoat"), ("3333333333333333333", "SomeoneElse")]

    presences = {"me": Presence(online=False), "2222222222222222222": Presence(online=True, platform="PS5",
                                                                              title="Roblox", image=ART)}

    async def fake_presence(self, account_id="me"):
        return presences[account_id]

    entry = MockConfigEntry(domain=DOMAIN, unique_id="0C7043751C7E", title="PS5-512", data={CONF_HOST: "192.168.86.40"},
                            options={"accounts": [{"name": "Jon", "npsso": "J" * 64, "account_id": "1111111111111111111"}],
                                     "psn_entity": "", "scan_interval": 5, "psn_interval": 30, "off_after": 3})
    entry.add_to_hass(hass)
    with patch("custom_components.ps5_status.coordinator.async_query", return_value=AWAKE), \
         patch("custom_components.ps5_status.psn.PsnAccount.async_login", fake_login), \
         patch("custom_components.ps5_status.psn.PsnAccount.async_friends", fake_friends), \
         patch("custom_components.ps5_status.psn.PsnAccount.async_presence", fake_presence):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        assert hass.states.get("media_player.ps5_512").state == "on"  # Jon's offline, nobody playing

        r = await hass.config_entries.options.async_init(entry.entry_id)
        assert r["menu_options"] == ["add_account", "add_friend", "remove_account", "settings", "link"]
        r = await hass.config_entries.options.async_configure(r["flow_id"], {"next_step_id": "add_friend"})
        assert r["step_id"] == "pick_friend"  # only one account, so it skips straight to the friends list
        r = await hass.config_entries.options.async_configure(r["flow_id"], {"account_id": "2222222222222222222", "name": "Jon"})
        assert r["errors"] == {"name": "name_taken"}
        r = await hass.config_entries.options.async_configure(r["flow_id"], {"account_id": "2222222222222222222", "name": "Von"})
        assert r["type"] is FlowResultType.CREATE_ENTRY
        await hass.async_block_till_done()
        friend = entry.options["accounts"][1]
        assert friend["friend_of"] == "Jon" and friend["account_id"] == "2222222222222222222" and "npsso" not in friend

        mp = hass.states.get("media_player.ps5_512")
        assert mp.state == "playing" and mp.attributes["whos_playing"] == "Von" and mp.attributes["media_title"] == "Roblox"

        # removing Jon takes Von with him (Von was tracked through Jon's sign-in)
        r = await hass.config_entries.options.async_init(entry.entry_id)
        r = await hass.config_entries.options.async_configure(r["flow_id"], {"next_step_id": "remove_account"})
        r = await hass.config_entries.options.async_configure(r["flow_id"], {"remove": ["Jon"]})
        await hass.async_block_till_done()
        assert entry.options["accounts"] == []
