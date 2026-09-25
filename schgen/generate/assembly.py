from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path

from schgen.core import native
from schgen.core.project import PROJECT_ROOT, REPO_ROOT
from schgen.generate import pcb as pcb_mod
from schgen.generate.pcb import PcbModel
from schgen.generate.pcb.constants import FIDUCIAL_FOOTPRINT, FootprintInst
from schgen.generate.pcb._native_emit import prepare, policy

CARRIER = PROJECT_ROOT
ASSEMBLY_MD = CARRIER / "manufacturing" / "ASSEMBLY.md"
PNG_DIR = CARRIER / "renders" / "assembly"


@dataclass(frozen=True)
class Step:
    n: int
    slug: str
    title: str
    insts: tuple[FootprintInst, ...]
    notes: tuple[str, ...] = ()


@dataclass(frozen=True)
class Phase:
    n: int
    slug: str
    title: str
    sheets: tuple[str, ...]
    insts: tuple[FootprintInst, ...]
    checkpoints: tuple[str, ...] = ()
    lead: str = ""


def _joint(mod_path: Path) -> str:
    return native.module().assembly_joint(str(mod_path), mod_path.read_text())


def _is_fiducial(inst: FootprintInst) -> bool:
    return inst.footprint == FIDUCIAL_FOOTPRINT


def _is_mech(inst: FootprintInst) -> bool:
    return "MountingHole" in inst.footprint


def assembly_insts(model: PcbModel) -> list[FootprintInst]:
    return [inst for inst in model.insts if not _is_fiducial(inst)]


def _hydrate(cls, rows, model):
    result = []
    for raw in rows:
        row = dict(raw)
        row["insts"] = tuple(model.insts[i] for i in row["insts"])
        for key in ("notes", "sheets", "checkpoints"):
            if key in row:
                row[key] = tuple(row[key])
        result.append(cls(**row))
    return result


def process_steps(model: PcbModel) -> list[Step]:
    return _hydrate(Step, native.module().assembly_steps(prepare(model), policy()), model)


def bringup_phases(model: PcbModel, sheets) -> list[Phase]:
    from schgen.verify import powertree
    return _hydrate(Phase, native.module().assembly_phases(
        prepare(model), asdict(powertree.analyze(sheets)), policy()), model)


def _indices(model, instances):
    positions = {id(inst): n for n, inst in enumerate(model.insts)}
    return [positions[id(inst)] for inst in instances]


def _groups(model, groups):
    return [{**{key: value for key, value in vars(group).items() if key != "insts"},
             "insts": _indices(model, group.insts)} for group in groups]


def _markdown(model: PcbModel, steps: list[Step], phases: list[Phase], name: str) -> str:
    return native.module().assembly_markdown(
        prepare(model), _groups(model, steps), _groups(model, phases), name)


def _png_stage(model: PcbModel, done: list[FootprintInst],
               cur: list[FootprintInst], out: Path, caption: str,
               mate_box=None) -> None:
    out.write_bytes(native.module().assembly_stage_image(
        prepare(model), _indices(model, done), _indices(model, cur), caption, mate_box))


def _stage_pngs(model: PcbModel, steps: list[Step], phases: list[Phase],
                out_dir: Path) -> list[Path]:
    images = native.module().assembly_images(
        prepare(model), _groups(model, steps), _groups(model, phases))
    out_dir.mkdir(parents=True, exist_ok=True)
    for stale in out_dir.glob("*.png"):
        stale.unlink()
    paths = []
    for name, data in images:
        path = out_dir / name
        path.write_bytes(data)
        paths.append(path)
    return paths


def generate(model: PcbModel | None = None) -> dict:
    if model is None:
        model = pcb_mod.build_model()
    from schgen.core.link import all_subsystem_paths, load_subsystem
    from schgen.core.project import spec
    from schgen.verify import powertree
    sheets = [load_subsystem(p.stem) for p in all_subsystem_paths()]
    result = native.module().assembly_run(
        prepare(model), asdict(powertree.analyze(sheets)), spec().name,
        str(ASSEMBLY_MD), str(PNG_DIR), policy())
    for key in ("md", "png_dir"):
        result[key] = Path(result[key])
    result["pngs"] = [Path(path) for path in result["pngs"]]
    for key in ("n_steps", "n_phases", "n_parts", "n_pngs"):
        result[key] = int(result[key])
    return result


def verdict(res: dict | None) -> tuple[bool, str]:
    raw = dict(res) if res is not None else None
    if raw:
        for key in ("md", "png_dir"):
            if raw.get(key) is not None:
                raw[key] = str(raw[key])
        if "pngs" in raw:
            raw["pngs"] = [str(path) for path in raw["pngs"]]
    return native.module().assembly_verdict(raw, str(REPO_ROOT))
