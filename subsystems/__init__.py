"""Project-agnostic, reusable schgen subsystem library.

Each subsystems/<name>/ package declares its interface as ABSTRACT port + rail names
and is consumed by a project via a bind map (abstract -> real net). See
subsystems/usb_pd/ for the exemplar and its README.
"""
