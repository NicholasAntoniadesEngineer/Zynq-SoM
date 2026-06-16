"""pd_input — carrier ADAPTER for the reusable USB-C PD power-inlet subsystem.

THIN ADAPTER. The portable circuit lives in the project-agnostic library
``subsystems/pd_input/`` (netlist + README + SPICE + local test). This file is the
carrier-specific GLUE: it imports the library subsystem and BINDS its abstract
ports/rails to the carrier's real net names, returning the bound Circuit. The
board build discovers it exactly as before (``circuit()`` exposed here), and the
binding reproduces the EXACT same net names the hand-written sheet used, so the
emitted carrier/schematic/pd_input.kicad_sch + its golden render are unchanged.

DESIGN BACKGROUND (PLAN round-2 locked: USB-C PD ONLY, 20 V / 3 A (60 W), no
barrel jack). This sheet is the receptacle plus the inlet eFuse; the FUSB302B PD
PHY lives on usb_pd (same nets), and power.py consumes +VIN.

  Receptacle TYPE-C-31-M-12 (LCSC C165948): 16 contacts, 5 A / 20 V rating —
  margin for the 20 V/3 A contract. Same part as the OTG port (usbc_otg.py).

  +VIN eFuse TPS26631PWPR (C2866319, TI, HTSSOP-20): TPS2663x family 4.5-60 V
  op / 67 V abs max, 6 A / 31 mohm FET, +/-2% adjustable OVP cutoff, dVdT slew,
  MODE-selectable latch/auto-retry (TI SLVSE94G). Sits BETWEEN the receptacle
  VBUS (+VBUS_IN) and the board bulk (+VIN) so the PD source never sees the
  board's capacitance slam.

eFuse strap design (every number from TI SLVSE94G — preserved here as the
carrier rationale; the netlist itself is in the library):
- IN (1-3) + IN_SYS (6) tied to +VBUS_IN; B_GATE (4) / DRV (5) author NC — a
  USB-C inlet cannot be reverse-wired, so no blocking FET (DS Fig 8-8).
- UVLO (7) -> IN_SYS, per DS 8.3.3 ("must be connected to IN_SYS" when unused):
  the internal 4.3 V/4.2 V POR governs, so the 5 V default VBUS PASSES.
  CRITICAL: +3V3_SC (FUSB302 + SC supply) is generated ON the SoM from VIN — an
  eFuse that blocked 5 V would deadlock PD negotiation forever.
- OVP (8): R3/R4 = 100k/5.49k from +VBUS_IN -> cutoff at V_OVPR x (105.49/5.49)
  = 1.2 V x 19.215 = 23.06 V typ. PD-1 FIX (deep audit): the prior 5.6k gave
  22.6 V typ with a trip-MIN of ~21.9 V (full comparator +/-2% + 1% resistor
  stack) — uncomfortably close to the 21.0 V legal contract max. 5.49k lifts
  trip-typ to 23.06 V (trip-MIN ~22.6 V, clear of 21 V) while the worst-case
  cutoff stays guaranteed BELOW the SMBJ22A VBR-min: at 24.4 V with R4 -1% /
  R3 +1% the divided node is 1.246 V > V_OVPR-max 1.224 V, so OVP definitely
  trips before the TVS conducts. (5.36 V fails this strict worst case at
  1.218 V < 1.224 V — 5.49k is the robust refinement.) Divider burns 190 uA.
- ILIM (11): R5 = 5.1k -> I_OL = 18/5.1k = 3.53 A typ (DS Eq 5, ~+/-8%:
  3.2-3.8 A) — above the 3.0 A contract so the PD source's own limit is reached
  first, far below the 6 A device ceiling. Fast-trip 3 x I_OL + 45 A SCP internal.
- dVdT (10): C3 = 47n -> constant output slew 1.02 V/ms. INRUSH: downstream
  +VIN bulk = C2 10u (here) + power.py 2x10u + ~0.3u HF ~= 30.3 uF; I_inrush
  = C x dV/dt ~= 31 mA — two decades under the 3 A contract. The 5->20 V
  contract step is source-slewed into 30 uF = 0.9 A peak < I_OL: no foldback.
- MODE (12) -> GND = AUTO-RETRY (DS 6.5): a transient inlet fault recovers
  without a human cycling SHDN#; every downstream stage is DIP-gated anyway.
- PGTH (16) -> GND: disables the fast-recovery resample (DS 8.3.2.1) so EVERY
  recovery ramps dVdT-controlled (PD-friendly); PGOOD (17) reads low, author NC.
- SHDN# (13) author NC (internal pull-up); IMON (14) author NC (+VIN telemetry
  is power_mon's INA3221 shunt); EP (21) + GND (9) to GND.

Inlet protection + bulk:
- D1 SMBJ22A (C10214): unidirectional 600 W TVS, 22 V standoff (> 20 V
  contract), VBR 24.4-26.9 V, clamp 35.5 V @ 16.9 A — hot-plug/surge clamp on
  +VBUS_IN, AHEAD of the eFuse (the eFuse's 67 V abs max rides out the residue).
  CC-line ESD intentionally omitted: the FUSB302B integrates CC ESD + usb_pd
  adds 200p filters.
- C2 10u 50 V X7R 1210 (C596319) + C1 100n 50 V (C14663): C1 stays at the inlet
  (DS-recommended >= 0.1 uF on IN); C2 moves BEHIND the eFuse onto +VIN as the
  first slice of the dVdT-charged board bulk. X7R @ 50 V for DC-bias honesty.

CARRIER BINDING RATIONALE (the carrier net names + why):

  +VBUS_CONN  -> +VBUS_IN  the RAW receptacle VBUS, AHEAD of the eFuse: TVS +
                           inlet 100n + the eFuse IN/IN_SYS/UVLO + OVP-top. The
                           usb_pd PHY binds its +VBUS_SENSE to this SAME net so
                           it observes vSafe5V/vbus at the connector for attach
                           detection (AMX-1: U1.2 there sits at its 21.0 V
                           recommended-max at the legal 20 V+5% contract).
  +VBUS_OUT   -> +VIN      the FUSED output: the dVdT-charged board bulk; power.py
                           consumes it.
  +VDD_LOGIC  -> +3V3_SC   the FLT# pull-up AND the USBLC6 data-ESD clamp rail.
                           +3V3_SC (FUSB302 + SC supply) is an ALWAYS-ON SoM rail,
                           alive whenever the SC can read the fault flag / the
                           data pair is active. R6 pulls FLT# to +3V3_SC, NOT
                           +VBUS_IN: a TCA9535 IO abs-max is VCC+0.5 = 3.8 V. The
                           USBLC6 pin 5 clamp rail must be a <=5.25 V rail (its
                           internal TVS is ~5.25 V standoff); tying it to the 20 V
                           inlet VBUS would hold that TVS in continuous avalanche
                           — destructive AND it defeats the data ESD (audit CRIT).
  GND         -> GND       (identity).
  CHASSIS_GND -> CHASSIS_GND  the connector-shell earth island (identity).

  CC1/CC2     -> STM32_USB_CC1/2   the receptacle CC lines, crossing to the
                           FUSB302B (usb_pd, same nets) and the SoM STM32 CC-sense.
  USB_D_P/N   -> STM32_USB_D_P/N   the FS data pair to the SoM FS PHY, POST the
                           USBLC6 ESD array (cable-flip paired, usb_hs_pair).
  FLT_N       -> PD_FLT_N  the eFuse open-drain fault -> SoM SC via TCA9535 P15
                           (bringup_rails, DEF-F). The TPS26631 is the board's
                           ONLY +VIN protection device; the flag binds on the
                           generated bring-up expander, declared via ``expects``.
"""

from __future__ import annotations

from subsystems.pd_input import pd_input as _lib
from schgen.core.model import Circuit

# The eFuse fault flag binds on the bring-up TCA9535 expander (bringup_rails,
# DEF-F: TCA9535 port P15). EXPLICIT linker deferral so a standalone link reports
# it as awaiting-bringup, never a silent open.
_EXPANDER = "bringup (TCA9535 expander port P15)"

# The ONE standard adapter contract (schgen.core.subsystem.Meta) — the entire
# carrier-specific surface of this subsystem. Per-net rationale is in the module
# docstring above.
#   bind    abstract subsystem net -> carrier real net (EXACT hand-sheet names)
#   expects the eFuse FLT_N binds on the generated bring-up expander -> deferral
# (pd_input declares no draws()/buses; it SOURCES rails rather than budgeting a
#  load, matching the original hand-written sheet.)
META = {
    "bind": {
        "+VBUS_CONN": "+VBUS_IN",
        "+VBUS_OUT": "+VIN",
        "+VDD_LOGIC": "+3V3_SC",
        "GND": "GND",
        "CHASSIS_GND": "CHASSIS_GND",
        "CC1": "STM32_USB_CC1",
        "CC2": "STM32_USB_CC2",
        "USB_D_P": "STM32_USB_D_P",
        "USB_D_N": "STM32_USB_D_N",
        "FLT_N": "PD_FLT_N",
    },
    "expects": {
        "FLT_N": _EXPANDER,
    },
}


def circuit() -> Circuit:
    return _lib.circuit(META)
