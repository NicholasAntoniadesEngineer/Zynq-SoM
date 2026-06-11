"""Test-point machinery (PLAN round 4): engine placement + the COVERAGE GATE.

Authoring: ``c.testpoint(net)`` in a subsystem (model-only, purity intact)
adds a KiCad ``Connector:TestPoint`` on a pad-only footprint
(``TestPoint:TestPoint_Pad_D1.5mm`` — copper, no component, no BOM line:
the BOM/preflight exporters skip ``BOM=exclude`` parts).

Placement: the ENGINE owns all geometry. ``schgen.place.build`` strips the
TP parts before the topology templates run (so a probe point can never
perturb the circuit's own layout), then appends a dedicated PROBE ROW below
the sheet extent — one cell per TP:

- GROUND net:  TP (circle up) with a stub down to a GND symbol;
- POWER rail:  rail symbol on top, stub down to the TP (circle down) — the
  rail name is the TP's Value text, so it reads once;
- PORT net:    a LOCAL label on the stub top — KiCad merges the islet by
  name (route.py's labeled-islet rule), the netlist gate proves the merge.

Coverage GATE (hooked into ``schgen board``): every POWER/GROUND rail and
every key single-ended bus — i2c-typed ports, sd_bus CMD/CLK, UART RXD/TXD,
and EN lines (bring-up philosophy: every enable is probeable) — must own a
test point somewhere on the board, or carry an EXPLICIT author waiver
``c.waive_tp(net, reason)``. Waivers are listed verbatim in the report.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from schgen.model import Circuit, Net, NetClass
from schgen.emit import PlacedPart
from schgen.verify.visual_gate import Box

TP_LIB_ID = Circuit.TP_LIB_ID

U = 1.27


def is_testpoint(part) -> bool:
    return part.lib_id == TP_LIB_ID


def split(c: Circuit) -> tuple[Circuit, list[str]]:
    """A shallow working copy of ``c`` without the TP parts/pins (the
    engine's templates see the UNCHANGED circuit topology), plus the TP refs.
    The original circuit is never mutated."""
    tp_refs = sorted((r for r, p in c.parts.items() if is_testpoint(p)),
                     key=lambda r: (len(r), r))
    if not tp_refs:
        return c, []
    tps = set(tp_refs)
    import copy
    core = copy.copy(c)
    core.parts = {r: p for r, p in c.parts.items() if r not in tps}
    core.nets = {}
    for name, n in c.nets.items():
        nn = Net(name=n.name, net_class=n.net_class)
        nn.pins = [pr for pr in n.pins if pr.ref not in tps]
        core.nets[name] = nn
    return core, tp_refs


def add_probe_row(eng, c: Circuit, tp_refs: list[str]) -> None:
    """Append the probe row to the engine's placement. ``eng`` is the live
    ``place._Engine`` (its ``pl``/``power``/``llabel`` factories already
    carry the sheet's geometry); ``c`` is the FULL circuit (with TPs)."""
    if not tp_refs:
        return
    from schgen import textmetrics as tm
    from schgen.place import body_box_page, gceil, gsnap

    lib = eng.lib
    sp = eng.sp
    pl = eng.pl
    sdef = lib.get(TP_LIB_ID)
    ex0, ey0, ex1, ey1 = eng._extent()
    # tall sheets (the FMC connector fan rides the A3 height budget): the
    # probe row would push past the frame — stack a probe COLUMN to the
    # right of the extent instead. Same cells, vertical rhythm.
    vertical = (ey1 - ey0) > 244.0
    if vertical:
        fx = gceil(ex1 + 8 * U)
        row_y = gsnap(ey0 + 4 * U)
        wrap_at = None
    else:
        row_y = gceil(ey1 + 6 * U)      # top anchors of the probe row
        fx = gsnap(ex0 + 4 * U)
        # the row lives in the page's BOTTOM band where the title block
        # owns the right side: wrap into extra rows on the LEFT half so a
        # wide probe row can never reach the frame's title block. The
        # extent is centered on the page later, and the title block's left
        # edge sits ~27 mm right of the page center on A4 (~88 mm on A3) —
        # capping the row at extent-center + 20 mm clears both papers.
        wrap_at = min(ex0 + max(140.0, 0.5 * (ex1 - ex0)),
                      (ex0 + ex1) / 2 + 20.0)
    row_x0 = fx

    def net_of_tp(ref: str):
        for n in c.nets.values():
            if any(pr.ref == ref for pr in n.pins):
                return n
        raise ValueError(f"{ref}: test point carries no net")

    for ref in tp_refs:
        net = net_of_tp(ref)
        part = c.parts[ref]
        if not vertical:
            # cell-width-aware wrap BEFORE placing: the ref/value texts and
            # the label all extend right of the stub
            w_ref0, _ = tm.text_wh(ref)
            w_val0, _ = tm.text_wh(part.value)
            cell_right = max(0.76 + 0.42 + max(w_ref0, w_val0),
                             tm.text_wh(net.name)[0] + 1.0)
            if wrap_at is not None and fx > row_x0 \
                    and fx + cell_right > wrap_at:
                fx = row_x0
                row_y = gceil(row_y + 13 * U)   # next probe row
        if net.net_class is NetClass.GROUND:
            # TP circle up at the row line, stub DOWN to the ground symbol
            tp_xy, rot = (fx, row_y), 0
            pl.plan(net.name, (fx, row_y), (fx, row_y + 2 * U))
            eng.power(net.name, fx, row_y + 2 * U,
                      eng._power_rot(net.name, True))
        elif net.net_class is NetClass.POWER:
            # rail symbol on top (name shown once, as the TP Value)
            eng.power(net.name, fx, row_y, 0, show_value=False)
            pl.plan(net.name, (fx, row_y), (fx, row_y + 2 * U))
            tp_xy, rot = (fx, row_y + 2 * U), 180
        else:                              # PORT: labeled islet (route.py)
            eng.llabel(net.name, fx, row_y, 0)
            pl.plan(net.name, (fx, row_y), (fx, row_y + 2 * U))
            tp_xy, rot = (fx, row_y + 2 * U), 180

        body = body_box_page(sdef, tp_xy[0], tp_xy[1], rot, "body", ref)
        w_ref, _ = tm.text_wh(ref)
        w_val, _ = tm.text_wh(part.value)
        cy = (body.y0 + body.y1) / 2
        rp = (body.x1 + 0.42 + w_ref / 2, cy - 1.27, 0)
        vp = (body.x1 + 0.42 + w_val / 2, cy + 1.27, 0)
        pl.parts.append(PlacedPart(ref, part.lib_id, part.value,
                                   tp_xy[0], tp_xy[1], rot, part.footprint,
                                   ref_pos=rp, val_pos=vp))
        pl.boxes.append(body)
        pl.boxes.append(Box(*tm.centered_box(ref, rp[0], rp[1]),
                            "reference", ref))
        pl.boxes.append(Box(*tm.centered_box(part.value, vp[0], vp[1]),
                            "value", ref))
        eng._done.add(ref)

        if vertical:
            # advance DOWN one cell (stub + body + breathing room)
            row_y = gceil(row_y + 2 * U + 4.064 + 4 * U)
        else:
            # advance RIGHT past this cell's widest feature
            right = max(body.x1 + 0.42 + w_ref, body.x1 + 0.42 + w_val,
                        fx + tm.text_wh(net.name)[0] + 1.0)
            fx = gceil(right + max(sp.flag_pitch - 6 * U, 2 * U) + 2 * U)


# ---- the coverage gate -----------------------------------------------------------

_UART_RE = re.compile(r"UART\d*_(TXD|RXD)$")
_EN_RE = re.compile(r"(^EN_|_EN$)")


@dataclass
class Coverage:
    required: dict[str, str] = field(default_factory=dict)   # net -> why
    have: dict[str, list[str]] = field(default_factory=dict)  # net -> TP locs
    waived: dict[str, tuple[str, str]] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    extras: dict[str, list[str]] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return not self.errors

    @property
    def covered(self) -> int:
        return sum(1 for n in self.required if n in self.have)

    def report(self) -> str:
        lines = ["schgen test-point coverage gate", "=" * 64, ""]
        lines.append("rule: every POWER/GROUND rail + key single-ended bus "
                     "(i2c ports, sd_bus CMD/CLK, UART RXD/TXD, EN lines) "
                     "owns a probe point or an explicit waiver.")
        lines.append("")
        lines.append(f"required nets ({len(self.required)}):")
        for net in sorted(self.required):
            if net in self.have:
                state = "TP @ " + ", ".join(self.have[net])
            elif net in self.waived:
                sheet, reason = self.waived[net]
                state = f"WAIVED ({sheet}): {reason}"
            else:
                state = "UNCOVERED"
            lines.append(f"  {net:<22} [{self.required[net]:<9}] {state}")
        extra = {n: locs for n, locs in self.have.items()
                 if n not in self.required}
        if extra:
            lines.append("")
            lines.append(f"additional probe points ({len(extra)}):")
            for net in sorted(extra):
                lines.append(f"  {net:<22} TP @ {', '.join(extra[net])}")
        if self.waived:
            lines.append("")
            lines.append(f"waivers — author-declared, verbatim "
                         f"({len(self.waived)}):")
            for net in sorted(self.waived):
                sheet, reason = self.waived[net]
                lines.append(f"  {net:<22} ({sheet}) {reason}")
        lines.append("")
        if self.errors:
            lines.append(f"ERRORS ({len(self.errors)}):")
            for e in self.errors:
                lines.append(f"  ERROR: {e}")
        else:
            lines.append("errors: none")
        lines.append("")
        lines.append(f"TESTPOINTS: {'PASS' if self.ok else 'FAIL'} "
                     f"({self.covered}/{len(self.required)} required nets "
                     f"covered, {len(self.waived)} waived)")
        return "\n".join(lines)


def check_coverage(sheets) -> Coverage:
    cov = Coverage()
    for sc in sheets:
        c = sc.circuit
        for net in c.nets.values():
            if net.net_class in (NetClass.POWER, NetClass.GROUND):
                cov.required.setdefault(net.name, "rail")
            elif net.net_class is NetClass.PORT:
                pt = c.port_type_of(net.name)
                if pt.kind == "i2c":
                    cov.required.setdefault(net.name, "i2c")
                elif pt.kind == "sd_bus" and \
                        net.name.endswith(("CMD", "CLK")):
                    cov.required.setdefault(net.name, "sd_bus")
                elif _UART_RE.search(net.name):
                    cov.required.setdefault(net.name, "uart")
                elif _EN_RE.search(net.name):
                    cov.required.setdefault(net.name, "enable")
        for ref, part in sorted(c.parts.items()):
            if is_testpoint(part):
                tp_net = next(n.name for n in c.nets.values()
                              if any(pr.ref == ref for pr in n.pins))
                cov.have.setdefault(tp_net, []).append(f"{sc.name}:{ref}")
        for net, reason in c.tp_waivers.items():
            cov.waived[net] = (sc.name, reason)
    for net in sorted(cov.required):
        if net not in cov.have and net not in cov.waived:
            cov.errors.append(
                f"{net} [{cov.required[net]}] has no test point and no "
                f"waiver — add c.testpoint({net!r}) or "
                f"c.waive_tp({net!r}, reason)")
    return cov
