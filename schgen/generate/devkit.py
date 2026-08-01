from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

REPO_ROOT = Path(__file__).resolve().parents[2]
DEVKIT_DIR = REPO_ROOT / "examples" / "devkit_mini"


def build_devkit(render: bool = True) -> bool:
    from examples.devkit_mini import devkit_mini
    from schgen.core.symbols import Library
    from schgen.generate import board as board_mod
    from schgen.layout import place
    from schgen.output.emit import Junction as EJunction
    from schgen.output.emit import PlacedDesign, Wire, emit
    from schgen.verify import cc_gate, netlist_gate

    lib = Library()
    sch_dir = DEVKIT_DIR / "schematic"
    ren_dir = DEVKIT_DIR / "renders"
    rep_dir = DEVKIT_DIR / "reports"
    for d in (sch_dir, ren_dir, rep_dir):
        d.mkdir(parents=True, exist_ok=True)

    sheets = [SimpleNamespace(name=name, circuit=circ)
              for name, circ in devkit_mini.subsystem_circuits()]

    ok_all = True
    placements: dict[str, tuple] = {}
    cc_prepared: list[tuple] = []
    print(f"DEVKIT: building {len(sheets)} library subsystems -> {DEVKIT_DIR}")
    for s in sheets:
        c = s.circuit
        c.validate({r: lib.pin_numbers(p.lib_id) for r, p in c.parts.items()})
        placement, routed, _geo = place.place_and_route(c, lib)
        placements[s.name] = (placement, routed)
        cc_prepared.append((s.name, c, placement, routed))
        design = PlacedDesign(
            circuit=c, parts=placement.parts, powers=placement.powers,
            wires=[Wire(seg.x0, seg.y0, seg.x1, seg.y1) for seg in routed.segs],
            junctions=[EJunction(x, y) for x, y in routed.junctions],
            hlabels=placement.hlabels, llabels=placement.llabels,
            no_connects=placement.no_connects, paper=placement.paper)
        sch = sch_dir / f"{s.name}.kicad_sch"
        emit(design, sch, lib)
        net_res = netlist_gate.check(c, sch)
        ok_all = ok_all and net_res.ok
        print(f"  {s.name}: netlist={'PASS' if net_res.ok else 'FAIL'}")

    cc_res = cc_gate.check_board(cc_prepared, lib)
    (rep_dir / "cc_gate.txt").write_text(cc_res.summary() + "\n")
    ok_all = ok_all and cc_res.ok
    print(f"  CC GATE: {'PASS' if cc_res.ok else 'FAIL'} "
          f"(0 shorts / 0 opens -> {rep_dir / 'cc_gate.txt'})")

    board_ok = board_mod.build_board(
        sheets, lib, DEVKIT_DIR, placements=placements,
        root_name="devkit_mini", sheet_subdir="schematic", reports_dir=rep_dir)
    ok_all = ok_all and board_ok
    print(f"  BOARD NETLIST GATE: {'PASS' if board_ok else 'FAIL'}")

    if render:
        from schgen.output.render import render_sheet_to_png
        for s in sheets:
            try:
                render_sheet_to_png(sch_dir / f"{s.name}.kicad_sch",
                                    ren_dir / f"{s.name}.png")
            except Exception as exc:  # noqa: BLE001
                print(f"  render {s.name}: {exc}")
        print(f"  renders -> {ren_dir}/<name>.png")

    print(f"DEVKIT: {'PASS' if ok_all else 'FAIL'} "
          f"({len(sheets)} sheets -> {DEVKIT_DIR / 'devkit_mini.kicad_pro'})")
    return ok_all


def cmd(args) -> int:
    return 0 if build_devkit(render=not getattr(args, "no_render", False)) else 1


if __name__ == "__main__":
    import argparse
    raise SystemExit(cmd(argparse.ArgumentParser().parse_args()))
