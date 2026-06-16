"""power — carrier ADAPTER for the reusable multi-rail regulator-tree subsystem.

THIN ADAPTER. The portable circuit lives in the project-agnostic library
``subsystems/power/`` (netlist + README + SPICE + local test). This file is the
carrier-specific GLUE: it imports the library subsystem and BINDS its abstract
ports/rails to the carrier's real net names, returning the bound Circuit. The
board build discovers it exactly as before (``circuit()`` exposed here), and the
binding reproduces the EXACT same net names the hand-written sheet used, so the
emitted carrier/schematic/power.kicad_sch + its golden render are unchanged.

The carrier rail tree: +VIN(20V) -> +5V buck -> +3V3 buck -> +1V8 LDO. (The
always-on +5V_SOM buck (U4, P0 fix) + the INA3221 rail current-monitor + its
series shunts RS1..RS4 are SEPARATE carrier sheets — power_som.py / power_mon.py —
NOT part of this subsystem.) U1 (LM61460) keeps its lib_id="schgen:LM61460"
override (a PENDING hand-built-symbol migration, symbol_law.PENDING_MIGRATION);
the library preserves it verbatim — a separate deep-engine task owns that symbol.

WT/BUCK RE-SPEC (2026-06-14): the +5V buck U1 — the board's heaviest converter
(2.95 A @ 5 V) — was the LMR33630ADDA (3 A), running at 98% of rating with no
headroom and a Tj over the gate guard band (waived). U1 is RE-SPEC'd to the
LM61460AANRJRR: TI 3-42 V / 6-A low-EMI SYNCHRONOUS buck (SNVSBD5D), VQFN-HR
(RJR "HotRod"), LCSC C2864505 (JLC 2026-06-14: Extended, stock 3,761). 6 A ->
~2x current margin over 2.95 A; Vin op-max 36 V (abs 42 V) covers the 21 V
+VIN_SYS rail. The thermal gate now credits a CONSERVATIVE pour-aware effective
RthJA (30 C/W vs 58.7 bare; DS 7.3 4-layer = 25 C/W) so U1 PASSES on real
thermal margin (Tj ~128 C < 140 C guard) — NO waiver. See the stage-1 block +
thermal.py pour-aware-RthJA docs. (TPS54302 U2 keeps its no-EP waiver.)

PLAN round-2 locked: USB-C PD supplies +VIN (20 V); the carrier generates
+5V (buck from VIN), +3V3 (buck from +5V) and +1V8 (LDO from +3V3). Every
rail has an EN port (driven by the bringup subsystem's DIP-AND-STM32 enable
cells, ports EN_5V0 / EN_3V3 / EN_1V8 per the bringup dossier contract) and
a power-good LED.

CARRIER BINDING RATIONALE (the carrier net names + why):

  +VIN          -> +VIN_SYS   DEF-D: U1 input is the POST-shunt rail +VIN_SYS
                              (RS1 series-inserts between the eFuse +VIN and the
                              buck inputs in power_mon.py), so the buck input
                              current — including the input-cap ripple/inrush —
                              flows through RS1 and is counted on the U1 ch1
                              (+VIN) channel. The input caps move with it.
  +VOUT_5V_REG  -> +5V_REG    DEF-D: buck-1 OUTPUT cluster (the inductor node,
                              output bulk caps, FB sense, BIAS tie + the PG LED)
                              is the reg-side of RS2; RS2 bridges +5V_REG -> +5V
                              so consumer draw is measured.
  +VOUT_5V      -> +5V        the board +5V rail (post-RS2) carries the measured
                              consumers (U2 input, C7/C8).
  +VOUT_3V3_REG -> +3V3_REG   DEF-D: buck-2 OUTPUT cluster, reg-side of RS3.
  +VOUT_3V3     -> +3V3       the board +3V3 rail (post-RS3); U2's INPUT stays
                              the board +5V — it is a +5V consumer (RS2). The
                              LDO input cap C12 + the +1V8 PG LED anode sit here.
  +VOUT_1V8_REG -> +1V8_REG   DEF-D: LDO OUTPUT, reg-side of RS4.
  +VOUT_1V8     -> +1V8       the board +1V8 rail (post-RS4) the loads see.
  GND           -> GND        (identity; also the LM61460 heat path).

  EN_VOUT_5V  -> EN_5V0       buck/LDO enables driven by the bringup subsystem's
  EN_VOUT_3V3 -> EN_3V3       wave-2 rail-enable cells (DIP-AND-STM32), dossier
  EN_VOUT_1V8 -> EN_1V8       section 3.1; they bind on the bringup sheets, so
                              the adapter declares that linker deferral via the
                              library's ``expects`` hook.

The INTERNAL SIGNAL nets (the LM61460 SW/FB/BOOT/BIAS/VCC/RT + the +3V3 buck
SW/FB/BOOT + the PG-LED cathode/FET-gate nodes) stay VERBATIM in the library —
they are private regulator wiring, NEVER bound.
"""

from __future__ import annotations

from subsystems.power import power as _lib
from schgen.core.model import Circuit

# The rail enables bind on the bringup sheets (wave-2 DIP-AND-STM32 enable cells,
# dossier section 3.1). EXPLICIT linker deferral so a standalone link reports
# them as awaiting-bringup, never a silent open.
_BRINGUP = "bringup (wave 2 rail-enable cells, dossier section 3.1)"

# The ONE standard adapter contract (schgen.core.subsystem.Meta) — the entire
# carrier-specific surface of this subsystem. Per-net rationale is in the module
# docstring above.
#   bind    abstract subsystem net -> carrier real net (ALL external rails+ports)
#   expects the EN ports bind on the bringup sheets -> explicit linker deferral
#   notes   the power-tree draw notes use the carrier's exact dossier wording so
#           carrier/reports/power_tree.txt stays byte-identical to the hand sheet
META = {
    "bind": {
        "+VIN": "+VIN_SYS",
        "+VOUT_5V_REG": "+5V_REG",
        "+VOUT_5V": "+5V",
        "+VOUT_3V3_REG": "+3V3_REG",
        "+VOUT_3V3": "+3V3",
        "+VOUT_1V8_REG": "+1V8_REG",
        "+VOUT_1V8": "+1V8",
        "GND": "GND",
        "EN_VOUT_5V": "EN_5V0",
        "EN_VOUT_3V3": "EN_3V3",
        "EN_VOUT_1V8": "EN_1V8",
    },
    "expects": {
        "EN_VOUT_5V": _BRINGUP,
        "EN_VOUT_3V3": _BRINGUP,
        "EN_VOUT_1V8": _BRINGUP,
    },
    "notes": {
        "draws_5v": "PG LED (KT-0603R + 1k, ~3 mA) + FB divider 60 uA",
        "draws_3v3": ("PG LED (330R ~3.9 mA) + 1V8 PG sense LED chain "
                      "(330R ~3.9 mA) + FB divider 27 uA"),
        "draws_1v8": "PG FET gate divider 10k+100k (16 uA), rounded up",
    },
}


def circuit() -> Circuit:
    return _lib.circuit(META)
