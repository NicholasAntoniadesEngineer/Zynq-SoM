from __future__ import annotations

import re
from dataclasses import dataclass, field

from schgen.core.model import Circuit, Net, NetClass
from schgen.output.emit import PlacedPart
from schgen.verify.visual_gate import Box

TP_LIB_ID = Circuit.TP_LIB_ID
MH_LIB_ID = Circuit.MH_LIB_ID

U = 1.27

TALL_SHEET_MM = 244.0
GROUND_CELL_LIFT = 2 * U


def is_testpoint(part) -> bool:
    return part.lib_id == TP_LIB_ID


def is_aux_pin(part) -> bool:
    return part.lib_id in (TP_LIB_ID, MH_LIB_ID)


def split(c: Circuit) -> tuple[Circuit, list[str]]:
    tp_refs = sorted((r for r, p in c.parts.items() if is_aux_pin(p)),
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
    if not tp_refs:
        return
    from schgen.layout import textmetrics as tm
    from schgen.layout.place import body_box_page, gceil, gsnap

    lib = eng.lib
    sp = eng.sp
    pl = eng.pl
    ex0, ey0, ex1, ey1 = eng._extent()
    vertical = (ey1 - ey0) > TALL_SHEET_MM
    if vertical:
        fx = gceil(ex1 + 8 * U)
        row_y = gsnap(ey0 + 4 * U)
        wrap_at = None
    else:
        row_y = gceil(ey1 + 6 * U)
        fx = gsnap(ex0 + 4 * U)
        wrap_at = min(ex0 + max(140.0, 0.5 * (ex1 - ex0)),
                      (ex0 + ex1) / 2 + 20.0)
    row_x0 = fx

    def net_of_tp(ref: str):
        for n in c.nets.values():
            if any(pr.ref == ref for pr in n.pins):
                return n
        raise ValueError(f"{ref}: test point carries no net")

    for i, ref in enumerate(tp_refs):
        net = net_of_tp(ref)
        part = c.parts[ref]
        next_is_ground_after_high = (
            net.net_class is not NetClass.GROUND
            and i + 1 < len(tp_refs)
            and net_of_tp(tp_refs[i + 1]).net_class is NetClass.GROUND)
        if not vertical:
            w_ref0, _ = tm.text_wh(ref)
            w_val0, _ = tm.text_wh(part.value)
            cell_right = max(0.76 + 0.42 + max(w_ref0, w_val0),
                             tm.text_wh(net.name)[0] + 1.0)
            if wrap_at is not None and fx > row_x0 \
                    and fx + cell_right > wrap_at:
                fx = row_x0
                row_y = gceil(row_y + 13 * U)
        if net.net_class is NetClass.GROUND:
            tp_xy, rot = (fx, row_y), 0
            pl.plan(net.name, (fx, row_y), (fx, row_y + 2 * U))
            eng.power(net.name, fx, row_y + 2 * U,
                      eng._power_rot(net.name, True))
        elif net.net_class is NetClass.POWER:
            eng.power(net.name, fx, row_y, 0, show_value=False)
            pl.plan(net.name, (fx, row_y), (fx, row_y + 2 * U))
            tp_xy, rot = (fx, row_y + 2 * U), 180
        else:
            eng.llabel(net.name, fx, row_y, 0)
            pl.plan(net.name, (fx, row_y), (fx, row_y + 2 * U))
            tp_xy, rot = (fx, row_y + 2 * U), 180

        sdef = lib.get(part.lib_id)
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
            row_y = gceil(row_y + 2 * U + 4.064 + 4 * U
                          + (GROUND_CELL_LIFT if next_is_ground_after_high
                             else 0.0))
        else:
            right = max(body.x1 + 0.42 + w_ref, body.x1 + 0.42 + w_val,
                        fx + tm.text_wh(net.name)[0] + 1.0)
            fx = gceil(right + max(sp.flag_pitch - 6 * U, 2 * U) + 2 * U)


_UART_RE = re.compile(r"UART\d*_(TXD|RXD)$")
_EN_RE = re.compile(r"(^EN_|_EN$)")


@dataclass
class Coverage:
    required: dict[str, str] = field(default_factory=dict)
    have: dict[str, list[str]] = field(default_factory=dict)
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
