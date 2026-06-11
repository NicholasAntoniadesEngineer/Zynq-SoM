"""hdmi_rx — HDMI-A sink: connector + 24C02-class EDID EEPROM + HPD/CEC/5V.

Sink-side reference circuit (mirrors hdmi_tx's connector front end, RX
orientation). The four TMDS lanes run DC-coupled connector -> Zynq HR-bank
pins (TMDS_33 inputs, Digilent Zybo/Nexys-proven sink topology — termination
is the receiver's IBUFDS, no discretes on the lanes). The sink must present
EDID even when the carrier is off (HDMI 1.4 sec 8.5), so a 2-Kbit I2C EEPROM
(ST M24C02, LCSC C7562) sits on the DDC bus powered from the CABLE's +5V
(pin 18): a source can always read — and, with WC# strapped low like common
dev boards, field-(re)program — the EDID. DDC pull-ups live on the SOURCE
side per spec, so none are duplicated here. E0/E1/E2 are grounded (EDID
address 0xA0/0x50).

Hot-plug detect is asserted passively: 1k from the cable's own +5V to HPD
(pin 19) — a plugged source sees its 5V returned on HPD and starts reading
EDID with zero carrier involvement (HPD is 5-V-domain, so it is NOT routed
to a 3V3 FPGA bank). Source presence IS observable: a 10k/15k divider on the
cable 5V gives HDMI_RX_5V_DET (3.15 V max at 5.25 V — LVCMOS33-safe). CEC is
3V3-domain signalling, routed to the FPGA with the spec 27k pull-up to the
gated module rail +3V3_HDMI_RX (carrier/research/bringup_power_gating.md).

Connector: SOFNG HDMI-019S (LCSC C111617). Symbol schgen:HDMI_A_RX is the
local re-pin (DDC rows match the EEPROM's SDA-over-SCL order for straight
runs; TMDS rows at 5.08 mm label pitch; HPD/CEC/shields on the bottom edge);
its pads 20-23 are the shell tabs of the faithful generated footprint
(parts/HDMI-019S/), stacked on pin 20 and tied to CHASSIS_GND like the
ethernet magjack shield (chassis star-bonds to GND elsewhere). Pin 14
(UTILITY/HEAC+) is reserved -> author no-connect (HEAC unused, so pin 19
is plain HPD).
"""

from __future__ import annotations

from schgen.model import Circuit

# DELIBERATE symbol overrides (use_part lib_id=): the RX-direction schgen
# receptacle drawing + the stock EEPROM drawing stay; MPN/LCSC/datasheet +
# the faithful footprints come from parts/HDMI-019S/ + parts/M24C02-WMN6TP/.
J_LIB = "schgen:HDMI_A_RX"
U_LIB = "Memory_EEPROM:M24C02-WMN"
R_FP = "Resistor_SMD:R_0603_1608Metric"
C_FP = "Capacitor_SMD:C_0603_1608Metric"

# connector pin -> TMDS port net (RX direction: lanes IN from the source).
# The SoM contract (carrier/som_interface.json) exposes raw FPGA bank IO_*
# names; the generated J2/J3 sheets (wave 3) carry the bank function map.
J23_MAP = "som_j2_j3_connector (wave 3 FPGA bank function map)"
TMDS_PORTS = {
    1: "HDMI_RX_D2_P", 3: "HDMI_RX_D2_N",
    4: "HDMI_RX_D1_P", 6: "HDMI_RX_D1_N",
    7: "HDMI_RX_D0_P", 9: "HDMI_RX_D0_N",
    10: "HDMI_RX_CLK_P", 12: "HDMI_RX_CLK_N",
}


def circuit() -> Circuit:
    c = Circuit("hdmi_rx", "HDMI RX: HDMI-A sink + EDID EEPROM")
    c.use_part("HDMI-019S", ref="J1", lib_id=J_LIB)
    c.use_part("M24C02-WMN6TP", ref="U1", lib_id=U_LIB)
    c.part("R1", "Device:R", "1k", R_FP, LCSC="C21190")     # HPD assert
    c.part("R2", "Device:R", "27k", R_FP, LCSC="C22967")    # CEC pull-up
    c.part("R3", "Device:R", "10k", R_FP, LCSC="C25804")    # 5V-det divider top
    c.part("R4", "Device:R", "15k", R_FP, LCSC="C22809")    # 5V-det divider bottom
    c.part("C1", "Device:C", "100n", C_FP, LCSC="C14663")   # EEPROM VCC bypass

    # TMDS lanes: 100R differential, DC-coupled to the Zynq HR bank (wave 3)
    for pin, net in TMDS_PORTS.items():
        c.port(net, f"J1.{pin}")
    for lane in ("D0", "D1", "D2", "CLK"):
        c.port_type(f"HDMI_RX_{lane}_P", kind="tmds_pair",
                    pair_with=f"HDMI_RX_{lane}_N", expect=J23_MAP)

    # DDC: source-mastered I2C, EEPROM is the only sink-side device
    c.net("HDMI_RX_SDA", "J1.16", "U1.5")
    c.net("HDMI_RX_SCL", "J1.15", "U1.6")

    # cable +5V domain: EEPROM supply + bypass, HPD assert, presence divider
    c.net("HDMI_RX_5V", "J1.18", "U1.8", "C1.1", "R1.1", "R3.1")
    c.net("GND", "C1.2")
    c.net("HDMI_RX_HPD", "J1.19", "R1.2")
    c.port("HDMI_RX_5V_DET", "R3.2", "R4.1", expect=J23_MAP)
    c.net("GND", "R4.2")

    # CEC to the FPGA, spec 27k pull-up to the gated module rail
    c.port("HDMI_RX_CEC", "J1.13", "R2.2", expect=J23_MAP)
    c.net("+3V3_HDMI_RX", "R2.1")

    # grounds: TMDS shields + DDC/CEC ground on signal GND; shell on chassis
    c.net("GND", "J1.2", "J1.5", "J1.8", "J1.11", "J1.17",
          "U1.1", "U1.2", "U1.3", "U1.4", "U1.7")
    c.net("CHASSIS_GND", "J1.20", "J1.21", "J1.22", "J1.23")

    # pin 14 UTILITY/HEAC+: reserved, HEAC unused by design
    c.nc("J1.14")
    return c
