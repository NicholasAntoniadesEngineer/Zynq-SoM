from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from pathlib import Path

from schgen.core import native as _native
from schgen.core.link import _vcco_rail_map
from schgen.core.model import NetClass, PortType
from schgen.core.project import PROJECT_ROOT
from schgen.core.project import spec as _project_spec
from schgen.core.som_interface import extract_zynq

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SOM = REPO_ROOT / "som" / "Zynq_SoM.kicad_sch"
DEFAULT_CONTRACT = PROJECT_ROOT / "som_interface.json"
DEFAULT_OUT = PROJECT_ROOT / "fpga" / "Zynq_Carrier_pins.xdc"


def _function_map() -> dict[str, str]:
    import importlib.util
    gen_path = PROJECT_ROOT / "som_conn_gen.py"
    spec = importlib.util.spec_from_file_location("_xdc_som_conn_gen", gen_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    m = dict(mod.FUNCTION_MAP)
    m.update(mod.PUDC_STRAPS)
    return m


def bank_rail_map() -> dict[str, str]:
    return dict(_project_spec().bank_rails)


_IOSTD_SINGLE = {3.3: "LVCMOS33", 2.5: "LVCMOS25", 1.8: "LVCMOS18"}


class XdcError(ValueError):
    pass


def _rail_volts(rail: str) -> float:
    try:
        return _native.module().xdc_rail_volts(rail)
    except ValueError as exc:
        raise XdcError(str(exc)) from exc


@dataclass
class PinEntry:
    net: str
    jpin: str
    ball: str
    pin_name: str
    bank: str
    iostd: str = ""
    consumers: list[str] = field(default_factory=list)
    ptype: PortType = field(default_factory=PortType)

    @property
    def clock_capable(self) -> str | None:
        return _native.module().xdc_pin_traits(self.pin_name)[0] or None

    @property
    def p_side(self) -> bool:
        return _native.module().xdc_pin_traits(self.pin_name)[1]


@dataclass
class XdcResult:
    path: Path
    entries: list[PinEntry]
    checks: list[str]

    @property
    def count(self) -> int:
        return len(self.entries)


def _source_path(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def generate(sheets, out_path: Path = DEFAULT_OUT, *,
             som_sch: Path = DEFAULT_SOM,
             contract_path: Path = DEFAULT_CONTRACT,
             refs: tuple[str, ...] = ("J1", "J2", "J3")) -> XdcResult:
    """Adapt live project inputs to the pure native XDC engine."""
    contract = json.loads(contract_path.read_text())["connectors"]
    live = extract_zynq(som_sch, jrefs=tuple(refs))
    ports, types = [], []
    for sheet in sheets:
        circuit = sheet.circuit
        for net in circuit.nets.values():
            if net.net_class != NetClass.PORT:
                continue
            pt = circuit.port_types.get(net.name, PortType())
            ports.append((net.name, sheet.name, pt.kind, pt.pair_with,
                          pt.impedance, len(types)))
            types.append(pt)

    bank_rail = bank_rail_map()
    vcco = {k.removeprefix("+VCCO_"): v for k, v in _vcco_rail_map().items()}
    inputs = {
        "connectors": [(ref, list(data["pins"].items()))
                       for ref, data in contract.items()],
        "ball_net": list(live["ball_net"].items()),
        "pin_names": list(live["pin_names"].items()),
        "jpin_net": list(live["jpin_net"].items()),
        "function_map": list(_function_map().items()),
        "bank_rails": list(bank_rail.items()),
        "vcco_rails": list(vcco.items()),
        # Preserve the historical diagnostic's ordering; no validation here.
        "drift_order": list(set(bank_rail) | set(vcco)),
        "ports": ports,
        "refs": list(refs),
        "device": live["value"],
        "zynq_ref": live["zynq_ref"],
        "contract_path": str(contract_path),
        "contract_source": _source_path(contract_path),
        "som_source": _source_path(som_sch),
    }
    try:
        text, raw_entries, checks = _native.module().generate_xdc(inputs)
    except ValueError as exc:
        raise XdcError(str(exc)) from exc
    entries = [
        PinEntry(net, jpin, ball, pin_name, bank, iostd, list(consumers),
                 types[type_index] if type_index >= 0 else PortType())
        for net, jpin, ball, pin_name, bank, iostd, consumers, type_index
        in raw_entries
    ]
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(text)
    return XdcResult(path=out_path, entries=entries, checks=list(checks))


def cmd_xdc(args: argparse.Namespace) -> int:
    from schgen.core.link import all_subsystem_paths, load_subsystem
    names = args.subsystems or [p.stem for p in all_subsystem_paths()]
    sheets = [load_subsystem(n) for n in names]
    refs = tuple(r.strip() for r in args.refs.split(",") if r.strip())
    try:
        res = generate(sheets, args.output, som_sch=args.som, refs=refs)
    except XdcError as exc:
        print(f"XDC: FAIL — {exc}")
        return 1
    for c in res.checks:
        print(f"  check: {c}")
    print(f"XDC: {res.path} ({res.count} pins)")
    return 0
