"""Signal-integrity CONSTRAINTS (not routing) for the carrier PCB.

This is the SI-rule layer that sits ON TOP of the PCB foundation
(``schgen/generate/pcb.py``). It does NOT route anything and does NOT touch
the schematic netlist or any sheet render. It harvests every differential pair
the schematic actually declares (via ``c.port_type(..., kind=<pair>,
pair_with=..., impedance=...)``), joins each pair to the researched SI target
table (``carrier/research/si_spec.json`` — 37 pairs with target Z_diff,
intra-pair skew, group length-match tolerance, AC-coupling and a standard
citation), and emits three artifacts a layout engineer needs:

1. KiCad **differential-pair + matched-length design rules** appended to the
   board ``.kicad_dru`` (``carrier/manufacturing/Zynq_Carrier_pcb.kicad_dru``):
   per-pair ``(diff_pair_uncoupled ...)``/``skew`` intra-pair rules and per
   length-match-GROUP ``(length ...)`` / ``skew`` rules keyed on the pair's PCB
   net class. KiCad's DRC enforces these once the pairs are routed.
2. A machine + human **SI_CONSTRAINTS.md** table
   (``carrier/manufacturing/SI_CONSTRAINTS.md``): one row per pair with
   interface, net_p, net_n, Z_diff, intra-pair skew, length-match group + group
   tolerance, AC-coupled and the spec citation — the single page of rules.
3. A light **assertion hook** (:func:`check`) the board flow runs: every
   schematic-declared diff pair must have an emitted constraint. It returns a
   verdict object; it does NOT raise, so it cannot flip an existing gate.

DETERMINISM: pairs are sorted by (interface, net_p); groups by a stable key;
the vendored si_spec is committed (no /tmp dependency), so output is
byte-identical across runs and PYTHONHASHSEED. LAW 0: this only ADDS rule text;
it never moves a wire, edits a net, or relaxes a validator (LAW 4).
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from pathlib import Path

from schgen.core.project import PROJECT_ROOT

REPO_ROOT = Path(__file__).resolve().parents[2]
CARRIER = PROJECT_ROOT
SI_SPEC_PATH = CARRIER / "research" / "si_spec.json"
MM_PER_MIL = 0.0254


# ---- the researched SI target table ----------------------------------------------

@dataclass(frozen=True)
class PairSpec:
    """One differential pair's researched SI targets (from si_spec.json)."""
    interface: str
    signal: str
    net_p: str
    net_n: str
    z_diff_ohm: int
    match_tol_mil: float
    intra_pair_skew_mil: float
    ac_coupled: bool
    spec_cite: str
    notes: str

    @property
    def nets(self) -> frozenset[str]:
        return frozenset((self.net_p, self.net_n))


def load_si_spec(path: Path = SI_SPEC_PATH) -> list[PairSpec]:
    """Parse the vendored si_spec.json into PairSpec rows (deterministically
    sorted). Raises if the file is missing — it is committed, so a build
    without it is a real error, not a soft skip."""
    if not path.exists():
        raise FileNotFoundError(
            f"{path} not found — the vendored SI target table is required "
            f"(committed under the project's research/).")
    data = json.loads(path.read_text())
    out: list[PairSpec] = []
    for p in data.get("pairs", []):
        out.append(PairSpec(
            interface=p["interface"],
            signal=p.get("signal", ""),
            net_p=p["net_p"],
            net_n=p["net_n"],
            z_diff_ohm=int(p["z_diff_ohm"]),
            match_tol_mil=float(p["match_tol_mil"]),
            intra_pair_skew_mil=float(p["intra_pair_skew_mil"]),
            ac_coupled=bool(p["ac_coupled"]),
            spec_cite=p["spec_cite"],
            notes=p.get("notes", ""),
        ))
    return sorted(out, key=lambda s: (s.interface, s.net_p))


# ---- harvest the pairs the SCHEMATIC actually declares ---------------------------

def declared_pairs(sheets) -> dict[frozenset[str], tuple[str, str, int]]:
    """{ {net_p,net_n} : (sheet, kind, impedance) } for every differential pair
    declared via ``c.port_type(kind=<pair>, pair_with=...)`` in the subsystem
    models. The frozenset key makes the join order-independent (P/N either
    way)."""
    from schgen.core.model import NetClass
    _PAIR_KINDS = {"diff_pair", "tmds_pair", "usb_hs_pair"}
    seen: dict[frozenset[str], tuple[str, str, int]] = {}
    for sc in sheets:
        c = sc.circuit
        for net in c.nets.values():
            if net.net_class != NetClass.PORT:
                continue
            pt = c.port_type_of(net.name)
            if pt.kind not in _PAIR_KINDS or not pt.pair_with:
                continue
            key = frozenset((net.name, pt.pair_with))
            # impedance is filled by port_type (usb_hs_pair defaults to 90,
            # tmds_pair to 100); first sheet wins, both members agree.
            seen.setdefault(key, (sc.name, pt.kind, pt.impedance or 0))
    return seen


# ---- length-match GROUPS ----------------------------------------------------------
# A group is the set of pairs that must be length-matched TO EACH OTHER (e.g. the
# 3 TMDS data lanes + clock of ONE HDMI port). We group by the pair's interface
# string — every si_spec interface label already names exactly one such port /
# bus instance (e.g. "HDMI TX (TMDS, source)", "MIPI CSI-2 D-PHY (camera)",
# "FMC LPC (VITA 57.1)"). The group's match tolerance is the TIGHTEST (min)
# match_tol_mil of its members (the conservative bound). Deterministic.

_GROUP_RE = re.compile(r"[^A-Za-z0-9]+")


def group_id(interface: str) -> str:
    """Stable, KiCad-friendly group identifier from the interface label."""
    tok = _GROUP_RE.sub("_", interface).strip("_").upper()
    return f"LM_{tok}"


@dataclass(frozen=True)
class LengthGroup:
    gid: str
    interface: str
    members: tuple[PairSpec, ...]      # pairs in this group (sorted)
    tol_mil: float                      # tightest (min) member match tolerance


def length_groups(pairs: list[PairSpec]) -> list[LengthGroup]:
    """Bucket pairs by interface into deterministic length-match groups."""
    by_iface: dict[str, list[PairSpec]] = {}
    for p in pairs:
        by_iface.setdefault(p.interface, []).append(p)
    groups: list[LengthGroup] = []
    for iface in sorted(by_iface):
        members = tuple(sorted(by_iface[iface], key=lambda s: s.net_p))
        tol = min(m.match_tol_mil for m in members)
        groups.append(LengthGroup(group_id(iface), iface, members, tol))
    return groups


# ---- PCB net class of a pair ------------------------------------------------------
# Reuse the SAME class names pcb.py / constraints.py assign so the .dru rules
# (keyed on A.NetClass) line up with the net_settings classes KiCad loads.

def net_class_of(kind: str, impedance: int) -> str:
    from schgen.generate.constraints import _net_class
    return _net_class(kind, impedance, None)


# ---- the model -------------------------------------------------------------------

@dataclass(frozen=True)
class SiModel:
    pairs: tuple[PairSpec, ...]               # every diff pair (spec + present)
    groups: tuple[LengthGroup, ...]
    declared: dict                            # frozenset -> (sheet, kind, imp)
    missing_in_spec: tuple[frozenset[str], ...]   # declared but no spec row
    missing_in_schematic: tuple[PairSpec, ...]    # spec row, not declared


def build_model(sheets) -> SiModel:
    declared = declared_pairs(sheets)
    # The vendored target table is REQUIRED exactly when the project declares
    # diff pairs (a declared pair with no researched target is the real error);
    # a project with zero declared pairs has nothing to constrain — its table
    # is legitimately absent, never a crash.
    spec = ([] if not declared and not SI_SPEC_PATH.exists()
            else load_si_spec())
    spec_by_nets = {s.nets: s for s in spec}

    # pairs we emit = spec rows whose nets are present in the schematic.
    emitted = [s for s in spec if s.nets in declared]
    missing_in_schematic = tuple(s for s in spec if s.nets not in declared)
    missing_in_spec = tuple(sorted(
        (k for k in declared if k not in spec_by_nets),
        key=lambda fs: tuple(sorted(fs))))

    pairs = tuple(sorted(emitted, key=lambda s: (s.interface, s.net_p)))
    groups = tuple(length_groups(list(pairs)))
    return SiModel(pairs=pairs, groups=groups, declared=declared,
                   missing_in_spec=missing_in_spec,
                   missing_in_schematic=missing_in_schematic)


# ---- .kicad_dru emission ----------------------------------------------------------
# We APPEND to the board .kicad_dru that pcb.write_dru already wrote (net-class
# geometry). Here we add SI rules: per-pair intra-pair skew (matched-length
# within the pair) and per-GROUP inter-pair length match. KiCad expresses these
# with (constraint skew ...) on a diff-pair condition and (constraint length
# ...) grouped via net-class. We key on the pair's net names so the rule is
# unambiguous regardless of how the router names the coupled pair.

_SI_BANNER = "# ==== SI CONSTRAINTS (schgen/generate/si_constraints.py) ===="


def _dru_rules(model: SiModel) -> list[str]:
    """The SI rule block to append to the board .kicad_dru."""
    L: list[str] = [
        "",
        _SI_BANNER,
        "# Differential-pair + matched-length rules harvested from the schematic's",
        "# typed ports and joined to carrier/research/si_spec.json (researched",
        "# targets, standard-cited). Intra-pair skew = P/N length match within a",
        "# pair; group length = inter-pair match across a port/bus. Enforced by",
        "# KiCad DRC once the pairs are routed. NOT routing — constraints only.",
        "",
    ]
    # per-pair intra-pair skew (P vs N matched length)
    for p in model.pairs:
        skew_mm = round(p.intra_pair_skew_mil * MM_PER_MIL, 4)
        L += [
            f'(rule "intra_skew_{_safe(p.net_p)}"',
            f"  # {p.interface} — {p.signal}; Zdiff {p.z_diff_ohm}ohm; "
            f"{'AC-coupled' if p.ac_coupled else 'DC-coupled'}",
            f"  # spec: {p.spec_cite}",
            f'  (condition "(A.NetName == \'{p.net_p}\' && '
            f"B.NetName == '{p.net_n}') || (A.NetName == '{p.net_n}' && "
            f"B.NetName == '{p.net_p}')\")",
            f"  (constraint skew (max {skew_mm}mm))",
            ")",
            "",
        ]
    # per-group inter-pair length match: a (constraint skew ...) keyed on every
    # member net of the group. KiCad's `skew` constrains the *relative* length
    # (delay) difference among all nets matching the condition — i.e. matched
    # length across the port/bus — which is exactly the inter-pair tolerance.
    # (We use skew, not an absolute `length` max, so it bounds the spread, not
    # each net's total length.)
    for g in model.groups:
        tol_mm = round(g.tol_mil * MM_PER_MIL, 4)
        nets = []
        for m in g.members:
            nets += [m.net_p, m.net_n]
        cond = " || ".join(f"A.NetName == '{n}'" for n in nets)
        L += [
            f'(rule "lenmatch_{g.gid}"',
            f"  # {g.interface}: {len(g.members)} pair(s) length-matched as a "
            f"group (inter-pair), tol +/-{g.tol_mil:g} mil",
            f'  (condition "{cond}")',
            f"  (constraint skew (max {tol_mm}mm))",
            ")",
            "",
        ]
    return L


def _safe(net: str) -> str:
    """A KiCad-rule-name-safe token from a net name (no quotes/spaces/+/-)."""
    return re.sub(r"[^A-Za-z0-9]+", "_", net).strip("_")


def append_dru(model: SiModel, dru_path: Path) -> Path:
    """Append the SI rule block to the board .kicad_dru. Idempotent: any prior
    SI block (from a previous run) is stripped first, so re-running yields a
    byte-identical file (determinism) and never duplicates rules."""
    base = dru_path.read_text() if dru_path.exists() else "(version 1)\n"
    # strip a previously-appended SI block (everything from the banner on)
    idx = base.find(_SI_BANNER)
    if idx != -1:
        # back up to the blank line that precedes the banner, if any
        base = base[:idx].rstrip("\n")
    else:
        base = base.rstrip("\n")
    text = base + "\n" + "\n".join(_dru_rules(model)) + "\n"
    dru_path.parent.mkdir(parents=True, exist_ok=True)
    dru_path.write_text(text)
    return dru_path


# ---- SI_CONSTRAINTS.md emission ---------------------------------------------------

def _md(model: SiModel) -> str:
    n_pairs = len(model.pairs)
    n_groups = len(model.groups)
    lines = [
        "# Signal-Integrity Constraints — Zynq Carrier",
        "",
        "GENERATED by `schgen/generate/si_constraints.py` (do not hand-edit).",
        "Source of targets: `carrier/research/si_spec.json` (researched, "
        "standard-cited); pairs are harvested from the schematic's typed ports "
        "(`c.port_type(kind=..., pair_with=..., impedance=...)`) so this table "
        "only lists pairs that actually exist on the board.",
        "",
        f"**{n_pairs} differential pairs** in **{n_groups} length-match "
        "groups**. These are CONSTRAINTS for the layout engineer / KiCad DRC — "
        "no routing is implied. The matching rules are also emitted into "
        "`Zynq_Carrier_pcb.kicad_dru` (KiCad design rules).",
        "",
        "## Stackup",
        "",
        "JLCPCB JLC04161H-7628, 4-layer 1.6 mm (Sig / GND / PWR / Sig). "
        "Diff-pair trace geometry (width/gap) per class lives in the "
        "`.kicad_pro` net_settings + `.kicad_dru`: 90R = 0.2611/0.2032 mm, "
        "100R = 0.2052/0.2032 mm (JLCPCB impedance calculator, this stackup).",
        "",
        "## Differential pairs",
        "",
        "| Interface | Signal | net_p | net_n | Z_diff (ohm) | Intra-pair skew "
        "| Length-match group | Group tol | AC-coupled | Net class | Spec |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    gid_of = {}
    for g in model.groups:
        for m in g.members:
            gid_of[m.nets] = g
    for p in model.pairs:
        g = gid_of[p.nets]
        sheet, kind, imp = model.declared[p.nets]
        ncls = net_class_of(kind, imp or p.z_diff_ohm)
        skew_mm = round(p.intra_pair_skew_mil * MM_PER_MIL, 3)
        tol_mm = round(g.tol_mil * MM_PER_MIL, 3)
        lines.append(
            f"| {p.interface} | {p.signal} | `{p.net_p}` | `{p.net_n}` "
            f"| {p.z_diff_ohm} | +/-{p.intra_pair_skew_mil:g} mil "
            f"({skew_mm} mm) | {g.gid} | +/-{g.tol_mil:g} mil ({tol_mm} mm) "
            f"| {'yes' if p.ac_coupled else 'no'} | {ncls} | {p.spec_cite} |")

    lines += ["", "## Length-match groups", "",
              "Each group's pairs must be length-matched **to each other** "
              "(inter-pair) to the group tolerance; within every pair, P and N "
              "match to the intra-pair skew above.", "",
              "| Group | Interface | Pairs | Group match tol | Members |",
              "|---|---|---|---|---|"]
    for g in model.groups:
        mem = ", ".join(f"`{m.net_p}`/`{m.net_n}`" for m in g.members)
        tol_mm = round(g.tol_mil * MM_PER_MIL, 3)
        lines.append(
            f"| {g.gid} | {g.interface} | {len(g.members)} "
            f"| +/-{g.tol_mil:g} mil ({tol_mm} mm) | {mem} |")

    # honesty footer: anything declared-but-unspecced or specced-but-undeclared
    if model.missing_in_spec or model.missing_in_schematic:
        lines += ["", "## Notes / coverage gaps", ""]
        for fs in model.missing_in_spec:
            lines.append(f"- DECLARED in schematic but NO si_spec row: "
                         f"`{'`/`'.join(sorted(fs))}` (no SI target emitted)")
        for s in model.missing_in_schematic:
            lines.append(f"- si_spec row not present in schematic: "
                         f"{s.interface} `{s.net_p}`/`{s.net_n}` "
                         f"({s.notes[:80]})")
    lines.append("")
    return "\n".join(lines)


def write_md(model: SiModel, md_path: Path) -> Path:
    md_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.write_text(_md(model))
    return md_path


# ---- the assertion hook (light gate) ----------------------------------------------

@dataclass(frozen=True)
class SiVerdict:
    ok: bool
    n_pairs: int
    n_groups: int
    uncovered: tuple[frozenset[str], ...]     # declared pair w/ no emitted rule

    def summary(self) -> str:
        head = (f"SI constraints: {self.n_pairs} diff pairs, "
                f"{self.n_groups} length-match groups emitted")
        if self.ok:
            return head + " — every declared pair covered."
        miss = "; ".join("/".join(sorted(fs)) for fs in self.uncovered)
        return head + f" — UNCOVERED declared pair(s): {miss}"


def check(model: SiModel) -> SiVerdict:
    """Assertion: every schematic-declared diff pair has an emitted SI
    constraint (i.e. a matching si_spec row). Returns a verdict; never raises,
    so it cannot flip an existing gate's PASS/FAIL. ``missing_in_spec`` are
    declared pairs with no spec row -> uncovered (the only failure)."""
    emitted_nets = {p.nets for p in model.pairs}
    declared_nets = set(model.declared)
    uncovered = tuple(sorted(
        (fs for fs in declared_nets if fs not in emitted_nets),
        key=lambda fs: tuple(sorted(fs))))
    return SiVerdict(ok=not uncovered, n_pairs=len(model.pairs),
                     n_groups=len(model.groups), uncovered=uncovered)


# ---- entry point ------------------------------------------------------------------

def generate(sheets=None) -> dict:
    """Build the SI model from the carrier sheets, append the .kicad_dru rules,
    write SI_CONSTRAINTS.md, return a result dict (paths, counts, verdict)."""
    if sheets is None:
        from schgen.core.link import all_subsystem_paths, load_subsystem
        sheets = [load_subsystem(p.stem) for p in all_subsystem_paths()]
    model = build_model(sheets)

    dru_path = CARRIER / "manufacturing" / "Zynq_Carrier_pcb.kicad_dru"
    append_dru(model, dru_path)
    md_path = CARRIER / "manufacturing" / "SI_CONSTRAINTS.md"
    write_md(model, md_path)
    verdict = check(model)
    return {
        "dru": dru_path, "md": md_path,
        "n_pairs": verdict.n_pairs, "n_groups": verdict.n_groups,
        "verdict": verdict, "model": model,
    }


def cmd_si(args: argparse.Namespace) -> int:
    res = generate()
    v: SiVerdict = res["verdict"]
    print(f"SI: {res['n_pairs']} diff pairs, {res['n_groups']} length-match "
          f"groups")
    print(f"  rules  -> {res['dru'].relative_to(REPO_ROOT)}")
    print(f"  table  -> {res['md'].relative_to(REPO_ROOT)}")
    print("  " + v.summary())
    return 0 if v.ok else 1


if __name__ == "__main__":
    import sys
    p = argparse.ArgumentParser(prog="schgen si")
    sys.exit(cmd_si(p.parse_args()))
