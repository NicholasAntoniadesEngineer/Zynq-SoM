"""pd_input — USB-C PD power inlet: receptacle + TPS26631 eFuse (GAP #1 +
PLAN round-5 VBUS pre-contract decision).

PLAN round-2 locked: USB-C PD ONLY, 20 V / 3 A (60 W), no barrel jack. This
sheet is the receptacle plus the inlet eFuse; the FUSB302B PD PHY lives on
usb_pd (same nets), and power.py consumes +VIN.

Receptacle: TYPE-C-31-M-12 (LCSC C165948 — LIVE-verified 2026-06-11:
stock 191,682, Extended; LCSC detail API attributes: Current Rating 5 A,
Voltage Rating 20 V, 16 contacts) — adequate margin for the 20 V/3 A
contract. Same part as the OTG port (usbc_otg.py), so one connector reel.

+VIN eFuse — TPS26631PWPR (PLAN round 5; LIVE-verified on the JLC parts API
2026-06-12: C2866319, genuine TI, HTSSOP-20, stock 207, Extended,
$4.56 @ qty 1). TPS2663x family: 4.5-60 V operating / 67 V abs max, 6 A /
31 mohm integrated FET, +/-2% adjustable OVP CUTOFF, dVdT output slew
control, 2x pulse-overcurrent support, MODE-selectable latch/auto-retry
(TI SLVSE94G). Sits BETWEEN the receptacle VBUS (+VBUS_IN) and the board
bulk (+VIN), so the PD source never sees the board's capacitance slam.
  Why not the suggested families: TPS25940 (18 V op / 20 V abs) and
  TPS2596 (19 V op / 20 V abs) leave ZERO headroom on a 20 V contract
  rail; TPS25982 (24 V) is 20-150 deep at JLC; TPS2662x tops out at
  2.23 A < the 3 A contract. Alternates (live 2026-06-12): TPS26631PWPT
  C2832195 (stock 205, reel sibling), TPS26631RGER C1850273 (69, QFN24),
  Tokmas TPS26630RGER clone C52940996 (2,830 — clone AND the latch-off
  sibling: last-resort only).

eFuse strap design (every number from TI SLVSE94G; section refs cited):
- IN (1-3) + IN_SYS (6) tied to +VBUS_IN; B_GATE (4) / DRV (5) author NC —
  a USB-C inlet cannot be reverse-wired, so no blocking FET (DS Fig 8-8).
- UVLO (7) -> IN_SYS, per DS 8.3.3 ("must be connected to IN_SYS" when
  unused, never floating): the internal 4.3 V/4.2 V POR governs, so the
  5 V default VBUS PASSES. CRITICAL: +3V3_SC (FUSB302 + SC supply) is
  generated ON the SoM from VIN — an eFuse that blocked 5 V would
  deadlock PD negotiation forever.
- OVP (8): R3/R4 = 100k/5.49k from +VBUS_IN (R3 JLC Basic C25803; R4
  live-verified on the JLC parts API 2026-06-13: C188263 YAGEO
  RC0603FR-075K49L, 0603 1%, stock 5,046, Extended, min-qty 1 — alternate
  C3000723 FOJAN FRC0603F5491TS, 26,183) -> cutoff at V_OVPR x (105.49/
  5.49) = 1.2 V x 19.215 = 23.06 V typ. PD-1 FIX (deep audit 2026-06-12):
  the prior 5.6k gave 22.6 V typ with a trip-MIN of ~21.9 V (full
  comparator +/-2% + 1% resistor stack) — uncomfortably close to the 21.0 V
  legal contract max. 5.49k lifts trip-typ to 23.06 V (trip-MIN ~22.6 V,
  clear of 21 V) while the worst-case cutoff stays guaranteed BELOW the
  SMBJ22A VBR-min: at 24.4 V with R4 -1% / R3 +1% the divided node is
  1.246 V > V_OVPR-max 1.224 V, so OVP definitely trips before the TVS
  conducts. (5.36 V was the audit's first cut but it fails this strict
  worst case at 1.218 V < 1.224 V — 5.49k is the robust refinement.) Well
  under the TPS54302 30 V VIN abs-max either way. Divider burns 20 V/
  105.49k = 190 uA.
- ILIM (11): R5 = 5.1k (Basic C23186) -> I_OL = 18/5.1k = 3.53 A typ
  (DS Eq 5, ~+/-8%: 3.2-3.8 A) — above the 3.0 A contract so the PD
  source's own limit is reached first, far below the 6 A device ceiling.
  Fast-trip at 3 x I_OL and 45 A SCP are internal (DS 6.5).
- dVdT (10): C3 = 47n (Basic C1622) -> t_dVdT = 20.8e3 x V_IN x C
  (DS Eq 2) = 4.9 ms at 5 V / 19.6 ms at 20 V, i.e. a CONSTANT output
  slew of 1/(20.8e3 x 47n) = 1.02 V/ms. INRUSH MATH (the round-4
  pre-contract audit, now closed): downstream +VIN bulk = C2 10u (here)
  + power.py 2x10u + ~0.3u HF = 30.3 uF nominal; I_inrush = C x dV/dt
  = 30.3 uF x 1.02 V/ms ~= 31 mA — two decades under the 3 A contract
  and well under the 0.4 A remedy-A target. Pre-contract the source now
  sees ONLY C1 = 100n at the receptacle (<< the ~10 uF cSnkBulk
  guidance); the 30 uF board bulk hides behind the eFuse and only
  matters post-contract (sinks may present ~100 uF after an explicit
  contract). The 5->20 V contract step is source-slewed (<= 30 mV/us)
  into 30 uF = 0.9 A peak < I_OL: no foldback.
- MODE (12) -> GND = AUTO-RETRY (DS 6.5 MODE_SEL): a transient inlet
  fault recovers without a human cycling SHDN#; every downstream stage
  is individually DIP-gated anyway (bring-up architecture).
- PGTH (16) -> GND: disables the fast-recovery resample (DS 8.3.2.1) so
  EVERY recovery ramps dVdT-controlled — the PD-friendly behaviour;
  PGOOD (17) then reads low and is author NC (unused).
- SHDN# (13) author NC (internal pull-up, open-circuit 2.7 V typ, DS
  6.5); IMON (14) author NC (+VIN telemetry is power_mon's INA3221 RS1
  shunt); FLT# (15) author NC (open-drain, unused). EP (21) + GND (9)
  to GND (EP for heat sinking, not the only GND connection — DS 5-1).

Inlet protection + bulk (LIVE-verified on the JLC parts API 2026-06-11):
- D1 SMBJ22A (C10214, RUILON, stock 4,499, Ext): unidirectional 600 W TVS,
  22 V standoff (> 20 V contract), VBR 24.4-26.9 V, clamp 35.5 V @ 16.9 A —
  hot-plug/surge clamp on +VBUS_IN, AHEAD of the eFuse (the eFuse's 67 V
  abs max rides out what the TVS lets through). CC-line ESD intentionally
  omitted: the FUSB302B integrates CC ESD protection and usb_pd adds 200p
  filters; a TPD2EUSB30-class array remains a stuffing option if EMC
  testing demands.
- C2 10u 50 V X7R 1210 (C596319, YAGEO CC1210KKX7R9BB106, stock 13,618,
  Ext) + C1 100n 50 V (C14663): C1 stays at the inlet (the DS-recommended
  >= 0.1 uF on IN); C2 moves BEHIND the eFuse onto +VIN as the first
  slice of the dVdT-charged board bulk. X7R @ 50 V rating chosen for
  DC-bias honesty on a 20 V rail.
"""

from __future__ import annotations

from schgen.core.model import Circuit

C0603 = "Capacitor_SMD:C_0603_1608Metric"
C1210 = "Capacitor_SMD:C_1210_3225Metric"
R0603 = "Resistor_SMD:R_0603_1608Metric"
TVS_FP = "Diode_SMD:D_SMB"

USB_PD_SHEET = "usb_pd (FUSB302B CC PHY)"
J1_MAP = "som_j1_connector (STM32 USB FS + CC sense)"


def circuit() -> Circuit:
    c = Circuit("pd_input", "Power inlet: USB-C PD 20V/3A + TPS26631 eFuse")
    c.use_part("TYPE-C-31-M-12", ref="J1")
    c.use_part("TPS26631PWPR", ref="U1")
    c.use_part("USBLC6-2SC6", ref="U2")        # FS data-pair ESD array

    # ---- receptacle VBUS -> +VBUS_IN: TVS + the DS-minimum inlet 100n -----
    c.part("C1", "Device:C", "100n", C0603, LCSC="C14663")
    c.part("D1", "Device:D_Zener", "SMBJ22A", TVS_FP, LCSC="C10214")
    c.net("+VBUS_IN", "J1.VBUS", "C1.1", "D1.1",       # both stacked pads
          "U1.IN", "U1.IN_SYS", "U1.UVLO")             # UVLO unused -> IN_SYS
    c.net("GND", "J1.GND", "C1.2", "D1.2")             # both stacked pads
    c.nc("U1.B_GATE", "U1.DRV")          # no reverse-blocking FET (Fig 8-8)

    # ---- eFuse straps: OVP divider, ILIM, dVdT, MODE/PGTH ------------------
    c.part("R3", "Device:R", "100k", R0603, LCSC="C25803")
    c.part("R4", "Device:R", "5.49k", R0603, LCSC="C188263")   # PD-1: widen OVP
    c.net("PD_OVP_SET", "U1.OVP", "R3.2", "R4.1")      # trip 23.06 V typ
    c.net("+VBUS_IN", "R3.1")
    c.part("R5", "Device:R", "5.1k", R0603, LCSC="C23186")
    c.net("PD_ILIM_SET", "U1.ILIM", "R5.1")            # I_OL = 18/5.1k = 3.5 A
    c.part("C3", "Device:C", "47n", C0603, LCSC="C1622")
    c.net("PD_DVDT", "U1.dVdT", "C3.1")                # slew 1.02 V/ms
    c.net("GND", "U1.GND", "U1.EP", "U1.MODE",         # MODE=GND: auto-retry
          "U1.PGTH",                                   # PGTH=GND: dVdT-only
          "R4.2", "R5.2", "C3.2")
    c.nc("U1.SHDN#", "U1.IMON", "U1.PGOOD")            # unused per DS
    # FLT# (open-drain fault) -> SoM SC via TCA9535 P15 (PD_FLT_N — bringup_rails,
    # DEF-F). The TPS26631 is the board's ONLY +VIN protection device; its fault
    # flag was author-NC (blind). Pull-up to +3V3_SC, NOT +VBUS_IN: a TCA9535 IO
    # abs-max is VCC+0.5 = 3.8 V, and +3V3_SC is alive whenever the SC can read
    # the flag (mirrors the usbc_otg R3 re-rail; wave3_function_map G4).
    c.part("R6", "Device:R", "100k", R0603, LCSC="C25803")
    c.port("PD_FLT_N", "U1.FLT#", "R6.2",
           expect="bringup (TCA9535 expander port P15)")
    c.net("+3V3_SC", "R6.1")

    # ---- eFuse OUT -> +VIN: the dVdT-charged board bulk starts here --------
    c.part("C2", "Device:C", "10u", C1210, LCSC="C596319")   # 50V X7R
    c.net("+VIN", "U1.OUT", "C2.1")
    c.net("GND", "C2.2")

    # ---- CC lines to the FUSB302B (usb_pd sheet) + SoM STM32 ---------------
    c.port("STM32_USB_CC1", "J1.CC1")
    c.port("STM32_USB_CC2", "J1.CC2")

    # ---- FS data to the STM32 (device/dual-role port), cable-flip paired ---
    # PD-USB-DATA-NO-ESD FIX: the FUSB302B only protects the CC lines; the data
    # pair reached the SoM FS PHY with no ESD. Insert a USBLC6-2SC6 array at the
    # receptacle, exactly like usbc_otg: connector pads on one channel I/O (1/3),
    # PHY-side on that channel's other pin (6/4), VBUS->pin5, GND->pin2.
    c.net("PD_USB_DP_CONN", "J1.DP1", "J1.DP2", "U2.1")   # both flip pads -> ESD
    c.net("PD_USB_DN_CONN", "J1.DN1", "J1.DN2", "U2.3")
    c.port("STM32_USB_D_P", "U2.6")                       # PHY-side, post-ESD
    c.port("STM32_USB_D_N", "U2.4")
    c.port_type("STM32_USB_D_P", kind="usb_hs_pair", pair_with="STM32_USB_D_N")
    # ESD clamp rail = +3V3_SC, NOT the 20 V inlet VBUS. The USBLC6-2SC6 pin 5
    # is the VBUS-referenced rail clamp: an internal TVS pin5->GND with ~5.25 V
    # standoff / ~6 V breakdown. The protected pair is the STM32 USB FS data
    # (3.3 V domain), so the clamp must reference a <=5.25 V rail that is alive
    # whenever the SC's USB is active — +3V3_SC (always-on SC rail, present on
    # this sheet), matching the lcd/board_qwiic USBLC6 precedent. Tying pin 5 to
    # +VBUS_IN (20 V PD contract) would hold that internal TVS in continuous
    # avalanche — destructive AND it defeats the data ESD function (audit CRIT).
    c.net("+3V3_SC", "U2.5")
    c.net("GND", "U2.2")

    # ---- SBU unused; shell to chassis (usbc_otg pattern) -------------------
    c.nc("J1.SBU1", "J1.SBU2")
    c.net("CHASSIS_GND", "J1.EH")                        # all four shell pads

    # round-4 coverage gate: probe the raw inlet AND the fused rail — the
    # first bring-up question is "is the fault before or after the eFuse?"
    c.testpoint("+VBUS_IN")
    c.testpoint("+VIN")
    c.waive_tp("CHASSIS_GND", "chassis island is probeable at every "
               "connector shell tab (USB-C/HDMI/magjack); no pad needed")
    return c
