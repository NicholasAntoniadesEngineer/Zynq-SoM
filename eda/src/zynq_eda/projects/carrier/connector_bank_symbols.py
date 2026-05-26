"""Carrier-board sub-symbol generator for high-density connectors.

The carrier's 4 high-pin-count connectors (J1/J2/J3 = three 168-pin FX10A
SoM mates, plus the 160-pin FMC LPC) and the 40-pin LVDS FFC are too dense
to render legibly on a single sheet. We split each across multiple bank
sub-sheets, each rendering its own KiCad sub-symbol carved out of the
parent's pin list (same pin names + numbers + footprint, just fewer
pins per sheet).

Multi-unit KiCad symbols would be the textbook solution; this module uses
distinct sub-symbols and lets the BOM emitter collapse them by
(value, footprint) into one BOM line per physical part.

The bank pin lists below distribute the parent's pin space across N
banks. Each bank symbol lands in
``shared/symbols/generated/connector_banks/<NAME>.kicad_sym`` and is
registered in ``board.SHARED_SYMBOL_LIBRARIES``.
"""

from __future__ import annotations

from pathlib import Path

from zynq_eda.catalog.connector_banks import emit_bank_symbol


# Repo root (5 levels up from this file).
_REPO_ROOT = Path(__file__).resolve().parents[5]
PARENT_LIB_PATH = _REPO_ROOT / "shared" / "symbols" / "zynq_eda.kicad_sym"
BANK_OUTPUT_DIR = _REPO_ROOT / "shared" / "symbols" / "generated" / "connector_banks"


# Pin distributions for each bank.
# ============================================================================
# FX10A 168-pin connector (SoM mate). Pins A1..A84 + B1..B84.
# Split into 3 banks per J-connector ≈ 56 pins/bank.

def _fx10a_pins(a_range: range, b_range: range) -> tuple[str, ...]:
    return tuple(f"A{i}" for i in a_range) + tuple(f"B{i}" for i in b_range)


# J1 (PS-side: MIO + system rails) banks
J1_BANK_MIO_PINS         = _fx10a_pins(range(1, 28),  range(1, 28))   # A1..A27 + B1..B27 = 54
J1_BANK_PS_AUX_PINS      = _fx10a_pins(range(28, 55), range(28, 55))  # A28..A54 + B28..B54 = 54
J1_BANK_PL_POWER_GND_PINS = _fx10a_pins(range(55, 85), range(55, 85)) # A55..A84 + B55..B84 = 60

# J2 (PL bank 13: high-speed I/O) banks
J2_BANK_DIFF_PAIRS_PINS  = _fx10a_pins(range(1, 28),  range(1, 28))   # 54
J2_BANK_SE_PINS          = _fx10a_pins(range(28, 55), range(28, 55))  # 54
J2_BANK_POWER_PINS       = _fx10a_pins(range(55, 85), range(55, 85))  # 60

# J3 (PL bank 35: single-ended + auxiliary) banks
J3_BANK_DIFF_PAIRS_PINS  = _fx10a_pins(range(1, 28),  range(1, 28))   # 54
J3_BANK_SE_PINS          = _fx10a_pins(range(28, 55), range(28, 55))  # 54
J3_BANK_POWER_PINS       = _fx10a_pins(range(55, 85), range(55, 85))  # 60


# FMC LPC 160-pin connector — columns C/D/G/H, rows 1..40.
# Split by FUNCTION (LA pair index range and power/clk/jtag), enumerating
# the actual pins each bank needs so the sub-symbol's pin set matches the
# bank's pin_to_net assignments.

# LA00..LA15 pin pairs from the VITA 57.1 LPC table.
_FMC_LA_LOW_PAIR_PINS = (
    "G6","G7", "D8","D9", "H7","H8", "G9","G10", "H10","H11", "D11","D12",
    "C10","C11", "H13","H14", "G12","G13", "D14","D15", "C14","C15",
    "H16","H17", "G15","G16", "D17","D18", "C18","C19", "H19","H20",
)
# GND pins paired with LA00..LA15 area (rows 1..21).
_FMC_LA_LOW_GND_PINS = (
    "C1", "C2", "C5", "C8", "C11", "C14", "C17", "C20",
    "D1", "D2", "D5", "D11", "D14", "D17", "D20",
    "G1", "G4", "G10", "G13", "G16", "G19",
    "H1", "H10", "H13", "H16", "H19",
)
FMC_LA_LOW_PINS = tuple(
    dict.fromkeys(_FMC_LA_LOW_PAIR_PINS + _FMC_LA_LOW_GND_PINS)
)

# LA16..LA33 pin pairs from the VITA 57.1 LPC table.
_FMC_LA_HIGH_PAIR_PINS = (
    "G18","G19", "D20","D21", "C22","C23", "H22","H23", "G21","G22",
    "H25","H26", "G24","G25", "D23","D24", "H28","H29", "G27","G28",
    "D26","D27", "C26","C27", "H31","H32", "G30","G31", "H34","H35",
    "G33","G34", "H37","H38", "G36","G37",
)
_FMC_LA_HIGH_GND_PINS = (
    "C23", "C26", "C29", "C32",
    "D23", "D26", "D29",
    "G22", "G25", "G28", "G31", "G34", "G37",
    "H22", "H25", "H28", "H31", "H34", "H37",
)
FMC_LA_HIGH_PINS = tuple(
    dict.fromkeys(_FMC_LA_HIGH_PAIR_PINS + _FMC_LA_HIGH_GND_PINS)
)

# Power + clocks + mgmt + JTAG (the catch-all bank).
_FMC_PWR_CLK_JTAG_PINS = (
    # Power pins
    "C35", "C37",                  # +12V
    "C39", "D36", "D38", "D40",    # +3V3
    "C36", "C38", "C40", "D35", "D37", "D39",  # VADJ
    # Management I2C
    "C30", "C31",
    # JTAG
    "D29", "D30", "D31", "D32", "D33",
    # PRSNT
    "H2",
    # Clocks (CLK0_M2C, CLK1_M2C)
    "H4", "H5", "G2", "G3",
    # GND pins in this region
    "H40", "C32",
)
FMC_PWR_CLK_JTAG_PINS = tuple(dict.fromkeys(_FMC_PWR_CLK_JTAG_PINS))


# FFC 40-pin LVDS LCD connector — pins "1".."40".
# Pin types in source library:
#   1: GND_1 (power_in)
#   2: +3V3 (power_in)
#   3: +3V3_3 (power_in)
#   4: EDID_SDA (bidirectional)
#   5: EDID_SCL (output)
#   ... then LVDS pairs + GND interleaved
#
# Split: signals (pins 4-26 = clock, LVDS pairs, backlight ctrl) and power (1-3 + 27-40).

LVDS_LCD_SIGNAL_PINS = tuple(str(n) for n in range(4, 27))  # pins 4..26 = 23 pins (signals)
LVDS_LCD_POWER_PINS  = ("1", "2", "3") + tuple(str(n) for n in range(27, 41))  # 17 pins (power + GND)


# Bank symbol metadata: (bank_name, parent_symbol, pin_numbers, mpn, footprint)
# Single source of truth for bank symbol generation.
# Tuple format: (bank_symbol_name, parent_symbol, pin_numbers, value_text, footprint)
ALL_BANKS: tuple[tuple[str, str, tuple[str, ...], str, str], ...] = (
    # J1 banks (FX10A)
    ("FX10A_168P_J1_MIO",         "FX10A_168P", J1_BANK_MIO_PINS,         "FX10A-168P-SV(91)", "Connector_FFC-FPC:FX10A-168P-SV1"),
    ("FX10A_168P_J1_PS_AUX",      "FX10A_168P", J1_BANK_PS_AUX_PINS,      "FX10A-168P-SV(91)", "Connector_FFC-FPC:FX10A-168P-SV1"),
    ("FX10A_168P_J1_PL_POWER",    "FX10A_168P", J1_BANK_PL_POWER_GND_PINS,"FX10A-168P-SV(91)", "Connector_FFC-FPC:FX10A-168P-SV1"),
    # J2 banks (FX10A)
    ("FX10A_168P_J2_DIFF",        "FX10A_168P", J2_BANK_DIFF_PAIRS_PINS,  "FX10A-168P-SV(91)", "Connector_FFC-FPC:FX10A-168P-SV1"),
    ("FX10A_168P_J2_SE",          "FX10A_168P", J2_BANK_SE_PINS,          "FX10A-168P-SV(91)", "Connector_FFC-FPC:FX10A-168P-SV1"),
    ("FX10A_168P_J2_POWER",       "FX10A_168P", J2_BANK_POWER_PINS,       "FX10A-168P-SV(91)", "Connector_FFC-FPC:FX10A-168P-SV1"),
    # J3 banks (FX10A)
    ("FX10A_168P_J3_DIFF",        "FX10A_168P", J3_BANK_DIFF_PAIRS_PINS,  "FX10A-168P-SV(91)", "Connector_FFC-FPC:FX10A-168P-SV1"),
    ("FX10A_168P_J3_SE",          "FX10A_168P", J3_BANK_SE_PINS,          "FX10A-168P-SV(91)", "Connector_FFC-FPC:FX10A-168P-SV1"),
    ("FX10A_168P_J3_POWER",       "FX10A_168P", J3_BANK_POWER_PINS,       "FX10A-168P-SV(91)", "Connector_FFC-FPC:FX10A-168P-SV1"),
    # FMC LPC banks
    ("FMC_LPC_LA_LOW",            "FMC_LPC",    FMC_LA_LOW_PINS,          "ASP-134604-01",      "Connector_Samtec:ASP-134604-01"),
    ("FMC_LPC_LA_HIGH",           "FMC_LPC",    FMC_LA_HIGH_PINS,         "ASP-134604-01",      "Connector_Samtec:ASP-134604-01"),
    ("FMC_LPC_PWR_CLK_JTAG",      "FMC_LPC",    FMC_PWR_CLK_JTAG_PINS,    "ASP-134604-01",      "Connector_Samtec:ASP-134604-01"),
    # FFC 40P banks (LVDS)
    ("FFC_40P_LVDS_SIGNALS",      "FFC_40P",    LVDS_LCD_SIGNAL_PINS,     "FPC-05F-40PH20",     "Connector_FFC-FPC:XUNPU_FPC-05F-40PH20"),
    ("FFC_40P_LVDS_POWER",        "FFC_40P",    LVDS_LCD_POWER_PINS,      "FPC-05F-40PH20",     "Connector_FFC-FPC:XUNPU_FPC-05F-40PH20"),
)


def output_path_for(bank_name: str) -> Path:
    return BANK_OUTPUT_DIR / f"{bank_name}.kicad_sym"


def generate_all_bank_symbols() -> tuple[Path, ...]:
    """Regenerate every bank's ``.kicad_sym`` from its pin list.

    Idempotent: writes only if the output file is missing or stale (a small
    text diff regenerates the file). Returns the resolved paths in declaration
    order.
    """
    written: list[Path] = []
    for bank_name, parent_sym, pins, value_text, footprint in ALL_BANKS:
        out_path = output_path_for(bank_name)
        emit_bank_symbol(
            parent_lib_path=PARENT_LIB_PATH,
            parent_symbol_name=parent_sym,
            bank_symbol_name=bank_name,
            pin_numbers=pins,
            output_path=out_path,
            value_text=value_text,
            footprint=footprint,
            show_pin_names=True,
        )
        written.append(out_path.resolve())
    return tuple(written)


def bank_symbol_library_paths() -> tuple[Path, ...]:
    """Return the .kicad_sym library paths the carrier should register."""
    return tuple(output_path_for(name).resolve() for name, *_ in ALL_BANKS)
