"""devkit — build the examples/devkit_mini board from the REUSABLE subsystems.

Proves the library architecture end-to-end: examples/devkit_mini/devkit_mini.py
binds four project-agnostic ``subsystems/<name>/`` packages (usb_pd, usbc_otg,
microsd, uart_bridge) to a SECOND board's net names via thin META adapters, with
ZERO changes to the library. This builds that composition into real KiCad output
(per-sheet schematics + hierarchy root + per-sheet renders) and PROVES the
netlist with the same two oracles the carrier uses — the board netlist gate
(build_board) and the geometry-only connected-components short/open check
(cc_gate, LAW 0).

It reuses the SAME generic machinery as the carrier (`place.place_and_route`,
`output.emit`, `generate.board.build_board`, `verify.cc_gate`,
`output.render.render_sheet_to_png`) — no carrier code is copied. The
carrier-specific steps (the SoM DF40 contract, carrier/sheet_index.json, the
carrier_structure gate, the SoM-centered floorplan) simply do not apply: the
devkit has no SoM, so its sheets just share the board rails
(+3V3_MINI / +5V_MINI / +VBUS_MINI / GND). cmd_board is left untouched, so the
carrier output stays byte-identical.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

REPO_ROOT = Path(__file__).resolve().parents[2]
DEVKIT_DIR = REPO_ROOT / "examples" / "devkit_mini"


def build_devkit(render: bool = True) -> bool:
    """Build examples/devkit_mini -> schematics + hierarchy + renders, and prove
    the netlist (board gate + cc gate). Returns True iff every gate passes."""
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

    # the project's bound subsystem circuits (lib subsystem + this board's META)
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

    # LAW-0 short/open proof, geometry-only (independent of kicad-cli)
    cc_res = cc_gate.check_board(cc_prepared, lib)
    (rep_dir / "cc_gate.txt").write_text(cc_res.summary() + "\n")
    ok_all = ok_all and cc_res.ok
    print(f"  CC GATE: {'PASS' if cc_res.ok else 'FAIL'} "
          f"(0 shorts / 0 opens -> {rep_dir / 'cc_gate.txt'})")

    # the openable hierarchy project + the board netlist gate (no SoM, no
    # sheet_index — refdes bands fall back to sheet order)
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
            except Exception as exc:  # noqa: BLE001 — render is best-effort
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
