"""pmod — 2x Digilent-standard Pmod host ports (J2 bank 13, LVCMOS33).

Per carrier/research/debug_boot_pmod.md (d): each host port is a 2x6
right-angle FEMALE 2.54 mm socket at the board edge (CONNFLY DS1024-2x6R2,
the spec-exact part; BOOMELE C36191 straight female is the committed
stock fallback). Pmod pin numbering is row-major (top row 1-6, bottom row
7-12; 1-4 = IO1-4, 5 = GND, 6 = VCC, 7-10 = IO5-8, 11 = GND, 12 = VCC) —
NOT the generic 2x6 zigzag. The generated DS1024-2x6R2 footprint IS
zigzag-numbered (odd pads = one row, even pads = the other, vertical
column pairs (2k-1, 2k)), so PAD maps Pmod positions onto connector pads:
top-row position p -> pad 2p-1, bottom-row position p -> pad 2(p-6).
Verify odd-row = top row against the DS1024 datasheet drawing at layout.

Digilent-standard protection: 200R series on every IO (C8218 Basic).
Signals are 8 full bank-13 LVDS-capable pairs from J2 (pairs kept intact,
no MRCC/SRCC pins) — REQUIRES +VCCO_13 = +3V3 in the rail map. VCC pins
feed from the bring-up-gated +3V3_PMOD rail with 100n + 10u per port
(~100 mA budget per module per the Pmod spec).
"""

from __future__ import annotations

from schgen.model import Circuit

R0603 = "Resistor_SMD:R_0603_1608Metric"
C0603 = "Capacitor_SMD:C_0603_1608Metric"
C0805 = "Capacitor_SMD:C_0805_2012Metric"

BRINGUP = "bringup (gated +3V3_PMOD rail)"
J2_MAP = "som_j2_connector"

# Pmod logical position (1-12, row-major per the Digilent spec) -> connector
# pad number (zigzag, columns left-to-right at the mating face).
PAD = {p: 2 * p - 1 for p in range(1, 7)}        # top row 1-6 -> odd pads
PAD.update({p: 2 * (p - 6) for p in range(7, 13)})  # bottom 7-12 -> even pads

# Pmod IO index (1-8) -> logical position on the socket.
IO_POS = {1: 1, 2: 2, 3: 3, 4: 4, 5: 7, 6: 8, 7: 9, 8: 10}

# SoM J2 bank-13 nets, VERBATIM from carrier/som_interface.json (note
# IO_L5P_13 has no underscore before P — SoM symbol quirk, do not "fix").
PORT_NETS = {
    "PMOD0": ["IO_L2_P_13", "IO_L2_N_13", "IO_L3_P_13", "IO_L3_N_13",
              "IO_L4_P_13", "IO_L4_N_13", "IO_L5P_13", "IO_L5_N_13"],
    "PMOD1": ["IO_L7_P_13", "IO_L7_N_13", "IO_L8_P_13", "IO_L8_N_13",
              "IO_L9_DQS_P_13", "IO_L9_DQS_N_13", "IO_L10_P_13",
              "IO_L10_N_13"],
}


def circuit() -> Circuit:
    c = Circuit("pmod", "2x Pmod host ports (bank 13, 200R series, gated 3V3)")
    vcc_pins: list[str] = []
    gnd_pins: list[str] = []
    rnum = 1
    for jref, port in (("J1", "PMOD0"), ("J2", "PMOD1")):
        c.use_part("DS1024-2x6R2", ref=jref)   # zigzag pads stay numeric

        # ---- IOs: SoM bank-13 net (port) -> 200R -> socket pin ------------
        for io, som_net in enumerate(PORT_NETS[port], start=1):
            ref = f"R{rnum}"
            rnum += 1
            c.part(ref, "Device:R", "200R", R0603, LCSC="C8218")
            c.port(som_net, f"{ref}.1", expect=J2_MAP)
            c.net(f"{port}_IO{io}", f"{ref}.2", f"{jref}.{PAD[IO_POS[io]]}")

        # ---- power pins (positions 5/11 = GND, 6/12 = VCC) -----------------
        gnd_pins += [f"{jref}.{PAD[5]}", f"{jref}.{PAD[11]}"]
        vcc_pins += [f"{jref}.{PAD[6]}", f"{jref}.{PAD[12]}"]

    # gated module rail: both ports' VCC + 100n/10u per port
    c.part("C1", "Device:C", "100n", C0603, LCSC="C1591")
    c.part("C2", "Device:C", "10u", C0805, LCSC="C15850")
    c.part("C3", "Device:C", "100n", C0603, LCSC="C1591")
    c.part("C4", "Device:C", "10u", C0805, LCSC="C15850")
    # +3V3_PMOD is the bring-up-gated module rail (SY6280 #7 on
    # bringup_modules): a POWER net with its own symbol, like +5V_USB.
    c.net("+3V3_PMOD", *vcc_pins, "C1.1", "C2.1", "C3.1", "C4.1")
    c.net("GND", *gnd_pins, "C1.2", "C2.2", "C3.2", "C4.2")

    # power-tree budget (round 4): 2 host ports x ~100 mA module budget
    # (Digilent Pmod spec, debug_boot_pmod.md)
    c.draws("+3V3_PMOD", 0.200, "2x Pmod module budget ~100 mA each")
    return c
