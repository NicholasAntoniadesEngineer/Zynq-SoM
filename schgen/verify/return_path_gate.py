"""HS-pair RETURN-PATH gate — a ground contact must sit physically near every
high-speed differential pair crossing the SoM DF40 mezzanine connectors.

The defect this closes is invisible to ERC, DRC and the netlist gate: a
high-speed differential pair (Ethernet MDI, USB) whose DF40 contacts have NO
ground contact in their immediate physical neighbourhood has no local return
path. The return current is forced to detour to the nearest ground pin, which
inflates the loop area, radiates, and degrades the pair's impedance/insertion
loss. The netlist is perfectly connected in that case (GND exists somewhere on
the connector), so no connectivity check fires — only the PHYSICAL adjacency of
a ground contact to the pair's contacts tells the truth. This gate reads that
adjacency straight from the footprint PAD GEOMETRY.

Why geometry, not pin numbers: the DF40 numbering does NOT run monotonically
across the two rows. On this footprint the top row (Y>0) carries pads 1..50 with
X DECREASING as the number rises, while the bottom row (Y<0) carries pads
51..100 with X INCREASING. So the contact physically FACING pad ``n`` in the top
row is ``101-n`` in the bottom row, NOT ``n+50``. Deriving neighbourhoods from
the numbering would therefore mis-identify every facing neighbour. The row and
along-row index of each contact are recovered from the pad (at X Y) positions,
which are the ground truth.

Pair naming (BOTH conventions the SoM contract uses):
  * SUFFIX style ``<base>_P`` / ``<base>_N`` — the on-SoM Ethernet MDI and USB
    pairs (``ETH_PHY_MDI0_P``/``_N``, ``STM32_USB_D_P``/``_N``).
  * XILINX style ``IO_L<n>_<P|N>_<bank>`` and its ``SRCC``/``MRCC``/``VREF``
    variants (``IO_L11_SRCC_<P|N>_<bank>``, ``IO_L14_<P|N>_SRCC_<bank>``): the
    ``P``/``N`` token sits MID-NAME, before the bank suffix. TMDS/FMC/CSI diff
    pairs arrive on exactly these. A pair is two nets identical in every
    underscore-delimited token EXCEPT one position, which is ``P`` in one and
    ``N`` in the other — regardless of where in the name that token sits. The
    two nets must land on the SAME connector (conservative: a half-pair routed
    to only one connector is treated as single-ended, not a pair).
  ALL detected pairs are treated as HIGH-SPEED for the return-path check (the
  safe direction). The per-connector pair COUNT is reported so the verdict can
  be sanity-checked.

INVARIANT (measured, reported as numbers — see the two-gate split below):
  * every contact that carries an HS-pair net (a P/N partner net present on the
    SAME DF40 connector, either naming style above) has at least one GROUND
    contact within physical radius ``K`` steps — measured as same-row index
    steps and facing-row nearest-index steps (see ``K`` below).

TWO-GATE SPLIT (codified 2026-07-02, T2 escape wave).  The SoM pinout is
FIXED: no carrier copper can add a ground CONTACT next to a pair, so this
gate's contact-level result is a measured FACT of the mated interface — red
by module design (29 contacts beyond K=2 on the live pinout).  It is
therefore REPORT-ONLY, permanently: its verdict is quoted VERBATIM in the
board report (never buried, never softened — K and every threshold are
untouched, LAW 4), its population scalars are pinned in pytest so any SoM
drift alarms, and its failing set is the BUILD INPUT the escape generator
(schgen/generate/pcb/escape.py) consumes.  The carrier-side HARD obligation
lives in ``schgen.verify.return_stitch_gate`` (return-path v2): every
v1-failing contact must have a carrier GND stitch via within 2.0 mm on a
file-visible GND ladder under the In1 plane.  That gate is ANDed into the
board verdict; this one is deliberately NOT — a tested design decision
(test_return_path_gate.py::test_v1_is_report_only_by_design), not a wiring
accident.  Nothing anywhere claims "return path fixed": the deliverable is
carrier escape-fanout return stitching.

The module has NO import side effects and touches no global state.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from schgen.core.project import PROJECT_ROOT

# Physical search radius, in CONTACT STEPS, for a ground return contact around an
# HS-pair contact. K = 2 means: the two same-row neighbours on each side, plus
# the facing-row contacts within +/-2 along-row indices of the pair contact. The
# justification is the DF40 0.4 mm pitch and the 2-row 1.6 mm row spacing: at
# K=2 the farthest ground still admitted is ~0.8 mm along the row or ~1.7 mm
# diagonally across the rows, i.e. a ground fully adjacent to the pair's own
# two contacts (a P/N pair already occupies 2 in-row steps). A ground beyond
# K=2 is separated from the pair by another signal contact on every path, so the
# return current must route AROUND that signal — the SI defect this gate exists
# to catch. K is fixed (not a tunable) so the gate cannot be weakened (LAW 4).
K = 2

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PARTS_DIR = _REPO_ROOT / "parts"
_INTERFACE_JSON = PROJECT_ROOT / "som_interface.json"

# A pad block in a KiCad .kicad_mod, single- or multi-line, capturing the pad
# NUMBER then the first (at X Y ...) inside the same block.
_PAD_RE = re.compile(
    r'\(pad\s+"([^"]*)"'          # pad number/name
    r'(?:(?!\(pad).)*?'           # anything up to the pad's own (at ...)
    r'\(at\s+(-?[\d.]+)\s+(-?[\d.]+)',
    re.DOTALL,
)

# rows are considered "the same" if their pad-Y coincides to this tolerance (mm)
_ROW_TOL = 0.05


@dataclass(frozen=True)
class Contact:
    """One populated connector contact: its physical place + electrical role."""

    ref: str            # connector reference (J1/J2/J3)
    pad: str            # pad number as printed in the footprint
    row: int            # 0-based row index (sorted by Y descending -> stable)
    index: int          # 0-based along-row index (sorted by X ascending)
    x: float
    y: float
    net: str
    klass: str          # "GND" | "POWER" | "SIGNAL"


@dataclass
class Violation:
    ref: str
    base: str           # HS-pair base label ('*' at flipped token), e.g.
    #                     "ETH_PHY_MDI0_*" or "IO_L10_*_13"
    net: str            # the specific rail (P or N half) that is exposed
    pad: str
    distance: int | None  # steps to nearest GND, or None if none anywhere

    def _dist_str(self) -> str:
        return "none-on-connector" if self.distance is None else str(self.distance)

    def as_line(self) -> str:
        return (f"{self.ref} pad {self.pad} net {self.net} (pair {self.base}): "
                f"nearest GND at {self._dist_str()} steps > K={K}")


@dataclass
class ReturnPathResult:
    ok: bool = True
    k: int = K
    n_pairs: int = 0                       # HS pairs crossing the DF40s
    n_pair_contacts: int = 0               # contacts carrying an HS-pair net
    violations: list[Violation] = field(default_factory=list)
    # distance -> how many HS-pair contacts had that nearest-GND distance
    dist_hist: dict[int, int] = field(default_factory=dict)
    # ref -> (pair contacts, failing contacts) tally
    per_conn: dict[str, tuple[int, int]] = field(default_factory=dict)
    # ref -> number of distinct HS pairs landing on that connector (both halves)
    pairs_per_conn: dict[str, int] = field(default_factory=dict)
    worst_distance: int | None = None      # max nearest-GND distance seen
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
    """GND / POWER / SIGNAL for a connector net name.

    GND  : named GND/AGND/DGND, or ending in "GND".
    POWER: starts with '+', or a VCC-/VDD- prefixed rail.
    else : SIGNAL.
    """
    up = net.upper()
    if up in {"GND", "AGND", "DGND"} or up.endswith("GND"):
        return "GND"
    if net.startswith("+") or up.startswith("VCC") or up.startswith("VDD"):
        return "POWER"
    return "SIGNAL"


def hs_pair_bases(nets: set[str]) -> list[str]:
    """Bases for which both ``<base>_P`` and ``<base>_N`` are in ``nets``.

    SUFFIX-style detector only: recognises the exact ``_P``/``_N`` suffix (the
    SoM's Ethernet MDI and USB pairs). This is the narrow historical helper kept
    for its stable contract; the full gate uses :func:`pair_partner` /
    :func:`hs_pairs_in`, which also cover the Xilinx MID-NAME ``P``/``N`` style.
    Sorted for determinism."""
    p_bases = {n[:-2] for n in nets if n.endswith("_P")}
    n_bases = {n[:-2] for n in nets if n.endswith("_N")}
    return sorted(p_bases & n_bases)


def pair_partner(net: str) -> str | None:
    """The differential PARTNER net of ``net`` by flipping its single ``P``/``N``.

    A diff-pair net has EXACTLY ONE underscore-delimited token equal to ``P`` or
    ``N``; the partner is that same name with the token flipped (``P``<->``N``).
    This covers BOTH the suffix style (``ETH_PHY_MDI0_P`` ->
    ``ETH_PHY_MDI0_N``) and the Xilinx mid-name style (``IO_L10_P_13`` ->
    ``IO_L10_N_13``; ``IO_L11_SRCC_P_13`` -> ``IO_L11_SRCC_N_13``;
    ``IO_L14_P_SRCC_13`` -> ``IO_L14_N_SRCC_13``).

    Returns None when the net has NO ``P``/``N`` token or has MORE THAN ONE
    (ambiguous — refuse to guess; conservative single-ended). The partner is a
    STRING; whether it actually exists on a connector is decided by the caller
    (a pair requires both halves on the SAME connector)."""
    toks = net.split("_")
    pn_positions = [i for i, t in enumerate(toks) if t in ("P", "N")]
    if len(pn_positions) != 1:
        return None
    i = pn_positions[0]
    flipped = toks[:]
    flipped[i] = "N" if toks[i] == "P" else "P"
    return "_".join(flipped)


def pair_base(net: str, partner: str) -> str:
    """A stable, position-independent BASE label shared by a P/N pair.

    Built by replacing the flipped token with ``*`` (e.g. ``IO_L10_P_13`` and
    ``IO_L10_N_13`` both yield ``IO_L10_*_13``; ``ETH_PHY_MDI0_P``/``_N`` ->
    ``ETH_PHY_MDI0_*``). Deterministic and identical for both halves, so it
    groups the pair in reports regardless of which net is looked at first."""
    a = net.split("_")
    b = partner.split("_")
    return "_".join("*" if x != y else x for x, y in zip(a, b, strict=False))


def hs_pairs_in(nets: set[str]) -> dict[str, str]:
    """Map every net that is HALF of a same-set differential pair to its base.

    A net participates only when its :func:`pair_partner` also lies in ``nets``
    (both halves present) — the SAME-connector requirement when ``nets`` is one
    connector's nets. Returns ``{net: base}`` covering both halves of each pair;
    single-ended nets and unmatched half-pairs are absent."""
    out: dict[str, str] = {}
    for net in nets:
        partner = pair_partner(net)
        if partner is not None and partner in nets:
            out[net] = pair_base(net, partner)
    return out


def _resolve_footprint(value: str, footprint: str) -> Path | None:
    """The .kicad_mod dossier for a connector.

    Prefer the populated part's ``value`` dossier
    (``parts/<value>/<value>.kicad_mod``) — that is the authoritative geometry.
    Fall back to the footprint field's ``<nick>:<name>`` (stripping a KiCad
    ``HRS_`` vendor prefix and trailing underscores). Returns None if neither
    resolves; the caller decides how to report a missing footprint."""
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
    """pad number -> (x, y) from a .kicad_mod. Empty pad names are skipped."""
    text = mod_path.read_text()
    out: dict[str, tuple[float, float]] = {}
    for num, sx, sy in _PAD_RE.findall(text):
        if num == "":
            continue
        out[num] = (float(sx), float(sy))
    return out


def _rows_from_positions(
    positions: dict[str, tuple[float, float]],
) -> dict[str, tuple[int, int]]:
    """Map each pad to (row_index, along_row_index) from GEOMETRY alone.

    Rows are the distinct pad-Y bands (tolerance ``_ROW_TOL``), ordered by Y
    DESCENDING so the assignment is stable and independent of pad numbering.
    Within a row the along-row index is the rank of the pad's X (ascending)."""
    ys = sorted({y for _, y in positions.values()}, reverse=True)
    row_of_y: list[float] = []
    for y in ys:
        if not any(abs(y - ry) <= _ROW_TOL for ry in row_of_y):
            row_of_y.append(y)

    def row_index(y: float) -> int:
        for i, ry in enumerate(row_of_y):
            if abs(y - ry) <= _ROW_TOL:
                return i
        return len(row_of_y)  # unreachable for well-formed input

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
    """Ordered, geometry-placed, classified contacts for one connector.

    Only pads that exist BOTH in the pinout and in the footprint geometry become
    contacts (shield/mechanical pads absent from the contract are ignored)."""
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
    """Min contact-step distance from ``contact`` to a GND contact within k.

    Neighbourhood of a contact at (row r, index i), radius k:
      * SAME row, indices i-k..i+k (excluding i itself) -> distance |di|.
      * the FACING row (nearest other row, chosen by physical row-Y gap): the
        contact at each along-row index j in i-k..i+k, mapped by GEOMETRY (the
        facing contact nearest in X), at distance max(1, |di|).
    Returns the minimum distance to any GND contact in that set, or None if
    there is no GND within k (or no GND on the connector at all)."""
    same_row = {c.index: c for c in contacts if c.row == contact.row}
    other_rows = sorted({c.row for c in contacts if c.row != contact.row})
    facing_row = None
    if other_rows:
        # facing = the row whose contacts are physically closest in Y
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

    # same-row neighbours
    for di in range(-k, k + 1):
        if di == 0:
            continue
        nb = same_row.get(contact.index + di)
        if nb is not None and nb.klass == "GND":
            dist = abs(di)
            best = dist if best is None else min(best, dist)

    # facing-row neighbours: nearest-in-X contact at each offset index
    for di in range(-k, k + 1):
        target_index = contact.index + di
        # nearest facing contact to that along-row index (geometry: closest X to
        # the same-row contact at target_index, else to this contact's own X)
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
    """Nearest GND in the WHOLE connector, in contact steps (for reporting).

    Distance is same-row index gap, or for a cross-row GND the along-row index
    gap between the two contacts' along-row positions (min 1). None if the
    connector has no GND contact at all."""
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
    """Run the gate over already-built per-connector contact maps.

    Split out from :func:`check` so tests can drive SYNTHETIC maps with no repo
    data. Returns a :class:`ReturnPathResult`."""
    res = ReturnPathResult(k=k)
    res.connectors = sorted(contacts_by_ref)

    # HS pairs are detected PER CONNECTOR (a pair requires both halves on the
    # SAME connector) and cover BOTH naming styles via pair_partner(). Bases are
    # position-independent ``*`` labels so the two conventions report uniformly.
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
        # distinct pair bases actually landing on THIS connector (both halves)
        res.pairs_per_conn[ref] = len(set(net_to_base.values()))

    res.n_pairs = len(all_bases)
    res.violations.sort(key=lambda v: (v.ref, v.base, v.net, v.pad))
    res.ok = not res.violations
    return res


def check(
    interface_json: Path | None = None,
    k: int = K,
):
    """Load the SoM interface contract + footprint geometry and run the gate.

    ``interface_json`` defaults to ``carrier/som_interface.json``. Raises
    FileNotFoundError if the interface or a connector footprint is missing (a
    missing footprint is an integrity failure, not something to silently pass).
    """
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
