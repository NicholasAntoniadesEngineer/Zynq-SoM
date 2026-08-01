from __future__ import annotations

from carrier.basis import register
from schgen.core.model import Circuit

R_FP = "Resistor_SMD:R_0603_1608Metric"
C_FP = "Capacitor_SMD:C_0603_1608Metric"

LCSC_100K = "C25803"
LCSC_10K = "C25804"
LCSC_4K7 = "C23162"
LCSC_100N = "C14663"

J3_MAP = "som_j3_connector (wave 3 STM32 GPIO function map)"
J12_MAP = "som_j1_j2 bank-33 PL pin assignment (P3 linker)"
EXPECT_EN = "bringup_en (EN AND-gate cells, dossier section 3.1/3.2)"

EXPANDER_ADDR = register(
    "bringup_rails.expander_addr", "0x20", "i2c-addr",
    "A0=A1=A2=GND. FUSB302B at 0x22 shares the bus, no clash. POR state is "
    "all-inputs, so with the cells' 100k pull-ups everything defaults to DIP "
    "control and a blank system controller still boots stage 1.",
    "datasheet")

I2C_SPEED_HZ = register("bringup_rails.i2c_speed", 400_000, "Hz",
                        "Fast-mode STM32_I2C2.", "datasheet")

BUS_PULLUP = register(
    "bringup_rails.bus_pullup", "4k7", "ohm",
    "The STM32_I2C2 pull-ups live ONCE, here, on +3V3_SC — dossier risk R1: the "
    "bus must be alive before any carrier rail exists, because PD negotiation "
    "precedes them all. LCSC C23162.",
    "datasheet")

INT_PULLUP = register(
    "bringup_rails.int_pullup", "10k", "ohm",
    "This sheet OWNS the single pull-up for the merged SC_INT_N net (the "
    "TCA9535 INT# wire-ORed with the FUSB302 INT, G2). usb_pd's redundant 4k7 "
    "was deleted — one pull per net. LCSC C25804.",
    "datasheet")

SPARE_PULLDOWN = register(
    "bringup_rails.spare_pulldown", "100k", "ohm",
    "The TCA9535 has NO internal pulls (unlike the PCA9555), so an unused port "
    "must not float. P10 also carries this pulldown so the LCD_BL provision "
    "defaults OFF until software raises it. LCSC C25803.",
    "datasheet")

BUTTON_PULLUP = register(
    "bringup_rails.button_pullup", "10k", "ohm",
    "Active-LOW PL buttons pulled to +3V3, the bank VCCO of those PL pins. "
    "LCSC C25804.",
    "datasheet")

DEBOUNCE_CAP = register("bringup_rails.debounce_cap", "100n", "F",
                        "RC debounce across the tact contacts. LCSC C14663.",
                        "datasheet")

EXPANDER_DECAP = register("bringup_rails.expander_decap", "100n", "F",
                          "TCA9535 VCC bypass. LCSC C14663.", "datasheet")

PUDC_STRAP = register(
    "bringup_rails.pudc_strap", "10k", "ohm",
    "IO_L3P_PUDC_34 has NO resistor on the SoM. PUDC LOW during config ENABLES "
    "the internal pull-ups (UG470), which suits the LCD 'DISP defaults on' 10k "
    "and the active-low PL buttons. The strap is a carrier-side part so it "
    "lives on this config-strap sheet, not the connector-only J3 sheet. "
    "LCSC C25804.",
    "datasheet")

SC_DRAW_A = register(
    "bringup_rails.sc_draw", 0.005, "A",
    "TCA9535 uA-class + 14 closed-DIP pull currents at 33 uA each + the "
    "I2C/INT pull-ups when sinking. Dossier R3 caps this subsystem at 5 mA.",
    "datasheet")

BUTTON_DRAW_A = register("bringup_rails.button_draw", 0.001, "A",
                         "Two user-button 10k pull-ups when pressed.",
                         "datasheet")

DIP4_PAIRING = register(
    "bringup_rails.dip4_pairing", "pos n = pins (n, 9-n)", "pin-map",
    "DSHP04 (SW1, SW6) pairs a position diagonally, so the odd pins carry the "
    "+3V3_SC bus side and the BU_DIP nets land on the even pins.",
    "datasheet")

DIP8_PAIRING = register(
    "bringup_rails.dip8_pairing", "pos n = pins (n, n+8)", "pin-map",
    "DSHP08 (SW2) numbers its bottom row 9..16 left-to-right, so a rocker "
    "bridges the two pads in the SAME COLUMN — a STRAIGHT pairing, NOT the "
    "DSHP04 diagonal. Using the diagonal here SHORTED enable pairs (audit "
    "2026-06-19 CRITICAL); fixed in this map, never by renumbering the "
    "faithful EasyEDA footprint.",
    "measured")

N_PL_BUTTONS = 2
FIRST_BUTTON_REF = 3

SW1_MAP = (("8", "BU_DIP_5V0"), ("2", "BU_DIP_3V3"),
           ("6", "BU_DIP_1V8"), ("4", "BU_DIP_USER_LED"))
SW2_MAP = (("9", "BU_DIP_HDMI_TX"), ("10", "BU_DIP_HDMI_RX"),
           ("11", "BU_DIP_LCD"), ("12", "BU_DIP_CAM"),
           ("13", "BU_DIP_SD"), ("14", "BU_DIP_USB"),
           ("15", "BU_DIP_PMOD"), ("16", "BU_DIP_SPARE"))
SW6_MAP = (("8", "BU_DIP_HDMI_TX_5V"), ("2", "BU_DIP_LCD_5V"))
P0_MAP = ("BU_OVR_HDMI_TX", "BU_OVR_HDMI_RX", "BU_OVR_LCD", "BU_OVR_CAM",
          "BU_OVR_SD", "BU_OVR_USB", "BU_OVR_PMOD", "BU_OVR_USER_LED")
P1_MAP = (("P12", "BU_OVR_HDMI_TX_5V"), ("P13", "BU_OVR_LCD_5V"))

FLAG_PORT_POLICY = register(
    "bringup_rails.flag_ports", "P11/P14/P15", "pin-map",
    "The three telemetry flags land on expander INPUTS because the STM32 has "
    "zero free direct GPIOs (G4 census). Their pull-ups live on the OWNING "
    "sheets, so these ports get NO don't-float resistor here — one would fight "
    "the real pull and form a sloppy divider. P12/P13 are taken by the round-5 "
    "5 V module gates, which is why USBOTG_FLT_N is on P14, not the dossier's "
    "stale P12.",
    "policy")

_FLAG_PORTS = (
    ("PMON_ALERT_N", "P11",
     "power_mon (INA3221 CRITICAL wire-OR, 10k PU +3V3_SC)"),
    ("USBOTG_FLT_N", "P14", "usbc_otg (TPS2051C FLT#, 100k PU +3V3_SC)"),
    ("PD_FLT_N", "P15", "pd_input (TPS26631 eFuse FLT#, 100k PU +3V3_SC)"),
)


def circuit() -> Circuit:
    c = Circuit("bringup_rails",
                "Bring-up controls: rail/module DIPs + TCA9535 + buttons")

    c.use_part("DSHP04TSGER", ref="SW1")
    c.net("+3V3_SC", "SW1.1", "SW1.3", "SW1.5", "SW1.7")
    for pin, net in SW1_MAP:
        c.port(net, f"SW1.{pin}", expect=EXPECT_EN)
    c.use_part("DSHP08TSGER", ref="SW2")
    c.net("+3V3_SC", "SW2.1", "SW2.2", "SW2.3", "SW2.4",
          "SW2.5", "SW2.6", "SW2.7", "SW2.8")
    for pin, net in SW2_MAP:
        c.port(net, f"SW2.{pin}", expect=EXPECT_EN)
    c.use_part("DSHP04TSGER", ref="SW6")
    c.net("+3V3_SC", "SW6.1", "SW6.3", "SW6.5", "SW6.7")
    for pin, net in SW6_MAP:
        c.port(net, f"SW6.{pin}", expect=EXPECT_EN)
    c.nc("SW6.4", "SW6.6")

    c.use_part("TCA9535PWR", ref="U1")
    c.net("+3V3_SC", "U1.VCC")
    for cap in c.decouple("U1.VCC", EXPANDER_DECAP, footprint=C_FP):
        cap.fields["LCSC"] = LCSC_100N
    c.net("GND", "U1.GND", "U1.A1", "U1.A2", "U1.A0")
    for k, net in enumerate(P0_MAP):
        c.port(net, f"U1.P0{k}", expect=EXPECT_EN)
    c.port("BU_OVR_LCD_BL", "U1.P10", expect=EXPECT_EN)
    r = c.part(c.auto_ref("R"), "Device:R", SPARE_PULLDOWN, R_FP,
               LCSC=LCSC_100K)
    c.net("BU_OVR_LCD_BL", f"{r.ref}.1")
    c.net("GND", f"{r.ref}.2")
    for pname, net in P1_MAP:
        c.port(net, f"U1.{pname}", expect=EXPECT_EN)
    for net, pin, owner in _FLAG_PORTS:
        c.port(net, f"U1.{pin}", expect=owner)
    for k in (6, 7):
        net = f"BU_P1{k}"
        rr = c.part(c.auto_ref("R"), "Device:R", SPARE_PULLDOWN, R_FP,
                    LCSC=LCSC_100K)
        c.net(net, f"U1.P1{k}", f"{rr.ref}.1")
        c.net("GND", f"{rr.ref}.2")
    c.port("STM32_I2C2_SCL", "U1.SCL",
           kind="i2c", role="scl", bus="STM32_I2C2", speed_hz=I2C_SPEED_HZ,
           expect=J3_MAP)
    c.port("STM32_I2C2_SDA", "U1.SDA",
           kind="i2c", role="sda", bus="STM32_I2C2", speed_hz=I2C_SPEED_HZ,
           expect=J3_MAP)
    c.pullup("U1.SCL", BUS_PULLUP, "+3V3_SC",
             footprint=R_FP).fields["LCSC"] = LCSC_4K7
    c.pullup("U1.SDA", BUS_PULLUP, "+3V3_SC",
             footprint=R_FP).fields["LCSC"] = LCSC_4K7
    c.port("SC_INT_N", "U1.INT#", expect=J3_MAP)
    c.pullup("U1.INT#", INT_PULLUP, "+3V3_SC",
             footprint=R_FP).fields["LCSC"] = LCSC_10K

    for k in range(N_PL_BUTTONS):
        sw = c.use_part("TS-1187A-B-A-B", ref=f"SW{FIRST_BUTTON_REF + k}")
        net = f"PL_BTN{k}"
        cd = c.part(c.auto_ref("C"), "Device:C", DEBOUNCE_CAP, C_FP,
                    LCSC=LCSC_100N)
        c.port(net, f"{sw.ref}.1", f"{sw.ref}.2", f"{cd.ref}.1",
               expect=J12_MAP)
        c.net("GND", f"{sw.ref}.3", f"{sw.ref}.4", f"{cd.ref}.2")
        c.pullup(f"{sw.ref}.1", BUTTON_PULLUP, "+3V3",
                 footprint=R_FP).fields["LCSC"] = LCSC_10K

    # The reset button resets the SC = whole-system reset; the SoM provides its
    # own RC, so only the 100n across the contacts is fitted here.
    c.use_part("TS-1187A-B-A-B", ref="SW5")
    cr = c.part(c.auto_ref("C"), "Device:C", DEBOUNCE_CAP, C_FP,
                LCSC=LCSC_100N)
    c.port("STM32_NRST", "SW5.1", "SW5.2", f"{cr.ref}.1")
    c.net("GND", "SW5.3", "SW5.4", f"{cr.ref}.2")

    rp = c.part(c.auto_ref("R"), "Device:R", PUDC_STRAP, R_FP, LCSC=LCSC_10K)
    c.port("PUDC_34", f"{rp.ref}.2", expect=J3_MAP)
    c.net("GND", f"{rp.ref}.1")

    c.testpoint("+3V3_SC")
    c.testpoint("STM32_I2C2_SDA")
    c.testpoint("STM32_I2C2_SCL")

    c.draws("+3V3_SC", SC_DRAW_A, "TCA9535 + DIP/I2C/INT pull networks "
                                  "(dossier R3 < 5 mA)")
    c.draws("+3V3", BUTTON_DRAW_A, "2x user-button 10k pull-ups when pressed")
    return c
