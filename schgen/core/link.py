from __future__ import annotations

import argparse
import importlib.util
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from schgen.core.model import Circuit, NetClass, PortType, pair_polarity
from schgen.core.project import PROJECT_ROOT

REPO_ROOT = Path(__file__).resolve().parents[2]
SUBSYSTEMS_DIR = PROJECT_ROOT / "subsystems"
SOM_INTERFACE = PROJECT_ROOT / "som_interface.json"

RAIL_ALIASES: dict[str, str] = {}

REBOUND_SOM_RAILS: dict[str, str] = {
    "+5V_SOM": "VIN",
}

ISOLATED_SOM_RAILS: dict[str, str] = {
    "+3V3": "SoM MPM3834 3V3 output on J1.24-27 — carrier TPS54302 "
            "(power:U2) is the only +3V3 source",
    "+1V8": "SoM MPM3834 1V8 output on J1.56/58/60 — carrier AP2112K "
            "(power:U3) is the only +1V8 source",
}


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
    if foldered.exists():
        return foldered
    return None


def exec_subsystem_py(name_or_path: str) -> SheetCircuit:
    path = Path(name_or_path)
    if path.suffix != ".py":
        path = _carrier_subsystem_file(Path(name_or_path).stem)
    if path is None or not path.exists():
        raise SystemExit(f"subsystem not found: {name_or_path}")
    spec = importlib.util.spec_from_file_location(f"carrier_subsys_{path.stem}", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    c = mod.circuit()
    return SheetCircuit(name=c.name, circuit=c, path=path, module=mod)


def load_subsystem(name_or_path: str) -> SheetCircuit:
    from schgen.core import native as _nat
    from schgen.core.model import Circuit
    name = Path(name_or_path).stem
    json_path = _circuit_json_file(name)
    if json_path is None:
        raise SystemExit(
            f"subsystem circuit.json missing: {name} — dump it with "
            f"scripts/dump_circuits.py")
    rec = _nat.circuit_sheet(name)
    circuit = Circuit.from_ir(rec)
    return SheetCircuit(name=circuit.name, circuit=circuit, path=json_path,
                        module=None)


def has_subsystem(name: str) -> bool:
    return _circuit_json_file(name) is not None or _carrier_subsystem_file(name) is not None


def missing_subsystems(names: tuple[str, ...]) -> list[str]:
    return [n for n in names if not has_subsystem(n)]


def all_subsystem_paths() -> list[Path]:
    by_name: dict[str, Path] = {}
    for p in SUBSYSTEMS_DIR.glob("*.py"):
        if p.stem != "__init__" and not p.name.startswith("test_"):
            by_name[p.stem] = p
    for d in SUBSYSTEMS_DIR.iterdir():
        if d.is_dir() and not d.name.startswith((".", "_")):
            f = d / f"{d.name}.py"
            if f.exists():
                by_name[d.name] = f
    return [by_name[name] for name in sorted(by_name)]


def load_som_contract(path: Path = SOM_INTERFACE) -> dict[str, list[str]]:
    data = json.loads(path.read_text())
    nets: dict[str, list[str]] = {}
    for jref, conn in data["connectors"].items():
        for pin, net in conn["pins"].items():
            nets.setdefault(net, []).append(f"{jref}.{pin}")
    for locs in nets.values():
        locs.sort(key=lambda s: (s.split(".")[0], int(s.split(".")[1])))
    return nets


def _tokens(name: str) -> list[str]:
    return re.findall(r"[A-Za-z]+|\d+", name.upper())


def _levenshtein(a: str, b: str, cap: int = 3) -> int:
    if abs(len(a) - len(b)) > cap:
        return cap + 1
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1,
                           prev[j - 1] + (ca != cb)))
        if min(cur) > cap:
            return cap + 1
        prev = cur
    return prev[-1]


def drift_candidates(name: str, pool: set[str]) -> list[str]:
    out: list[str] = []
    ta = _tokens(name)
    flat_a = "".join(ta)
    for cand in sorted(pool):
        if cand == name:
            continue
        tb = _tokens(cand)
        if cand.upper() == name.upper() or "".join(tb) == flat_a:
            out.append(cand)
            continue
        common = 0
        rest = list(tb)
        for t in ta:
            if t in rest:
                rest.remove(t)
                common += 1
        if common >= 3 and common >= max(len(ta), len(tb)) - 1:
            out.append(cand)
            continue
        if _levenshtein(name.upper(), cand.upper()) <= 2:
            out.append(cand)
    return out


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
        lines = ["schgen link report", "=" * 60]
        lines.append(f"sheets ({len(self.sheets)}): "
                     + ", ".join(s.name for s in self.sheets))
        lines.append("")
        lines.append("alias map (rails only, exact, enumerated):")
        for a, b in sorted(RAIL_ALIASES.items()):
            lines.append(f"  carrier {a!r} <-> SoM {b!r}")
        if not RAIL_ALIASES:
            lines.append("  (no pure spelling aliases)")
        for a, b in sorted(REBOUND_SOM_RAILS.items()):
            lines.append(f"  carrier {a!r} == SoM {b!r}  (P0 REBIND, not a "
                         f"spelling alias — wave3_function_map.md P0)")
        lines.append("  (identity rails +3V3 / +1V8 / GND need no entry; "
                     "signals are never aliased)")
        lines.append("")
        bound = [b for b in self.bindings if b.status == "bound"]
        lines.append(f"bound ports ({len(bound)}):")
        for b in bound:
            t = "; ".join(b.targets)
            kind = b.ptype.kind if b.ptype.kind != "single" else ""
            lines.append(f"  {b.sheet}:{b.net}"
                         + (f" [{kind}]" if kind else "") + f" -> {t}")
        lines.append("")
        lines.append(f"rails ({len(self.rail_bindings)}):")
        for r in self.rail_bindings:
            lines.append(f"  {r}")
        lines.append("")
        lines.append(f"deferred ports — author-declared, awaiting later waves "
                     f"({len(self.deferred)}) [WARNING]:")
        for d in self.deferred:
            lines.append(f"  {d}")
        lines.append("")
        lines.append(f"unbound SoM nets — no consumer yet, later waves "
                     f"({len(self.unbound_som)}) [WARNING]:")
        for chunk_start in range(0, len(self.unbound_som), 6):
            lines.append("  " + ", ".join(
                self.unbound_som[chunk_start:chunk_start + 6]))
        lines.append("")
        if self.warnings:
            lines.append(f"other warnings ({len(self.warnings)}):")
            for w in self.warnings:
                lines.append(f"  WARNING: {w}")
            lines.append("")
        if self.errors:
            lines.append(f"ERRORS ({len(self.errors)}):")
            for e in self.errors:
                lines.append(f"  ERROR: {e}")
        else:
            lines.append("errors: none")
        lines.append("")
        nwarn = len(self.deferred) + (1 if self.unbound_som else 0) \
            + len(self.warnings)
        lines.append(f"LINK: {'PASS' if self.ok else 'FAIL'} "
                     f"({len(self.errors)} errors, {nwarn} warnings)")
        return "\n".join(lines)


def link(sheets: list[SheetCircuit],
         som_nets: dict[str, list[str]] | None = None) -> LinkResult:
    if som_nets is None:
        som_nets = load_som_contract()
    res = LinkResult(sheets=sheets)
    som_names = set(som_nets)

    ports_by_name: dict[str, list[SheetCircuit]] = {}
    for sc in sheets:
        for net in sc.circuit.nets.values():
            if net.net_class == NetClass.PORT:
                ports_by_name.setdefault(net.name, []).append(sc)

    bound_som_names: set[str] = set()

    for sc in sheets:
        c = sc.circuit
        for net in c.nets.values():
            if net.net_class != NetClass.PORT:
                continue
            pt = c.port_type_of(net.name)
            b = PortBinding(sheet=sc.name, net=net.name, ptype=pt)
            peers = [p.name for p in ports_by_name.get(net.name, [])
                     if p is not sc]
            som_name = canon_to_som(net.name)
            if peers:
                b.targets += [f"sheet {p}:{net.name}" for p in peers]
            if som_name in som_names:
                pins = ",".join(som_nets[som_name][:4])
                more = len(som_nets[som_name]) - 4
                b.targets.append(
                    f"SoM {som_name} ({pins}{f',+{more}' if more > 0 else ''})")
                bound_som_names.add(som_name)
            if not b.targets:
                if pt.expect:
                    b.status = "deferred"
                    res.deferred.append(
                        f"{sc.name}:{net.name} — awaiting {pt.expect}")
                else:
                    b.status = "error"
                    pool = (som_names | set(ports_by_name)) - {net.name}
                    cands = drift_candidates(net.name, pool)
                    if cands:
                        res.errors.append(
                            f"name drift: {sc.name}:{net.name} resolves "
                            f"nowhere; near-miss candidates: "
                            + ", ".join(cands))
                    else:
                        res.errors.append(
                            f"undefined port: {sc.name}:{net.name} resolves "
                            f"nowhere (no same-named port on another sheet, "
                            f"not a SoM net, no expect= deferral)")
            res.bindings.append(b)

    rails: dict[str, set[str]] = {}
    for sc in sheets:
        for net in sc.circuit.nets.values():
            if net.net_class in (NetClass.POWER, NetClass.GROUND):
                rails.setdefault(net.name, set()).add(sc.name)
    for rail, users in sorted(rails.items()):
        som_name = canon_to_som(rail)
        if rail in ISOLATED_SOM_RAILS:
            iso_conns = {loc.split(".")[0] for loc in som_nets.get(som_name, [])}
            offenders = sorted(u for u in users if u.startswith("som_j")
                               and u[len("som_"):].upper() in iso_conns)
            if offenders:
                res.errors.append(
                    f"RAIL ISOLATION VIOLATED: {rail} is declared isolated "
                    f"from the SoM ({ISOLATED_SOM_RAILS[rail]}) but the SoM "
                    f"{som_name!r} output pins still bind it on connector "
                    f"sheet(s) {', '.join(offenders)} — som_conn_gen must "
                    f"author those pins NC")
            bound_som_names.add(som_name)
            res.rail_bindings.append(
                f"{rail} — ISOLATED from SoM {som_name!r} pins (round-5 "
                f"decision: {ISOLATED_SOM_RAILS[rail]}; pins author-NC on "
                f"the J1 sheet); carrier-local rail (sheets: "
                f"{', '.join(sorted(users))})")
        elif rail in REBOUND_SOM_RAILS:
            if not any(u.startswith("som_j") for u in users):
                res.errors.append(
                    f"REBIND BROKEN: {rail} is declared the P0 stand-in for "
                    f"SoM {som_name!r} pins but appears on NO connector sheet "
                    f"(sheets: {', '.join(sorted(users))}) — som_conn_gen "
                    f"REBOUND_SOM_RAILS must map SoM {som_name!r} -> {rail}")
            elif som_name not in som_names:
                res.errors.append(
                    f"REBIND BROKEN: {rail} -> SoM {som_name!r} but "
                    f"{som_name!r} is not a SoM contract net")
            else:
                bound_som_names.add(som_name)
                res.rail_bindings.append(
                    f"{rail} — P0 REBIND of SoM {som_name!r} (the SoM 4.2-5V "
                    f"input; never the 20V +VIN PD rail — "
                    f"wave3_function_map.md P0) <- sheets: "
                    f"{', '.join(sorted(users))} -> SoM "
                    f"{len(som_nets[som_name])} pins")
        elif som_name in som_names:
            bound_som_names.add(som_name)
            alias = f" (alias of SoM {som_name!r})" if som_name != rail else ""
            res.rail_bindings.append(
                f"{rail}{alias} <- sheets: {', '.join(sorted(users))} "
                f"-> SoM {len(som_nets[som_name])} pins")
        else:
            on_conn = sorted(u for u in users if u.startswith("som_j"))
            if on_conn and rail in REBOUND_SOM_RAILS.values():
                res.errors.append(
                    f"REBIND DRIFT: SoM net {rail!r} appears RAW on connector "
                    f"sheet(s) {', '.join(on_conn)} — som_conn_gen must rebind "
                    f"it (REBOUND_SOM_RAILS) onto its carrier rail")
            if on_conn and rail == "+VIN":
                res.errors.append(
                    f"SoM OVERVOLTAGE: the 20V PD rail +VIN reaches connector "
                    f"sheet(s) {', '.join(on_conn)} — the SoM is a 4.2-5V "
                    f"module; J1 VIN must rebind to +5V_SOM "
                    f"(wave3_function_map.md P0)")
            res.rail_bindings.append(
                f"{rail} — carrier-local rail (sheets: "
                f"{', '.join(sorted(users))})")

    _check_pairs(sheets, res)
    _check_buses(sheets, res)
    _check_net_type_agreement(sheets, res)

    bound_ports = {b.net for b in res.bindings if b.status == "bound"}
    for som_net, func_net in _function_map().items():
        if som_net in som_names and func_net in bound_ports:
            bound_som_names.add(som_net)

    for som_net, target_rail in _vcco_rail_map().items():
        if som_net in som_names and target_rail in rails:
            bound_som_names.add(som_net)

    res.unbound_som = sorted(n for n in som_names if n not in bound_som_names)
    return res


def _load_som_conn_gen():
    import importlib.util
    gen_path = PROJECT_ROOT / "som_conn_gen.py"
    spec = importlib.util.spec_from_file_location("_link_som_conn_gen", gen_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _function_map() -> dict[str, str]:
    mod = _load_som_conn_gen()
    m = dict(mod.FUNCTION_MAP)
    m.update(mod.PUDC_STRAPS)
    return m


def _vcco_rail_map() -> dict[str, str]:
    return dict(_load_som_conn_gen().VCCO_RAIL_MAP)


def _check_pairs(sheets: list[SheetCircuit], res: LinkResult) -> None:
    for sc in sheets:
        c = sc.circuit
        seen: set[frozenset[str]] = set()
        for name, pt in c.port_types.items():
            if pt.pair_with is None:
                continue
            key = frozenset((name, pt.pair_with))
            if key in seen:
                continue
            seen.add(key)
            pols = {n: pair_polarity(n) for n in key}
            if set(pols.values()) != {"P", "N"}:
                res.errors.append(
                    f"diff-pair polarity: {sc.name}: pair {sorted(key)} "
                    f"reads as {pols} — need exactly one P and one N")
        for net in c.nets.values():
            if net.net_class != NetClass.PORT or net.name in c.port_types:
                continue
            pol = pair_polarity(net.name)
            if pol != "P":
                continue
            comp = _complement_name(net.name)
            if comp and comp in c.nets and comp not in c.port_types:
                res.warnings.append(
                    f"{sc.name}: ports {net.name}/{comp} look like a pair "
                    f"but are untyped (no port_type)")


def _complement_name(name: str) -> str | None:
    up = name.upper()
    for p_sfx, n_sfx in (("_P", "_N"), ("_DP", "_DM"), ("DP", "DM"),
                         ("D+", "D-"), ("+", "-"), ("P", "N")):
        if up.endswith(p_sfx):
            return name[: len(name) - len(p_sfx)] + n_sfx
    return None


def _check_buses(sheets: list[SheetCircuit], res: LinkResult) -> None:
    for sc in sheets:
        buses: dict[str, dict[str, list[str]]] = {}
        for name, pt in sc.circuit.port_types.items():
            if pt.kind == "i2c":
                bus = pt.bus or "I2C"
                buses.setdefault(bus, {}).setdefault(pt.role, []).append(name)
        for bus, roles in buses.items():
            for role, nets in roles.items():
                if len(nets) > 1:
                    res.errors.append(
                        f"i2c bus {bus!r} on {sc.name}: duplicate role "
                        f"{role!r}: {sorted(nets)}")
            for missing in {"scl", "sda"} - set(roles):
                res.warnings.append(
                    f"i2c bus {bus!r} on {sc.name}: no {missing} member typed")


def _check_net_type_agreement(sheets: list[SheetCircuit],
                              res: LinkResult) -> None:
    by_net: dict[str, list[tuple[str, PortType]]] = {}
    for sc in sheets:
        for name, pt in sc.circuit.port_types.items():
            by_net.setdefault(name, []).append((sc.name, pt))
    sd_levels: dict[str, dict[float, list[str]]] = {}
    for sc in sheets:
        for name, pt in sc.circuit.port_types.items():
            if pt.kind == "sd_bus" and pt.level_v is not None:
                bus = pt.bus or "SD"
                sd_levels.setdefault(bus, {}).setdefault(
                    pt.level_v, []).append(f"{sc.name}:{name}")
    for bus, levels in sd_levels.items():
        if len(levels) > 1:
            detail = "; ".join(f"{lv}V: {', '.join(ms)}"
                               for lv, ms in sorted(levels.items()))
            res.errors.append(
                f"sd_bus level mismatch on bus {bus!r}: {detail}")
    for net, typed in by_net.items():
        if len(typed) < 2:
            continue
        kinds = {pt.kind for _, pt in typed if pt.kind != "single"}
        if len(kinds) > 1:
            res.errors.append(
                f"type mismatch on linked net {net!r}: "
                + "; ".join(f"{s}={pt.kind}" for s, pt in typed))
        imps = {pt.impedance for _, pt in typed if pt.impedance is not None}
        if len(imps) > 1:
            res.errors.append(
                f"impedance mismatch on linked net {net!r}: "
                + "; ".join(f"{s}={pt.impedance}R" for s, pt in typed))
        levels = {pt.level_v for _, pt in typed if pt.level_v is not None}
        if len(levels) > 1:
            res.errors.append(
                f"level mismatch on linked net {net!r}: "
                + "; ".join(f"{s}={pt.level_v}V" for s, pt in typed))


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
