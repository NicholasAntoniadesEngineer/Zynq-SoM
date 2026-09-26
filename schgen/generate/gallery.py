"""Transitional transport for native gallery rendering and publication."""
from pathlib import Path
from schgen.core import native
from schgen.core.project import PROJECT_ROOT

REPO_ROOT = Path(__file__).resolve().parents[2]


def _full_section(readme_dir: Path) -> str:
    return native.module().gallery_section(
        str(REPO_ROOT), str(PROJECT_ROOT), str(readme_dir), False)


def _compact_section(readme_dir: Path) -> str:
    return native.module().gallery_section(
        str(REPO_ROOT), str(PROJECT_ROOT), str(readme_dir), True)


def generate() -> list[Path]:
    paths, _ = native.module().gallery_run(str(REPO_ROOT), str(PROJECT_ROOT))
    return [Path(path) for path in paths]


def readme_targets() -> str:
    return native.module().gallery_targets(str(REPO_ROOT), str(PROJECT_ROOT))


def cmd_gallery(args) -> int:
    _, summary = native.module().gallery_run(str(REPO_ROOT), str(PROJECT_ROOT))
    print(summary)
    return 0
