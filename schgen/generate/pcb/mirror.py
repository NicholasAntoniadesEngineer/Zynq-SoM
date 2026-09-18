from __future__ import annotations

from pathlib import Path

from schgen.core import native, sexpr
from .constants import REPO_ROOT

MIRROR_DIR = REPO_ROOT / ".mirrored_fp"


class MirrorUnsupported(AssertionError):
    pass


def mirror_fp_doc(doc: list) -> None:
    try:
        result = native.module().mirror_footprint(doc)
    except native.module().MirrorUnsupported as exc:
        raise MirrorUnsupported(str(exc)) from exc
    doc[:] = sexpr._from_tagged(result)


def mirrored_mod(src: Path) -> Path:
    try:
        return Path(native.module().write_mirrored_footprint(str(src), str(MIRROR_DIR)))
    except native.module().MirrorUnsupported as exc:
        raise MirrorUnsupported(str(exc)) from exc


def is_mirrored_path(p: Path) -> bool:
    return p.parent.name == MIRROR_DIR.name
