"""Power-up sequence diagram (SVG) — the bring-up staging, drawn.

``carrier/docs/power_sequence.svg``: a top-to-bottom staged view of how the
board comes alive, derived from the SAME power-tree analysis the budget gate
runs (``schgen.verify.powertree.analyze``) — so the drawn sequence can never
drift from the netlist. It is the visual twin of the staged
``carrier/docs/BRINGUP.md`` manual:

  Stage 0  always-on (pre-DIP)  : the rails that exist before any DIP closes —
           the USB-C source contract + every rail fed by an ALWAYS-ON
           converter (no EN_* port) or a source, reachable from the inlet.
  Stage 1  rail chain           : the DIP-gated core regulator chain, in
           dependency (BFS-depth) order — each stage's input is the previous
           stage's output, so the order is electrical, not cosmetic.
  Stage 2+ gated module rails   : the load-switch module rails, grouped by the
           parent rail they gate off.

Each box names the rail (+ voltage/load) and, for a gated rail, the EN line /
gate that turns it on. The arrows are dependency edges (parent rail -> child
rail), so the diagram reads exactly like the BRINGUP.md "close one DIP at a
time" procedure.

Deterministic: sorted iteration throughout, content-derived geometry, no
timestamps — re-running ``schgen board`` is byte-identical (proven by the
cross-PYTHONHASHSEED determinism stage in scripts/check.sh, which rebuilds the
whole board).
"""

from __future__ import annotations

import argparse
from pathlib import Path

from schgen.verify import powertree
from schgen.verify.powertree import Reg, Result, SOURCES, rail_volts

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUT = REPO_ROOT / "carrier" / "docs" / "power_sequence.svg"

_FONT = "ui-monospace, SFMono-Regular, Menlo, monospace"

# rails alive before any DIP closes (always-on by design). +5V_SOM is fed by an
# always-on buck (no EN port); +3V3_SC is the SoM SC LDO source. The detector
# below also marks any source rail and any rail whose feeding reg has no EN.
ALWAYS_ON_RAILS = ("+3V3_SC", "+5V_SOM")


def _esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _en_port_of(sheets, reg: Reg) -> str | None:
    """The EN_* PORT net on the regulator's own pins, if any. A reg with an
    EN port is DIP-gated; one without is always-on (strapped on)."""
    from schgen.core.model import NetClass
    by_name = {sc.name: sc.circuit for sc in sheets}
    c = by_name.get(reg.sheet)
    if c is None:
        return None
    ens = []
    for net in c.nets.values():
        if net.net_class != NetClass.PORT:
            continue
        if not net.name.startswith("EN_"):
            continue
        if any(p.ref == reg.ref for p in net.pins):
            ens.append(net.name)
    return sorted(ens)[0] if ens else None


def _depth(res: Result) -> dict[str, int]:
    """BFS depth of every rail from the sources (the dependency order)."""
    depth: dict[str, int] = {r: 0 for r in SOURCES}
    # shunt-bridge endpoints share their source's depth lineage
    changed = True
    while changed:
        changed = False
        for reg in res.regs:
            if reg.vin in depth:
                d = depth[reg.vin] + 1
                if depth.get(reg.vout, -1) < d:
                    depth[reg.vout] = d
                    changed = True
        for _s, _r, a, b in res.bridges:
            if a in depth and depth.get(b, -1) < depth[a]:
                depth[b] = depth[a]
                changed = True
    return depth


def build(sheets, res: Result | None = None) -> dict:
    """The sequence as a plain dict (pure; no I/O) so a test can assert on it
    without rendering. Keys:
      stage0  : sorted always-on rail names (pre-DIP)
      chain   : list of {vout, vin, v, load, limit, en, kind, ref, sheet}
                for the DIP-gated CORE chain (non-load_switch regs), in
                dependency order
      modules : list of same dicts for the load_switch module rails, sorted
                by (parent rail, vout)
    """
    if res is None:
        res = powertree.analyze(sheets)
    depth = _depth(res)

    def row(reg: Reg) -> dict:
        return {
            "vout": reg.vout, "vin": reg.vin,
            "v": rail_volts(reg.vout), "load": round(reg.i_out, 3),
            "limit": round(reg.limit_a, 3), "kind": reg.kind,
            "ref": reg.ref, "sheet": reg.sheet,
            "en": _en_port_of(sheets, reg),
        }

    rows = [row(r) for r in res.regs]
    # Stage 0 = the rails alive before any DIP closes: the source contracts +
    # the documented always-on bucks/LDO outputs (those fed by a converter with
    # NO EN_* port — strapped on by design, e.g. +5V_SOM). A load_switch rail is
    # NEVER always-on (it is gated by a DIP/manual switch even when its EN is a
    # local strap rather than an EN_* port), so it always lands in `modules`.
    always_on = set(SOURCES) | set(ALWAYS_ON_RAILS)
    for r in rows:
        if r["en"] is None and r["kind"] != "load_switch" and r["vout"] in depth:
            always_on.add(r["vout"])

    chain = sorted(
        (r for r in rows
         if r["kind"] != "load_switch" and r["vout"] not in always_on),
        key=lambda r: (depth.get(r["vout"], 99), r["vout"]))
    modules = sorted(
        (r for r in rows if r["kind"] == "load_switch"),
        key=lambda r: (r["vin"], r["vout"]))
    stage0 = sorted(a for a in always_on if a in depth or a in SOURCES)
    return {"stage0": stage0, "chain": chain, "modules": modules}


# ---- SVG render ----------------------------------------------------------------

_BOX_W, _ROW_H, _GAP = 250, 46, 26
_LANE_X = 40
_COL2_X = _LANE_X + _BOX_W + 120        # module column


def _rail_box(x: int, y: int, r: dict, fill: str, stroke: str) -> list[str]:
    e = [f'<rect x="{x}" y="{y}" width="{_BOX_W}" height="{_ROW_H}" rx="8" '
         f'fill="{fill}" stroke="{stroke}" stroke-width="1.5"/>']
    v = r.get("v")
    head = _esc(r["vout"]) + (f"  ({v:g} V)" if v else "")
    e.append(f'<text x="{x + 10}" y="{y + 17}" font-weight="bold" '
             f'font-size="12">{head}</text>')
    sub = f'load {r["load"]:.3f} A / lim {r["limit"]:.2f} A'
    if r.get("en"):
        sub += f'  ·  {_esc(r["en"])}'
    e.append(f'<text x="{x + 10}" y="{y + 34}" fill="#374151" '
             f'font-size="10">{_esc(sub)}</text>')
    return e


def render_svg(seq: dict, out: Path, *, ok: bool = True) -> Path:
    stage0, chain, modules = seq["stage0"], seq["chain"], seq["modules"]

    # vertical layout: stage-0 strip, then one row per chain stage, then the
    # module rails to the right of their parent (looked up by vout position).
    e: list[str] = []
    y = 84
    # key -> box top y. Stage-0/chain keys are the rail name (str); module keys
    # are ("MOD", rail) so a module rail and its parent rail can't collide.
    ypos: dict = {}

    # ---- stage 0 (always-on, pre-DIP) ----
    s0_y = y
    for r in stage0:
        ypos[r] = y
        y += _ROW_H + _GAP
    chain_top = y + 14

    # ---- chain stages ----
    y = chain_top
    for r in chain:
        ypos[r["vout"]] = y
        y += _ROW_H + _GAP
    chain_bottom = y

    # ---- module rails: place each in column 2 at its own row ----
    mod_y0 = max(chain_top, s0_y)
    my = mod_y0
    for r in modules:
        ypos[("MOD", r["vout"])] = my
        my += _ROW_H + 14

    height = max(chain_bottom, my) + 70
    width = _COL2_X + _BOX_W + 60

    e.append(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} '
             f'{height}" font-family="{_FONT}" font-size="11">')
    e.append(f'<rect width="{width}" height="{height}" fill="white"/>')
    e.append(f'<text x="{_LANE_X}" y="30" font-size="15" font-weight="bold">'
             f'carrier power-up sequence — staged bring-up '
             f'({"PASS" if ok else "FAIL"})</text>')
    e.append(f'<text x="{_LANE_X}" y="52" font-size="11" fill="#6b7280">'
             f'derived from the power-tree netlist; matches carrier/docs/'
             f'BRINGUP.md staging. Arrows = rail dependency (parent -&gt; '
             f'child).</text>')

    # stage band labels
    e.append(f'<text x="{_LANE_X}" y="{s0_y - 8}" font-size="12" '
             f'font-weight="bold" fill="#92400e">'
             f'stage 0 — always-on (pre-DIP / pre-PD)</text>')
    e.append(f'<text x="{_LANE_X}" y="{chain_top - 8}" font-size="12" '
             f'font-weight="bold" fill="#1e3a8a">'
             f'stages 1-3 — rail chain (close one DIP at a time)</text>')
    if modules:
        e.append(f'<text x="{_COL2_X}" y="{mod_y0 - 22}" font-size="12" '
                 f'font-weight="bold" fill="#065f46">'
                 f'stage 4 — gated module rails (SY6280 load switches)</text>')

    # dependency edges: parent rail (by vout/source) -> child. Drawn first so
    # boxes paint on top. Chain edges are vertical-ish in column 1; module
    # edges run column 1 -> column 2.
    def cy(key) -> int | None:
        yy = ypos.get(key)
        return yy + _ROW_H // 2 if yy is not None else None

    for r in chain:
        py, ch = cy(r["vin"]), cy(r["vout"])
        if py is None or ch is None:
            continue
        x = _LANE_X + _BOX_W // 2
        color = "#dc2626" if r["load"] > r["limit"] else "#1e3a8a"
        e.append(f'<path d="M{x},{py + _ROW_H // 2 - 1} '
                 f'C{x},{py + 30} {x},{ch - 30} {x},{ch - _ROW_H // 2 + 1}" '
                 f'fill="none" stroke="{color}" stroke-width="1.6"/>')
    for r in modules:
        py, ch = cy(r["vin"]), cy(("MOD", r["vout"]))
        if py is None or ch is None:
            continue
        ax = _LANE_X + _BOX_W
        color = "#dc2626" if r["load"] > r["limit"] else "#059669"
        e.append(f'<path d="M{ax},{py + _ROW_H // 2} '
                 f'C{ax + 60},{py + _ROW_H // 2} {_COL2_X - 60},{ch + _ROW_H // 2} '
                 f'{_COL2_X},{ch + _ROW_H // 2}" fill="none" '
                 f'stroke="{color}" stroke-width="1.2" stroke-opacity="0.6"/>')

    # boxes
    for r in stage0:
        e += _rail_box(_LANE_X, ypos[r], {"vout": r, "v": rail_volts(r),
                       "load": 0.0, "limit": SOURCES.get(r, (0, 0, ""))[1]
                       if r in SOURCES else 0.0, "en": None},
                       "#fef3c7", "#92400e")
    for r in chain:
        e += _rail_box(_LANE_X, ypos[r["vout"]], r, "#eff6ff", "#1e3a8a")
    for r in modules:
        e += _rail_box(_COL2_X, ypos[("MOD", r["vout"])], r,
                       "#ecfdf5", "#065f46")

    e.append("</svg>")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(e) + "\n")
    return out


# ---- entry points ----------------------------------------------------------------

def generate(sheets, res: Result | None = None,
             out: Path = DEFAULT_OUT) -> Path:
    """Render the power-up sequence SVG. ``res`` is the already-computed
    power-tree Result from the board run (recomputed if absent)."""
    if res is None:
        res = powertree.analyze(sheets)
    seq = build(sheets, res)
    return render_svg(seq, out, ok=res.ok)


def cmd_power_sequence(args: argparse.Namespace) -> int:
    from schgen.core.link import (all_subsystem_paths, link,
                                  load_som_contract, load_subsystem)
    names = [p.stem for p in all_subsystem_paths()]
    sheets = [load_subsystem(n) for n in names]
    link(sheets, load_som_contract())
    out = generate(sheets, out=getattr(args, "output", None) or DEFAULT_OUT)
    seq = build(sheets)
    print(f"POWER SEQUENCE: {out.relative_to(REPO_ROOT)} "
          f"({len(seq['stage0'])} always-on, {len(seq['chain'])} chain, "
          f"{len(seq['modules'])} gated module rails)")
    return 0
