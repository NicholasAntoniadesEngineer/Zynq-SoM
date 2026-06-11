"""bringup_en_modules — the nine MODULE EN cells: "DIP AND STM32-override" for every
enable in the system (carrier/research/bringup_power_gating.md section 3.1,
3.2; one uniform cell, dossier section 1):

    +3V3_SC                       +3V3_SC
       |                             |
      [DIP pos n]                 [100k pullup]      SN74LVC1G08 (VCC=+3V3_SC)
       |________ A _________________ |              .----------.
                 |                   +---- B ------>|A      Y  |--> EN_<thing>
               [100k pulldown]       |              |B         |
                 |             STM32 GPIO /         '----------'
                GND            TCA9535 P0x (Hi-Z at reset => B=1)

AND, not OR: the DIP is the master, software is a VETO (force-OFF only) —
an unprogrammed STM32 / unconfigured TCA9535 (POR = all inputs) leaves B
pulled high, so stage-1 bring-up works with switches alone, and software can
never force a probe-shorted module ON behind a human's back. Gate:
SN74LVC1G08DBVR (SOT-23-5, pinout 1=A 2=B 3=GND 4=Y 5=VCC, inputs 5.5 V
tolerant, 32 mA rail-to-rail output — drives any regulator/load-switch EN
directly), VCC = +3V3_SC (alive from default VBUS before PD), 100 nF each.

Twelve cells: 3 rails (+5V/+3V3/+1V8 — A from SW1, B from STM32_GPIO1..3
direct so rails stay controllable even if I2C is down), 8 modules (A from
SW2, B from TCA9535 P00..P07), and the spare cell (A = SW2 position 8,
B = TCA9535 P10) emitting the EN_LCD_BL provision for the LCD backlight
boost — B rides P10's 100k pullDOWN (bringup_rails), so the provision is
OFF until software raises it. Every A-input carries the cell's 100k
pulldown, every rail/module B-input its 100k pullup to +3V3_SC; both live
HERE at the gate so each cell is complete on this sheet.

EN_5V0/EN_3V3/EN_1V8 bind to the power subsystem's regulator EN pins
(3.3 V CMOS, active-high, push-pull — TPS54302 EN VIH 1.21 V typ and the
AP2112K EN both accept it rail-to-rail). EN_<module> bind to the SY6280
gates on bringup_modules.
"""

from __future__ import annotations

from schgen.model import Circuit

GATE_LIB = "74xGxx:74LVC1G08"
GATE_FP = "Package_TO_SOT_SMD:SOT-23-5"
R_FP = "Resistor_SMD:R_0603_1608Metric"
C_FP = "Capacitor_SMD:C_0603_1608Metric"

LCSC_GATE = "C7666"        # SN74LVC1G08DBVR (TI) — live-verified 2026-06-10
LCSC_100K = "C25803"
LCSC_100N = "C1591"

J3_MAP = "som_j3_connector (wave 3 STM32 GPIO function map)"
EXPECT_RAILS = "bringup_rails (DIP / TCA9535 control surfaces)"
EXPECT_MODULES = "bringup_modules (SY6280 load-switch cells)"
EXPECT_POWER = "power (regulator EN pins, dossier section 3.1)"
EXPECT_LCD = "lvds_lcd_power (backlight boost EN provision, dossier 3.2)"

# (cell, A net <- DIP, B net <- override, Y net -> enable, B pullup?, Y expect)
CELLS = (    # modules: B = TCA9535 P00..P07 (bringup_rails)
    ("HDMI_TX", "BU_DIP_HDMI_TX", "BU_OVR_HDMI_TX", "EN_HDMI_TX",
     True, EXPECT_MODULES),
    ("HDMI_RX", "BU_DIP_HDMI_RX", "BU_OVR_HDMI_RX", "EN_HDMI_RX",
     True, EXPECT_MODULES),
    ("LCD", "BU_DIP_LCD", "BU_OVR_LCD", "EN_LCD", True, EXPECT_MODULES),
    ("CAM", "BU_DIP_CAM", "BU_OVR_CAM", "EN_CAM", True, EXPECT_MODULES),
    ("SD", "BU_DIP_SD", "BU_OVR_SD", "EN_SD", True, EXPECT_MODULES),
    ("USB", "BU_DIP_USB", "BU_OVR_USB", "EN_USB", True, EXPECT_MODULES),
    ("PMOD", "BU_DIP_PMOD", "BU_OVR_PMOD", "EN_PMOD", True, EXPECT_MODULES),
    ("USER_LED", "BU_DIP_USER_LED", "BU_OVR_USER_LED", "EN_USER_LED",
     True, EXPECT_MODULES),
    # spare cell: SW2 pos 8 AND TCA9535 P10 -> LCD backlight provision.
    # NO pullup here — P10 carries the dossier's 100k pullDOWN on
    # bringup_rails (provision defaults OFF until software raises P10).
    ("LCD_BL", "BU_DIP_SPARE", "BU_OVR_LCD_BL", "EN_LCD_BL", False,
     EXPECT_LCD),
)


def circuit() -> Circuit:
    c = Circuit("bringup_en_modules",
                "Bring-up EN cells: 9x SN74LVC1G08 module DIP-AND-override")
    for k, (name, a_net, b_net, y_net, b_pull, y_expect) in enumerate(CELLS):
        u = c.part(f"U{k + 1}", GATE_LIB, "SN74LVC1G08", GATE_FP,
                   LCSC=LCSC_GATE)
        # A: DIP contact net + the cell's 100k pulldown (closed DIP = 1)
        c.port(a_net, f"{u.ref}.1", expect=EXPECT_RAILS)
        rd = c.part(c.auto_ref("R"), "Device:R", "100k", R_FP,
                    LCSC=LCSC_100K)
        c.net(a_net, f"{rd.ref}.1")
        c.net("GND", f"{rd.ref}.2")
        # B: override veto, pulled to +3V3_SC (Hi-Z source => enabled)
        c.port(b_net, f"{u.ref}.2",
               expect=J3_MAP if b_net.startswith("STM32") else EXPECT_RAILS)
        if b_pull:
            c.pullup(f"{u.ref}.2", "100k", "+3V3_SC",
                     footprint=R_FP).fields["LCSC"] = LCSC_100K
        # Y: the enable, 3.3 V CMOS push-pull, active-high
        c.port(y_net, f"{u.ref}.4", expect=y_expect)
        # supply: +3V3_SC, 100n per gate
        c.net("+3V3_SC", f"{u.ref}.5")
        c.net("GND", f"{u.ref}.3")
        for cap in c.decouple(f"{u.ref}.5", "100n", footprint=C_FP):
            cap.fields["LCSC"] = LCSC_100N

    # round-4 coverage gate: every EN line is probeable (bring-up
    # philosophy — stage 3 is debugged with a meter on the EN cells)
    for _name, _a, _b, y_net, _p, _e in CELLS:
        c.testpoint(y_net)

    # power-tree budget (round 4): 9 LVC gates (uA static) + A/B 100k pull
    # networks (33 uA each when driven)
    c.draws("+3V3_SC", 0.005, "9x SN74LVC1G08 + 100k pull networks")
    return c
