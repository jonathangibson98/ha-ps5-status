# PS5 Status for Home Assistant

<img src="custom_components/ps5_status/brand/icon.png" width="96" align="right">

Your PS5's **real power state** (on, rest mode, off) straight from your home network, merged with **what's playing and the game's picture** from any media player (usually Home Assistant's PlayStation Network integration), as one PS5 device. It can also **turn the PS5 on**.

| Entity | What it shows |
|---|---|
| `media_player.<ps5>` | **off**, **standby** (rest mode), **on**, or **playing** with the game title and cover art. Works in any media card. Its power button turns the PS5 on once it's linked |
| `sensor.<ps5>_power` | On / Rest mode / Off |
| `sensor.<ps5>_now_playing` | The game, empty when nothing is playing |
| `binary_sensor.<ps5>_awake` | On while the console is awake |
| `binary_sensor.<ps5>_playing_a_game` | On while a game is running |
| `image.<ps5>_game_picture` | The game's picture, for picture cards and wallpapers |
| `button.<ps5>_turn_on` | Turns the PS5 on (only after linking, see below) |

## How it works

- **Power** comes from the console itself. Every few seconds Home Assistant asks the PS5 on your network (the same check the Remote Play app uses to find it). It answers "awake" or "rest mode". No answer means off. No PSN login, no pairing and no add-on needed, and it changes within seconds.
- **The game and picture** come from a media player you pick, because the PS5 doesn't tell the local network what's running. Usually that's the [PlayStation Network](https://www.home-assistant.io/integrations/playstation_network) integration's console player, but **any media player works** (your TV, a universal media player, anything with a title and picture). The title is its media title (or app name), and the picture is fetched through Home Assistant the same way that player's own card gets it, so it works even when the art isn't on the internet. When the source changes it shows up straight away. In rest mode or off, nothing shows as playing even if the source lags behind.
- **Turning on** works like the PS Remote Play app: link once with the code the PS5 shows, then Home Assistant can send it the wake-up.
- One missed answer doesn't flip it to off: it waits for 3 in a row (about 15 seconds), so a dropped Wi-Fi packet doesn't cause a false "off".

## Install

1. **Set up PlayStation Network first** (Settings > Devices & services > Add integration > PlayStation Network) if you want the game and picture.
2. **HACS**: HACS > ⋮ > **Custom repositories**, add `https://github.com/jonathangibson98/ha-ps5-status` with type **Integration**, then search for **PS5 Status** and download it. Restart Home Assistant.
   Or copy `custom_components/ps5_status` into your `/config/custom_components/` folder and restart.
3. **Settings > Devices & services > Add integration > PS5 Status.** Your PS5 is found on the network: pick it (or type its IP address). Then pick the media player the game comes from (PlayStation Network's player for it, or any other), or leave that empty for power only.

## Turning it on

1. On the PS5, turn on **Settings > System > Remote Play > Enable Remote Play**.
2. In Home Assistant: **Settings > Devices & services > PS5 Status > Configure > Link for turning on**.
3. On the PS5: **Settings > System > Remote Play > Link Device**. It shows an 8-digit code.
4. Pick your PSN account (it's filled in from the PlayStation Network integration, or type your PSN account ID number), type the code and submit while it's still on screen.

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
| Game source media player | (picked at setup) | Where the game and picture come from: any media player. Empty for power only |
| Check every | 5 s | How often the PS5 is asked |
| Missed answers before it counts as off | 3 | Stops a dropped packet from flipping it off |

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
- With PlayStation Network as the source, your PSN privacy settings have to let your online status and what you're playing be seen, and it updates on PSN's schedule (about 30 seconds).

## Credits and license

Linking and waking follow the Remote Play protocol worked out by [Chiaki](https://git.sr.ht/~thestr4ng3r/chiaki) and implemented in Python by [pyremoteplay](https://github.com/ktnrg45/pyremoteplay). `remoteplay.py` is adapted from pyremoteplay for the PS5 only, using the `cryptography` package Home Assistant already ships, so nothing extra is installed. Because of that, this project is licensed under the **GNU GPL v3** like pyremoteplay.

## Development

```sh
pip install pytest-homeassistant-custom-component
pytest
```
