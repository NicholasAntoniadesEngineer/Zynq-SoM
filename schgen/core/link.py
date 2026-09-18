from __future__ import annotations

import argparse
import importlib.util
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from types import SimpleNamespace

from schgen.core.model import Circuit, PortType
from schgen.core.project import PROJECT_ROOT

REPO_ROOT = Path(__file__).resolve().parents[2]
SUBSYSTEMS_DIR = PROJECT_ROOT / "subsystems"
SOM_INTERFACE = PROJECT_ROOT / "som_interface.json"
SOM_MAPPING = PROJECT_ROOT / "som_mapping.json"


def _load_som_mapping() -> dict:
    data = json.loads(SOM_MAPPING.read_text())
    if not isinstance(data, dict) or data.get("schema") != "schgen.som_mapping.v1":
        raise ValueError(f"invalid SoM mapping schema: {SOM_MAPPING}")
    for key in ("function_map", "pudc_straps", "vcco_rail_map",
                "rebound_som_rails", "isolated_som_rails"):
        value = data.get(key)
        if not isinstance(value, dict) or any(
                not isinstance(k, str) or not k or not isinstance(v, str) or not v
                for k, v in value.items()):
            raise ValueError(f"{SOM_MAPPING}: {key} must map nonempty strings")
    straps = data.get("do_not_load_straps")
    if not isinstance(straps, list) or any(
            not isinstance(s, str) or not s for s in straps):
        raise ValueError(f"{SOM_MAPPING}: do_not_load_straps must be strings")
    mapped = set().union(*(data[k] for k in (
        "function_map", "pudc_straps", "vcco_rail_map", "rebound_som_rails")))
    if loaded := set(straps) & mapped:
        raise ValueError(f"{SOM_MAPPING}: SoM voltage straps mapped: {sorted(loaded)}")
    return data


RAIL_ALIASES: dict[str, str] = {}

# Discovery itself needs only circuit JSON. Linking requires som_mapping.json
# (validated by _function_map), including projects without authoring Python.
_SOM_POLICY = _load_som_mapping() if SOM_MAPPING.is_file() else {}
REBOUND_SOM_RAILS: dict[str, str] = {
    target: source for source, target in
    _SOM_POLICY.get("rebound_som_rails", {}).items()}
ISOLATED_SOM_RAILS: dict[str, str] = dict(
    _SOM_POLICY.get("isolated_som_rails", {}))


def canon_to_som(name: str) -> str:
    if name in REBOUND_SOM_RAILS:
        return REBOUND_SOM_RAILS[name]
    return RAIL_ALIASES.get(name, name)


@dataclass
class SheetCircuit:
    name: str
    circuit: Circuit
    path: Path
    module: object


def _carrier_subsystem_file(name: str) -> Path | None:
    foldered = SUBSYSTEMS_DIR / name / f"{name}.py"
    if foldered.exists():
        return foldered
    flat = SUBSYSTEMS_DIR / f"{name}.py"
    return flat if flat.exists() else None


def _circuit_json_file(name: str) -> Path | None:
    foldered = SUBSYSTEMS_DIR / name / "circuit.json"
    if foldered.is_file():
        return foldered
    return None


def _subsystem_name(name_or_path: str | Path) -> str:
    path = Path(name_or_path)
    return path.parent.name if path.name == "circuit.json" else path.stem


def exec_subsystem_py(name_or_path: str | Path) -> SheetCircuit:
    """Execute retained authoring Python explicitly, for migration comparisons."""
    path = Path(name_or_path)
    if path.suffix != ".py":
        path = _carrier_subsystem_file(_subsystem_name(path))
    elif (not path.is_file()
          and path == SUBSYSTEMS_DIR / path.stem / path.name):
        # JSON-only discovery returns stable handles even for formerly flat
        # authoring files. Resolve those handles only in this legacy utility.
        path = _carrier_subsystem_file(path.stem)
    if path is None or not path.exists():
        raise SystemExit(f"subsystem not found: {name_or_path}")
    spec = importlib.util.spec_from_file_location(f"carrier_subsys_{path.stem}", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    c = mod.circuit()
    return SheetCircuit(name=c.name, circuit=c, path=path, module=mod)


def load_subsystem(name_or_path: str | Path) -> SheetCircuit:
    from schgen.core import native as _nat
    from schgen.core.model import Circuit
    name = _subsystem_name(name_or_path)
    json_path = _circuit_json_file(name)
    if json_path is None:
        raise SystemExit(
            f"subsystem circuit.json missing: {name} — export the retained "
            f"authoring baseline with exec_subsystem_py({name!r}).circuit.to_ir()")
    rec = _nat.circuit_sheet(name)
    circuit = Circuit.from_ir(rec)
    return SheetCircuit(name=circuit.name, circuit=circuit, path=json_path,
                        module=None)


def has_subsystem(name: str) -> bool:
    return _circuit_json_file(name) is not None


def missing_subsystems(names: tuple[str, ...]) -> list[str]:
    return [n for n in names if not has_subsystem(n)]


def all_subsystem_paths() -> list[Path]:
    """Sorted subsystem handles discovered exclusively from canonical JSON.

    Keep the historical ``<name>/<name>.py`` path shape: consumers use .stem
    as the sheet ID and .parent for adjacent artifacts. These are handles, not
    executable inputs, and do not require the authoring files to exist.
    """
    from schgen.core import native as _nat

    return [path.parent / f"{name}.py"
            for name, path in _nat.subsystem_json_paths(SUBSYSTEMS_DIR)]


def load_som_contract(path: Path = SOM_INTERFACE) -> dict[str, list[str]]:
    data = json.loads(path.read_text())
    nets: dict[str, list[str]] = {}
    for jref, conn in data["connectors"].items():
        for pin, net in conn["pins"].items():
            nets.setdefault(net, []).append(f"{jref}.{pin}")
    for locs in nets.values():
        locs.sort(key=lambda s: (s.split(".")[0], int(s.split(".")[1])))
    return nets


def drift_candidates(name: str, pool: set[str]) -> list[str]:
    from schgen.core import native
    return native.module().link_drift_candidates(name, pool)


def _runtime_mapping() -> dict:
    data = _load_som_mapping()
    data["function_map"] = _function_map()
    data["pudc_straps"] = {}
    data["vcco_rail_map"] = _vcco_rail_map()
    data["rebound_som_rails"] = {
        som: carrier for carrier, som in REBOUND_SOM_RAILS.items()}
    data["isolated_som_rails"] = dict(ISOLATED_SOM_RAILS)
    data["rail_aliases"] = dict(RAIL_ALIASES)
    return data


@dataclass
class PortBinding:
    sheet: str
    net: str
    ptype: PortType
    targets: list[str] = field(default_factory=list)
    status: str = "bound"


@dataclass
class LinkResult:
    sheets: list[SheetCircuit] = field(default_factory=list)
    bindings: list[PortBinding] = field(default_factory=list)
    rail_bindings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    unbound_som: list[str] = field(default_factory=list)
    deferred: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors

    def report(self) -> str:
        from schgen.core import native
        return native.module().link_report({
            "sheets": [s.name for s in self.sheets],
            "bindings": [asdict(b) for b in self.bindings],
            "rail_bindings": self.rail_bindings,
            "errors": self.errors, "warnings": self.warnings,
            "unbound_som": self.unbound_som, "deferred": self.deferred,
        }, _runtime_mapping())


def link(sheets: list[SheetCircuit],
         som_nets: dict[str, list[str]] | None = None) -> LinkResult:
    from schgen.core import native
    # Preserve historical diagnostic ordering only; native code performs checks.
    pairs = [(i, name, list(frozenset((name, pt.pair_with))))
             for i, sc in enumerate(sheets)
             for name, pt in sc.circuit.port_types.items()
             if pt.pair_with is not None]
    raw = native.module().link_sheets(
        [(sc.name, sc.circuit.to_ir()) for sc in sheets],
        load_som_contract() if som_nets is None else som_nets,
        _runtime_mapping(), pairs, list({"scl", "sda"}))
    return LinkResult(
        sheets=list(sheets),
        bindings=[PortBinding(b["sheet"], b["net"], PortType(**b["ptype"]),
                              list(b["targets"]), b["status"])
                  for b in raw["bindings"]],
        rail_bindings=list(raw["rail_bindings"]), errors=list(raw["errors"]),
        warnings=list(raw["warnings"]), unbound_som=list(raw["unbound_som"]),
        deferred=list(raw["deferred"]))


def _load_som_conn_gen():
    """Compatibility view for policy consumers; never execute authoring code."""
    data = _load_som_mapping()

    def resolve_net(som_net: str) -> str:
        for key in ("rebound_som_rails", "vcco_rail_map", "function_map",
                    "pudc_straps"):
            if som_net in data[key]:
                return data[key][som_net]
        return som_net

    return SimpleNamespace(
        FUNCTION_MAP=dict(data["function_map"]),
        PUDC_STRAPS=dict(data["pudc_straps"]),
        VCCO_RAIL_MAP=dict(data["vcco_rail_map"]),
        REBOUND_SOM_RAILS=dict(data["rebound_som_rails"]),
        RAIL_SPELLING=dict(data["rebound_som_rails"]),
        ISOLATED_SOM_RAILS=dict(data["isolated_som_rails"]),
        DO_NOT_LOAD_STRAPS=frozenset(data["do_not_load_straps"]),
        resolve_net=resolve_net)


def _function_map() -> dict[str, str]:
    data = _load_som_mapping()
    m = dict(data["function_map"])
    m.update(data["pudc_straps"])
    return m


def _vcco_rail_map() -> dict[str, str]:
    return dict(_load_som_mapping()["vcco_rail_map"])


def cmd_link(args: argparse.Namespace) -> int:
    names = args.subsystems or [p.stem for p in all_subsystem_paths()]
    sheets = [load_subsystem(n) for n in names]

    from schgen.core.symbols import Library
    lib = Library()
    for sc in sheets:
        sc.circuit.validate({r: lib.pin_numbers(p.lib_id)
                             for r, p in sc.circuit.parts.items()})

    som_nets = load_som_contract()
    res = link(sheets, som_nets)

    carrier = PROJECT_ROOT
    override = args.outdir
    if override is None and args.subsystems:
        import tempfile
        override = Path(tempfile.mkdtemp(prefix="schgen_link_"))
        print(f"(partial link of {len(args.subsystems)} sheet(s) -> {override}; "
              f"pass -o to choose an output dir, or run `schgen link` with no "
              f"sheet args to refresh the committed carrier/ artifacts)")
    rep_dir = override or (carrier / "reports")
    man_dir = override or (carrier / "manufacturing")
    diag_path = (override / "block_diagram.svg" if override
                 else carrier / "docs" / "block_diagram.svg")
    diag_path.parent.mkdir(parents=True, exist_ok=True)
    rep_dir.mkdir(parents=True, exist_ok=True)
    man_dir.mkdir(parents=True, exist_ok=True)

    report_path = rep_dir / "link_report.txt"
    report_path.write_text(res.report() + "\n")
    print(res.report())
    print(f"\nlink report: {report_path}")

    from schgen.generate import constraints
    dru, csv_path = constraints.export(sheets, man_dir)
    print(f"constraints: {dru} + {csv_path}")

    from schgen.output import diagram
    svg = diagram.render(res, som_nets, diag_path)
    print(f"block diagram: {svg}")

    board_ok = True
    if not args.no_board:
        from schgen.core.project import stable_sheet_index
        from schgen.generate import board
        sheet_index, _ = stable_sheet_index(sc.name for sc in sheets)
        if override:
            board_ok = board.build_board(sheets, lib, override / "board",
                                         sheet_index=sheet_index)
        else:
            board_ok = board.build_board(
                sheets, lib, carrier, placements=None,
                root_name="Zynq_Carrier", sheet_subdir="schematic",
                sheet_index=sheet_index, reports_dir=rep_dir)

    ok = res.ok and board_ok
    print(f"LINK CMD: {'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1
