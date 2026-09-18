from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path



def parse_si(text: str) -> float | None:
    from schgen.core import native
    return native.module().parse_si_value(text)


# first match wins: an exact-anchored rail must precede its generic prefix
_VOLT_PATTERNS: tuple[tuple[str, float], ...] = (
    (r"^\+VBUS_IN$", 20.0),
    (r"^\+VIN_SYS$", 20.0),
    (r"^\+VIN", 20.0),
    (r"^\+5V_SOM$", 4.65),
    (r"^\+5V_REG$", 5.0),
    (r"^\+5V", 5.0),
    (r"^USB_VBUS$", 5.0),
    (r"^USB_UART_VBUS$", 5.0),
    (r"^HDMI_RX_5V$", 5.0),
    (r"^HDMI_TX_CON_5V0$", 5.0),
    (r"^LCD_VLED_P$", 30.0),
    (r"^\+3V3_REG$", 3.3),
    (r"^\+3V3", 3.3),
    (r"^\+1V8_REG$", 1.8),
    (r"^\+1V8", 1.8),
    (r"^\+2V5", 2.5),
    (r"^\+VCCO_35$", 2.5),
    (r"^\+VCCO_", 3.3),
    (r"^VBUS$", 5.0),
)


def rail_volts(name: str) -> float | None:
    from schgen.core import native
    return native.module().power_rail_volts(name, _VOLT_PATTERNS)


@dataclass(frozen=True)
class RegSpec:
    kind: str
    limit_a: float | None
    eff: float = 1.0
    in_pin: str = ""
    out_pin: str = ""
    iset_pin: str = ""
    ilim_num: float = 6800.0
    note: str = ""


REG_SPECS: dict[str, RegSpec] = {
    "TPS54302": RegSpec("buck", 3.0, eff=0.90, in_pin="3", out_pin="2",
                        note="TI 3 A synchronous buck (SW->L->rail); "
                             "thermal-gate test fixture"),
    "LM61460": RegSpec("buck", 6.0, eff=0.90, in_pin="8", out_pin="10",
                       note="TI 6 A 3-36V synchronous buck (VIN1=8 ->L<-SW=10 ->rail)"),
    "LMR33630": RegSpec("buck", 3.0, eff=0.90, in_pin="2", out_pin="8",
                        note="TI 3 A 36V synchronous buck (VIN=2, SW=8 ->L->rail)"),
    "AP2112K": RegSpec("ldo", 0.6, in_pin="1", out_pin="5",
                       note="600 mA LDO"),
    "TLV75725": RegSpec("ldo", 0.4, in_pin="1", out_pin="5",
                        note="1 A LDO held to 0.4 A continuous (PWR-3: DYD "
                             "thermal-pad, RthJA ~92.5 C/W EP-to-GND, Tj ~80 C "
                             "at 0.32 W/Ta=50 C — fmc.md section 3)"),
    "SY6280": RegSpec("load_switch", None, in_pin="IN", out_pin="OUT",
                      iset_pin="ISET", note="ILIM = 6800/RSET from netlist"),
    "TPS26631": RegSpec("efuse", None, in_pin="IN", out_pin="OUT",
                        iset_pin="ILIM", ilim_num=18000.0,
                        note="ILIM = 18/R_kohm from netlist (TPS2663 Eq 5)"),
}

SOURCES: dict[str, tuple[float, float, str]] = {
    "+VBUS_IN": (20.0, 3.0, "USB-C PD sink contract 20 V / 3 A at the "
                            "receptacle (pd_input J1; +VIN sits behind "
                            "the TPS26631 eFuse, round 5)"),
    "+3V3_SC": (3.3, 0.3, "SoM TPS7A20 always-on SC LDO U13 (J1.37); 300 mA "
                          "class — the SoM power_architecture sheet says "
                          "'3V3 (300mA)'. Envelope shared with the SoM-side "
                          "SC (STM32G431 ~50 mA); carrier tally only here"),
    "+5V_DBG": (5.0, 0.5, "debug USB-C VBUS (usb_jtag_connector J1) — host-"
                          "supplied 5 V / 0.5 A USB2 default; feeds the usb_jtag "
                          "AP2112K-3.3 debug-island LDO; isolated from carrier +5V"),
}

KNOWN_DEFERRED: dict[str, str] = {}


@dataclass
class Reg:
    n: int
    sheet: str
    ref: str
    value: str
    kind: str
    vin: str
    vout: str
    limit_a: float
    eff: float
    note: str
    i_out: float = 0.0
    i_in: float = 0.0


@dataclass
class Result:
    regs: list[Reg] = field(default_factory=list)
    rails: dict[str, float] = field(default_factory=dict)
    draws: dict[str, list[tuple[str, float, str]]] = field(default_factory=dict)
    bridges: list[tuple[str, str, str, str]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    findings: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    source_load: dict[str, float] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return not self.errors


def _detect_regs(sheets) -> tuple[list[Reg], list[str]]:
    from schgen.core import native
    result = _native_result(native.module().power_detect(_native_sheets(sheets), _native_policy()))
    return result.regs, result.errors


def _native_policy():
    from dataclasses import asdict
    return dict(voltage_patterns=_VOLT_PATTERNS,
                regulators={key: asdict(value) for key, value in REG_SPECS.items()},
                sources=SOURCES, known_deferred=KNOWN_DEFERRED)


def _native_sheets(sheets):
    return [dict(name=sc.name, circuit=sc.circuit.to_ir()) for sc in sheets]


def _native_result(raw):
    raw["regs"] = [_native_record(Reg, row) for row in raw["regs"]]
    raw["rails"] = {key: float(value) for key, value in raw["rails"].items()}
    raw["source_load"] = {key: float(value) for key, value in raw["source_load"].items()}
    raw["bridges"] = [tuple(row) for row in raw["bridges"]]
    raw["draws"] = {net: [(row[0], float(row[1]), row[2]) for row in rows]
                    for net, rows in raw["draws"].items()}
    return Result(**raw)


def _native_record(cls, row):
    from dataclasses import fields
    floats = {f.name for f in fields(cls) if f.type in (float, "float")}
    return cls(**{key: float(value) if key in floats else value for key, value in row.items()})


def analyze(sheets) -> Result:
    from schgen.core import native
    return _native_result(native.module().power_analyze(_native_sheets(sheets), _native_policy()))


def report(res: Result) -> str:
    from dataclasses import asdict
    from schgen.core import native
    return native.module().power_render(asdict(res), _native_policy(), False)


def render_svg(res: Result, out: Path) -> Path:
    from dataclasses import asdict
    from schgen.core import native
    text = native.module().power_render(asdict(res), _native_policy(), True)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text)
    return out


def run(sheets, reports_dir: Path, docs_dir: Path) -> Result:
    from schgen.core import native
    return _native_result(native.module().power_run(
        _native_sheets(sheets), _native_policy(), str(reports_dir), str(docs_dir)))


def cmd_powertree(args) -> int:
    from schgen.core.link import all_subsystem_paths, load_subsystem
    from schgen.core.project import PROJECT_ROOT
    names = args.subsystems or [p.stem for p in all_subsystem_paths()]
    sheets = [load_subsystem(n) for n in names]
    res = run(sheets, PROJECT_ROOT / "reports", PROJECT_ROOT / "docs")
    print(report(res))
    print(f"\nreport: {PROJECT_ROOT / 'reports' / 'power_tree.txt'}")
    print(f"diagram: {PROJECT_ROOT / 'docs' / 'power_tree.svg'}")
    return 0 if res.ok else 1
