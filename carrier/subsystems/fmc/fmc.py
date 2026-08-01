from __future__ import annotations

from carrier.basis import register
from schgen.core.model import Circuit

R0603 = "Resistor_SMD:R_0603_1608Metric"
C0603 = "Capacitor_SMD:C_0603_1608Metric"
C0805 = "Capacitor_SMD:C_0805_2012Metric"

HDR_SYM = "Connector_Generic:Conn_02x20_Odd_Even"
HDR_FP = "Connector_PinHeader_2.54mm:PinHeader_2x20_P2.54mm_Vertical"

J35_MAP = "som_j3/j1 bank-35 pin map (dossier fmc.md section 1, P3 linker)"

PAIR_IMPEDANCE = register(
    "fmc.pair_impedance", 100, "ohm",
    "Each bank-35 pair stays typed as a 100R diff pair: the SoM->header PCB "
    "trace is still impedance-controlled. Only the header pads themselves are "
    "not — the nature of a 0.1 in breakout.",
    "policy")

VADJ_LDO = register(
    "fmc.vadj_ldo", "TLV75725PDYDR", "part",
    "Makes +2V5_VADJ from +3V3 as the bank-35 VCCO reference for BOTH these LA "
    "pairs and the camera CSI pairs, and offers it on the header so broken-out "
    "IO sits at the right level. EP pad (pin 6) is netted to GND (DEF-E) — a "
    "real gate-checkable ground, not a layout-only pour bond. Pins: 1=IN 2=GND "
    "3=EN 4=NC 5=OUT 6=EP.",
    "datasheet")

RAIL_BULK = register("fmc.rail_bulk", "10u", "F",
                     "+3V3 bulk shared with J1.1 and the LDO input. "
                     "LCSC C15850.", "datasheet")
RAIL_HF = register("fmc.rail_hf", "100n", "F",
                   "+3V3 bypass at the header. LCSC C14663.", "datasheet")
LDO_IN = register("fmc.ldo_in", "1u", "F",
                  "TLV75725 input cap at U1.IN (pin 1). LCSC C15849.",
                  "datasheet")
LDO_OUT = register("fmc.ldo_out", "10u", "F",
                   "TLV75725 output cap at U1.OUT (pin 5). LCSC C15850.",
                   "datasheet")
HEADER_VADJ_HF = register("fmc.header_vadj_hf", "100n", "F",
                          "At-header +2V5_VADJ bypass, a connector-rail cap "
                          "left to the packer. LCSC C14663.", "datasheet")

HDR_3V3_DRAW_A = register(
    "fmc.hdr_3v3_draw", 0.500, "A",
    "Conservative +3V3 allowance for an add-on on a generic breakout — not a "
    "1 A FMC mezzanine.",
    "policy")

VADJ_DRAW_A = register(
    "fmc.vadj_draw", 0.350, "A",
    "Budget BOOKKEEPING, not a part or thermal ceiling (audit 2026-06-19): the "
    "TLV75725 is a 1 A LDO and the real bank-35 VCCO load is only ~0.05 A. "
    "0.350 here + ~0.05 on som_j3 fills the 0.40 A header allowance, which is "
    "why the rail reports 100 % of budget.",
    "policy")

# Stems keep the FMC_* functional names so the SoM-side FUNCTION_MAP still
# merges — only the carrier-side connector changed from a VITA FMC LPC.
HEADER_PAIRS = (
    ("FMC_CLK0_M2C", 3, 4),
    ("FMC_CLK1_M2C", 5, 6),
    ("FMC_LA00_CC", 9, 10),
    ("FMC_LA01_CC", 11, 12),
    ("FMC_LA02", 13, 14),
    ("FMC_LA03", 17, 18),
    ("FMC_LA04", 19, 20),
    ("FMC_LA05", 21, 22),
    ("FMC_LA06", 25, 26),
    ("FMC_LA07", 27, 28),
    ("FMC_LA08", 29, 30),
    ("FMC_LA09", 33, 34),
    ("FMC_LA10", 35, 36),
    ("FMC_LA11", 37, 38),
)
GND_PINS = (7, 8, 15, 16, 23, 24, 31, 32, 39, 40)


def circuit() -> Circuit:
    c = Circuit("fmc", "SoM bank-35 IO breakout (2x20 2.54mm header, VADJ 2.5V)")

    c.part("J1", HDR_SYM, "Header_2x20_2.54mm", HDR_FP)

    # P on the odd pin, N on the following even pin, so each pair sits
    # side-by-side on one physical row of the stock footprint.
    for stem, p_pin, n_pin in HEADER_PAIRS:
        c.port(f"{stem}_P", f"J1.{p_pin}")
        c.port(f"{stem}_N", f"J1.{n_pin}")
        c.port_type(f"{stem}_P", kind="diff_pair", pair_with=f"{stem}_N",
                    impedance=PAIR_IMPEDANCE, expect=J35_MAP)

    c.use_part(VADJ_LDO, ref="U1",
               footprint="TLV75725PDYDR:TLV75725PDYDR")
    c.part("C1", "Device:C", RAIL_BULK, C0805, LCSC="C15850")
    c.part("C2", "Device:C", RAIL_HF, C0603, LCSC="C14663")
    c.part("C3", "Device:C", LDO_IN, C0603, LCSC="C15849")
    c.part("C4", "Device:C", LDO_OUT, C0805, LCSC="C15850")
    c.part("C5", "Device:C", HEADER_VADJ_HF, C0603, LCSC="C14663")

    c.net("+3V3", "J1.1", "U1.1", "U1.3", "C1.1", "C2.1", "C3.1")
    c.net("+2V5_VADJ", "J1.2", "U1.5", "C4.1", "C5.1")
    c.net("GND", *[f"J1.{p}" for p in GND_PINS],
          "U1.2", "U1.6", "C1.2", "C2.2", "C3.2", "C4.2", "C5.2")
    c.nc("U1.4")

    c.testpoint("+2V5_VADJ")

    c.draws("+3V3", HDR_3V3_DRAW_A, "bank-35 IO header +3V3 add-on allowance")
    c.draws("+2V5_VADJ", VADJ_DRAW_A,
            "VADJ bank-35 VCCO budget (TLV75725 DYD 0.40 A "
            "envelope less ~0.05 A bank-35 VCCO)")
    return c
