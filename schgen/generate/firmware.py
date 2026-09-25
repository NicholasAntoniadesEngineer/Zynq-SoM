from __future__ import annotations

import argparse
from pathlib import Path
from schgen.core import native
from schgen.core.project import PROJECT_ROOT
from schgen.generate import bringup_facts as bf, _native_docs

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUT = PROJECT_ROOT / "firmware" / "zynq_carrier_contract.h"
RV3028_ADDR = 0x52
ID_EEPROM_BASE = 0x50

RAIL_OVERRIDE_GPIO = {
    "STM32_RAIL_EN_5V0": "STM32_GPIO1",
    "STM32_RAIL_EN_3V3": "STM32_GPIO2",
    "STM32_RAIL_EN_1V8": "STM32_GPIO3",
}
EXPANDER_INT_GPIO = ("SC_INT_N (TCA9535 INT# wire-OR FUSB302 INT)",
                     "STM32_GPIO4")

EXPANDER_INPUT_NOTES = {
    "P11": "INA3221 CRITICAL wire-OR (power_mon, 10k PU +3V3_SC)",
    "P14": "TPS2051C fault (usbc_otg, 100k PU re-railed +3V3_SC)",
    "P15": "TPS26631 +VIN eFuse fault (pd_input, 100k PU +3V3_SC)",
}

BOOT_MODES = (("JTAG", 0x0), ("QSPI", 0x1), ("SD", 0x2), ("RESERVED", 0x3))
BOOTSEL_NETS = ("STM32_GPIO7", "STM32_GPIO8")
SWD_RESERVED = {"STM32_GPIO6": ("A", 13, "SWDIO"),
                "STM32_GPIO5": ("A", 14, "SWCLK")}


FirmwareError = native.module().FirmwareDocsError


def absent_inputs() -> list[str]:
    return _native_docs.missing("firmware")


def _sources() -> list[str]:
    return _native_docs.sources()


def _shunt_mohm(c, in_p: str, in_n: str) -> int | None:
    return native.module().bringup_shunt_mohm(bf._circuit(c), in_p, in_n)


def _id_eeprom_addr(c) -> int:
    return native.module().bringup_id_eeprom_addr(bf._circuit(c))


def generate(out: Path = DEFAULT_OUT) -> Path:
    text = native.module().firmware_docs_render(*_native_docs.inputs(), "firmware")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text)
    return out


def cmd_firmware(args: argparse.Namespace) -> int:
    out = generate(args.output or DEFAULT_OUT)
    n_defines = sum(1 for line in out.read_text().splitlines()
                    if line.startswith("#define"))
    print(f"FIRMWARE CONTRACT: {out} ({n_defines} #defines)")
    return 0
