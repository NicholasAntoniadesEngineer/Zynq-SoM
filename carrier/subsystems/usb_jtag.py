"""usb_jtag — cable-free USB-JTAG/UART debug bridge (CH347T, self-powered+isolated).

Stream-C C1. A USB-C cable plugged here gives a host PC a Zynq JTAG programmer
AND a console UART (one CH347 channel each, MODE 3) WITHOUT any external pod —
and it does so even when the carrier's main rails are OFF, because the bridge
runs entirely off its OWN debug-USB VBUS and its JTAG IO is buffered so it
never back-feeds an unpowered carrier (your Q15 answer: SELF-POWERED + ISOLATED).

PART CHOICE — CH347T over the FT2232H. The FT2232H is the canonical dual-channel
FTDI JTAG+UART bridge, but its 64-pin LQFP is far larger than any other carrier
IC (next biggest = 25-pin) and the schgen auto-placer cannot route a 64-pin part
(verified: even a power-only FT2232H fails the escape-lane router — a real engine
limit, not a density the netlist can shed). The WCH CH347T (TSSOP-20) is the
direct, widely-used HS USB->JTAG+UART alternative (the standard low-cost FPGA/CPU
programmer chip): MODE 3 = "USB to high-speed single serial port + USB to JTAG
port" (DS v1A section 5.2 / 4.6) — exactly a JTAG programmer + a console UART in
one. Smaller, fewer support parts (built-in USB termination + built-in EEPROM +
built-in POR), and TSSOP side-only pins place cleanly. The FT2232H/93LC56 parts
fetched earlier are removed.

PARTS (live JLC stock 2026-06-15, JLCPCB parts API):
  * U1  CH347T            C5122332 (1,953, TSSOP-20) — HS USB to JTAG + dual UART
        bridge (MODE 3 = JTAG + UART). Built-in USB-PHY + 1.5k pull-up + series
        matching (UD+/UD- go DIRECT to the bus, DS p.3 note), built-in power-on
        reset, built-in config EEPROM (NO external 93C56 needed). `part add
        C5122332` (parts/CH347T/).
  * Y1  1C208000BC0R      C57131   (32,856, SMD3225-4P) — 8 MHz crystal on XI/XO
        (DS section 5.1: "connect an 8 MHz crystal between XI and XO with ~22 pF
        oscillation caps"). `part add C57131`.
  * U4  AP2112K-3.3TRG1   C51118   (87,465) — the self-powered-island LDO: debug
        USB VBUS (5 V) -> +3V3_DBG. AP2112K is the carrier's standard LDO family
        (power.py uses the 1.8 V sibling). `part add C51118`.
  * U2  SN74LVC125ADR     C7661    (7,330, SOIC-14) — quad 3-state buffer, the
        JTAG ISOLATION buffer (OE-gated; the contention proof below). `part add`.
  (the USB-C UFP receptacle TYPE-C-31-M-12 + the USBLC6-2SC6 D+/D- ESD live on
  the usb_jtag_connector sheet — the carrier's "connectors get their own sheet"
  idiom, twin of usb_uart_connector; that sheet publishes +5V_DBG (the VBUS
  rail) + DBG_USB_DP/DM (the protected pair) for this bridge to consume.)

POWER — SELF-POWERED ISLAND (constraint C1, satisfied structurally). The whole
bridge is powered from +3V3_DBG, which U4 (AP2112K) regulates from +5V_DBG (the
debug cable's own 5 V VBUS) — NOT from any carrier rail. So:
  * the bridge is ALIVE only while the debug USB cable is plugged in (C1: "only
    powered when the debug cable is present"), and
  * it can program / console a carrier whose +VIN/+3V3/+1V8 are all OFF.
The CH347 is a single-supply 3.3 V part (DS section 5.1 / 6.2: VCC 3.0-3.6 V,
ICC ~38 mA typ): VCC(14) <- +3V3_DBG with a 100n decoupling cap; built-in POR
(RST# pin 1 has an internal pull-up — only an optional external 10k is added for
noise immunity, NO RC by design).

MODE 3 STRAP (JTAG + UART). The CH347 latches its working mode from DTR1(10) and
RTS1(13) at power-on reset (DS section 5.2 table): MODE 3 = "DTR1 pulls down low,
RTS1 pulls down low". So both carry a 10k pulldown to GND here -> the bridge
always enumerates as one UART + one JTAG TAP. (Both pins have built-in pull-ups,
so the external 10k pulldowns must dominate -> 10k vs the ~40k internal.)

ISOLATION / CONTENTION PROOF (LAW-0). The carrier already exposes ZYNQ_TCK/TMS/
TDI/TDO on the debug_boot 2x7 JTAG header (a passive connector + TMS/TDI 4k7
insurance pulls). If the CH347 drove those nets directly it would (a) fight a
JTAG pod plugged into that header, and (b) back-feed the Zynq's JTAG inputs when
the carrier is OFF. U2 (SN74LVC125, quad 3-state buffer) breaks both:
  * The three CH347 JTAG OUTPUTS TCK/TDI/TMS pass through three buffer gates
    whose OUTPUTS drive ZYNQ_TCK/ZYNQ_TDI/ZYNQ_TMS; the fourth gate buffers
    ZYNQ_TDO back to the CH347 TDO INPUT. When the buffer is DISABLED every
    output is Hi-Z.
  * ALL FOUR OE# pins are tied to DBG_JTAG_OE_N, gated by SW1 (DSHP04 pos 1):
    DEFAULT-OFF — a 100k pull-up to +3V3_DBG holds OE# HIGH (outputs Hi-Z) until
    a human closes SW1 to pull OE# LOW. So:
      - power-up / cable-just-plugged: OE# high -> buffer Hi-Z -> the header pod
        (or the Zynq) owns JTAG, ZERO contention by default;
      - carrier OFF, debug USB plugged, SW1 OPEN: +3V3_DBG alive but OE# high ->
        outputs Hi-Z -> NO drive onto the (unpowered) Zynq JTAG inputs -> no
        back-feed (the LVC125 Ioff partial-power-down spec keeps the disabled
        output Hi-Z even with the downstream rail at 0 V);
      - user closes SW1 only when they intend to program from the bridge AND no
        pod is on the header -> exactly one JTAG master at a time.
  * U2 itself is powered from +3V3_DBG (the USB island), so when the debug cable
    is UNPLUGGED the buffer is unpowered -> outputs Hi-Z regardless of SW1.
This is the "buffer / bus-switch with OE" the brief asks for: a tap, never a
hard short; the OE default + the USB-island power make contention structurally
impossible without a deliberate human action. (CH347 TRST is left NC — the Zynq
dedicated-JTAG bank has no TRST and the debug_boot header doesn't expose one;
TRST is an OPTIONAL JTAG line per the CH347 DS section 5.6.)

CHANNELS (MODE 3 pin map, DS section 4.6):
  * JTAG: TCK(6), TMS(5), TDI(7) -> buffer -> ZYNQ_TCK/TMS/TDI; ZYNQ_TDO ->
    buffer -> TDO(8, CH347 input, has an internal pull-up). TRST(9) NC.
  * UART console (UART1): TXD1(3) -> DBG_UART_RXD (Zynq RXD), RXD1(4) <-
    DBG_UART_TXD (Zynq TXD) -> a free PL-bank UART (bank 13 EMIO), bound via the
    FUNCTION_MAP to DBG_UART_RXD (J2.42) / DBG_UART_TXD (J2.40). 2-wire console;
    CTS1/RTS1/DTR1 modem lines are the mode strap / unused. Bank 13 is +VCCO_13
    = +3V3 = LVCMOS33, matching the CH347 3.3 V IO (level-safe).
"""

from __future__ import annotations

from schgen.core.model import Circuit

R0603 = "Resistor_SMD:R_0603_1608Metric"
C0603 = "Capacitor_SMD:C_0603_1608Metric"
C0805 = "Capacitor_SMD:C_0805_2012Metric"

LCSC_100N = "C14663"     # 100n X7R 0603
LCSC_1U = "C15849"      # 1u 0603 X7R (LDO Cin)
LCSC_10U = "C15850"     # 10u 0805 bulk
LCSC_22P = "C1653"      # 22p C0G 0603 (crystal load), JLC Basic
LCSC_10K = "C25804"     # 10k 1% 0603
LCSC_100K = "C25803"    # 100k 1% 0603 (OE default pull-up)

USB_MAP = "usb_jtag_connector (USB-C UFP receptacle + USBLC6 ESD)"
J2_MAP = "som_j2_connector (PL bank 13 EMIO UART, LVCMOS33 — FUNCTION_MAP)"
HDR_MAP = "debug_boot (the 2x7 JTAG header carries the same ZYNQ_T* nets)"


def circuit() -> Circuit:
    c = Circuit("usb_jtag",
                "USB-JTAG/UART debug bridge: CH347T, self-powered + isolated")

    # =====================================================================
    # self-powered island LDO: debug-USB VBUS (+5V_DBG, from the USB-C
    # receptacle on usb_jtag_connector) -> +3V3_DBG. +5V_DBG is alive ONLY
    # with the debug cable plugged -> the whole bridge is too (constraint C1).
    # =====================================================================
    c.use_part("AP2112K-3.3TRG1", ref="U4")
    c.net("+5V_DBG", "U4.VIN", "U4.EN")               # EN tied on (alive on VBUS)
    c.net("+3V3_DBG", "U4.VOUT")
    c.net("GND", "U4.GND")
    c.nc("U4.NC")
    for cap in c.decouple("U4.VIN", "1u", footprint=C0603):
        cap.fields["LCSC"] = LCSC_1U                  # LDO Cin
    for cap in c.decouple("U4.VOUT", "10u", footprint=C0805):
        cap.fields["LCSC"] = LCSC_10U                 # AP2112K needs >=1u Cout
    for cap in c.decouple("U4.VOUT", "100n", footprint=C0603):
        cap.fields["LCSC"] = LCSC_100N

    # =====================================================================
    # CH347T — the bridge (MODE 3 = JTAG + UART)
    # =====================================================================
    c.use_part("CH347T", ref="U1", value="CH347T")
    c.net("+3V3_DBG", "U1.14")                         # VCC (3.3 V single supply)
    c.net("GND", "U1.18")                              # GND
    for cap in c.decouple("U1.14", "100n", footprint=C0603):
        cap.fields["LCSC"] = LCSC_100N                # DS: ~0.1u on VCC

    # USB to the ESD-protected pair from the connector sheet (UD+ = 17, UD- =
    # 16). The CH347 UD+/UD- take the bus DIRECTLY (DS forbids a series R); the
    # USBLC6 on usb_jtag_connector is a SHUNT array, no series element added.
    c.port("DBG_USB_DP", "U1.17")                     # protected UD+
    c.port("DBG_USB_DM", "U1.16")                     # protected UD-
    c.port_type("DBG_USB_DP", kind="usb_hs_pair", pair_with="DBG_USB_DM",
                expect=USB_MAP)

    # 8 MHz crystal on XI(19)/XO(20) with 22p load caps (DS section 5.1)
    c.use_part("1C208000BC0R", ref="Y1", value="8MHz")
    c.net("DBG_XI", "U1.19", "Y1.1")                  # OSC1
    c.net("DBG_XO", "U1.20", "Y1.3")                  # OSC2
    c.net("GND", "Y1.2", "Y1.4")                      # crystal shield/NC pads
    for sig in ("DBG_XI", "DBG_XO"):
        cap = c.part(c.auto_ref("C"), "Device:C", "22p", C0603, LCSC=LCSC_22P)
        c.net(sig, f"{cap.ref}.1")
        c.net("GND", f"{cap.ref}.2")

    # RST#(1): built-in POR + internal pull-up; add an external 10k for noise
    # immunity (no RC cap by design — the CH347 has its own power-on reset)
    c.net("DBG_RST_N", "U1.1")
    c.pullup("U1.1", "10k", "+3V3_DBG").fields["LCSC"] = LCSC_10K

    # MODE 3 strap: DTR1(10) low + RTS1(13) low -> JTAG + UART (DS section 5.2).
    # Both have internal pull-ups; the 10k pulldowns dominate at reset.
    c.net("DBG_MODE_DTR1", "U1.10")
    c.net("DBG_MODE_RTS1", "U1.13")
    r_d = c.part(c.auto_ref("R"), "Device:R", "10k", R0603, LCSC=LCSC_10K)
    c.net("DBG_MODE_DTR1", f"{r_d.ref}.1")
    c.net("GND", f"{r_d.ref}.2")
    r_r = c.part(c.auto_ref("R"), "Device:R", "10k", R0603, LCSC=LCSC_10K)
    c.net("DBG_MODE_RTS1", f"{r_r.ref}.1")
    c.net("GND", f"{r_r.ref}.2")

    # unused: CTS1(2), GPIO/SCL(11), GPIO/SDA(12), ACT/DCD0(15), TRST(9 — NC,
    # the Zynq dedicated-JTAG has no TRST line; OPTIONAL per the CH347 DS)
    c.nc("U1.2", "U1.9", "U1.11", "U1.12", "U1.15")

    # =====================================================================
    # Channel A = JTAG through the SN74LVC125 isolation buffer (contention
    # proof in the header). CH347 MODE-3 JTAG: TCK=6, TMS=5, TDI=7, TDO=8.
    # =====================================================================
    c.use_part("SN74LVC125ADR", ref="U2")
    c.net("+3V3_DBG", "U2.14")                         # VCC: buffer on the island
    c.net("GND", "U2.7")                               # GND
    for cap in c.decouple("U2.14", "100n", footprint=C0603):
        cap.fields["LCSC"] = LCSC_100N

    # CH347 channel-A JTAG pins (the buffer-INPUT side)
    c.net("DBG_FT_TCK", "U1.6")                        # TCK out
    c.net("DBG_FT_TMS", "U1.5")                        # TMS out
    c.net("DBG_FT_TDI", "U1.7")                        # TDI out
    c.net("DBG_FT_TDO", "U1.8")                        # TDO in (internal pull-up)

    # SN74LVC125 pins by NUMBER: 1OE#=1,1A=2,1Y=3,2OE#=4,2A=5,2Y=6,GND=7,
    # 3Y=8,3A=9,3OE#=10,4Y=11,4A=12,4OE#=13,VCC=14.
    # gate 1: TCK (1A=2) -> 1Y(3) -> ZYNQ_TCK
    c.net("DBG_FT_TCK", "U2.2")
    c.port("ZYNQ_TCK", "U2.3", expect=HDR_MAP)
    # gate 2: TDI (2A=5) -> 2Y(6) -> ZYNQ_TDI
    c.net("DBG_FT_TDI", "U2.5")
    c.port("ZYNQ_TDI", "U2.6", expect=HDR_MAP)
    # gate 4: TMS (4A=12) -> 4Y(11) -> ZYNQ_TMS
    c.net("DBG_FT_TMS", "U2.12")
    c.port("ZYNQ_TMS", "U2.11", expect=HDR_MAP)
    # gate 3 REVERSE: ZYNQ_TDO (3A=9) -> 3Y(8) -> CH347 TDO (it reads)
    c.port("ZYNQ_TDO", "U2.9", expect=HDR_MAP)
    c.net("DBG_FT_TDO", "U2.8")

    # OE# (all four: 1OE#=1, 2OE#=4, 3OE#=10, 4OE#=13) = DBG_JTAG_OE_N:
    # default-HIGH via 100k -> outputs Hi-Z, closed by SW1 (DSHP04 pos 1) to
    # GND to ENABLE the bridge's JTAG. THE CONTENTION GUARD (see header):
    # default-off, USB-island powered.
    c.net("DBG_JTAG_OE_N", "U2.1", "U2.4", "U2.10", "U2.13")
    c.pullup("U2.1", "100k", "+3V3_DBG").fields["LCSC"] = LCSC_100K
    c.use_part("DSHP04TSGER", ref="SW1")
    c.net("DBG_JTAG_OE_N", "SW1.1")                   # pos 1 closes OE# -> GND
    c.net("GND", "SW1.8")
    c.nc("SW1.2", "SW1.3", "SW1.4", "SW1.5", "SW1.6", "SW1.7")

    # =====================================================================
    # Channel B = console UART1 to a free PL-bank UART (bank 13 EMIO).
    # TXD1=3, RXD1=4 (2-wire console).
    # =====================================================================
    c.port("DBG_UART_RXD", "U1.3", expect=J2_MAP)     # TXD1 -> Zynq RXD
    c.port("DBG_UART_TXD", "U1.4", expect=J2_MAP)     # RXD1 <- Zynq TXD

    # ---- coverage + budget ----------------------------------------------
    c.testpoint("+3V3_DBG")                            # the USB island rail
    c.testpoint("DBG_UART_TXD")                        # console bring-up probe
    c.testpoint("DBG_UART_RXD")

    # power budget: everything rides +3V3_DBG, which U4 (AP2112K, 600 mA)
    # sources from +5V_DBG. CH347 ICC ~38 mA typ (DS 6.2) + buffer + pulls.
    c.draws("+3V3_DBG", 0.045,
            "CH347 ~38 mA typ (DS) + SN74LVC125 + RST/mode/OE pull network")

    # design-rule waiver: DBG_RST_N (CH347 RST#) is a defined-high reset with a
    # 10k pull-up only — NO RC cap by design. The CH347 has a built-in power-on
    # reset circuit (DS section 5.1) and RST# carries its own internal pull-up;
    # the external 10k is noise-immunity insurance. A runtime reset is host-/
    # driver-mediated over USB, not an RC ramp.
    c.waive_reset("DBG_RST_N",
                  "CH347 RST#: 10k pull-up + the chip's built-in power-on reset "
                  "(DS 5.1); no external RC cap fitted by design")
    return c
