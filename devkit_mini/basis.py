"""Declared values and bind decisions, each with a registered basis."""

from __future__ import annotations

from schgen.core.basis import Registry

UNITS = ("A", "C/W", "F", "H", "Hz", "V", "count", "i2c-addr", "net", "ohm",
         "part", "pin-map")

_BASIS = Registry(units=UNITS)
REGISTRY = _BASIS.entries
BINDS = _BASIS.binds
register = _BASIS.register
bind = _BASIS.bind
