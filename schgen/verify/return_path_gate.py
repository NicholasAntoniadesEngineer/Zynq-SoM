from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from schgen.core.project import PROJECT_ROOT

K = 2

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PARTS_DIR = _REPO_ROOT / "parts"
_INTERFACE_JSON = PROJECT_ROOT / "som_interface.json"

_PAD_RE = re.compile(
    r'\(pad\s+"([^"]*)"'
    r'(?:(?!\(pad).)*?'
    r'\(at\s+(-?[\d.]+)\s+(-?[\d.]+)',
    re.DOTALL,
)

_ROW_TOL = 0.05


@dataclass(frozen=True)
class Contact:
    ref: str
    pad: str
    row: int
    index: int
    x: float
    y: float
    net: str
    klass: str


@dataclass
class Violation:
    ref: str
    base: str
    net: str
    pad: str
    distance: int | None

    def _dist_str(self) -> str:
        return "none-on-connector" if self.distance is None else str(self.distance)

    def as_line(self) -> str:
        return (f"{self.ref} pad {self.pad} net {self.net} (pair {self.base}): "
                f"nearest GND at {self._dist_str()} steps > K={K}")


@dataclass
class ReturnPathResult:
    ok: bool = True
    k: int = K
    n_pairs: int = 0
    n_pair_contacts: int = 0
    violations: list[Violation] = field(default_factory=list)
    dist_hist: dict[int, int] = field(default_factory=dict)
    per_conn: dict[str, tuple[int, int]] = field(default_factory=dict)
    pairs_per_conn: dict[str, int] = field(default_factory=dict)
    worst_distance: int | None = None
    connectors: list[str] = field(default_factory=list)

    @property
    def n_fail(self) -> int:
        return len(self.violations)

    def summary(self) -> str:
        lines = [
            f"RETURN-PATH GATE (HS pairs): {'PASS' if self.ok else 'FAIL'} "
            f"(K={self.k} contact steps)",
            f"  HS pairs crossing DF40s : {self.n_pairs}",
            f"  HS-pair contacts        : {self.n_pair_contacts}",
            f"  failing contacts        : {self.n_fail}",
            f"  worst nearest-GND dist  : "
            f"{'n/a' if self.worst_distance is None else self.worst_distance} "
            f"(budget K={self.k})",
        ]
        lines.append("  nearest-GND distance distribution (dist: count):")
        for dist in sorted(self.dist_hist):
            lines.append(f"    {dist:>2d} steps : {self.dist_hist[dist]}")
        lines.append("  per-connector (pairs, pair-contacts, failing):")
        for ref in sorted(self.per_conn):
            pc, fc = self.per_conn[ref]
            npairs = self.pairs_per_conn.get(ref, 0)
            lines.append(
                f"    {ref}: {npairs} pairs, {pc} pair-contacts, {fc} failing")
        if self.violations:
            lines.append("  VIOLATIONS:")
            for v in sorted(self.violations,
                            key=lambda x: (x.ref, x.base, x.net, x.pad)):
                lines.append(f"    {v.as_line()}")
        return "\n".join(lines)


def classify_net(net: str) -> str:
    up = net.upper()
    if up in {"GND", "AGND", "DGND"} or up.endswith("GND"):
        return "GND"
    if net.startswith("+") or up.startswith("VCC") or up.startswith("VDD"):
        return "POWER"
    return "SIGNAL"


def hs_pair_bases(nets: set[str]) -> list[str]:
    p_bases = {n[:-2] for n in nets if n.endswith("_P")}
    n_bases = {n[:-2] for n in nets if n.endswith("_N")}
    return sorted(p_bases & n_bases)


def pair_partner(net: str) -> str | None:
    toks = net.split("_")
    pn_positions = [i for i, t in enumerate(toks) if t in ("P", "N")]
    if len(pn_positions) != 1:
        return None
    i = pn_positions[0]
    flipped = toks[:]
    flipped[i] = "N" if toks[i] == "P" else "P"
    return "_".join(flipped)


def pair_base(net: str, partner: str) -> str:
    a = net.split("_")
    b = partner.split("_")
    return "_".join("*" if x != y else x for x, y in zip(a, b, strict=False))


def hs_pairs_in(nets: set[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for net in nets:
        partner = pair_partner(net)
        if partner is not None and partner in nets:
            out[net] = pair_base(net, partner)
    return out


def _resolve_footprint(value: str, footprint: str) -> Path | None:
    cand = _PARTS_DIR / value / f"{value}.kicad_mod"
    if cand.is_file():
        return cand
    _, _, name = footprint.partition(":")
    name = name.strip("_")
    if name.startswith("HRS_"):
        name = name[4:]
    if name:
        cand = _PARTS_DIR / name / f"{name}.kicad_mod"
        if cand.is_file():
            return cand
    return None


def _parse_pad_positions(mod_path: Path) -> dict[str, tuple[float, float]]:
    text = mod_path.read_text()
    out: dict[str, tuple[float, float]] = {}
    for num, sx, sy in _PAD_RE.findall(text):
        if num == "":
            continue
        out[num] = (float(sx), float(sy))
    return out


# DF40 pad numbering is not monotonic across rows: row/index come from XY only
def _rows_from_positions(
    positions: dict[str, tuple[float, float]],
) -> dict[str, tuple[int, int]]:
    ys = sorted({y for _, y in positions.values()}, reverse=True)
    row_of_y: list[float] = []
    for y in ys:
        if not any(abs(y - ry) <= _ROW_TOL for ry in row_of_y):
            row_of_y.append(y)

    def row_index(y: float) -> int:
        for i, ry in enumerate(row_of_y):
            if abs(y - ry) <= _ROW_TOL:
                return i
        return len(row_of_y)

    by_row: dict[int, list[tuple[float, str]]] = {}
    for pad, (x, y) in positions.items():
        by_row.setdefault(row_index(y), []).append((x, pad))
    result: dict[str, tuple[int, int]] = {}
    for r, entries in by_row.items():
        for idx, (_x, pad) in enumerate(sorted(entries)):
            result[pad] = (r, idx)
    return result


def build_contacts(
    ref: str,
    pins: dict[str, str],
    positions: dict[str, tuple[float, float]],
) -> list[Contact]:
    rows = _rows_from_positions(positions)
    contacts: list[Contact] = []
    for pad, net in pins.items():
        if pad not in positions or pad not in rows:
            continue
        r, idx = rows[pad]
        x, y = positions[pad]
        contacts.append(Contact(ref=ref, pad=pad, row=r, index=idx, x=x, y=y,
                                 net=net, klass=classify_net(net)))
    contacts.sort(key=lambda c: (c.row, c.index))
    return contacts


def _neighbourhood_gnd_distance(
    contact: Contact,
    contacts: list[Contact],
    k: int,
) -> int | None:
    same_row = {c.index: c for c in contacts if c.row == contact.row}
    other_rows = sorted({c.row for c in contacts if c.row != contact.row})
    facing_row = None
    if other_rows:
        facing_row = min(
            other_rows,
            key=lambda r: abs(
                contact.y
                - next(c.y for c in contacts if c.row == r)
            ),
        )
    facing = ([c for c in contacts if c.row == facing_row]
              if facing_row is not None else [])

    best: int | None = None

    for di in range(-k, k + 1):
        if di == 0:
            continue
        nb = same_row.get(contact.index + di)
        if nb is not None and nb.klass == "GND":
            dist = abs(di)
            best = dist if best is None else min(best, dist)

    for di in range(-k, k + 1):
        target_index = contact.index + di
        anchor = same_row.get(target_index)
        anchor_x = anchor.x if anchor is not None else contact.x
        cand = min(facing, key=lambda c: abs(c.x - anchor_x), default=None)
        if cand is not None and cand.klass == "GND":
            dist = max(1, abs(di))
            best = dist if best is None else min(best, dist)

    return best


def _nearest_gnd_distance_any(
    contact: Contact,
    contacts: list[Contact],
) -> int | None:
    best: int | None = None
    for c in contacts:
        if c.klass != "GND":
            continue
        if c.row == contact.row:
            dist = abs(c.index - contact.index)
        else:
            dist = max(1, abs(c.index - contact.index))
        best = dist if best is None else min(best, dist)
    return best


def check_map(contacts_by_ref: dict[str, list[Contact]], k: int = K):
    res = ReturnPathResult(k=k)
    res.connectors = sorted(contacts_by_ref)

    all_bases: set[str] = set()

    for ref in sorted(contacts_by_ref):
        contacts = contacts_by_ref[ref]
        conn_nets = {c.net for c in contacts}
        net_to_base = hs_pairs_in(conn_nets)
        all_bases.update(net_to_base.values())
        pc_count = 0
        fail_count = 0
        for c in sorted(contacts, key=lambda x: (x.row, x.index)):
            if c.net not in net_to_base:
                continue
            pc_count += 1
            res.n_pair_contacts += 1
            base = net_to_base[c.net]
            within = _neighbourhood_gnd_distance(c, contacts, k)
            report_dist = (within if within is not None
                           else _nearest_gnd_distance_any(c, contacts))
            if report_dist is not None:
                res.dist_hist[report_dist] = res.dist_hist.get(report_dist, 0) + 1
                if res.worst_distance is None or report_dist > res.worst_distance:
                    res.worst_distance = report_dist
            if within is None:
                fail_count += 1
                res.violations.append(
                    Violation(ref=ref, base=base, net=c.net, pad=c.pad,
                              distance=report_dist))
        res.per_conn[ref] = (pc_count, fail_count)
        res.pairs_per_conn[ref] = len(set(net_to_base.values()))

    res.n_pairs = len(all_bases)
    res.violations.sort(key=lambda v: (v.ref, v.base, v.net, v.pad))
    res.ok = not res.violations
    return res


def check(
    interface_json: Path | None = None,
    k: int = K,
):
    path = interface_json or _INTERFACE_JSON
    data = json.loads(Path(path).read_text())
    connectors = data["connectors"]

    contacts_by_ref: dict[str, list[Contact]] = {}
    for ref in sorted(connectors):
        conn = connectors[ref]
        pins: dict[str, str] = conn["pins"]
        mod = _resolve_footprint(conn.get("value", ""), conn.get("footprint", ""))
        if mod is None:
            raise FileNotFoundError(
                f"{ref}: cannot resolve footprint dossier "
                f"(value={conn.get('value')!r}, "
                f"footprint={conn.get('footprint')!r})")
        positions = _parse_pad_positions(mod)
        contacts_by_ref[ref] = build_contacts(ref, pins, positions)

    return check_map(contacts_by_ref, k=k)
