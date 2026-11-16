# PS5 Status for Home Assistant

<img src="custom_components/ps5_status/brand/icon.png" width="96" align="right">

Your PS5's **real power state** (on, rest mode, off) straight from your home network, plus **what's playing, the game's picture and who's playing** straight from PlayStation Network, as **one** PS5 device and **one** media player. No PlayStation Network integration needed. It can also **turn the PS5 on**.

| Entity | What it shows |
|---|---|
| `media_player.<ps5>` | **off**, **standby** (rest mode), **on**, or **playing** with the game title and cover art. Works in any media card. Its power button turns the PS5 on once it's linked |
| `sensor.<ps5>_power` | On / Rest mode / Off |
| `sensor.<ps5>_now_playing` | The game, empty when nothing is playing |
| `sensor.<ps5>_who_s_playing` | Which of your PSN accounts is on the console (Jon, Von...) |
| `binary_sensor.<ps5>_awake` | On while the console is awake |
| `binary_sensor.<ps5>_playing_a_game` | On while a game is running |
| `image.<ps5>_game_picture` | The game's picture, for picture cards and wallpapers |
| `button.<ps5>_turn_on` | Turns the PS5 on (only after linking, see below) |

## How it works

- **Power** comes from the console itself. Every few seconds Home Assistant asks the PS5 on your network (the same check the Remote Play app uses to find it). It answers "awake" or "rest mode". No answer means off. No PSN login, no pairing and no add-on needed, and it changes within seconds.
- **The game, picture and who's playing** come from PlayStation Network, because the PS5 doesn't tell the local network what's running. PS5 Status signs in to PSN itself with an **NPSSO token** (the same thing the PlayStation Network integration asks for), so you don't need that integration. Add one account or several (you, a roommate): whoever is signed in on the console shows as **who's playing**, and the media player's `media_artist` and `whos_playing` attribute say who. PSN is only asked while the PS5 is on (every 30 seconds, plus right when it wakes up). In rest mode or off, nothing shows as playing even if PSN lags behind.
- **Old way still works:** with no PSN account added, you can pick any media player as the game source in Settings.
- **Turning on** works like the PS Remote Play app: link once with the code the PS5 shows, then Home Assistant can send it the wake-up.
- One missed answer doesn't flip it to off: it waits for 3 in a row (about 15 seconds), so a dropped Wi-Fi packet doesn't cause a false "off".

## Install

1. **Get an NPSSO token**: sign in at [playstation.com](https://www.playstation.com), then in the same browser open [ca.account.sony.com/api/v1/ssocookie](https://ca.account.sony.com/api/v1/ssocookie). Copy the 64-character code (or the whole `{"npsso":"..."}` line). Tokens last about 2 months.
2. **HACS**: HACS > ⋮ > **Custom repositories**, add `https://github.com/jonathangibson98/ha-ps5-status` with type **Integration**, then search for **PS5 Status** and download it. Restart Home Assistant.
   Or copy `custom_components/ps5_status` into your `/config/custom_components/` folder and restart.
3. **Settings > Devices & services > Add integration > PS5 Status.** Your PS5 is found on the network: pick it (or type its IP address). Then type a name (like Jon) and paste the NPSSO token, or leave it empty for power only.
4. More people on the same console: **Configure > Add a PSN account** for each, or **Add a friend** to track a friend through your own sign-in (no token from them needed, like the PlayStation Network integration's friend tracking).
5. Once it works you can **delete the PlayStation Network integration** and any template/universal PS5 players you made to glue things together.

## Turning it on

1. On the PS5, turn on **Settings > System > Remote Play > Enable Remote Play**.
2. In Home Assistant: **Settings > Devices & services > PS5 Status > Configure > Link for turning on**.
3. On the PS5: **Settings > System > Remote Play > Link Device**. It shows an 8-digit code.
4. Pick your PSN account (filled in from the PSN accounts you added, or type your PSN account ID number), type the code and submit while it's still on screen.

After that the media player's power button and the **Turn on** button wake the PS5 (it takes 10-20 seconds). **Unlink** in the same menu makes Home Assistant forget the key.

Turning it **off** (rest mode) isn't supported: the PS5 only accepts that inside a full Remote Play streaming session.

### On the PS5

- Give the PS5 a **fixed IP address** in your router, so Home Assistant always finds it.
- For **rest mode** to show as rest mode (instead of off): **Settings > System > Power Saving > Features Available in Rest Mode**, turn on **Stay Connected to the Internet**. Without it, rest mode looks the same as off.
- Home Assistant and the PS5 have to be on the same network (UDP port 9302 between them).

## Options

**Settings > Devices & services > PS5 Status > Configure**:

| Option | Default | What |
|---|---|---|
| Add / Remove a PSN account | | The accounts whose game and name show up |
| Add a friend | | Pick someone from your PSN friends list. Their privacy settings must let friends see their online status and game |
| Check PSN every | 30 s | Only while the PS5 is on. PSN rate-limits, so keep it 30 s or more |
| Game source media player | empty | The old way: the game comes from another media player. Ignored once a PSN account is added |
| Check every | 5 s | How often the PS5 is asked |
| Missed answers before it counts as off | 3 | Stops a dropped packet from flipping it off |

## Using it with Template Media Player UI

You don't need a template player anymore: `media_player.ps5_512` already has the power state, game, picture and who's playing. If you still want your Template Media Player UI player (for its card or custom actions), point every template at this one entity instead of mixing PSN, image and sensor entities:

| Template | Value |
|---|---|
| State | `{{ states('media_player.ps5_512') }}` |
| Media title | `{{ state_attr('media_player.ps5_512', 'media_title') }}` |
| Artist | `{{ state_attr('media_player.ps5_512', 'whos_playing') }}` |
| Entity picture | `{{ state_attr('media_player.ps5_512', 'entity_picture') }}` |
| Who's playing (attribute) | `{{ state_attr('media_player.ps5_512', 'whos_playing') or 'Nobody' }}` |
| Turn on action | `media_player.turn_on` on `media_player.ps5_512` |

Because it all comes from one place, the state and who's playing can't disagree (no more "playing Roblox / Powered off").

## Dashboard examples

Media card with the game art:

```yaml
type: media-control
entity: media_player.ps5_512
```

Picture of the game, only while playing:

```yaml
type: conditional
conditions:
  - condition: state
    entity: binary_sensor.ps5_512_playing_a_game
    state: "on"
card:
  type: picture-entity
  entity: image.ps5_512_game_picture
  show_state: false
  name: "{{ states('sensor.ps5_512_now_playing') }}"
```

Automation: dim the living room when a game starts:

```yaml
triggers:
  - trigger: state
    entity_id: binary_sensor.ps5_512_playing_a_game
    to: "on"
actions:
  - action: light.turn_on
    target:
      entity_id: light.living_room
    data:
      brightness_pct: 25
```

Replace `ps5_512` with your console's name (it's the name the PS5 gives itself, like PS5-512).

## Limits

- It can turn the PS5 on, not off (see above).
- Friends: PSN says a friend is on *a* PS5, not *which* one. If they're gaming on their own console at their place while yours is on, they'll show as playing yours. Your own accounts always win over friends.
- NPSSO tokens expire after about 2 months. When one does, the media player's `psn_problem` attribute says so: **Configure > Add a PSN account** with the same name and a fresh token replaces it.
- Your PSN privacy settings have to let your online status and what you're playing be seen, and it updates on PSN's schedule (about 30 seconds).

## Credits and license

Linking and waking follow the Remote Play protocol worked out by [Chiaki](https://git.sr.ht/~thestr4ng3r/chiaki) and implemented in Python by [pyremoteplay](https://github.com/ktnrg45/pyremoteplay). `remoteplay.py` is adapted from pyremoteplay for the PS5 only, using the `cryptography` package Home Assistant already ships, so nothing extra is installed. Because of that, this project is licensed under the **GNU GPL v3** like pyremoteplay.

## Development

```sh
pip install pytest-homeassistant-custom-component
pytest
```
