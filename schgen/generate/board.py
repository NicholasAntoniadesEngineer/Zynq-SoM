from __future__ import annotations

import copy
from pathlib import Path

from schgen.core.model import PinRef
from schgen.core.symbols import Library
from schgen.output.emit import PlacedDesign

def _renamed_ref(ref: str, index: int, *, sheet: str = "") -> str:
    from schgen.core import native
    return native.module().board_renamed_ref(ref, index, sheet)


def uniquify(design: PlacedDesign, index: int) -> PlacedDesign:
    d = copy.deepcopy(design)
    c = d.circuit
    ref_map = {ref: _renamed_ref(ref, index, sheet=c.name) for ref in c.parts}
    c.parts = {ref_map[ref]: part for ref, part in c.parts.items()}
    for part in c.parts.values():
        part.ref = ref_map[part.ref]
    for net in c.nets.values():
        net.pins = [PinRef(ref_map[pr.ref], pr.pin) for pr in net.pins]
    c.nc_pins = {PinRef(ref_map[pr.ref], pr.pin) for pr in c.nc_pins}
    for p in d.parts:
        p.ref = ref_map[p.ref]
    for pw in d.powers:
        pw.ref = _renamed_ref(pw.ref, index, sheet=c.name)
    d.standalone = False
    return d




def build_board(sheets, lib: Library, outdir: Path, *,
                placements: dict | None = None,
                root_name: str = "board",
                sheet_subdir: str = "",
                sheet_index: dict[str, int],
                reports_dir: Path | None = None) -> bool:
    from dataclasses import asdict
    from schgen.core import native
    rows = []
    for sheet in sheets:
        row = {"circuit": sheet.circuit.to_ir(), "band": sheet_index[sheet.name]}
        if placements and sheet.name in placements:
            placement, routed = placements[sheet.name]
            data = asdict(placement)
            data["label_bridged"] = sorted(placement.label_bridged)
            row.update(placement=data, segments=[asdict(s) for s in routed.segs],
                       junctions=routed.junctions)
        rows.append(row)
    ok, report = native.module().build_board_schematic(
        rows, lib._native, str(outdir), root_name, sheet_subdir,
        str(reports_dir or outdir))
    print(report)
    return ok


def _board_gate(placed, root_path: Path, outdir: Path, lib: Library) -> bool:
    from dataclasses import asdict
    from schgen.core import native
    rows = []
    for name, design, symbol_uuid in placed:
        data = {key: [asdict(item) for item in getattr(design, key)]
                for key in ("parts", "powers", "wires", "junctions", "hlabels",
                            "llabels", "no_connects", "sheets")}
        data.update(paper=design.paper, standalone=design.standalone)
        rows.append(dict(name=name, circuit=design.circuit.to_ir(),
                         design=data, uuid=symbol_uuid))
    ok, report = native.module().board_netlist_gate(
        rows, lib._native, str(root_path), str(outdir))
    print(report)
    return ok
