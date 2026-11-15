# PS5 Status for Home Assistant

Your PS5's **real power state** (on, rest mode, off) straight from your home network, merged with **what's playing and the game's picture** from Home Assistant's PlayStation Network integration, as one PS5 device.

| Entity | What it shows |
|---|---|
| `media_player.<ps5>` | **off**, **standby** (rest mode), **on**, or **playing** with the game title and cover art. Works in any media card |
| `sensor.<ps5>_power` | On / Rest mode / Off |
| `sensor.<ps5>_now_playing` | The game, empty when nothing is playing |
| `binary_sensor.<ps5>_awake` | On while the console is awake |
| `binary_sensor.<ps5>_playing_a_game` | On while a game is running |
| `image.<ps5>_game_picture` | The game's picture, for picture cards and wallpapers |

## How it works

- **Power** comes from the console itself. Every few seconds Home Assistant asks the PS5 on your network (the same check the Remote Play app uses to find it). It answers "awake" or "rest mode". No answer means off. No PSN login, no pairing and no add-on needed, and it changes within seconds.
- **The game and picture** come from the [PlayStation Network](https://www.home-assistant.io/integrations/playstation_network) integration, because the PS5 doesn't tell the local network what's running. When PSN reports a new game it shows up straight away. In rest mode or off, nothing shows as playing even if PSN lags behind.
- One missed answer doesn't flip it to off: it waits for 3 in a row (about 15 seconds), so a dropped Wi-Fi packet doesn't cause a false "off".

## Install

1. **Set up PlayStation Network first** (Settings > Devices & services > Add integration > PlayStation Network) if you want the game and picture.
2. **HACS**: HACS > ⋮ > **Custom repositories**, add `https://github.com/jonathangibson98/ha-ps5-status` with type **Integration**, then search for **PS5 Status** and download it. Restart Home Assistant.
   Or copy `custom_components/ps5_status` into your `/config/custom_components/` folder and restart.
3. **Settings > Devices & services > Add integration > PS5 Status.** Your PS5 is found on the network: pick it (or type its IP address). Then pick the PlayStation Network media player for it, or leave that empty for power only.

### On the PS5

- Give the PS5 a **fixed IP address** in your router, so Home Assistant always finds it.
- For **rest mode** to show as rest mode (instead of off): **Settings > System > Power Saving > Features Available in Rest Mode**, turn on **Stay Connected to the Internet**. Without it, rest mode looks the same as off.
- Home Assistant and the PS5 have to be on the same network (UDP port 9302 between them).

## Options

**Settings > Devices & services > PS5 Status > Configure**:

| Option | Default | What |
|---|---|---|
| PlayStation Network media player | (picked at setup) | Where the game and picture come from. Empty for power only |
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

- It reads the power state, it doesn't change it. Turning the PS5 on or putting it to rest needs Remote Play pairing (the PS5-MQTT add-on does that).
- The game comes from PSN, so your PSN privacy settings have to let your online status and what you're playing be seen, and it updates on PSN's schedule (about 30 seconds).

## Development

```sh
pip install pytest-homeassistant-custom-component
pytest
```
