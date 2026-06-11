"""bringup_rails — bring-up control surfaces: DIP switches, override
expander, buttons (carrier/research/bringup_power_gating.md sections 1, 3.4,
3.5, 4).

The staged bring-up contract is one uniform EN cell per enable — "DIP is the
master, STM32 is a veto" — implemented as SN74LVC1G08 AND gates on the
bringup_en sheet. THIS sheet carries the human/software control surfaces the
cells consume:

* SW1 (DSHP04TSGER): rail DIP — silkscreen positions 1=+5V, 2=+3V3, 3=+1V8,
  4=USER_LED (the rail DIP's spare position runs module switch #8 so SW2
  keeps all eight positions for real modules). One contact of every position
  is bused to +3V3_SC (the SoM system-controller rail, alive from default
  5 V VBUS before any carrier rail); the other contact is the cell's A-input
  net BU_DIP_* (100k pulldown lives at the gate, bringup_en).
  Position->pin map per the Kangshen DSHP footprint (counterclockwise DIP
  numbering, position n = pins n & 2N+1-n): the +3V3_SC side uses the odd
  pins, the BU_DIP nets land on even pins 8/2/6/4 for positions 1/2/3/4.
* SW2 (DSHP08TSGER): module DIP — positions 1=HDMI_TX, 2=HDMI_RX, 3=LCD,
  4=CAM, 5=SD, 6=USB, 7=PMOD, 8=spare (EN_LCD_BL provision). Position n =
  pins n & 17-n: BU_DIP nets on even pins 16/2/14/4/12/6/10/8.
* SW6 (DSHP04TSGER): the PLAN round-5 EXTENSION DIP. SW1's four and SW2's
  eight positions were ALL in use when the round-5 decision added module
  gates for the (previously unsourced) +5V_HDMI_TX and +5V_LCD rails, so
  the bit map extends HONESTLY with a third DIP rather than overloading an
  existing position: silkscreen 1=HDMI_TX_5V, 2=LCD_5V, 3/4=spare (even
  pins 6/4 author-NC; the odd +3V3_SC bus covers all four positions so a
  future gate only adds the BU_DIP port). Same DSHP04 position->pin map
  as SW1 (pos n = pins n & 9-n, signals on even pins 8/2).
* U1 (TCA9535PWR, I2C addr 0x20 — A0=A1=A2=GND; FUSB302B at 0x22 shares the
  bus, no clash): the STM32 override expander. POR state is all-inputs, so
  with the cells' 100k pull-ups everything defaults to DIP control — a blank
  system controller boots stage-1 "switches only". P00..P07 are the eight
  module veto lines BU_OVR_*; P10 is the EN_LCD_BL provision driver
  (BU_OVR_LCD_BL, 100k pulldown — the spare cell is OFF until software
  raises it); P12/P13 are the round-5 veto lines BU_OVR_HDMI_TX_5V /
  BU_OVR_LCD_5V (100k pull-ups at their gates, like P00..P07); P11 stays
  a 100k-to-GND spare RESERVED for power_mon's PMON_ALERT_N (its dossier
  + the firmware header both name it); P14..P17 have no internal pulls
  and must not float: 100k to GND each. SDA/SCL ride STM32_I2C2 (usb_pd's
  FUSB302 bus) with 4k7 pull-ups to +3V3_SC (dossier risk R1: the bus
  must live before any carrier rail). INT# is open-drain: 10k to +3V3_SC,
  port STM32_BRINGUP_INT (J3 GPIO4 function map, wave-3 deferral).
* Buttons (TS-1187A-B-A-B, pads 1/2 and 3/4 are internally bridged pairs):
  two user buttons to PL pins — active-LOW, 10k pull-up to +3V3 (the bank
  VCCO of the PL pins) + 100n across the contacts for RC debounce — and the
  reset button on STM32_NRST (J3.47; the STM32's internal ~40k pull-up, no
  external resistor) + 100n.

All parts live-verified on LCSC/JLCPCB 2026-06-10 (dossier section 2).
"""

from __future__ import annotations

from schgen.model import Circuit

R_FP = "Resistor_SMD:R_0603_1608Metric"
C_FP = "Capacitor_SMD:C_0603_1608Metric"

LCSC_100K = "C25803"       # 0603 100k 1%
LCSC_10K = "C25804"        # 0603 10k 1%
LCSC_4K7 = "C23162"        # 0603 4.7k 1%
LCSC_100N = "C1591"        # CL10B104KB8NNNC 100n X7R

J3_MAP = "som_j3_connector (wave 3 STM32 GPIO function map)"

# SW1 rail DIP: silkscreen position -> (even pin, BU_DIP net). DSHP04
# pairing: pos n = pins (n, 9-n); odd pins 1/3/5/7 carry the +3V3_SC side.
SW1_MAP = (("8", "BU_DIP_5V0"), ("2", "BU_DIP_3V3"),
           ("6", "BU_DIP_1V8"), ("4", "BU_DIP_USER_LED"))
# SW2 module DIP: pos n = pins (n, 17-n); odd pins carry +3V3_SC.
SW2_MAP = (("16", "BU_DIP_HDMI_TX"), ("2", "BU_DIP_HDMI_RX"),
           ("14", "BU_DIP_LCD"), ("4", "BU_DIP_CAM"),
           ("12", "BU_DIP_SD"), ("6", "BU_DIP_USB"),
           ("10", "BU_DIP_PMOD"), ("8", "BU_DIP_SPARE"))
# SW6 round-5 extension DIP (DSHP04, same pairing as SW1): positions 1/2
# carry the 5V module gates, 3/4 spare (even pins 6/4 author-NC below).
SW6_MAP = (("8", "BU_DIP_HDMI_TX_5V"), ("2", "BU_DIP_LCD_5V"))
# TCA9535 P00..P07 (pins 4..11) -> module veto nets, dossier section 3.2.
P0_MAP = ("BU_OVR_HDMI_TX", "BU_OVR_HDMI_RX", "BU_OVR_LCD", "BU_OVR_CAM",
          "BU_OVR_SD", "BU_OVR_USB", "BU_OVR_PMOD", "BU_OVR_USER_LED")
# TCA9535 P12/P13 -> round-5 veto nets (P10 = LCD_BL provision, P11
# reserved for PMON_ALERT_N, P14..P17 spare 100k-to-GND).
P1_MAP = (("P12", "BU_OVR_HDMI_TX_5V"), ("P13", "BU_OVR_LCD_5V"))
EXPECT_EN = "bringup_en (EN AND-gate cells, dossier section 3.1/3.2)"


def circuit() -> Circuit:
    c = Circuit("bringup_rails",
                "Bring-up controls: rail/module DIPs + TCA9535 + buttons")

    # ---- SW1 / SW2: DIP switches, one side bused to +3V3_SC ----------------
    c.use_part("DSHP04TSGER", ref="SW1")        # position pins stay numeric
    c.net("+3V3_SC", "SW1.1", "SW1.3", "SW1.5", "SW1.7")
    for pin, net in SW1_MAP:
        c.port(net, f"SW1.{pin}", expect=EXPECT_EN)
    c.use_part("DSHP08TSGER", ref="SW2")
    c.net("+3V3_SC", "SW2.1", "SW2.3", "SW2.5", "SW2.7",
          "SW2.9", "SW2.11", "SW2.13", "SW2.15")
    for pin, net in SW2_MAP:
        c.port(net, f"SW2.{pin}", expect=EXPECT_EN)
    # SW6: round-5 extension DIP (docstring) — positions 3/4 spare
    c.use_part("DSHP04TSGER", ref="SW6")
    c.net("+3V3_SC", "SW6.1", "SW6.3", "SW6.5", "SW6.7")
    for pin, net in SW6_MAP:
        c.port(net, f"SW6.{pin}", expect=EXPECT_EN)
    c.nc("SW6.4", "SW6.6")                 # spare positions 4/3

    # ---- U1: TCA9535 override expander @0x20 -------------------------------
    c.use_part("TCA9535PWR", ref="U1")
    c.net("+3V3_SC", "U1.VCC")
    for cap in c.decouple("U1.VCC", "100n", footprint=C_FP):          # C1
        cap.fields["LCSC"] = LCSC_100N
    c.net("GND", "U1.GND", "U1.A1", "U1.A2", "U1.A0")        # addr = 0x20
    for k, net in enumerate(P0_MAP):
        c.port(net, f"U1.P0{k}", expect=EXPECT_EN)
    # P10 = EN_LCD_BL provision driver; unused P1x 100k to GND (no internal
    # pulls in the TCA9535 — unlike PCA9555 — so unused ports must not float)
    c.port("BU_OVR_LCD_BL", "U1.P10", expect=EXPECT_EN)
    r = c.part(c.auto_ref("R"), "Device:R", "100k", R_FP, LCSC=LCSC_100K)
    c.net("BU_OVR_LCD_BL", f"{r.ref}.1")
    c.net("GND", f"{r.ref}.2")
    # P12/P13 = round-5 module veto lines (their 100k pull-UPS live at the
    # gates on bringup_en_modules, exactly like the P00..P07 cells)
    for pname, net in P1_MAP:
        c.port(net, f"U1.{pname}", expect=EXPECT_EN)
    for k in (1, 4, 5, 6, 7):              # P11 (PMON_ALERT_N rsv), P14..P17
        net = f"BU_P1{k}"
        rr = c.part(c.auto_ref("R"), "Device:R", "100k", R_FP, LCSC=LCSC_100K)
        c.net(net, f"U1.P1{k}", f"{rr.ref}.1")
        c.net("GND", f"{rr.ref}.2")
    # I2C: shared STM32 bus (FUSB302 @0x22 on usb_pd) — pull-ups on +3V3_SC
    # per dossier risk R1 (PD negotiation precedes every carrier rail)
    c.port("STM32_I2C2_SCL", "U1.SCL",
           kind="i2c", role="scl", bus="STM32_I2C2", speed_hz=400_000,
           expect=J3_MAP)
    c.port("STM32_I2C2_SDA", "U1.SDA",
           kind="i2c", role="sda", bus="STM32_I2C2", speed_hz=400_000,
           expect=J3_MAP)
    c.pullup("U1.SCL", "4k7", "+3V3_SC", footprint=R_FP).fields["LCSC"] = LCSC_4K7
    c.pullup("U1.SDA", "4k7", "+3V3_SC", footprint=R_FP).fields["LCSC"] = LCSC_4K7
    # INT#: open-drain, 10k to +3V3_SC, optional STM32 readback interrupt
    c.port("STM32_BRINGUP_INT", "U1.INT#", expect=J3_MAP)
    c.pullup("U1.INT#", "10k", "+3V3_SC", footprint=R_FP).fields["LCSC"] = LCSC_10K

    # ---- user buttons: active-LOW, 10k to +3V3 (bank VCCO), 100n debounce --
    J12_MAP = "som_j1_j2 bank-33 PL pin assignment (P3 linker)"
    for k in range(2):
        sw = c.use_part("TS-1187A-B-A-B", ref=f"SW{3 + k}")
        net = f"PL_BTN{k}"
        cd = c.part(c.auto_ref("C"), "Device:C", "100n", C_FP, LCSC=LCSC_100N)
        c.port(net, f"{sw.ref}.1", f"{sw.ref}.2", f"{cd.ref}.1",
               expect=J12_MAP)
        c.net("GND", f"{sw.ref}.3", f"{sw.ref}.4", f"{cd.ref}.2")
        c.pullup(f"{sw.ref}.1", "10k", "+3V3",
                 footprint=R_FP).fields["LCSC"] = LCSC_10K

    # ---- reset button: STM32_NRST (J3.47), internal pull-up, 100n ----------
    c.use_part("TS-1187A-B-A-B", ref="SW5")
    cr = c.part(c.auto_ref("C"), "Device:C", "100n", C_FP, LCSC=LCSC_100N)
    c.port("STM32_NRST", "SW5.1", "SW5.2", f"{cr.ref}.1")
    c.net("GND", "SW5.3", "SW5.4", f"{cr.ref}.2")

    # round-4 coverage gate: the always-on SC rail + the shared SC I2C bus
    # are probed HERE (the sheet that owns the bus pull-ups)
    c.testpoint("+3V3_SC")
    c.testpoint("STM32_I2C2_SDA")
    c.testpoint("STM32_I2C2_SCL")

    # power-tree budget (round 4, dossier R3: subsystem total < 5 mA):
    # TCA9535 uA-class + 14 closed-DIP pull currents (33 uA each) + I2C/INT
    # pull-ups when sinking
    c.draws("+3V3_SC", 0.005, "TCA9535 + DIP/I2C/INT pull networks "
                              "(dossier R3 < 5 mA)")
    c.draws("+3V3", 0.001, "2x user-button 10k pull-ups when pressed")
    return c
