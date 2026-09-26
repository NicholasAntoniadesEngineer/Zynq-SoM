"""Transitional data transport for native KiCad 3D rendering."""
from __future__ import annotations

from pathlib import Path

from schgen.core import native


def find_model_dir() -> Path | None:
    path = native.module().render3d_find_model_dir()
    return Path(path) if path is not None else None


def render(pcb: Path, out_dir: Path, quality: str = "high",
           width: int = 1600, height: int = 1200) -> list[Path]:
    raw = native.module().render3d_run(
        str(pcb), str(out_dir), quality, width, height)
    if not raw["ok"]:
        diagnostics = "\n".join(
            f"{failure['view']} view failed: {failure['diagnostic']}"
            for failure in raw["failures"])
        raise RuntimeError(f"render3d: incomplete 3D render\n{diagnostics}")
    print(raw["summary"])
    return [Path(path) for path in raw["written"]]


def cmd(args) -> int:
    repo = Path(__file__).resolve().parents[2]
    pcb = repo / "carrier" / "Zynq_Carrier.kicad_pcb"
    try:
        render(pcb, repo / "carrier" / "renders")
    except (RuntimeError, OSError) as exc:
        print(f"render3d: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    import argparse
    raise SystemExit(cmd(argparse.ArgumentParser().parse_args()))
