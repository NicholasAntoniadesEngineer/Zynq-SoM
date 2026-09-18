from __future__ import annotations

from dataclasses import dataclass, field

from schgen.core import native as _nat
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
            # A probe-only PORT has no core component to emit its sheet pin.
            # A local label looks correct in a standalone netlist but leaves
            # the probe disconnected when this sheet joins the board hierarchy.
            exported = any(h.name == net.name for h in pl.hlabels)
            if net.net_class is NetClass.PORT and not exported:
                eng.label(net.name, fx, row_y, 0)
                stub = 4 * U  # Clear the hierarchical frame from probe text.
            else:
                eng.llabel(net.name, fx, row_y, 0)
                stub = 2 * U
            pl.plan(net.name, (fx, row_y), (fx, row_y + stub))
            tp_xy, rot = (fx, row_y + stub), 180

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
        return _nat.module().testpoint_coverage_report(self)


def check_coverage(sheets) -> Coverage:
    raw = _nat.module().testpoint_coverage(sheets)
    return Coverage(required=raw["required"], have=raw["have"],
                    waived={net: tuple(value) for net, value in raw["waived"].items()},
                    errors=raw["errors"], extras=raw["extras"])
