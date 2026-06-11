"""bringup_modules — per-module power gates + status/user LEDs
(carrier/research/bringup_power_gating.md sections 3.2, 3.3, 3.4).

Stage-3 bring-up: EVERY module is individually power-gated so a fault is
isolated by eye — a SY6280AAC load switch per module with a PROGRAMMABLE
current limit (ILIM = 6800/RSET; constant-current foldback, OTP, reverse
blocking): a shorted module folds back at its own limit instead of dragging
+3V3 down for everything else, and that one module's status LED sags and
points at the fault. SY6280AAC pinout (SOT-23-5, Silergy DS):
1=OUT 2=GND 3=ISET 4=EN 5=IN.

Switch table (dossier 3.2 — RSET on verified JLC-Basic E-series values):

  # module    IN    OUT (gated rail)  RSET            limit
  1 HDMI TX   +3V3  +3V3_HDMI_TX      13k  (C22797)   523 mA
  2 HDMI RX   +3V3  +3V3_HDMI_RX      13k             523 mA
  3 LCD       +3V3  +3V3_LCD          6.8k (C23212)   1.0 A
  4 Camera    +3V3  +3V3_CAM          13k             523 mA
  5 microSD   +3V3  +3V3_SD           6.8k            1.0 A
  6 USB VBUS  +5V   +5V_USB           6.8k            1.0 A
  7 PMOD      +3V3  +3V3_PMOD         13k             523 mA
  8 User LEDs +3V3  +3V3_USER_LED     13k             523 mA

Every EN comes from its bringup_en AND-cell (push-pull 3.3 V — EN never
floats). 100 nF on each switch input and output (module subsystems own
their own bulk). Per-module status LED: KT-0603R red + 330R on each gated
3V3 output, 1k on the 5 V USB output (~3-4 mA). The gated rails are POWER
nets — module sheets (hdmi_tx, hdmi_rx, ...) consume them by name.

Stage-2 user IO: 4x LTST-C190KFKT yellow LEDs (visually distinct from the
red infrastructure LEDs; do NOT "upgrade" to green InGaN — Vf~3.1 V is
marginal on 3.3 V, dossier risk R4), anodes bused on +3V3_USER_LED (switch
#8), cathode -> 330R -> PL pin, ACTIVE-LOW (~3.9 mA, fine for a 3.3 V
LVCMOS bank pin). Final PL pin assignment is the P3 linker's job — this
sheet publishes the PL_LED0..3 sink ports.
"""

from __future__ import annotations

from schgen.model import Circuit

SW_LIB = "SY6280AAC:SY6280AAC"
SW_FP = "SY6280AAC:SY6280AAC"
R_FP = "Resistor_SMD:R_0603_1608Metric"
C_FP = "Capacitor_SMD:C_0603_1608Metric"
LED_FP = "LED_SMD:LED_0603_1608Metric"

LCSC_SW = "C55136"         # SY6280AAC (Silergy), live-verified 2026-06-10
LCSC_13K = "C22797"        # 0603 13k -> 523 mA
LCSC_6K8 = "C23212"        # 0603 6.8k -> 1.0 A
LCSC_330R = "C23138"
LCSC_1K = "C21190"
LCSC_100N = "C1591"
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
)


def circuit() -> Circuit:
    c = Circuit("bringup_modules",
                "Bring-up module gates: 8x SY6280 + status/user LEDs")
    for k, (mod, in_rail, out_rail, rset, rset_id, led_r, led_r_id) \
            in enumerate(MODULES):
        u = c.part(f"U{k + 1}", SW_LIB, "SY6280AAC", SW_FP, LCSC=LCSC_SW)
        c.net(in_rail, f"{u.ref}.5")                     # IN
        c.net(out_rail, f"{u.ref}.1")                    # OUT -> gated rail
        c.net("GND", f"{u.ref}.2")
        c.port(f"EN_{mod}", f"{u.ref}.4", expect=EXPECT_EN)
        # ISET -> RSET -> GND: ILIM = 6800 / RSET
        rs = c.part(c.auto_ref("R"), "Device:R", rset, R_FP, LCSC=rset_id)
        c.net(f"BU_ISET_{mod}", f"{u.ref}.3", f"{rs.ref}.1")
        c.net("GND", f"{rs.ref}.2")
        # 100n local on IN and OUT (dossier 3.2 wiring note)
        for cap in c.decouple(f"{u.ref}.5", "100n", footprint=C_FP):
            cap.fields["LCSC"] = LCSC_100N
        for cap in c.decouple(f"{u.ref}.1", "100n", footprint=C_FP):
            cap.fields["LCSC"] = LCSC_100N
        # per-module status LED on the gated output (red, dossier 3.3)
        d = c.part(c.auto_ref("D"), "Device:LED", "red", LED_FP,
                   LCSC=LCSC_RED)
        rl = c.part(c.auto_ref("R"), "Device:R", led_r, R_FP, LCSC=led_r_id)
        c.net(out_rail, f"{d.ref}.2")
        c.net(f"BU_PG_{mod}", f"{d.ref}.1", f"{rl.ref}.1")
        c.net("GND", f"{rl.ref}.2")

    # ---- user LEDs: +3V3_USER_LED -> yellow LED -> 330R -> PL pin (sink) ---
    for k in range(4):
        d = c.part(c.auto_ref("D"), "Device:LED", "yellow", LED_FP,
                   LCSC=LCSC_YEL)
        r = c.part(c.auto_ref("R"), "Device:R", "330R", R_FP,
                   LCSC=LCSC_330R)
        c.net("+3V3_USER_LED", f"{d.ref}.2")
        c.net(f"BU_LED{k}_K", f"{d.ref}.1", f"{r.ref}.1")
        c.port(f"PL_LED{k}", f"{r.ref}.2", expect=J12_MAP)
    return c
