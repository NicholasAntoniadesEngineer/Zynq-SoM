"""pmod_expansion — carrier ADAPTER for the reusable manual-gated Pmod port.

THIN ADAPTER. The portable circuit lives in the project-agnostic library
``subsystems/pmod_expansion/`` (netlist + README + SPICE + local test). This file
is the carrier-specific GLUE: it imports the library subsystem and BINDS its
abstract ports/rails to the carrier's real net names, returning the bound
Circuit. The board build discovers it exactly as before (``circuit()`` exposed
here), and the binding reproduces the EXACT same net names the hand-written
sheet used, so the emitted carrier/schematic/pmod_expansion.kicad_sch + its
golden render are unchanged.

Stream-C C2. A single host-side Pmod port: 8 IO + 2x VCC(3.3 V) + 2x GND on a
right-angle 2x6 socket at the board edge, the 8 IO bound to genuinely-FREE
Zynq PL bank-13 pins, the 3.3 V it provides taken from a MANUALLY-GATED rail so
a powered-down peripheral is never back-fed (constraint C1).

CARRIER BINDING RATIONALE (the carrier net names + why):

  +VDD_PMOD  -> +3V3        the carrier SOURCES +VCCO_13 = +3V3 (som_conn_gen
                           VCCO_RAIL_MAP), so bank 13 runs LVCMOS33 and the
                           Pmod's 3.3 V level-safety is structural — no level
                           translation needed. The SY6280 load switch gates this
                           +3V3 input.
  +VSW_PMOD  -> +3V3_PMODX  the MANUALLY-GATED output rail the port provides.
                           Default-OFF (constraint C1: "a manual power enable
                           like the previous"): the SY6280's enable is LOCAL —
                           SW1 (DSHP04 pos 1) closes +3V3 onto EN_PMODX and a
                           100k pulldown holds it low until a human flips the
                           switch. So a peripheral that is itself unpowered
                           (its own 3V3 down) cannot be back-fed from this port,
                           AND the port is dark at power-up until enabled.
  GND        -> GND        (identity).

  PMODX_IO1/2 = IO_L13_MRCC_P/N_13  (J2.29/27)
  PMODX_IO3/4 = IO_L23_P/N_13       (J2.33/31)
  PMODX_IO5/6 = IO_L14_P/N_SRCC_13  (J2.41/39)
  PMODX_IO7/8 = IO_L12_MRCC_P/N_13  (J2.49/47)

  PMOD_IO1..8 -> PMODX_IO1..8   the eight FREE bank-13 PL function nets
                           (som_conn_gen.FUNCTION_MAP), verified free vs every
                           existing subsystem + the wave-3 FUNCTION_MAP before
                           claiming (they read "unclaimed (wave-3 function map)"
                           in the prior XDC, used by NO other sheet). None of
                           L12/L13/L14 lose their MRCC/SRCC clock capability
                           (Pmod IO is plain GPIO). The som_j2 connector sheet
                           renames each raw contract net to the PMODX_IO*
                           function port, so these ports bind J2<->this sheet
                           and the XDC constrains each ball automatically.

These ports bind on the generated J2 sheet (som_conn_gen FUNCTION_MAP), so the
adapter declares that linker deferral via the library's ``expects`` hook.
"""

from __future__ import annotations

from subsystems.pmod_expansion import pmod_expansion as _lib
from schgen.core.model import Circuit

# The generated J2 sheet (som_conn_gen FUNCTION_MAP) carries the PL bank-13
# function map (+VCCO_13=+3V3, LVCMOS33), so these ports bind there by name.
# EXPLICIT linker deferral so a standalone link reports them as awaiting-J2,
# never a silent open.
_J2_MAP = "som_j2_connector (PL bank 13, +VCCO_13=+3V3, LVCMOS33)"

# The ONE standard adapter contract (schgen.core.subsystem.Meta) — the entire
# carrier-specific surface of this subsystem. Per-net rationale is in the module
# docstring above.
#   bind    abstract subsystem net -> carrier real net
#   expects each Pmod IO binds on the generated J2 sheet -> explicit deferral
#   notes   power-tree draw note restores the carrier's house-style wording
META = {
    "bind": {
        "+VDD_PMOD": "+3V3",
        "+VSW_PMOD": "+3V3_PMODX",
        "GND": "GND",
        "PMOD_IO1": "PMODX_IO1",
        "PMOD_IO2": "PMODX_IO2",
        "PMOD_IO3": "PMODX_IO3",
        "PMOD_IO4": "PMODX_IO4",
        "PMOD_IO5": "PMODX_IO5",
        "PMOD_IO6": "PMODX_IO6",
        "PMOD_IO7": "PMODX_IO7",
        "PMOD_IO8": "PMODX_IO8",
    },
    "expects": {
        "PMOD_IO1": _J2_MAP, "PMOD_IO2": _J2_MAP,
        "PMOD_IO3": _J2_MAP, "PMOD_IO4": _J2_MAP,
        "PMOD_IO5": _J2_MAP, "PMOD_IO6": _J2_MAP,
        "PMOD_IO7": _J2_MAP, "PMOD_IO8": _J2_MAP,
    },
    "notes": {"draws_pmod": "1x Pmod module budget ~100 mA (Digilent spec) "
                            "+ status LED"},
}


def circuit() -> Circuit:
    return _lib.circuit(META)
