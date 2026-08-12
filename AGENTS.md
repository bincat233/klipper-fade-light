# klipper-fade-light — AI context

`fade_light.py` is a single-file Klipper plugin: a `FADE_LIGHT` command that
smoothly ramps a plain `[output_pin]` (dumb PWM LED strip, not addressable)
to a target value over time. See `README.md` for user-facing docs. This
file is for whoever (human or AI) next touches the implementation.

## Dev/test loop

There's no simulator for this — it only runs against real Klipper hardware.
Current dev rig is `umeko`'s Voron printer (`~/printer_data`, pins
`left_light`=PF10, `right_light`=PC0, both plain PWM `output_pin`s, no
`scale:` set). The repo here is the source of truth; the copy loaded by
Klipper is a symlink:

```
~/klipper/klippy/extras/fade_light.py -> ~/klipper-fade-light/fade_light.py
```

**After editing `fade_light.py`, `sudo systemctl restart klipper.service` —
`FIRMWARE_RESTART`/`RESTART` G-code is *not* enough.** Klippy's restart is a
`while 1` loop inside the same OS process that recreates the `Printer`
object (see `klippy.py`'s `main()`); it does not re-`import` Python modules
that are already loaded, so a `FIRMWARE_RESTART` after an edit keeps running
the old in-memory code. If `printer/info`'s `process_id` is unchanged after
a restart, that's the tell that it didn't take. This exact trap ate a long
debugging session early on (looked like "parameter validation isn't taking
effect" when really the old code was still running).

After restarting, sanity-check via Moonraker/klipper-mcp against the live
printer:
- `FADE_LIGHT PIN=left_light TARGET=1.0 DURATION=1.5 EASING=ease_in_out GAMMA=2.2`
  and watch that it completes in roughly the requested duration, not longer.
- Grep `printer_data/logs/klippy.log` for `Traceback`/`AttributeError` after
  the test call — reactor-timer exceptions don't always surface as a G-code
  error response, they just log and silently kill that timer.

## Key implementation lesson: don't use `GCodeRequestQueue` for a fade timer

`output_pin.py`'s `GCodeRequestQueue.send_async_request()` (the path
`SET_PIN ... TEMPLATE=` uses internally) looks like the obvious way to push
async value updates to a pin. It isn't, for anything faster than 10Hz:

- Klipper's `mcu.py` hardcodes `MIN_SCHEDULE_TIME = 0.100`, commented as
  "Minimum time host needs to get scheduled events queued into mcu" — i.e.
  a *per-request* lead-in margin.
- `GCodeRequestQueue` instead uses it as a **minimum gap between successive
  requests** on the same pin (`next_min_flush_time = max(prev, next_time +
  min_schedule_time)`). Calls faster than that aren't dropped — each gets
  queued with its execution time pushed further into the future than the
  last one, so requests silently back up.
- Concretely: a `FADE_UPDATE_INTERVAL = 0.02` (50Hz) timer backs up into a
  10Hz-spaced queue that keeps growing, so a `DURATION=1.5` fade actually
  takes 7-8 seconds to drain, arriving in visible ~100ms steps the whole
  time. Klipper's only built-in user of this path, `display_template`,
  refreshes at a fixed 0.5s and never trips this.

**Fix implemented**: call the pin's `MCU_pwm.set_pwm(print_time, value)`
directly (same primitive `output_pin` itself calls, and the same style of
direct-MCU-queue write `neopixel.py` uses for color updates), bypassing
`GCodeRequestQueue` entirely. `set_pwm()` has no built-in throttle beyond
requiring a monotonically non-decreasing `clock`, which a real-time-driven
fade satisfies for free. Still use `mcu.min_schedule_time()` per call as the
lead-in margin (`estimated_print_time(eventtime + min_schedule_time())`) —
that's its actual intended purpose — just don't chain it into a minimum gap
between calls.

Trade-off to keep in mind if you touch this again: bypassing
`GCodeRequestQueue` means also bypassing its `pin.last_value` bookkeeping,
so `_update()` sets `pin.last_value` itself after every write. That value
feeds both `SET_PIN`'s status reporting (Mainsail/Fluidd brightness
display) and this plugin's own fade-restart logic (`state['start_value'] =
pin.last_value`), so don't drop that assignment if you refactor.

**Do not "fix" a future regression by reverting to `pin.gcrq.send_async_request()`** —
that's the bug this file was written to get away from, and it'll silently
reintroduce the backlog/stepping described above.

## Design intent worth preserving

- Keep it a single file, no external dependencies beyond stock Klipper —
  it's meant to symlink-install into `klippy/extras/` with nothing else.
- `[fade_light]` is a bare, parameterless, global-singleton config section
  by design — it should keep working for any `output_pin` name without
  per-pin config.
