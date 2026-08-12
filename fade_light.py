# Smooth fade support for output_pin objects (e.g. plain 24V LED strips
# that are not addressable/neopixel-capable).
#
# Copyright (C) 2026 bincat233
#
# This file may be distributed under the terms of the GNU GPLv3 license.
#
# output_pin only supports instant value jumps via SET_PIN. This module
# adds a FADE_LIGHT command that ramps an existing [output_pin NAME] to a
# target value over a duration, using a Klipper reactor timer for
# non-blocking, tunable-precision updates (bypasses the G-code queue and
# the 0.5s-fixed update interval of the built-in SET_PIN ... TEMPLATE=
# mechanism).
#
# Usage: FADE_LIGHT PIN=<output_pin name> TARGET=<0.0-1.0>
#            [DURATION=<seconds, default 1.0>]
#            [EASING=<linear|ease_in|ease_out|ease_in_out, default linear>]
#            [GAMMA=<exponent, default 1.0 (no correction)>]
#
# EASING shapes how fade progress moves through time (e.g. ease_in_out
# starts and ends slow, speeds up in the middle) - this is a timing/pacing
# effect, independent of brightness.
#
# GAMMA compensates for the eye's non-linear brightness perception: a
# plain linear PWM ramp looks like it rushes through the dim end and
# lingers at the bright end, because perceived brightness is roughly a
# power-law function of physical output. Applying VALUE = t**GAMMA (with
# GAMMA around 2.2-2.8, the common display/LED convention) makes the
# fade look more evenly paced to the eye. This is applied to the fade's
# progress (0..1), not to absolute physical brightness, so it is most
# accurate for fades that span the full 0..1 range; it is still a
# reasonable approximation for partial-range fades.
#
# Install: symlink this file into ~/klipper/klippy/extras/fade_light.py,
# then add a bare [fade_light] section to printer.cfg.
#
# Talks to the pin's MCU_pwm.set_pwm() directly instead of going through
# output_pin's GCodeRequestQueue - the same approach neopixel.py uses to
# push color updates straight onto the MCU command queue. That queue's
# send_async_request() enforces a MIN_SCHEDULE_TIME (0.100s) *between*
# successive requests on the same pin, meant to guard generic/unbounded
# async triggers (e.g. a runaway display_template); at fade update rates
# that floor doesn't limit the rate so much as make requests back up and
# have their execution time pushed further into the future each call,
# so the fade drags out past DURATION in visible ~100ms steps. set_pwm()
# itself has no such floor - it only requires a monotonically-increasing
# clock, which a real-time-driven fade already provides - so we still use
# min_schedule_time() as the one-shot lead-in margin each call needs to
# reach the MCU in time (its original purpose), just without chaining it
# into a minimum gap between calls.
FADE_UPDATE_INTERVAL = 0.02  # 50Hz

EASINGS = {
    'linear': lambda t: t,
    'ease_in': lambda t: t * t,
    'ease_out': lambda t: 1.0 - (1.0 - t) * (1.0 - t),
    'ease_in_out': lambda t: (2.0 * t * t if t < 0.5
                               else 1.0 - ((-2.0 * t + 2.0) ** 2) / 2.0),
}


class FadeLight:
    def __init__(self, config):
        self.printer = config.get_printer()
        self.reactor = self.printer.get_reactor()
        self.fades = {}
        gcode = self.printer.lookup_object('gcode')
        gcode.register_command('FADE_LIGHT', self.cmd_FADE_LIGHT,
                                desc=self.cmd_FADE_LIGHT_help)

    cmd_FADE_LIGHT_help = "Smoothly fade an output_pin to a target value"

    def cmd_FADE_LIGHT(self, gcmd):
        pin_name = gcmd.get('PIN')
        target = gcmd.get_float('TARGET', minval=0., maxval=1.)
        duration = gcmd.get_float('DURATION', 1.0, above=0.)
        gamma = gcmd.get_float('GAMMA', 1.0, above=0.)
        easing_name = gcmd.get('EASING', 'linear')
        easing_fn = EASINGS.get(easing_name)
        if easing_fn is None:
            raise gcmd.error(
                "Unknown EASING '%s', must be one of: %s"
                % (easing_name, ', '.join(sorted(EASINGS))))
        pin = self.printer.lookup_object('output_pin ' + pin_name, None)
        if pin is None:
            raise gcmd.error("Unknown output_pin '%s'" % (pin_name,))
        eventtime = self.reactor.monotonic()
        state = self.fades.get(pin_name)
        if state is None:
            state = {'timer': self.reactor.register_timer(
                lambda et, pn=pin_name: self._update(pn, et))}
            self.fades[pin_name] = state
        state['pin'] = pin
        state['start_value'] = pin.last_value
        state['target_value'] = target
        state['start_time'] = eventtime
        state['duration'] = duration
        state['gamma'] = gamma
        state['easing'] = easing_fn
        self.reactor.update_timer(state['timer'], self.reactor.NOW)

    def _update(self, pin_name, eventtime):
        state = self.fades[pin_name]
        t_raw = (eventtime - state['start_time']) / state['duration']
        done = t_raw >= 1.0
        t_raw = min(max(t_raw, 0.0), 1.0)
        t = state['easing'](t_raw)
        if state['gamma'] != 1.0:
            t = t ** state['gamma']
        value = (state['start_value']
                 + (state['target_value'] - state['start_value']) * t)
        pin = state['pin']
        if value != pin.last_value:
            mcu = pin.mcu_pin.get_mcu()
            print_time = mcu.estimated_print_time(
                eventtime + mcu.min_schedule_time())
            pin.mcu_pin.set_pwm(print_time, value)
            pin.last_value = value
        if done:
            return self.reactor.NEVER
        return eventtime + FADE_UPDATE_INTERVAL


def load_config(config):
    return FadeLight(config)
