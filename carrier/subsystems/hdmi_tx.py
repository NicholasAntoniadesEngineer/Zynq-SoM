"""hdmi_tx — HDMI source port: Zynq -> TPD12S016 -> HDMI Type-A receptacle.

Reference circuit per TI TPD12S016 (SLLSE96F) Figure 15, "HDMI source using
one GPIO", with CT_HPD and LS_OE strapped HIGH (10k to V_CCA) so the level
shifters and the on-chip 55 mA +5V load switch are always on:

  * The 8 TMDS lines flow THROUGH the TPD's clamp pads to the receptacle.
    The schgen:TPD12S016 symbol draws them flow-through: each TMDS pad is a
    DUPLICATE pin number on both body edges (duplicate_pin_numbers_are_
    jumpers — KiCad nets the two edges as ONE pad; proven against kicad-cli
    netlist export, and the netlist gate re-proves it on every build).
  * DDC (SCL/SDA), CEC and HPD pass through the TPD's level shifters:
    A-side nets (ZYNQ_HDMI_TX_*) are V_CCA-domain ports to the Zynq PL;
    B-side nets (HDMI_TX_CON_*) run at the cable's 5 V to the receptacle.
    All DDC/CEC/HPD pull-ups are integrated (DS Sec 7.3.9/7.3.15) — no
    external resistors, and no EDID EEPROM (a SOURCE reads the sink's EDID).
  * 5V_OUT (the current-limited switch output) sources receptacle pin 18;
    100n HF + 1u bulk at the connector per HDMI 1.4 Sec 4.2.7.
  * Rails are the bring-up dossier's GATED module rails: +3V3_HDMI_TX on
    V_CCA (controller side) and +5V_HDMI_TX on V_CC5V (cable side), each
    decoupled 100n (DS Fig 15). The SY6280 gates live on the bringup sheet.
  * Receptacle: SOFNG HDMI-019S; shield/CK..D2 ground pins to GND, the four
    shell legs to CHASSIS_GND (star-bonded elsewhere). Pin 14 (HEC/Utility)
    is reserved -> author no-connect (HDMI 1.4: N.C. on non-HEAC devices).

Pin maps are the LCSC/EasyEDA tables fetched by `schgen part add C201665` /
`add C111617` (parts/TPD12S016PWR, parts/HDMI-019S) — the schgen symbols are
asserted against them at generation time, and `c.validate` + the netlist
gate re-check every pin on every build.
"""

from __future__ import annotations

from schgen.core.model import Circuit

# DELIBERATE symbol overrides (use_part lib_id=): the proven re-pinned
# schgen drawings stay; MPN/LCSC/datasheet + the faithful EasyEDA->KiCad
# footprints come from parts/TPD12S016PWR/ + parts/HDMI-019S/.
LIB_U = "schgen:TPD12S016"
LIB_J = "schgen:HDMI_A_019S"
R_FP = "Resistor_SMD:R_0603_1608Metric"
C_FP = "Capacitor_SMD:C_0603_1608Metric"

LCSC_100N = "C14663"     # CC0603KRX7R9BB104 100n 0603 X7R 50V (JLC Basic)
LCSC_1U = "C15849"      # CL10A105KB8NNNC 1u 0603 X5R 25V (JLC Basic)
LCSC_10K = "C25804"     # 0603WAF1002T5E 10k 1% (JLC Basic)

J2_MAP = "som_j2_connector (wave 3 PL function map)"

# TMDS lane -> (TPD flow-through pad, receptacle pin). Sources: TI SLLSE96F
# Sec 5 pin map; HDMI 1.4 Sec 4.2.2 connector pinout (both re-checked against
# the parts/<MPN>/part.py LCSC tables).
TMDS_LANES = (
    ("2_P", "23", "1"), ("2_N", "22", "3"),
    ("1_P", "21", "4"), ("1_N", "20", "6"),
    ("0_P", "18", "7"), ("0_N", "17", "9"),
    ("CLK_P", "16", "10"), ("CLK_N", "15", "12"),
)
# level-shifted lines: port name suffix -> (TPD A pin, TPD B pin, recept. pin)
SHIFTED = (
    ("CEC", "1", "7", "13"),
    ("SCL", "2", "8", "15"),
    ("SDA", "3", "9", "16"),
    ("HPD", "4", "10", "19"),
)


def circuit() -> Circuit:
    c = Circuit("hdmi_tx", "HDMI TX: TPD12S016 + HDMI-A receptacle (source)")
    c.use_part("TPD12S016PWR", ref="U1", lib_id=LIB_U)
    c.use_part("HDMI-019S", ref="J1", lib_id=LIB_J)

    # gated module rails (bringup_power_gating dossier) + DS Fig 15 decoupling
    c.net("+3V3_HDMI_TX", "U1.24")                 # V_CCA, controller side
    c.net("+5V_HDMI_TX", "U1.11")                  # V_CC5V, load-switch input
    for cap in c.decouple("U1.24", "100n", footprint=C_FP):       # C1
        cap.fields["LCSC"] = LCSC_100N
    for cap in c.decouple("U1.11", "100n", footprint=C_FP):       # C2
        cap.fields["LCSC"] = LCSC_100N
    # bulk on the gated +3V3_HDMI_TX rail (bringup_power_gating.md 3.2: each
    # module owns its bulk; matches camera/microsd 10u peers). C5: C3/C4 are
    # hardcoded further down, so an explicit free ref avoids a collision.
    c.part("C5", "Device:C", "10u",
           "Capacitor_SMD:C_0805_2012Metric", LCSC="C15850")
    c.net("+3V3_HDMI_TX", "C5.1")
    c.net("GND", "C5.2")

    # TMDS: Zynq port -> TPD clamp pad (flow-through) -> receptacle
    for lane, upin, jpin in TMDS_LANES:
        c.port(f"ZYNQ_HDMI_TX_TMDS_{lane}", f"U1.{upin}", f"J1.{jpin}")
    for lane in ("2", "1", "0", "CLK"):
        c.port_type(f"ZYNQ_HDMI_TX_TMDS_{lane}_P", kind="tmds_pair",
                    pair_with=f"ZYNQ_HDMI_TX_TMDS_{lane}_N", expect=J2_MAP)

    # DDC/CEC/HPD: A-side ports (Zynq), B-side wired nets (receptacle)
    c.port("ZYNQ_HDMI_TX_CEC", "U1.1", expect=J2_MAP)
    c.port("ZYNQ_HDMI_TX_SCL", "U1.2", kind="i2c", role="scl",
           bus="HDMI_TX_DDC", speed_hz=100_000, expect=J2_MAP)
    c.port("ZYNQ_HDMI_TX_SDA", "U1.3", kind="i2c", role="sda",
           bus="HDMI_TX_DDC", speed_hz=100_000, expect=J2_MAP)
    c.port("ZYNQ_HDMI_TX_HPD", "U1.4", expect=J2_MAP)
    for name, _a, bpin, jpin in SHIFTED:
        c.net(f"HDMI_TX_CON_{name}", f"U1.{bpin}", f"J1.{jpin}")

    # switched cable +5V: 5V_OUT -> pin 18, 100n HF + 1u bulk at the connector
    c.net("HDMI_TX_CON_5V0", "U1.13", "J1.18")
    for ref, val, lcsc in (("C3", "100n", LCSC_100N), ("C4", "1u", LCSC_1U)):
        c.part(ref, "Device:C", val, C_FP, LCSC=lcsc)
        c.net("HDMI_TX_CON_5V0", f"{ref}.1")
        c.net("GND", f"{ref}.2")

    # always-on straps: LS_OE + CT_HPD 10k to V_CCA (DS Fig 15 / Sec 8.2.1)
    c.net("HDMI_TX_LS_OE", "U1.5")
    c.net("HDMI_TX_CT_HPD", "U1.12")
    c.pullup("U1.5", "10k", "+3V3_HDMI_TX", footprint=R_FP).fields["LCSC"] = LCSC_10K   # R1
    c.pullup("U1.12", "10k", "+3V3_HDMI_TX", footprint=R_FP).fields["LCSC"] = LCSC_10K  # R2

    # grounds: TPD GND pins + receptacle TMDS shields/DDC ground; the four
    # shell legs bond to the chassis island (separate net, star-bond elsewhere)
    c.net("GND", "U1.6", "U1.14", "U1.19",
          "J1.2", "J1.5", "J1.8", "J1.11", "J1.17")
    c.net("CHASSIS_GND", "J1.20", "J1.21", "J1.22", "J1.23")

    # pin 14 = HEC/Utility, reserved (N.C. on non-HEAC devices, HDMI 1.4)
    c.nc("J1.14")

    # round-4 coverage gate: the (unsourced — power-tree finding) cable-5V
    # feed rail + the DDC bus this sheet owns
    c.testpoint("+5V_HDMI_TX")
    c.testpoint("ZYNQ_HDMI_TX_SCL")
    c.testpoint("ZYNQ_HDMI_TX_SDA")

    # power-tree budget (round 4): TPD12S016 ICCA < 1 mA + the two 10k
    # straps; the cable's +5V is the TPD's integrated 55 mA-limited switch
    # (DS Sec 7.3.10) fed from +5V_HDMI_TX
    c.draws("+3V3_HDMI_TX", 0.002, "TPD12S016 ICCA + LS_OE/CT_HPD straps")
    c.draws("+5V_HDMI_TX", 0.055, "HDMI source +5V to cable — TPD12S016 "
                                  "switch limit 55 mA (DS 7.3.10)")
    # design-rule waiver (verification P1): the DDC I2C pull-ups are INTEGRATED
    # in the TPD12S016 (DS 7.3.9/7.3.15 — "no external pull-ups"), so the
    # ZYNQ_HDMI_TX SCL/SDA nets carry none on-board by design.
    c.waive_pull("ZYNQ_HDMI_TX_SCL",
                 "DDC pull-ups integrated in TPD12S016 (DS 7.3.9/7.3.15)")
    c.waive_pull("ZYNQ_HDMI_TX_SDA",
                 "DDC pull-ups integrated in TPD12S016 (DS 7.3.9/7.3.15)")
    return c
