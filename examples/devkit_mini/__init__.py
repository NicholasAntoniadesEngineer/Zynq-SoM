"""devkit_mini — a hypothetical mini baseboard that REUSES the library subsystems.

A second, independent consumer of the project-agnostic ``subsystems/`` library
(the real ``carrier/`` is the first). It binds the SAME library packages
(``usb_pd``, ``usbc_otg``, ``microsd``, ``uart_bridge``) to a DIFFERENT set of
project net names, proving the subsystems port unchanged. See README.md.
"""

from examples.devkit_mini.devkit_mini import (
    PROJECT,
    subsystem_circuits,
    usb_pd_circuit,
    usbc_otg_circuit,
    microsd_circuit,
    uart_bridge_circuit,
)

__all__ = [
    "PROJECT",
    "subsystem_circuits",
    "usb_pd_circuit",
    "usbc_otg_circuit",
    "microsd_circuit",
    "uart_bridge_circuit",
]
