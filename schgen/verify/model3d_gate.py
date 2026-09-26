"""Data-only compatibility layer for the native model coverage/geometry gate."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path

from schgen.core import native
from schgen.core.project import PROJECT_ROOT

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PARTS_DIR = _REPO_ROOT / "parts"
# Compatibility for callers inspecting the old registry; never grants waivers.
_KNOWN_UNMATCHED: dict[str, str] = {}


@dataclass
class Model3dResult:
    ok: bool = True
    total: int = 0
    covered: int = 0
    unmatched: dict[str, str] = field(default_factory=dict)
    broken: dict[str, str] = field(default_factory=dict)
    missing: list[str] = field(default_factory=list)
    misfit: dict[str, str] = field(default_factory=dict)
    misplaced: dict[str, str] = field(default_factory=dict)
    invalid: dict[str, str] = field(default_factory=dict)

    @property
    def n_unmatched(self) -> int:
        return len(self.unmatched)

    def line(self) -> str:
        return native.module().model3d_result_text(asdict(self))["line"]

    def report(self) -> str:
        return native.module().model3d_result_text(asdict(self))["report"]


def _result(raw: dict) -> Model3dResult:
    return Model3dResult(**{
        name: raw[name] for name in Model3dResult.__dataclass_fields__})


def _model_dir() -> Path:
    return Path(native.module().model3d_default_directory())


def _resolve_model_path(raw: str, model_dir: Path) -> Path | None:
    path = native.module().model3d_resolve_path(
        raw, str(model_dir), str(PROJECT_ROOT))
    return Path(path) if path is not None else None


def _measure_files(mod_path: Path, clause_body: str, model_file: Path) -> dict:
    model_file = Path(model_file)
    return native.module().model3d_measure(
        Path(mod_path).read_text(errors="replace"), clause_body,
        model_file.read_text(errors="replace"), model_file.suffix)


def _placed_ok(mod_path: Path, clause_body: str, model_file: Path) -> str | None:
    return _measure_files(mod_path, clause_body, model_file)["misplaced"]


def _fit_ok(mod_path: Path, clause_body: str, model_file: Path) -> str | None:
    return _measure_files(mod_path, clause_body, model_file)["misfit"]


def check(model_dir: Path | None = None) -> Model3dResult:
    return _result(native.module().model3d_check(
        str(_PARTS_DIR), str(PROJECT_ROOT),
        str(model_dir) if model_dir is not None else None))


def run(rep_dir: Path | None = None,
        model_dir: Path | None = None) -> Model3dResult:
    if rep_dir is None:
        return check(model_dir=model_dir)
    return _result(native.module().model3d_run(
        str(_PARTS_DIR), str(PROJECT_ROOT), str(rep_dir),
        str(model_dir) if model_dir is not None else None))
