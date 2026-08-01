from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from schgen.core.model import Circuit, NetClass
from schgen.core.project import PROJECT_ROOT
from schgen.verify import powertree

PER_CONTACT_A = 0.3
PER_CONTACT_BASIS = (
    "Hirose DF40 series datasheet: rated current 0.3 A/contact "
    "(rated voltage 50 V AC/DC) — CITED (Hirose DF40 catalogue)")

DERATING = 0.8
DERATING_BASIS = (
    "0.8 (20% power-derating margin on the rated per-contact current) — the "
    "standard connector power convention, covering uneven multi-contact load "
    "share + temp-rise tolerance — JUDGMENT, fixed floor (LAW 4)")

_REPO_ROOT = Path(__file__).resolve().parents[2]
_INTERFACE_JSON = PROJECT_ROOT / "som_interface.json"


def _link_maps():
    from schgen.core.link import _load_som_conn_gen
    mod = _load_som_conn_gen()
    return mod.resolve_net, dict(mod.ISOLATED_SOM_RAILS)


@dataclass
class Rail:
    name: str
    contacts: int
    current_a: float
    volts: float | None
    conns: dict[str, int]

    @property
    def capacity_a(self) -> float:
        return self.contacts * PER_CONTACT_A * DERATING

    @property
    def margin_a(self) -> float:
        return self.capacity_a - self.current_a

    @property
    def over(self) -> bool:
        return self.current_a > self.capacity_a + 1e-9

    @property
    def util(self) -> float:
        return self.current_a / self.capacity_a if self.capacity_a > 0 else \
            float("inf")


@dataclass
class Result:
    rails: list[Rail] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    findings: list[str] = field(default_factory=list)
    per_contact_a: float = PER_CONTACT_A
    derating: float = DERATING

    @property
    def ok(self) -> bool:
        return not self.errors


def _delivered_current(pt_res: powertree.Result, sheets) -> dict[str, float]:
    out: dict[str, float] = {}
    for sc in sheets:
        if not sc.name.startswith("som_j"):
            continue
        for rail, entries in sc.circuit.loads.items():
            out[rail] = out.get(rail, 0.0) + sum(a for a, _n in entries)
    return out


def analyze(sheets, pt_res: powertree.Result | None = None,
            interface_json: Path | None = None) -> Result:
    if pt_res is None:
        pt_res = powertree.analyze(sheets)
    res = Result()

    resolve_net, isolated = _link_maps()

    path = interface_json or _INTERFACE_JSON
    data = json.loads(Path(path).read_text())
    connectors = data["connectors"]
    contacts: dict[str, dict[str, int]] = {}
    for ref in sorted(connectors):
        pins: dict[str, str] = connectors[ref]["pins"]
        for _pad, som_net in pins.items():
            if som_net in isolated:
                continue
            rail = resolve_net(som_net)
            if Circuit.classify(rail) is not NetClass.POWER:
                continue
            contacts.setdefault(rail, {}).setdefault(ref, 0)
            contacts[rail][ref] += 1

    delivered = _delivered_current(pt_res, sheets)

    for rail in sorted(contacts):
        conns = contacts[rail]
        n = sum(conns.values())
        current = round(delivered.get(rail, 0.0), 4)
        volts = powertree.rail_volts(rail)
        r = Rail(name=rail, contacts=n, current_a=current, volts=volts,
                 conns=dict(sorted(conns.items())))
        res.rails.append(r)
        if r.over:
            res.errors.append(
                f"UNDER-CONTACTED: {rail} carries {current:.3f} A across "
                f"{n} DF40 contact(s) but the deratied capacity is only "
                f"{r.capacity_a:.3f} A ({n} x {PER_CONTACT_A:g} A x "
                f"{DERATING:g} derate) — margin {r.margin_a:+.3f} A; add "
                f"contacts or reduce the rail current [{PER_CONTACT_BASIS}]")
        if current == 0.0:
            res.findings.append(
                f"{rail}: {n} DF40 contact(s) assigned but no SoM-side draw "
                f"declared on the som_j* sheets — capacity proven, load "
                f"unbooked (no ampacity risk until a draw is declared)")

    res.rails.sort(key=lambda r: (-r.util, r.name))
    return res


def report(res: Result) -> str:
    lines = ["schgen rail-ampacity gate (DF40 power-delivery contact adequacy)",
             "=" * 78, ""]
    lines.append("model: FAIL when rail_current > n_contacts x "
                 f"{res.per_contact_a:g} A x {res.derating:g} derate")
    lines.append(f"  per-contact ampacity : {PER_CONTACT_BASIS}")
    lines.append(f"  derating             : {DERATING_BASIS}")
    lines.append("")
    hdr = (f"  {'rail':<14} {'V':>5} {'contacts':>9} {'current/A':>10} "
           f"{'cap/A':>8} {'util':>6} {'margin/A':>9}  verdict")
    lines.append(hdr)
    lines.append("  " + "-" * (len(hdr) - 2))
    for r in res.rails:
        verdict = "OVER" if r.over else "ok"
        vstr = f"{r.volts:.2f}" if r.volts is not None else "?"
        contacts = "+".join(f"{ref}:{n}" for ref, n in r.conns.items())
        lines.append(
            f"  {r.name:<14} {vstr:>5} {r.contacts:>9} {r.current_a:>10.3f} "
            f"{r.capacity_a:>8.3f} {r.util:>6.2f} {r.margin_a:>+9.3f}  "
            f"{verdict}  [{contacts}]")
    lines.append("")
    if res.findings:
        lines.append(f"findings ({len(res.findings)}):")
        for f_ in res.findings:
            lines.append(f"  + {f_}")
        lines.append("")
    if res.errors:
        lines.append(f"ERRORS ({len(res.errors)}):")
        for e in res.errors:
            lines.append(f"  ERROR: {e}")
    else:
        lines.append("errors: none")
    lines.append("")
    lines.append(f"RAIL AMPACITY: {'PASS' if res.ok else 'FAIL'} "
                 f"({len(res.rails)} delivery rails, {len(res.errors)} "
                 f"under-contacted, {len(res.findings)} unbooked)")
    return "\n".join(lines)


def run(sheets, reports_dir: Path,
        pt_res: powertree.Result | None = None,
        interface_json: Path | None = None) -> Result:
    res = analyze(sheets, pt_res=pt_res, interface_json=interface_json)
    reports_dir.mkdir(parents=True, exist_ok=True)
    (reports_dir / "rail_ampacity.txt").write_text(report(res) + "\n")
    return res


def cmd_rail_ampacity(args) -> int:
    from schgen.core.link import all_subsystem_paths, load_subsystem
    names = getattr(args, "subsystems", None) or \
        [p.stem for p in all_subsystem_paths()]
    sheets = [load_subsystem(n) for n in names]
    repo = Path(__file__).resolve().parents[2]
    res = run(sheets, repo / "carrier" / "reports")
    print(report(res))
    print(f"\nreport: {repo / 'carrier' / 'reports' / 'rail_ampacity.txt'}")
    return 0 if res.ok else 1
