"""bringup_modules — per-module power gates + status/user LEDs
(carrier/research/bringup_power_gating.md sections 3.2, 3.3, 3.4).

Stage-3 bring-up: EVERY module is individually power-gated so a fault is
isolated by eye — a SY6280AAC load switch per module with a PROGRAMMABLE
current limit (ILIM = 6800/RSET; constant-current foldback, OTP, reverse
blocking): a shorted module folds back at its own limit instead of dragging
+3V3 down for everything else, and that one module's status LED sags and
points at the fault. SY6280AAC pinout (SOT-23-5, Silergy DS):
1=OUT 2=GND 3=ISET 4=EN 5=IN.

Switch table (dossier 3.2 — RSET on verified JLC-Basic E-series values;
rows 9-10 are the PLAN round-5 5 V module gates: +5V_HDMI_TX / +5V_LCD
were UNSOURCED power-tree findings, resolved by gating them from +5V
exactly like every other module):

  #  module      IN    OUT (gated rail)  RSET            limit
  1  HDMI TX     +3V3  +3V3_HDMI_TX      13k  (C22797)   523 mA
  2  HDMI RX     +3V3  +3V3_HDMI_RX      13k             523 mA
  3  LCD         +3V3  +3V3_LCD          6.8k (C23212)   1.0 A
  4  Camera      +3V3  +3V3_CAM          13k             523 mA
  5  microSD     +3V3  +3V3_SD           6.8k            1.0 A
  6  USB VBUS    +5V   +5V_USB           6.8k            1.0 A
  7  PMOD        +3V3  +3V3_PMOD        13k             523 mA
  8  User LEDs   +3V3  +3V3_USER_LED     13k             523 mA
  9  HDMI TX 5V  +5V   +5V_HDMI_TX       13k             523 mA
 10  LCD BL 5V   +5V   +5V_LCD           6.8k            1.0 A

ILIM sizing for the round-5 rows (ILIM = 6800/RSET, Silergy DS):
  * +5V_LCD: budget 450 mA (SY7201 boost input at the 133 mA LED operating
    point + margin, lcd_backlight.md) -> 6.8k = 1.0 A, the same
    budget-to-limit step as the 500 mA +5V_USB row.
  * +5V_HDMI_TX: budget 55 mA — but that load is already hard-limited
    INSIDE the TPD12S016 (its 5V_OUT switch limits at 55 mA, DS 7.3.10);
    the SY6280 limit only backstops a board-level fault on the rail trace.
    13k = 523 mA is the smallest dossier-verified RSET setting (the
    dossier deliberately stays on verified Basic E-values rather than
    introducing new high-RSET points outside the DS application range).

Every EN comes from its bringup_en AND-cell (push-pull 3.3 V — EN never
floats). 100 nF on each switch input and output (module subsystems own
their own bulk). Per-module status LED: KT-0603R red + 330R on each gated
3V3 output, 1k on the 5 V outputs (~3-4 mA). The gated rails are POWER
nets — module sheets (hdmi_tx, hdmi_rx, lcd, ...) consume them by name.

Stage-2 user IO: 4x LTST-C190KFKT yellow LEDs (visually distinct from the
red infrastructure LEDs; do NOT "upgrade" to green InGaN — Vf~3.1 V is
marginal on 3.3 V, dossier risk R4), anodes bused on +3V3_USER_LED (switch
#8), cathode -> 330R -> PL pin, ACTIVE-LOW (~3.9 mA, fine for a 3.3 V
LVCMOS bank pin). Final PL pin assignment is the P3 linker's job — this
sheet publishes the PL_LED0..3 sink ports.
"""

from __future__ import annotations

from schgen.core.model import Circuit

R_FP = "Resistor_SMD:R_0603_1608Metric"
C_FP = "Capacitor_SMD:C_0603_1608Metric"
LED_FP = "LED_SMD:LED_0603_1608Metric"

LCSC_13K = "C22797"        # 0603 13k -> 523 mA
LCSC_6K8 = "C23212"        # 0603 6.8k -> 1.0 A
LCSC_330R = "C23138"
LCSC_1K = "C21190"
LCSC_100N = "C14663"
LCSC_RED = "C2286"         # KT-0603R (JLC Basic)
LCSC_YEL = "C157740"       # LTST-C190KFKT yellow

EXPECT_EN = "bringup_en (EN AND-gate cells, dossier section 3.2)"
J12_MAP = "som_j1_j2 bank-33 PL pin assignment (P3 linker)"

# (module, IN rail, OUT rail, RSET value, RSET LCSC, LED series R, R LCSC)
MODULES = (
    ("HDMI_TX", "+3V3", "+3V3_HDMI_TX", "13k", LCSC_13K, "330R", LCSC_330R),
    ("HDMI_RX", "+3V3", "+3V3_HDMI_RX", "13k", LCSC_13K, "330R", LCSC_330R),
    ("LCD", "+3V3", "+3V3_LCD", "6.8k", LCSC_6K8, "330R", LCSC_330R),
    ("CAM", "+3V3", "+3V3_CAM", "13k", LCSC_13K, "330R", LCSC_330R),
    ("SD", "+3V3", "+3V3_SD", "6.8k", LCSC_6K8, "330R", LCSC_330R),
    ("USB", "+5V", "+5V_USB", "6.8k", LCSC_6K8, "1k", LCSC_1K),
    ("PMOD", "+3V3", "+3V3_PMOD", "13k", LCSC_13K, "330R", LCSC_330R),
    ("USER_LED", "+3V3", "+3V3_USER_LED", "13k", LCSC_13K, "330R", LCSC_330R),
    # PLAN round-5 5V module gates (sourcing the former unsourced rails)
    ("HDMI_TX_5V", "+5V", "+5V_HDMI_TX", "13k", LCSC_13K, "1k", LCSC_1K),
    ("LCD_5V", "+5V", "+5V_LCD", "6.8k", LCSC_6K8, "1k", LCSC_1K),
)


def circuit() -> Circuit:
    c = Circuit("bringup_modules",
                "Bring-up module gates: 10x SY6280 + status/user LEDs")
    for k, (mod, in_rail, out_rail, rset, rset_id, led_r, led_r_id) \
            in enumerate(MODULES):
        u = c.use_part("SY6280AAC", ref=f"U{k + 1}")
        c.net(in_rail, f"{u.ref}.IN")
        c.net(out_rail, f"{u.ref}.OUT")                  # -> gated rail
        c.net("GND", f"{u.ref}.GND")
        c.port(f"EN_{mod}", f"{u.ref}.EN", expect=EXPECT_EN)
        # ISET -> RSET -> GND: ILIM = 6800 / RSET
        rs = c.part(c.auto_ref("R"), "Device:R", rset, R_FP, LCSC=rset_id)
        c.net(f"BU_ISET_{mod}", f"{u.ref}.ISET", f"{rs.ref}.1")
        c.net("GND", f"{rs.ref}.2")
        # 100n local on IN and OUT (dossier 3.2 wiring note)
        for cap in c.decouple(f"{u.ref}.IN", "100n", footprint=C_FP):
            cap.fields["LCSC"] = LCSC_100N
        for cap in c.decouple(f"{u.ref}.OUT", "100n", footprint=C_FP):
            cap.fields["LCSC"] = LCSC_100N
        # per-module status LED on the gated output (red, dossier 3.3)
        d = c.part(c.auto_ref("D"), "Device:LED", "red", LED_FP,
                   LCSC=LCSC_RED)
        rl = c.part(c.auto_ref("R"), "Device:R", led_r, R_FP, LCSC=led_r_id)
        c.net(out_rail, f"{d.ref}.2")
        c.net(f"BU_PG_{mod}", f"{d.ref}.1", f"{rl.ref}.1")
        c.net("GND", f"{rl.ref}.2")

    # microSD power-cycle re-init needs VDD < ~0.5 V, but the SY6280 has no QOD,
    # so +3V3_SD would only decay through a possibly-high-Z card and could strand
    # above 0.5 V. Add a 10k bleed on +3V3_SD (research R5; 0.33 mA static <<
    # the 1 A limit, cannot mis-trip) so the rail discharges for a clean re-seat.
    # Only the SD rail has this power-cycle-for-re-init requirement (audit 2026-06-20).
    rbleed = c.part(c.auto_ref("R"), "Device:R", "10k", R_FP, LCSC="C25804")
    c.net("+3V3_SD", f"{rbleed.ref}.1")
    c.net("GND", f"{rbleed.ref}.2")

    # (user LEDs live on the user_io sheet, bound to real bank-13 pins —
    # this sheet only GATES their +3V3_USER_LED rail via switch #8)

    # round-4 coverage gate: every gated module rail is probed at its
    # source (the SY6280 output) — rail-by-rail bring-up needs the meter
    # on THIS side of the module connector
    for _mod, _in, out_rail, _rs, _ri, _lr, _li in MODULES:
        c.testpoint(out_rail)

    # power-tree budget (round 4): this sheet's own load on each gated rail
    # is its status LED — (3.3-2.0)/330R ~= 3.9 mA on the 3V3 rails,
    # (5-2)/1k = 3 mA on +5V_USB (dossier 3.3)
    for _mod, _in, out_rail, _rs, _ri, led_r, _li in MODULES:
        amps = 0.004 if led_r == "330R" else 0.003
        c.draws(out_rail, amps, f"status LED ({led_r}) on the gated output")
    return c
