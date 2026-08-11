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
# Usage: FADE_LIGHT PIN=<output_pin name> TARGET=<0.0-1.0> [DURATION=<seconds, default 1.0>]
#
# Install: symlink this file into ~/klipper/klippy/extras/fade_light.py,
# then add a bare [fade_light] section to printer.cfg.

FADE_UPDATE_INTERVAL = 0.02  # 50Hz


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
        self.reactor.update_timer(state['timer'], self.reactor.NOW)

    def _update(self, pin_name, eventtime):
        state = self.fades[pin_name]
        t = (eventtime - state['start_time']) / state['duration']
        if t >= 1.0:
            state['pin'].gcrq.send_async_request(state['target_value'])
            return self.reactor.NEVER
        value = (state['start_value']
                 + (state['target_value'] - state['start_value']) * t)
        state['pin'].gcrq.send_async_request(value)
        return eventtime + FADE_UPDATE_INTERVAL


def load_config(config):
    return FadeLight(config)
