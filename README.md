# klipper-fade-light

A tiny [Klipper](https://www.klipper3d.org/) plugin that adds smooth, non-blocking fade transitions for plain `[output_pin]` devices — e.g. dumb 24V single-color LED strips that aren't addressable (no WS2812/SK6812 chip, so [led_effect](https://github.com/julianschill/klipper-led_effect) can't drive them).

## Why

Klipper's built-in `output_pin` only supports instant value jumps via `SET_PIN PIN=x VALUE=y` — there's no native fade/transition support. The stock workaround (`SET_PIN ... TEMPLATE=`, backed by a `[display_template]`) re-renders on a fixed 0.5s interval hardcoded in Klipper itself, which is coarse and not configurable.

`fade_light.py` adds a `FADE_LIGHT` command that ramps any existing `output_pin` to a target value over a given duration, driven by a Klipper `reactor` timer at 50Hz. It:

- Updates via the same internal async request path Klipper's own `display_template` mechanism uses (`pin.gcrq.send_async_request`), so it bypasses the G-code queue entirely — safe to call mid-print without blocking other G-code.
- Supports multiple pins fading independently and concurrently.
- Needs no extra hardware and no other plugins.

## Install

```bash
cd ~
git clone https://github.com/bincat233/klipper-fade-light.git
ln -sf ~/klipper-fade-light/fade_light.py ~/klipper/klippy/extras/fade_light.py
sudo systemctl restart klipper
```

Then add a bare section to `printer.cfg`:

```ini
[fade_light]
```

No parameters — one `[fade_light]` section handles fading for every `output_pin` you have configured.

### Keep it updated (optional, via Moonraker's update manager)

```ini
[update_manager fade_light]
type: git_repo
path: ~/klipper-fade-light
origin: https://github.com/bincat233/klipper-fade-light.git
primary_branch: main
managed_services: klipper
```

## Usage

```
FADE_LIGHT PIN=<output_pin name> TARGET=<0.0-1.0> [DURATION=<seconds, default 1.0>]
```

- `PIN` — the name of any configured `[output_pin NAME]` section (just `NAME`, not the `output_pin` prefix).
- `TARGET` — target value, `0.0`–`1.0`.
- `DURATION` — fade time in seconds. Defaults to `1.0`.

### Example

```ini
[output_pin left_light]
pin: PF10
pwm: True
value: 0
shutdown_value: 0

[fade_light]
```

```
; fade in over 2 seconds
FADE_LIGHT PIN=left_light TARGET=1.0 DURATION=2
; fade out over 0.5 seconds
FADE_LIGHT PIN=left_light TARGET=0.0 DURATION=0.5
```

Calling `FADE_LIGHT` again on a pin that's mid-fade retargets it smoothly from its current value — no jump.

## Limitations

- Only works with `[output_pin]` sections. It does **not** control addressable LEDs (`neopixel`/`dotstar`) — use [led_effect](https://github.com/julianschill/klipper-led_effect) for those.
- `output_pin` must be configured with `pwm: True` for a fade to be visually meaningful (a digital on/off pin will just snap to whichever side of `0.5` it crosses).

## License

GPLv3 — see [LICENSE](LICENSE).
