"""
Generates a complete KiCad 9.0 schematic for the carrier_template project.

The schematic places every component that the carrier_template plugin
adds to the PCB and labels every connection so the design intent is
visible at a glance:

    * J1, J2, J3  - SoM mating connectors (100 pins each)
    * TP1..TP16   - bottom-side pogo-pin probes wired to the named
                    Zynq SoM nets (sourced from
                    manufacturing/fabrication/Zynq_SoM_Testpoints.csv)
    * H1..H4      - mechanical mounting holes tied to GND

All symbol definitions are embedded in the schematic so the file is
self-contained.  The schematic uses an A2 sheet, an explicit title
block, and per-block text titles so the layout reads as:

    +----------+----------+----------+--------------------------+
    | J1 conn  | J2 conn  | J3 conn  | Test Points (by class)   |
    |          |          |          | Power, QSPI, Config,     |
    |          |          |          | Boot Mode, Clocks        |
    |          |          |          | Mounting Holes (GND)     |
    +----------+----------+----------+--------------------------+

Run from a normal Python interpreter:

    python scripts/create_carrier_template_schematic.py

It writes scripts/carrier_template/carrier_template.kicad_sch and
synchronises the project's top_level_sheets UUID.
"""

import csv
import json
import os
import re
import sys
import uuid

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(SCRIPT_DIR)
CARRIER_DIR = os.path.join(SCRIPT_DIR, "carrier_template")
SYMBOL_LIB = os.path.join(CARRIER_DIR, "symbol_Zynq_SoM.kicad_sym")
SCHEMATIC_PATH = os.path.join(CARRIER_DIR, "carrier_template.kicad_sch")
PROJECT_PATH = os.path.join(CARRIER_DIR, "carrier_template.kicad_pro")
TESTPOINTS_CSV = os.path.join(
    REPO_ROOT, "manufacturing", "fabrication", "Zynq_SoM_Testpoints.csv"
)

LIB_NICKNAME = "Zynq_SoM"
CONNECTOR_FOOTPRINT = "fp:HRS_DF40C-100DP-0.4V_51_"
TESTPOINT_FOOTPRINT = "fp:Pogo_Pin_2mm_Base"
MOUNTINGHOLE_FOOTPRINT = "fp:Standoff_M2.5x3mm__Wurth_9774030151R"

CONNECTOR_REFERENCES = ("J1", "J2", "J3")
MOUNTING_HOLE_REFERENCES = ("H1", "H2", "H3", "H4")

CONNECTOR_POSITIONS = {
    "J1": (25.40, 25.40),
    "J2": (152.40, 25.40),
    "J3": (279.40, 25.40),
}

CONNECTOR_TITLES = {
    "J1": "J1  Power + USB + JTAG + SDIO + Ethernet PHY MDI",
    "J2": "J2  IO Banks 13 and 33 (HR I/O)",
    "J3": "J3  IO Banks 33, 34, 35 (HR I/O)",
}

# Test-point groups laid out in the rightmost band of the sheet.  Each
# entry is (reference, signal name, description).  Signal names are
# sanitised to legal KiCad net label characters when emitted.
TESTPOINT_GROUPS = (
    (
        "Power Rails",
        (
            ("TP14", "+1V0", "FPGA core supply monitor"),
            ("TP15", "+1V35", "DDR3L VDDQ supply monitor"),
            ("TP16", "+0V675_REF", "DDR3L VTT reference"),
            ("TP13", "+1V0_ETH", "Ethernet PHY 1V0 supply"),
        ),
    ),
    (
        "Configuration and Status",
        (
            ("TP1", "ZYNQ_PL_PROGB", "Force re-configuration"),
            ("TP2", "ZYNQ_PL_INITB", "Init / config error indicator"),
            ("TP3", "ZYNQ_PL_DONE", "PL configuration done"),
            ("TP5", "ZYNQ_PS_SRST", "PS system reset"),
        ),
    ),
    (
        "Boot Mode Straps",
        (
            ("TP9", "ZYNQ_BMODE_2", "Boot mode strap bit 2"),
            ("TP10", "ZYNQ_BMODE_0", "Boot mode strap bit 0"),
        ),
    ),
    (
        "Boot QSPI",
        (
            ("TP6", "QSPI_nCS", "QSPI chip select"),
            ("TP11", "QSPI_CLK", "QSPI clock"),
            ("TP7", "QSPI_D0_BM3", "QSPI D0 / boot mode strap 3"),
            ("TP8", "QSPI_D1_BM1", "QSPI D1 / boot mode strap 1"),
        ),
    ),
    (
        "Clocks",
        (
            ("TP4", "PS_CLK_33MHz", "Zynq PS reference clock"),
            ("TP12", "ETH_CLK_25MHz", "Ethernet PHY reference clock"),
        ),
    ),
)

MOUNTING_HOLE_GROUP_TITLE = "Mounting Holes (M2.5, tied to GND)"

# Sheet coordinates for the test-point band and the mounting hole band.
TP_BAND_X = 406.40
TP_BAND_X_LABEL = TP_BAND_X + 25.40
TP_BAND_Y_START = 25.40
TP_ROW_PITCH = 7.62
TP_GROUP_GAP = 12.70
MOUNTING_HOLE_X = 406.40
MOUNTING_HOLE_X_LABEL = MOUNTING_HOLE_X + 25.40
MOUNTING_HOLE_PITCH = 12.70

PAPER_SIZE = "A2"

PROJECT_NAME = os.path.splitext(os.path.basename(PROJECT_PATH))[0]

GND_NET_NAME = "GND"


# ---------------------------------------------------------------------------
# Symbol library helpers
# ---------------------------------------------------------------------------


def make_uuid() -> str:
    return str(uuid.uuid4())


def find_matching_paren(text: str, open_idx: int) -> int:
    depth = 0
    i = open_idx
    in_string = False
    while i < len(text):
        ch = text[i]
        if ch == '"' and (i == 0 or text[i - 1] != '\\'):
            in_string = not in_string
        elif not in_string:
            if ch == '(':
                depth += 1
            elif ch == ')':
                depth -= 1
                if depth == 0:
                    return i
        i += 1
    raise ValueError("Unbalanced parentheses while parsing symbol definition.")


def extract_symbol_definitions(lib_text: str, names: tuple[str, ...]) -> dict[str, str]:
    definitions: dict[str, str] = {}
    for name in names:
        pattern = re.compile(r'\(symbol\s+"' + re.escape(name) + r'"')
        match = pattern.search(lib_text)
        if not match:
            raise KeyError(f'Symbol "{name}" not found in {SYMBOL_LIB}')
        start = match.start()
        end = find_matching_paren(lib_text, start) + 1
        definitions[name] = lib_text[start:end]
    return definitions


def extract_pin_numbers(symbol_text: str) -> list[str]:
    return re.findall(r'\(number\s+"([^"]+)"', symbol_text)


def rename_symbol(symbol_text: str, original: str, qualified: str) -> str:
    return symbol_text.replace(f'(symbol "{original}"', f'(symbol "{qualified}"', 1)


def indent_block(block: str, level: int) -> str:
    prefix = "\t" * level
    return "\n".join(prefix + line if line else line for line in block.splitlines())


# ---------------------------------------------------------------------------
# Inline symbol definitions for TestPoint and MountingHole
# ---------------------------------------------------------------------------


def testpoint_symbol_definition(qualified_name: str) -> str:
    return (
        f'(symbol "{qualified_name}"\n'
        '\t(power)\n'
        '\t(pin_names\n'
        '\t\t(offset 0)\n'
        '\t\t(hide yes)\n'
        '\t)\n'
        '\t(exclude_from_sim no)\n'
        '\t(in_bom yes)\n'
        '\t(on_board yes)\n'
        '\t(property "Reference" "TP"\n'
        '\t\t(at 0 5.08 0)\n'
        '\t\t(effects\n'
        '\t\t\t(font\n'
        '\t\t\t\t(size 1.27 1.27)\n'
        '\t\t\t)\n'
        '\t\t)\n'
        '\t)\n'
        '\t(property "Value" "TestPoint"\n'
        '\t\t(at 0 -2.54 0)\n'
        '\t\t(effects\n'
        '\t\t\t(font\n'
        '\t\t\t\t(size 1.27 1.27)\n'
        '\t\t\t)\n'
        '\t\t\t(hide yes)\n'
        '\t\t)\n'
        '\t)\n'
        '\t(property "Footprint" ""\n'
        '\t\t(at 0 0 0)\n'
        '\t\t(effects\n'
        '\t\t\t(font\n'
        '\t\t\t\t(size 1.27 1.27)\n'
        '\t\t\t)\n'
        '\t\t\t(hide yes)\n'
        '\t\t)\n'
        '\t)\n'
        '\t(property "Datasheet" ""\n'
        '\t\t(at 0 0 0)\n'
        '\t\t(effects\n'
        '\t\t\t(font\n'
        '\t\t\t\t(size 1.27 1.27)\n'
        '\t\t\t)\n'
        '\t\t\t(hide yes)\n'
        '\t\t)\n'
        '\t)\n'
        '\t(property "Description" "Bottom-side pogo-pin probe"\n'
        '\t\t(at 0 0 0)\n'
        '\t\t(effects\n'
        '\t\t\t(font\n'
        '\t\t\t\t(size 1.27 1.27)\n'
        '\t\t\t)\n'
        '\t\t\t(hide yes)\n'
        '\t\t)\n'
        '\t)\n'
        f'\t(symbol "{qualified_name}_1_1"\n'
        '\t\t(circle\n'
        '\t\t\t(center 0 1.524)\n'
        '\t\t\t(radius 0.508)\n'
        '\t\t\t(stroke\n'
        '\t\t\t\t(width 0)\n'
        '\t\t\t\t(type default)\n'
        '\t\t\t)\n'
        '\t\t\t(fill\n'
        '\t\t\t\t(type none)\n'
        '\t\t\t)\n'
        '\t\t)\n'
        '\t\t(pin passive line\n'
        '\t\t\t(at 0 0 90)\n'
        '\t\t\t(length 1.016)\n'
        '\t\t\t(name "1"\n'
        '\t\t\t\t(effects\n'
        '\t\t\t\t\t(font\n'
        '\t\t\t\t\t\t(size 1.27 1.27)\n'
        '\t\t\t\t\t)\n'
        '\t\t\t\t)\n'
        '\t\t\t)\n'
        '\t\t\t(number "1"\n'
        '\t\t\t\t(effects\n'
        '\t\t\t\t\t(font\n'
        '\t\t\t\t\t\t(size 1.27 1.27)\n'
        '\t\t\t\t\t)\n'
        '\t\t\t\t)\n'
        '\t\t\t)\n'
        '\t\t)\n'
        '\t)\n'
        '\t(embedded_fonts no)\n'
        ')'
    )


def mountinghole_symbol_definition(qualified_name: str) -> str:
    return (
        f'(symbol "{qualified_name}"\n'
        '\t(exclude_from_sim no)\n'
        '\t(in_bom yes)\n'
        '\t(on_board yes)\n'
        '\t(property "Reference" "H"\n'
        '\t\t(at 0 5.08 0)\n'
        '\t\t(effects\n'
        '\t\t\t(font\n'
        '\t\t\t\t(size 1.27 1.27)\n'
        '\t\t\t)\n'
        '\t\t)\n'
        '\t)\n'
        '\t(property "Value" "MountingHole"\n'
        '\t\t(at 0 -3.81 0)\n'
        '\t\t(effects\n'
        '\t\t\t(font\n'
        '\t\t\t\t(size 1.27 1.27)\n'
        '\t\t\t)\n'
        '\t\t\t(hide yes)\n'
        '\t\t)\n'
        '\t)\n'
        '\t(property "Footprint" ""\n'
        '\t\t(at 0 0 0)\n'
        '\t\t(effects\n'
        '\t\t\t(font\n'
        '\t\t\t\t(size 1.27 1.27)\n'
        '\t\t\t)\n'
        '\t\t\t(hide yes)\n'
        '\t\t)\n'
        '\t)\n'
        '\t(property "Datasheet" ""\n'
        '\t\t(at 0 0 0)\n'
        '\t\t(effects\n'
        '\t\t\t(font\n'
        '\t\t\t\t(size 1.27 1.27)\n'
        '\t\t\t)\n'
        '\t\t\t(hide yes)\n'
        '\t\t)\n'
        '\t)\n'
        '\t(property "Description" "M2.5 mounting hole tied to GND"\n'
        '\t\t(at 0 0 0)\n'
        '\t\t(effects\n'
        '\t\t\t(font\n'
        '\t\t\t\t(size 1.27 1.27)\n'
        '\t\t\t)\n'
        '\t\t\t(hide yes)\n'
        '\t\t)\n'
        '\t)\n'
        f'\t(symbol "{qualified_name}_1_1"\n'
        '\t\t(circle\n'
        '\t\t\t(center 0 2.286)\n'
        '\t\t\t(radius 1.27)\n'
        '\t\t\t(stroke\n'
        '\t\t\t\t(width 0.254)\n'
        '\t\t\t\t(type default)\n'
        '\t\t\t)\n'
        '\t\t\t(fill\n'
        '\t\t\t\t(type none)\n'
        '\t\t\t)\n'
        '\t\t)\n'
        '\t\t(circle\n'
        '\t\t\t(center 0 2.286)\n'
        '\t\t\t(radius 0.635)\n'
        '\t\t\t(stroke\n'
        '\t\t\t\t(width 0.254)\n'
        '\t\t\t\t(type default)\n'
        '\t\t\t)\n'
        '\t\t\t(fill\n'
        '\t\t\t\t(type none)\n'
        '\t\t\t)\n'
        '\t\t)\n'
        '\t\t(pin passive line\n'
        '\t\t\t(at 0 0 90)\n'
        '\t\t\t(length 1.016)\n'
        '\t\t\t(name "1"\n'
        '\t\t\t\t(effects\n'
        '\t\t\t\t\t(font\n'
        '\t\t\t\t\t\t(size 1.27 1.27)\n'
        '\t\t\t\t\t)\n'
        '\t\t\t\t)\n'
        '\t\t\t)\n'
        '\t\t\t(number "1"\n'
        '\t\t\t\t(effects\n'
        '\t\t\t\t\t(font\n'
        '\t\t\t\t\t\t(size 1.27 1.27)\n'
        '\t\t\t\t\t)\n'
        '\t\t\t\t)\n'
        '\t\t\t)\n'
        '\t\t)\n'
        '\t)\n'
        '\t(embedded_fonts no)\n'
        ')'
    )


# ---------------------------------------------------------------------------
# Schematic primitives
# ---------------------------------------------------------------------------


def render_lib_symbols(symbol_defs: dict[str, str]) -> str:
    lines = ["\t(lib_symbols"]
    for name, body in symbol_defs.items():
        qualified = f"{LIB_NICKNAME}:{name}"
        renamed = rename_symbol(body, name, qualified)
        lines.append(indent_block(renamed, 2))
    tp_def = testpoint_symbol_definition(f"{LIB_NICKNAME}:TestPoint")
    mh_def = mountinghole_symbol_definition(f"{LIB_NICKNAME}:MountingHole")
    lines.append(indent_block(tp_def, 2))
    lines.append(indent_block(mh_def, 2))
    lines.append("\t)")
    return "\n".join(lines)


def render_connector_instance(
    reference: str,
    symbol_name: str,
    position: tuple[float, float],
    pin_numbers: list[str],
    schematic_uuid: str,
) -> str:
    x, y = position
    qualified = f"{LIB_NICKNAME}:{symbol_name}"
    instance_uuid = make_uuid()
    pin_blocks = "\n".join(
        f'\t\t(pin "{pin}"\n\t\t\t(uuid "{make_uuid()}")\n\t\t)'
        for pin in pin_numbers
    )
    return (
        "\t(symbol\n"
        f'\t\t(lib_id "{qualified}")\n'
        f"\t\t(at {x:.2f} {y:.2f} 0)\n"
        "\t\t(unit 1)\n"
        "\t\t(exclude_from_sim no)\n"
        "\t\t(in_bom yes)\n"
        "\t\t(on_board yes)\n"
        "\t\t(dnp no)\n"
        "\t\t(fields_autoplaced yes)\n"
        f'\t\t(uuid "{instance_uuid}")\n'
        f'\t\t(property "Reference" "{reference}"\n'
        f"\t\t\t(at {x + 5.08:.2f} {y - 7.62:.2f} 0)\n"
        "\t\t\t(effects\n"
        "\t\t\t\t(font\n"
        "\t\t\t\t\t(size 1.778 1.778)\n"
        "\t\t\t\t\t(bold yes)\n"
        "\t\t\t\t)\n"
        "\t\t\t\t(justify left)\n"
        "\t\t\t)\n"
        "\t\t)\n"
        f'\t\t(property "Value" "{symbol_name}"\n'
        f"\t\t\t(at {x + 5.08:.2f} {y - 5.08:.2f} 0)\n"
        "\t\t\t(effects\n"
        "\t\t\t\t(font\n"
        "\t\t\t\t\t(size 1.27 1.27)\n"
        "\t\t\t\t)\n"
        "\t\t\t\t(justify left)\n"
        "\t\t\t)\n"
        "\t\t)\n"
        f'\t\t(property "Footprint" "{CONNECTOR_FOOTPRINT}"\n'
        f"\t\t\t(at {x:.2f} {y:.2f} 0)\n"
        "\t\t\t(effects\n"
        "\t\t\t\t(font\n"
        "\t\t\t\t\t(size 1.27 1.27)\n"
        "\t\t\t\t)\n"
        "\t\t\t\t(hide yes)\n"
        "\t\t\t)\n"
        "\t\t)\n"
        f'\t\t(property "Datasheet" ""\n'
        f"\t\t\t(at {x:.2f} {y:.2f} 0)\n"
        "\t\t\t(effects\n"
        "\t\t\t\t(font\n"
        "\t\t\t\t\t(size 1.27 1.27)\n"
        "\t\t\t\t)\n"
        "\t\t\t\t(hide yes)\n"
        "\t\t\t)\n"
        "\t\t)\n"
        f'\t\t(property "Description" ""\n'
        f"\t\t\t(at {x:.2f} {y:.2f} 0)\n"
        "\t\t\t(effects\n"
        "\t\t\t\t(font\n"
        "\t\t\t\t\t(size 1.27 1.27)\n"
        "\t\t\t\t)\n"
        "\t\t\t\t(hide yes)\n"
        "\t\t\t)\n"
        "\t\t)\n"
        f"{pin_blocks}\n"
        "\t\t(instances\n"
        f'\t\t\t(project "{PROJECT_NAME}"\n'
        f'\t\t\t\t(path "/{schematic_uuid}"\n'
        f'\t\t\t\t\t(reference "{reference}")\n'
        "\t\t\t\t\t(unit 1)\n"
        "\t\t\t\t)\n"
        "\t\t\t)\n"
        "\t\t)\n"
        "\t)"
    )


def render_testpoint_instance(
    reference: str,
    position: tuple[float, float],
    schematic_uuid: str,
) -> str:
    x, y = position
    qualified = f"{LIB_NICKNAME}:TestPoint"
    instance_uuid = make_uuid()
    pin_uuid = make_uuid()
    return (
        "\t(symbol\n"
        f'\t\t(lib_id "{qualified}")\n'
        f"\t\t(at {x:.2f} {y:.2f} 180)\n"
        "\t\t(unit 1)\n"
        "\t\t(exclude_from_sim no)\n"
        "\t\t(in_bom yes)\n"
        "\t\t(on_board yes)\n"
        "\t\t(dnp no)\n"
        "\t\t(fields_autoplaced yes)\n"
        f'\t\t(uuid "{instance_uuid}")\n'
        f'\t\t(property "Reference" "{reference}"\n'
        f"\t\t\t(at {x - 5.08:.2f} {y - 1.27:.2f} 0)\n"
        "\t\t\t(effects\n"
        "\t\t\t\t(font\n"
        "\t\t\t\t\t(size 1.27 1.27)\n"
        "\t\t\t\t)\n"
        "\t\t\t\t(justify right)\n"
        "\t\t\t)\n"
        "\t\t)\n"
        f'\t\t(property "Value" "TestPoint"\n'
        f"\t\t\t(at {x:.2f} {y + 4.572:.2f} 0)\n"
        "\t\t\t(effects\n"
        "\t\t\t\t(font\n"
        "\t\t\t\t\t(size 1.27 1.27)\n"
        "\t\t\t\t)\n"
        "\t\t\t\t(hide yes)\n"
        "\t\t\t)\n"
        "\t\t)\n"
        f'\t\t(property "Footprint" "{TESTPOINT_FOOTPRINT}"\n'
        f"\t\t\t(at {x:.2f} {y:.2f} 0)\n"
        "\t\t\t(effects\n"
        "\t\t\t\t(font\n"
        "\t\t\t\t\t(size 1.27 1.27)\n"
        "\t\t\t\t)\n"
        "\t\t\t\t(hide yes)\n"
        "\t\t\t)\n"
        "\t\t)\n"
        f'\t\t(property "Datasheet" ""\n'
        f"\t\t\t(at {x:.2f} {y:.2f} 0)\n"
        "\t\t\t(effects\n"
        "\t\t\t\t(font\n"
        "\t\t\t\t\t(size 1.27 1.27)\n"
        "\t\t\t\t)\n"
        "\t\t\t\t(hide yes)\n"
        "\t\t\t)\n"
        "\t\t)\n"
        f'\t\t(property "Description" ""\n'
        f"\t\t\t(at {x:.2f} {y:.2f} 0)\n"
        "\t\t\t(effects\n"
        "\t\t\t\t(font\n"
        "\t\t\t\t\t(size 1.27 1.27)\n"
        "\t\t\t\t)\n"
        "\t\t\t\t(hide yes)\n"
        "\t\t\t)\n"
        "\t\t)\n"
        f'\t\t(pin "1"\n'
        f'\t\t\t(uuid "{pin_uuid}")\n'
        "\t\t)\n"
        "\t\t(instances\n"
        f'\t\t\t(project "{PROJECT_NAME}"\n'
        f'\t\t\t\t(path "/{schematic_uuid}"\n'
        f'\t\t\t\t\t(reference "{reference}")\n'
        "\t\t\t\t\t(unit 1)\n"
        "\t\t\t\t)\n"
        "\t\t\t)\n"
        "\t\t)\n"
        "\t)"
    )


def render_mountinghole_instance(
    reference: str,
    position: tuple[float, float],
    schematic_uuid: str,
) -> str:
    x, y = position
    qualified = f"{LIB_NICKNAME}:MountingHole"
    instance_uuid = make_uuid()
    pin_uuid = make_uuid()
    return (
        "\t(symbol\n"
        f'\t\t(lib_id "{qualified}")\n'
        f"\t\t(at {x:.2f} {y:.2f} 180)\n"
        "\t\t(unit 1)\n"
        "\t\t(exclude_from_sim no)\n"
        "\t\t(in_bom yes)\n"
        "\t\t(on_board yes)\n"
        "\t\t(dnp no)\n"
        "\t\t(fields_autoplaced yes)\n"
        f'\t\t(uuid "{instance_uuid}")\n'
        f'\t\t(property "Reference" "{reference}"\n'
        f"\t\t\t(at {x - 5.08:.2f} {y - 1.27:.2f} 0)\n"
        "\t\t\t(effects\n"
        "\t\t\t\t(font\n"
        "\t\t\t\t\t(size 1.27 1.27)\n"
        "\t\t\t\t)\n"
        "\t\t\t\t(justify right)\n"
        "\t\t\t)\n"
        "\t\t)\n"
        f'\t\t(property "Value" "MountingHole"\n'
        f"\t\t\t(at {x:.2f} {y + 6.35:.2f} 0)\n"
        "\t\t\t(effects\n"
        "\t\t\t\t(font\n"
        "\t\t\t\t\t(size 1.27 1.27)\n"
        "\t\t\t\t)\n"
        "\t\t\t\t(hide yes)\n"
        "\t\t\t)\n"
        "\t\t)\n"
        f'\t\t(property "Footprint" "{MOUNTINGHOLE_FOOTPRINT}"\n'
        f"\t\t\t(at {x:.2f} {y:.2f} 0)\n"
        "\t\t\t(effects\n"
        "\t\t\t\t(font\n"
        "\t\t\t\t\t(size 1.27 1.27)\n"
        "\t\t\t\t)\n"
        "\t\t\t\t(hide yes)\n"
        "\t\t\t)\n"
        "\t\t)\n"
        f'\t\t(property "Datasheet" ""\n'
        f"\t\t\t(at {x:.2f} {y:.2f} 0)\n"
        "\t\t\t(effects\n"
        "\t\t\t\t(font\n"
        "\t\t\t\t\t(size 1.27 1.27)\n"
        "\t\t\t\t)\n"
        "\t\t\t\t(hide yes)\n"
        "\t\t\t)\n"
        "\t\t)\n"
        f'\t\t(property "Description" ""\n'
        f"\t\t\t(at {x:.2f} {y:.2f} 0)\n"
        "\t\t\t(effects\n"
        "\t\t\t\t(font\n"
        "\t\t\t\t\t(size 1.27 1.27)\n"
        "\t\t\t\t)\n"
        "\t\t\t\t(hide yes)\n"
        "\t\t\t)\n"
        "\t\t)\n"
        f'\t\t(pin "1"\n'
        f'\t\t\t(uuid "{pin_uuid}")\n'
        "\t\t)\n"
        "\t\t(instances\n"
        f'\t\t\t(project "{PROJECT_NAME}"\n'
        f'\t\t\t\t(path "/{schematic_uuid}"\n'
        f'\t\t\t\t\t(reference "{reference}")\n'
        "\t\t\t\t\t(unit 1)\n"
        "\t\t\t\t)\n"
        "\t\t\t)\n"
        "\t\t)\n"
        "\t)"
    )


def render_wire(start: tuple[float, float], end: tuple[float, float]) -> str:
    sx, sy = start
    ex, ey = end
    return (
        "\t(wire\n"
        f"\t\t(pts\n\t\t\t(xy {sx:.2f} {sy:.2f}) (xy {ex:.2f} {ey:.2f})\n\t\t)\n"
        "\t\t(stroke\n"
        "\t\t\t(width 0)\n"
        "\t\t\t(type default)\n"
        "\t\t)\n"
        f'\t\t(uuid "{make_uuid()}")\n'
        "\t)"
    )


def render_global_label(
    net_name: str,
    position: tuple[float, float],
    angle: int = 0,
    shape: str = "input",
) -> str:
    x, y = position
    return (
        f'\t(global_label "{net_name}"\n'
        f"\t\t(shape {shape})\n"
        f"\t\t(at {x:.2f} {y:.2f} {angle})\n"
        "\t\t(effects\n"
        "\t\t\t(font\n"
        "\t\t\t\t(size 1.27 1.27)\n"
        "\t\t\t)\n"
        "\t\t\t(justify left)\n"
        "\t\t)\n"
        f'\t\t(uuid "{make_uuid()}")\n'
        '\t\t(property "Intersheetrefs" ""\n'
        '\t\t\t(at 0 0 0)\n'
        '\t\t\t(effects\n'
        '\t\t\t\t(font\n'
        '\t\t\t\t\t(size 1.27 1.27)\n'
        '\t\t\t\t)\n'
        '\t\t\t\t(hide yes)\n'
        '\t\t\t)\n'
        '\t\t)\n'
        "\t)"
    )


def render_text_label(text: str, position: tuple[float, float], size: float = 2.54) -> str:
    x, y = position
    return (
        f'\t(text "{text}"\n'
        f"\t\t(at {x:.2f} {y:.2f} 0)\n"
        "\t\t(effects\n"
        "\t\t\t(font\n"
        f"\t\t\t\t(size {size:.2f} {size:.2f})\n"
        "\t\t\t\t(bold yes)\n"
        "\t\t\t)\n"
        "\t\t\t(justify left bottom)\n"
        "\t\t)\n"
        f'\t\t(uuid "{make_uuid()}")\n'
        "\t)"
    )


# ---------------------------------------------------------------------------
# Block builders
# ---------------------------------------------------------------------------


def build_connector_blocks(
    symbol_defs: dict[str, str], schematic_uuid: str
) -> list[str]:
    pin_lookup = {name: extract_pin_numbers(body) for name, body in symbol_defs.items()}
    blocks: list[str] = []
    for ref in CONNECTOR_REFERENCES:
        symbol_name = f"Zynq_SoM_{ref}"
        x, y = CONNECTOR_POSITIONS[ref]
        blocks.append(render_text_label(CONNECTOR_TITLES[ref], (x, y - 12.70), size=2.54))
        blocks.append(
            render_connector_instance(
                reference=ref,
                symbol_name=symbol_name,
                position=CONNECTOR_POSITIONS[ref],
                pin_numbers=pin_lookup[symbol_name],
                schematic_uuid=schematic_uuid,
            )
        )
    return blocks


def build_testpoint_blocks(schematic_uuid: str) -> list[str]:
    blocks: list[str] = []
    cursor_y = TP_BAND_Y_START
    blocks.append(render_text_label("Test Points (bottom-side pogo pins)", (TP_BAND_X - 5.08, cursor_y - 7.62), size=3.18))
    for group_title, group_entries in TESTPOINT_GROUPS:
        cursor_y += TP_GROUP_GAP * 0.5
        blocks.append(render_text_label(group_title, (TP_BAND_X - 2.54, cursor_y), size=1.778))
        cursor_y += TP_GROUP_GAP * 0.5
        for ref, net_name, description in group_entries:
            tp_position = (TP_BAND_X, cursor_y)
            blocks.append(
                render_testpoint_instance(
                    reference=ref,
                    position=tp_position,
                    schematic_uuid=schematic_uuid,
                )
            )
            wire_start = (TP_BAND_X, cursor_y)
            wire_end = (TP_BAND_X_LABEL, cursor_y)
            blocks.append(render_wire(wire_start, wire_end))
            blocks.append(
                render_global_label(net_name, (TP_BAND_X_LABEL, cursor_y), angle=0)
            )
            blocks.append(
                render_text_label(
                    f"({description})",
                    (TP_BAND_X_LABEL + 38.10, cursor_y - 0.508),
                    size=1.27,
                )
            )
            cursor_y += TP_ROW_PITCH
    return blocks, cursor_y


def build_mountinghole_blocks(schematic_uuid: str, start_y: float) -> list[str]:
    blocks: list[str] = []
    cursor_y = start_y + 12.70
    blocks.append(render_text_label(MOUNTING_HOLE_GROUP_TITLE, (MOUNTING_HOLE_X - 5.08, cursor_y), size=2.54))
    cursor_y += 7.62
    for ref in MOUNTING_HOLE_REFERENCES:
        mh_position = (MOUNTING_HOLE_X, cursor_y)
        blocks.append(
            render_mountinghole_instance(
                reference=ref,
                position=mh_position,
                schematic_uuid=schematic_uuid,
            )
        )
        wire_start = (MOUNTING_HOLE_X, cursor_y)
        wire_end = (MOUNTING_HOLE_X_LABEL, cursor_y)
        blocks.append(render_wire(wire_start, wire_end))
        blocks.append(
            render_global_label(GND_NET_NAME, (MOUNTING_HOLE_X_LABEL, cursor_y), angle=0)
        )
        cursor_y += MOUNTING_HOLE_PITCH
    return blocks


def render_schematic(symbol_defs: dict[str, str]) -> tuple[str, str]:
    schematic_uuid = make_uuid()
    lib_symbols_block = render_lib_symbols(symbol_defs)
    connector_blocks = build_connector_blocks(symbol_defs, schematic_uuid)
    testpoint_blocks, tp_band_end_y = build_testpoint_blocks(schematic_uuid)
    mountinghole_blocks = build_mountinghole_blocks(schematic_uuid, tp_band_end_y)
    sheet_title = "Zynq SoM Carrier Template"
    schematic = "\n".join(
        [
            "(kicad_sch",
            "\t(version 20250114)",
            '\t(generator "eeschema")',
            '\t(generator_version "9.0")',
            f'\t(uuid "{schematic_uuid}")',
            f'\t(paper "{PAPER_SIZE}")',
            "\t(title_block",
            f'\t\t(title "{sheet_title}")',
            '\t\t(date "")',
            '\t\t(rev "A")',
            '\t\t(company "Zynq-SoM")',
            '\t\t(comment 1 "Auto-generated by create_carrier_template_schematic.py")',
            '\t\t(comment 2 "Mating connectors J1/J2/J3, bottom-side pogo test points TP1..TP16, and mounting holes H1..H4")',
            "\t)",
            lib_symbols_block,
            *connector_blocks,
            *testpoint_blocks,
            *mountinghole_blocks,
            "\t(sheet_instances",
            '\t\t(path "/"',
            '\t\t\t(page "1")',
            "\t\t)",
            "\t)",
            "\t(embedded_fonts no)",
            ")",
            "",
        ]
    )
    return schematic, schematic_uuid


def update_project_top_level_uuid(schematic_uuid: str) -> None:
    with open(PROJECT_PATH, "r", encoding="utf-8") as project_file:
        project_data = json.load(project_file)
    schematic_section = project_data.setdefault("schematic", {})
    schematic_section["top_level_sheets"] = [
        {
            "filename": os.path.basename(SCHEMATIC_PATH),
            "name": os.path.splitext(os.path.basename(SCHEMATIC_PATH))[0],
            "uuid": schematic_uuid,
        }
    ]
    with open(PROJECT_PATH, "w", encoding="utf-8") as project_file:
        json.dump(project_data, project_file, indent=2)
        project_file.write("\n")


def remove_stale_lock_files() -> None:
    for entry in os.listdir(CARRIER_DIR):
        if entry.endswith(".lck"):
            os.remove(os.path.join(CARRIER_DIR, entry))


def load_testpoint_csv() -> dict[str, str]:
    if not os.path.isfile(TESTPOINTS_CSV):
        raise FileNotFoundError(f"Testpoint manifest not found: {TESTPOINTS_CSV}")
    mapping: dict[str, str] = {}
    with open(TESTPOINTS_CSV, "r", encoding="utf-8") as csv_file:
        reader = csv.DictReader(csv_file)
        for row in reader:
            mapping[row["source ref des"].strip()] = row["net"].strip()
    return mapping


def main() -> int:
    if not os.path.isfile(SYMBOL_LIB):
        print(f"Symbol library not found: {SYMBOL_LIB}", file=sys.stderr)
        return 1

    expected_refs = {ref for _, entries in TESTPOINT_GROUPS for ref, _, _ in entries}
    csv_refs = set(load_testpoint_csv().keys())
    missing_from_csv = expected_refs - csv_refs
    missing_from_layout = csv_refs - expected_refs
    if missing_from_csv:
        print(
            "Warning: layout references testpoints not in CSV: "
            + ", ".join(sorted(missing_from_csv)),
            file=sys.stderr,
        )
    if missing_from_layout:
        print(
            "Warning: CSV defines testpoints not in layout: "
            + ", ".join(sorted(missing_from_layout)),
            file=sys.stderr,
        )

    with open(SYMBOL_LIB, "r", encoding="utf-8") as lib_file:
        lib_text = lib_file.read()

    symbol_names = tuple(f"Zynq_SoM_{ref}" for ref in CONNECTOR_REFERENCES)
    symbol_defs = extract_symbol_definitions(lib_text, symbol_names)

    schematic_text, schematic_uuid = render_schematic(symbol_defs)

    with open(SCHEMATIC_PATH, "w", encoding="utf-8") as schematic_file:
        schematic_file.write(schematic_text)

    update_project_top_level_uuid(schematic_uuid)
    remove_stale_lock_files()

    print(f"Wrote schematic: {SCHEMATIC_PATH}")
    print(f"Updated project: {PROJECT_PATH}")
    print(f"Connectors:      {', '.join(CONNECTOR_REFERENCES)}")
    tp_count = sum(len(entries) for _, entries in TESTPOINT_GROUPS)
    print(f"Test points:     {tp_count} placed across {len(TESTPOINT_GROUPS)} groups")
    print(f"Mounting holes:  {', '.join(MOUNTING_HOLE_REFERENCES)} tied to GND")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
