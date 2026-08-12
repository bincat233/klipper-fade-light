# klipper-fade-light

A tiny [Klipper](https://www.klipper3d.org/) plugin that adds smooth, non-blocking fade transitions for plain `[output_pin]` devices — e.g. dumb 24V single-color LED strips that aren't addressable (no WS2812/SK6812 chip, so [led_effect](https://github.com/julianschill/klipper-led_effect) can't drive them).

## Why

Klipper's built-in `output_pin` only supports instant value jumps via `SET_PIN PIN=x VALUE=y` — there's no native fade/transition support. The stock workaround (`SET_PIN ... TEMPLATE=`, backed by a `[display_template]`) re-renders on a fixed 0.5s interval hardcoded in Klipper itself, which is coarse and not configurable.

`fade_light.py` adds a `FADE_LIGHT` command that ramps any existing `output_pin` to a target value over a given duration, driven by a Klipper `reactor` timer at a genuine 50Hz. It:

- Writes straight to the pin's MCU command queue (`MCU_pwm.set_pwm()`) — the same low-level path `neopixel.py` uses for color updates — bypassing the G-code queue entirely, so it's safe to call mid-print without blocking other G-code. See [Implementation notes](#implementation-notes) for why it doesn't go through `output_pin`'s own async request helper.
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
primary_branch: master
managed_services: klipper
```

## Usage

```
FADE_LIGHT PIN=<output_pin name> TARGET=<0.0-1.0>
    [DURATION=<seconds, default 1.0>]
    [EASING=<linear|ease_in|ease_out|ease_in_out, default linear>]
    [GAMMA=<exponent, default 1.0 (no correction)>]
```

- `PIN` — the name of any configured `[output_pin NAME]` section (just `NAME`, not the `output_pin` prefix).
- `TARGET` — target value, `0.0`–`1.0`.
- `DURATION` — fade time in seconds. Defaults to `1.0`.
- `EASING` — shapes how fade progress moves through time. `linear` (default) is constant speed; `ease_in` starts slow; `ease_out` ends slow; `ease_in_out` starts and ends slow, speeds up in the middle. This is a *timing/pacing* effect, independent of brightness.
- `GAMMA` — compensates for the eye's non-linear brightness perception. A plain linear PWM ramp looks like it rushes through the dim end and lingers at the bright end, because perceived brightness is roughly a power-law function of physical output. Values around `2.2`–`2.8` (the common display/LED gamma convention) make the fade look more evenly paced. Applied to fade progress (`value = t ** gamma`), so it's most accurate for fades spanning the full `0..1` range. Defaults to `1.0` (no correction, matches plain linear behavior).

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
; more natural-looking fade: eased timing + gamma-corrected brightness
FADE_LIGHT PIN=left_light TARGET=1.0 DURATION=2 EASING=ease_in_out GAMMA=2.2
```

Calling `FADE_LIGHT` again on a pin that's mid-fade retargets it smoothly from its current value — no jump.

## Implementation notes

`output_pin` ships its own async update helper (`GCodeRequestQueue.send_async_request`, used internally by `SET_PIN ... TEMPLATE=`) that looks like the obvious thing to call from a fade timer. Don't — it enforces a `MIN_SCHEDULE_TIME` (0.100s, hardcoded in Klipper's `mcu.py`) as a minimum gap *between* successive requests on the same pin, not just a per-request lead-in margin. Calling it faster than 10Hz doesn't drop the extra calls; each one gets queued with its execution time pushed further into the future than the last, so the requests back up — a `DURATION=1.5` fade would actually take 7-8 seconds to finish draining the backlog, arriving in visible ~100ms steps the whole time. Klipper's only built-in user of that path (`display_template`) refreshes at a fixed 0.5s, so it never trips this.

`fade_light.py` instead calls the pin's `MCU_pwm.set_pwm(print_time, value)` directly — the same primitive `output_pin` itself calls once it's past the queue, and the same style of direct MCU-queue write `neopixel.py` uses for its color updates. That call has no built-in throttle beyond requiring a monotonically non-decreasing clock, which a real-time-driven fade satisfies for free. The trade-off: bypassing `GCodeRequestQueue` means also bypassing its `last_value` bookkeeping, so `fade_light.py` updates `pin.last_value` itself after every write to keep `SET_PIN`'s status reporting (and its own fade-restart logic, which reads `pin.last_value` as the starting point) consistent.

## Limitations

- Only works with `[output_pin]` sections. It does **not** control addressable LEDs (`neopixel`/`dotstar`) — use [led_effect](https://github.com/julianschill/klipper-led_effect) for those.
- `output_pin` must be configured with `pwm: True` for a fade to be visually meaningful (a digital on/off pin will just snap to whichever side of `0.5` it crosses).

## License

GPLv3 — see [LICENSE](LICENSE).
