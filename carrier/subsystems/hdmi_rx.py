"""hdmi_rx — HDMI-A sink: connector + 24C02-class EDID EEPROM + HPD/CEC/5V.

Sink-side reference circuit (mirrors hdmi_tx's connector front end, RX
orientation). The four TMDS lanes run DC-coupled connector -> Zynq HR-bank
pins (TMDS_33 inputs, bank 33 / +VCCO_33 = 3.3 V per the wave-3 function map).

SI-HDMIRX-TERM (electrical audit) — TMDS SINK TERMINATION: an HDMI/DVI sink
MUST present a 50 ohm-to-AVCC source-termination per single-ended line (the
standard 2x 49.9 ohm/pair to a 3.3 V AVCC node + decoupling, 8 R for the 4
pairs). The Zynq RX bank CANNOT supply it: bank 33 is a 7-series HR (high-
range) bank, and in 7-series only HP (high-performance) banks implement on-die
differential termination (DIFF_TERM/_ADV) — the TMDS_33 standard is HR-only and
is explicitly UNTERMINATED on-die (UG471 SelectIO). So the earlier "the IBUFDS
self-terminates, no discretes" assumption was WRONG; external sink termination
is required. RESOLUTION (live-verified, the HDMIRX-1 precedent): the populated
2x49.9 ohm/pair-to-AVCC network is carried as a DOCUMENTED, MANDATORY layout
requirement rather than auto-placed on THIS sheet, for two reasons:
  (a) ELECTRICAL PLACEMENT — TMDS sink termination must sit at the RECEIVER end
      of the line (adjacent to the Zynq bank pins, which are on the SoM-mezzanine
      J2 sheet), NOT at this HDMI connector (camera.py makes the same call:
      "place terminations at the SoM-connector end, not at the FFC"). Resistors
      here would stub the far end of the transmission line and reflect.
  (b) GATE — the 8 termination R's all converge on one AVCC node while the TMDS
      lines exit this sheet as off-sheet ports to the FPGA; the auto-placer's
      AVCC trunk cannot anchor (every R is port-pinned, "fewer than 2 taps"),
      and an in-line populated network crosses the other TMDS lanes — it fails
      the immutable zero-crossing visual gate (the exact HDMIRX-1 ESD-array
      failure class). LAYOUT NOTE (J2 sheet / PCB): per TMDS pair, fit 2x 49.9
      ohm 0603 1% (YAGEO RC0603FR-0749R9L, LCSC C114625, LIVE-verified
      2026-06-13: 458,900 in stock) from each single-ended line to a local
      AVCC = 3.3 V plane island, AVCC bypassed with 100 nF + 1 uF near the bank;
      8 R total for D2/D1/D0/CLK. These are the receiver's sink terminations and
      belong at the FPGA bank balls.

HDMIRX-1 (electrical audit) — RX TMDS ESD: the RX receptacle is user-facing
and the four TMDS pairs reach the FPGA with no ESD (the TX side has the
TPD12S016 clamp). The correct, electrically-verified part is the TI
TPD4E02B04DQAR (LCSC C106794, LIVE-verified 2026-06-13: 39,617 in stock,
Extended; 0.2 pF I/O capacitance typ << the 0.5 pF/line TMDS budget, 8 kV
contact / IEC 61000-4-2): a 4-channel shunt array, so TWO devices cover the
eight TMDS lines (D2+D1 on one, D0+CLK on the other), placed at the jack
between the receptacle and the bank. It is carried here as a DOCUMENTED DNP
STUFFING OPTION (like camera's TPD4E05U06, carrier/subsystems/camera.py
sec "ESD") rather than a populated part: the populated shunt array cannot be
auto-placed on this sheet under the immutable zero-crossing visual gate (the
TMDS sink is off-sheet on the FPGA, so the placer's shunt-cell idiom — which
needs each protected net to touch >=2 on-sheet multi-pin parts — is not
triggered, and an in-line populated array crosses other TMDS lanes). Layout
note for stuffing: place 2x TPD4E02B04DQAR at J1, IO1..IO4 tapping the four
single-ended lines of two adjacent pairs each, both GND pads to GND; the
lanes stay DC-coupled jack -> Zynq (shunt taps, not series). Confirm the
chosen part's IO cap <= 0.5 pF/line before populating. The sink must present
EDID even when the carrier is off (HDMI 1.4 sec 8.5), so a 2-Kbit I2C EEPROM
(ST M24C02, LCSC C7562) sits on the DDC bus powered from the CABLE's +5V
(pin 18): a source can always read the EDID. WC# is write-PROTECTED: it is
HARDWIRED to the EEPROM's own cable-5 V VCC node (HDMI_RX_5V = U1.8, the pin
adjacent to WC#=U1.7), so a runtime DDC write can never corrupt the fixed EDID.
COMP-1 (electrical audit, see the strap block): WC# MUST reference the EEPROM's
own cable-5 V VCC domain, NOT the gated +3V3_HDMI_RX rail — on the gated rail
the protection is defeated (WC# -> 0 V) in the carrier-off EDID-read case and
the 3.3 V level is below the 5 V-VCC EEPROM's VIH(min)=0.7*VCC~3.5 V. The fix
is a NETLIST FIX expressed directly here (WC# tied to HDMI_RX_5V); the earlier
10k strap on the jumper net HDMI_RX_EDID_WP is DELETED — this is a permanently
write-protected, fixed EDID with no field-(re)program path by design. DDC
pull-ups live on the SOURCE side per spec, so none are duplicated here.
E0/E1/E2 are grounded (EDID address 0xA0/0x50).

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

    # TMDS lanes: DC-coupled connector -> Zynq HR bank (bank 33, wave 3). The
    # 2x49.9R/pair sink termination to AVCC lives at the FPGA-bank (J2) end, NOT
    # here — SI-HDMIRX-TERM (docstring): an HR bank does not self-terminate
    # TMDS_33, so external sink termination is REQUIRED, placed at the receiver.
    for pin, net in TMDS_PORTS.items():
        c.port(net, f"J1.{pin}")
    for lane in ("D0", "D1", "D2", "CLK"):
        c.port_type(f"HDMI_RX_{lane}_P", kind="tmds_pair",
                    pair_with=f"HDMI_RX_{lane}_N", expect=J23_MAP)

    # DDC: source-mastered I2C, EEPROM is the only sink-side device
    c.net("HDMI_RX_SDA", "J1.16", "U1.5")
    c.net("HDMI_RX_SCL", "J1.15", "U1.6")

    # cable +5V domain: EEPROM supply + bypass, HPD assert, presence divider,
    # and the EDID WC# write-protect (COMP-1, see the strap block below) —
    # WC# (U1.7) is HARDWIRED to the EEPROM's OWN 5 V VCC node (U1.8, the
    # adjacent pin), so write-protect tracks VCC whenever a source is plugged
    c.net("HDMI_RX_5V", "J1.18", "U1.8", "U1.7", "C1.1", "R1.1", "R3.1")
    c.net("GND", "C1.2")
    c.net("HDMI_RX_HPD", "J1.19", "R1.2")
    c.port("HDMI_RX_5V_DET", "R3.2", "R4.1", expect=J23_MAP)
    c.net("GND", "R4.2")

    # CEC to the FPGA, spec 27k pull-up to the gated module rail
    c.port("HDMI_RX_CEC", "J1.13", "R2.2", expect=J23_MAP)
    c.net("+3V3_HDMI_RX", "R2.1")

    # HDMIRX-2 / COMP-1 (electrical audit): EDID write-protect. WC# (U1.7) is
    # HARDWIRED to the EEPROM's own cable-5 V VCC node HDMI_RX_5V (the adjacent
    # U1.8 pin) above — a NETLIST FIX, not a strap/jumper. This is the EDID a
    # fixed, permanently-write-protected sink: a runtime DDC write cannot
    # corrupt it, and there is no field-(re)program path by design.
    #   * Earlier revisions were WRONG in two ways. WC# started as a hard GND
    #     (write ENABLED — any DDC master could clobber the EDID). HDMIRX-2 then
    #     lifted it to a 10k pull-up on a jumper net HDMI_RX_EDID_WP, but pulled
    #     to +3V3_HDMI_RX, which is WRONG twice:
    #     (1) DOMAIN — +3V3_HDMI_RX is the GATED module rail. In the carrier-OFF
    #         EDID-read case (HDMI 1.4 sec 8.5: a source reads EDID with the sink
    #         board powered down, EEPROM alive on cable 5 V) that rail is dead ->
    #         WC# floats to 0 V -> write-ENABLED. Protection is DEFEATED in
    #         exactly the unattended case it must cover.
    #     (2) LEVEL — the M24C02-W (C7562, ST datasheet) inputs are ratiometric
    #         to its OWN VCC: VIH(min) = 0.7*VCC. The EEPROM runs on cable 5 V
    #         (U1.8 = HDMI_RX_5V), so VIH(min) ~ 3.5 V; a 3.3 V strap cannot
    #         guarantee a logic HIGH on WC# even with the carrier up.
    #   * COMP-1 FIX (live-verified): tie WC# directly to HDMI_RX_5V (the U1.8
    #     node, cable 5 V) -> WC# tracks VCC (VIH met) and write-protect holds
    #     whenever a source is plugged (5 V present), carrier on OR off. No pull-
    #     up resistor and no jumper net: the strap R5 and HDMI_RX_EDID_WP are
    #     DELETED. E0/E1/E2 address straps stay grounded (0xA0/0x50).

    # grounds: TMDS shields + DDC/CEC ground on signal GND; shell on chassis
    c.net("GND", "J1.2", "J1.5", "J1.8", "J1.11", "J1.17",
          "U1.1", "U1.2", "U1.3", "U1.4")
    c.net("CHASSIS_GND", "J1.20", "J1.21", "J1.22", "J1.23")

    # pin 14 UTILITY/HEAC+: reserved, HEAC unused by design
    c.nc("J1.14")

    # power-tree budget (round 4): only the CEC 27k pull-up sits on the gated
    # module rail (~0.12 mA when CEC is driven low). EDID WC# is now hardwired
    # to cable 5 V (COMP-1) so it draws nothing from +3V3_HDMI_RX; EEPROM runs
    # from cable 5 V.
    c.draws("+3V3_HDMI_RX", 0.001, "CEC 27k pull-up (EEPROM + EDID WC# are "
                                   "cable-5V-fed)")
    return c
