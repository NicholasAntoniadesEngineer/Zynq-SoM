"""fmc — SoM bank-35 IO broken out on a generic 2.54 mm header.

HISTORY (2026-06-18, user request). This site WAS a VITA 57.1 FMC LPC mezzanine
connector (Samtec ASP-134603-01) exposing the SoM bank-35 LVDS pairs. Per user
request the proprietary FMC connector was REPLACED with a generic 2x20 0.1" /
2.54 mm pin header so the SAME SoM bank-35 IO is broken out to a cheap,
universally-wireable header — no specific FMC mezzanine card required.

WHAT IS UNCHANGED. The 14 differential pairs (CLK0/CLK1_M2C + LA00-LA11) keep
their FUNCTIONAL port names (FMC_LA00_CC_P ...), so they still bind to the same
SoM bank-35 pins on som_j1/som_j3 — the FUNCTION_MAP (som_conn_gen.py), the XDC
pin constraints and the SI diff-pair constraints all reference the SoM side, not
this connector, and so are untouched by the swap. Each pair stays typed as a
100 R diff pair (the SoM->header PCB trace is still impedance-controlled; only
the header pads themselves are not — the nature of a 0.1" breakout).

VADJ RETAINED. +2V5_VADJ from the TLV75725PDYDR LDO (fed by +3V3) is kept: it is
the bank-35 VCCO reference for BOTH these LA pairs AND the camera CSI pairs, and
is offered on the header so the broken-out IO sits at the correct 2.5 V level.
The LDO's EP pad (pin 6) is netted to GND (DEF-E) — a real, gate-checkable
ground, not a layout-only pour bond. Pin map 1=IN 2=GND 3=EN 4=NC 5=OUT 6=EP.

WHAT IS GONE WITH THE CONNECTOR. The FMC-mezzanine management — GA address
straps, PRSNT_M2C/PG_C2M presence, the JTAG bypass chain, the mezzanine EEPROM
(0x50), the 400-pin VITA grid and its 61-GND census — is all meaningless on a
generic header and was removed.

HEADER PINOUT (Conn_02x20, 2.54 mm; P on the odd pin / N on the even pin of each
physical row so a pair sits side-by-side; a GND row every ~3 pairs for
return-current locality; +3V3 and +2V5_VADJ on row 1 so an add-on can be
powered + level-referenced from the header):

     1  +3V3          2  +2V5_VADJ
     3  CLK0_M2C_P    4  CLK0_M2C_N
     5  CLK1_M2C_P    6  CLK1_M2C_N
     7  GND           8  GND
     9  LA00_CC_P    10  LA00_CC_N
    11  LA01_CC_P    12  LA01_CC_N
    13  LA02_P       14  LA02_N
    15  GND          16  GND
    17  LA03_P       18  LA03_N
    19  LA04_P       20  LA04_N
    21  LA05_P       22  LA05_N
    23  GND          24  GND
    25  LA06_P       26  LA06_N
    27  LA07_P       28  LA07_N
    29  LA08_P       30  LA08_N
    31  GND          32  GND
    33  LA09_P       34  LA09_N
    35  LA10_P       36  LA10_N
    37  LA11_P       38  LA11_N
    39  GND          40  GND

The header is a STOCK KiCad part (Connector_Generic:Conn_02x20_Odd_Even +
Connector_PinHeader_2.54mm:PinHeader_2x20_P2.54mm_Vertical, with KiCad's own 3D
model) — faithful, not hand-built. It is intentionally generic: the integrator
picks the exact orderable 2x20 0.1" header (LCSC left open).
"""

from __future__ import annotations

from schgen.core.model import Circuit

R0603 = "Resistor_SMD:R_0603_1608Metric"
C0603 = "Capacitor_SMD:C_0603_1608Metric"
C0805 = "Capacitor_SMD:C_0805_2012Metric"

HDR_SYM = "Connector_Generic:Conn_02x20_Odd_Even"
HDR_FP = "Connector_PinHeader_2.54mm:PinHeader_2x20_P2.54mm_Vertical"

J35_MAP = "som_j3/j1 bank-35 pin map (dossier fmc.md section 1, P3 linker)"

# (functional stem, header P pin, header N pin). Stems keep the FMC_* functional
# names so the SoM-side binding (som_conn_gen FUNCTION_MAP) still merges — only
# the carrier-side connector changed. VITA spelled the clock-capable pairs
# LAnn_*_CC; that is preserved in the stem so the bound names are byte-stable.
HEADER_PAIRS = (
    ("FMC_CLK0_M2C", 3, 4),     # -> IO_L12_MRCC_*_35
    ("FMC_CLK1_M2C", 5, 6),     # -> IO_L11_SRCC_*_35
    ("FMC_LA00_CC", 9, 10),     # -> IO_L14_SRCC_*_35
    ("FMC_LA01_CC", 11, 12),    # -> IO_L21_DQS_*_35
    ("FMC_LA02", 13, 14),       # -> IO_L17_*_35
    ("FMC_LA03", 17, 18),       # -> IO_L20_*_35
    ("FMC_LA04", 19, 20),       # -> IO_L22_*_35
    ("FMC_LA05", 21, 22),       # -> IO_L23_*_35
    ("FMC_LA06", 25, 26),       # -> IO_L24_*_35
    ("FMC_LA07", 27, 28),       # -> IO_L19_*_35
    ("FMC_LA08", 29, 30),       # -> IO_L1_*_35
    ("FMC_LA09", 33, 34),       # -> IO_L4_*_35
    ("FMC_LA10", 35, 36),       # -> IO_L5_*_35
    ("FMC_LA11", 37, 38),       # -> IO_L6_*_35
)
GND_PINS = (7, 8, 15, 16, 23, 24, 31, 32, 39, 40)


def circuit() -> Circuit:
    c = Circuit("fmc", "SoM bank-35 IO breakout (2x20 2.54mm header, VADJ 2.5V)")

    # generic 2x20 0.1" header — stock KiCad symbol+footprint+3D (faithful)
    c.part("J1", HDR_SYM, "Header_2x20_2.54mm", HDR_FP)

    # ---- the 14 SoM bank-35 pairs -> typed 100R diff ports ------------------
    for stem, p_pin, n_pin in HEADER_PAIRS:
        c.port(f"{stem}_P", f"J1.{p_pin}")
        c.port(f"{stem}_N", f"J1.{n_pin}")
        c.port_type(f"{stem}_P", kind="diff_pair", pair_with=f"{stem}_N",
                    impedance=100, expect=J35_MAP)

    # ---- VADJ LDO: +3V3 -> TLV75725 (DYD thermal-pad) -> +2V5_VADJ ----------
    # EN strapped on; in/out caps; EP pad (pin 6) netted to GND (DEF-E). Retained
    # because +2V5_VADJ is the bank-35 VCCO reference (these LA pairs + the
    # camera CSI pairs) and is offered on the header for level-matched IO.
    c.use_part("TLV75725PDYDR", ref="U1",
               footprint="TLV75725PDYDR:TLV75725PDYDR")
    c.part("C1", "Device:C", "10u", C0805, LCSC="C15850")     # +3V3 bulk
    c.part("C2", "Device:C", "100n", C0603, LCSC="C14663")    # +3V3 bypass
    c.part("C3", "Device:C", "1u", C0603, LCSC="C15849")      # LDO in
    c.part("C4", "Device:C", "10u", C0805, LCSC="C15850")     # LDO out
    c.part("C5", "Device:C", "100n", C0603, LCSC="C14663")    # at-header VADJ

    c.net("+3V3", "J1.1", "U1.1", "U1.3", "C1.1", "C2.1", "C3.1")
    c.net("+2V5_VADJ", "J1.2", "U1.5", "C4.1", "C5.1")
    c.net("GND", *[f"J1.{p}" for p in GND_PINS],
          "U1.2", "U1.6", "C1.2", "C2.2", "C3.2", "C4.2", "C5.2")
    c.nc("U1.4")

    # round-4 coverage gate: the locally-generated VADJ rail is probeable
    c.testpoint("+2V5_VADJ")

    # power-tree budget: a generic breakout (not a 1 A FMC mezzanine) — a modest
    # +3V3 allowance for an add-on; +2V5_VADJ holds the bank-35 VCCO envelope
    # (the 12 LA pairs + 3 camera CSI pairs ride it; TLV75725 DYD 0.40 A thermal
    # envelope less ~0.05 A bank-35 VCCO).
    c.draws("+3V3", 0.500, "bank-35 IO header +3V3 add-on allowance")
    c.draws("+2V5_VADJ", 0.350, "VADJ bank-35 VCCO budget (TLV75725 DYD 0.40 A "
                                "envelope less ~0.05 A bank-35 VCCO)")
    return c
