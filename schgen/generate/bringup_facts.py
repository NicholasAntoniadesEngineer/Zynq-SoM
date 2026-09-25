from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from schgen.core import native
from schgen.core.link import load_som_contract
from schgen.core.model import Circuit
from schgen.verify.powertree import _native_sheets
from types import SimpleNamespace

REPO_ROOT = Path(__file__).resolve().parents[2]
SOM_SCH = REPO_ROOT / "som" / "Zynq_SoM.kicad_sch"
LVC1G08_PIN_A, LVC1G08_PIN_B, LVC1G08_PIN_Y = "1", "2", "4"
SY6280_ILIM_NUMERATOR = 6800.0
FB_VREF = {"TPS54302": 0.596, "LMR33630": 1.0, "LM61460": 1.0}
TCA9535_BASE_ADDR = 0x20
INA3221_BASE_ADDR = 0x40
FUSB302B_ADDR = 0x22

@dataclass(frozen=True)
class Stm32Net:
    net: str
    port: str
    pin: int
    j_pins: tuple[str, ...]


@dataclass(frozen=True)
class DipPosition:
    switch: str
    position: int
    net: str


@dataclass(frozen=True)
class EnCell:
    sheet: str
    gate: str
    dip_net: str
    override_net: str
    enable: str


@dataclass(frozen=True)
class Expander:
    ref: str
    addr: int
    ports: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class Monitor:
    ref: str
    addr: int
    channels: dict[int, tuple[str, str]] = field(default_factory=dict)


@dataclass
class RegulatorStage:
    ref: str
    value: str
    enable: str
    rail_in: str
    rail_out: str
    vout: float | None
    pg_led: str | None = None


@dataclass(frozen=True)
class ModuleGate:
    ref: str
    module: str
    rail_in: str
    rail_out: str
    enable: str
    ilim_ma: int | None
    status_led: str | None



def _circuit(c):
    return _native_sheets([SimpleNamespace(name=c.name, circuit=c)])[0]["circuit"]


def parse_value_ohms(value: str) -> float | None:
    return native.module().bringup_parse_value_ohms(value)


def c_ident(net: str) -> str:
    return native.module().bringup_c_ident(net)


def stm32_pin_map(som_sch: Path = SOM_SCH, ref: str = "U9") -> dict:
    from schgen.core.som_interface import extract_zynq
    raw = native.module().bringup_stm32_map(
        extract_zynq(som_sch, zynq_ref=ref), load_som_contract())
    for kind in ("nets", "internal"):
        raw[kind] = {name: Stm32Net(*row[:3], tuple(row[3]))
                     for name, row in raw[kind].items()}
    return raw


def dip_switch_refs(c: Circuit) -> list[str]:
    return native.module().bringup_dip_refs(_circuit(c))


def dip_positions(c: Circuit, ref: str,
                  common: tuple[str, ...] = ("+3V3_SC", "GND")) -> list[DipPosition]:
    return [DipPosition(*row) for row in
            native.module().bringup_dip_positions(_circuit(c), ref, common)]


def en_cells(c: Circuit) -> list[EnCell]:
    return [EnCell(*row) for row in native.module().bringup_en_cells(_circuit(c))]


def expander(c: Circuit) -> Expander:
    return Expander(*native.module().bringup_expander(_circuit(c)))


def ina3221_monitors(c: Circuit) -> list[Monitor]:
    return [Monitor(*row) for row in native.module().bringup_monitors(_circuit(c))]


def regulator_chain(power: Circuit, root: str = "+VIN",
                    monitor: Circuit | None = None) -> list[RegulatorStage]:
    return [RegulatorStage(*row) for row in native.module().bringup_regulator_chain(
        _circuit(power), root, _circuit(monitor) if monitor is not None else None)]


def module_gates(c: Circuit) -> list[ModuleGate]:
    return [ModuleGate(*row) for row in native.module().bringup_module_gates(_circuit(c))]
