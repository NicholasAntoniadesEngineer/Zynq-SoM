"""Explicit immutable PCB-check snapshots; never a cache of mutable models."""
from dataclasses import asdict
from pathlib import Path
from schgen.core import native


def snapshot(model):
    from schgen.generate.pcb import ORIGIN_X, ORIGIN_Y
    files, insts = {}, []
    for inst in model.insts:
        path = getattr(inst, "mod_path", None)
        key = str(path) if path is not None else None
        if key is not None and key not in files and Path(key).is_file():
            files[key] = Path(key).read_text()
        insts.append(dict(
            ref=inst.ref, value=inst.value, footprint=inst.footprint,
            sheet=inst.sheet, side=inst.side, x=inst.x, y=inst.y,
            rotation=inst.rotation, pad_nets=dict(inst.pad_nets),
            mirror=getattr(inst, "mirror", False), mod_path=key))
    meta = getattr(model, "escape_meta", None)
    raw = dict(board_w=model.board_w, board_h=model.board_h,
               origin_x=ORIGIN_X, origin_y=ORIGIN_Y, insts=insts,
               net_numbers=getattr(model, "net_numbers", {}),
               netclass_of=getattr(model, "netclass_of", {}),
               som_core=getattr(model, "som_core", None),
               copper=getattr(model, "copper", None) or [],
               escape_plan=getattr(model, "escape_plan", None),
               escape_interface_sha256=(meta.get("som_interface_sha256", "")
                                        if meta else None))
    return raw, files


def prepare(model):
    return native.module().pcb_check_prepare(*snapshot(model))


def summary(kind, result):
    return native.module().pcb_check_summary(kind, asdict(result))
