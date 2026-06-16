"""pmod — carrier ADAPTER for the reusable 2x Digilent-Pmod host-port subsystem.

THIN ADAPTER. The portable circuit lives in the project-agnostic library
``subsystems/pmod/`` (netlist + README + SPICE + local test). This file is the
carrier-specific GLUE: it imports the library subsystem and BINDS its abstract
ports/rails to the carrier's real net names, returning the bound Circuit. The
board build discovers it exactly as before (``circuit()`` exposed here), and the
binding reproduces the EXACT same net names the hand-written sheet used, so the
emitted carrier/schematic/pmod.kicad_sch + its golden render are unchanged.

CARRIER BINDING RATIONALE (the carrier net names + why):

  +VCC_PMOD -> +3V3_PMOD   the bring-up-gated module rail (SY6280 #7 on
                           bringup_modules): a POWER net with its own symbol,
                           like +5V_USB. VCC pins feed from this gated rail with
                           100n + 10u per port (~100 mA budget per module per the
                           Pmod spec).
  GND       -> GND         (identity).

  The 16 host signals bind to J2 bank-13 nets, VERBATIM from
  carrier/som_interface.json (per carrier/research/debug_boot_pmod.md (d)). These
  are 8 full bank-13 LVDS-capable pairs from J2 (pairs kept intact, no MRCC/SRCC
  pins) — which REQUIRES +VCCO_13 = +3V3 in the rail map. NOTE: IO_L5P_13 has no
  underscore before P (SoM symbol quirk, do not "fix"):
    PMOD0_SIG1..8 -> IO_L2_P_13/IO_L2_N_13/IO_L3_P_13/IO_L3_N_13/
                     IO_L4_P_13/IO_L4_N_13/IO_L5P_13/IO_L5_N_13
    PMOD1_SIG1..8 -> IO_L7_P_13/IO_L7_N_13/IO_L8_P_13/IO_L8_N_13/
                     IO_L9_DQS_P_13/IO_L9_DQS_N_13/IO_L10_P_13/IO_L10_N_13

The 16 host signals bind on the generated J2 sheet (som_j2_connector); the
adapter declares that linker deferral via the library's ``expects`` hook, so a
standalone link reports them as awaiting-J2, never a silent open.
"""

from __future__ import annotations

from subsystems.pmod import pmod as _lib
from schgen.core.model import Circuit

# The SoM J2 bank-13 signals bind on the generated J2 connector sheet; EXPLICIT
# linker deferral so a standalone link reports them as awaiting-J2, never a
# silent open.
_J2_MAP = "som_j2_connector"

# The carrier J2 bank-13 net for each abstract host signal, VERBATIM from
# carrier/som_interface.json (see module docstring for the SoM-symbol quirks).
_PORT_NETS = {
    "PMOD0": ["IO_L2_P_13", "IO_L2_N_13", "IO_L3_P_13", "IO_L3_N_13",
              "IO_L4_P_13", "IO_L4_N_13", "IO_L5P_13", "IO_L5_N_13"],
    "PMOD1": ["IO_L7_P_13", "IO_L7_N_13", "IO_L8_P_13", "IO_L8_N_13",
              "IO_L9_DQS_P_13", "IO_L9_DQS_N_13", "IO_L10_P_13",
              "IO_L10_N_13"],
}

# The ONE standard adapter contract (schgen.core.subsystem.Meta) — the entire
# carrier-specific surface of this subsystem. Per-net rationale is in the module
# docstring above.
#   bind    abstract subsystem net -> carrier real net (rails + the 16 J2 signals)
#   expects every host signal -> the generated J2 connector sheet
#   notes   power-tree draw note keeps the carrier's house-style wording
META = {
    "bind": {
        "+VCC_PMOD": "+3V3_PMOD",
        "GND": "GND",
        **{f"{port}_SIG{io}": net
           for port, nets in _PORT_NETS.items()
           for io, net in enumerate(nets, start=1)},
    },
    "expects": {f"{port}_SIG{io}": _J2_MAP
                for port, nets in _PORT_NETS.items()
                for io in range(1, len(nets) + 1)},
    "notes": {"draws": "2x Pmod module budget ~100 mA each"},
}


def circuit() -> Circuit:
    return _lib.circuit(META)
