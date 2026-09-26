from __future__ import annotations

from carrier.basis import PROJECT, register
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
    from schgen.core.authoring import project_circuit
    return project_circuit(PROJECT, 'bringup_rails', __file__)
