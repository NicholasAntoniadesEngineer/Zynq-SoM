"""lcd reusable subsystem (40-pin TTL RGB888 panel + SY7201 backlight + touch I2C)."""

from subsystems.lcd.lcd import circuit, INTERFACE, RAILS, PORTS

__all__ = ["circuit", "INTERFACE", "RAILS", "PORTS"]
