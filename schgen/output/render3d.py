from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

_MODEL_DIR_CANDIDATES = (
    "/Applications/KiCad/KiCad.app/Contents/SharedSupport/3dmodels",
    "/usr/share/kicad/3dmodels",
    "/usr/local/share/kicad/3dmodels",
)


def _kicad_major() -> int:
    try:
        out = subprocess.run(["kicad-cli", "version"], capture_output=True,
                             text=True, timeout=20).stdout
        m = re.search(r"(\d+)\.", out)
        if m:
            return int(m.group(1))
    except Exception:  # noqa: BLE001
        pass
    return 10


def find_model_dir() -> Path | None:
    for c in _MODEL_DIR_CANDIDATES:
        p = Path(c)
        if p.is_dir():
            return p
    return None


def render(pcb: Path, out_dir: Path, quality: str = "high",
           width: int = 1600, height: int = 1200) -> list[Path]:
    if shutil.which("kicad-cli") is None:
        print("render3d: kicad-cli not found — skipping 3D render")
        return []
    model_dir = find_model_dir()
    if model_dir is None:
        print("render3d: KiCad 3D-model library not found — skipping 3D render")
        return []
    var = f"KICAD{_kicad_major()}_3DMODEL_DIR"
    kiprjmod = str(pcb.resolve().parent)
    out_dir.mkdir(parents=True, exist_ok=True)
    pro = pcb.with_suffix(".kicad_pro")
    # trap: kicad-cli rewrites .kicad_pro on open; restore or the render dirties it
    pro_snapshot = pro.read_bytes() if pro.exists() else None
    views = (("top", ["--side", "top"]),
             ("bottom", ["--side", "bottom"]),
             ("left", ["--side", "left"]),
             ("right", ["--side", "right"]),
             ("front", ["--side", "front"]),
             ("back", ["--side", "back"]),
             ("persp", ["--perspective"]),
             ("persp_rear", ["--perspective", "--rotate", "0,0,180"]))
    written: list[Path] = []
    for name, view_args in views:
        png = out_dir / f"3d_{name}.png"
        cmd = ["kicad-cli", "pcb", "render", "-D", f"{var}={model_dir}",
               "-D", f"KIPRJMOD={kiprjmod}",
               "--quality", quality, "--background", "opaque",
               "-w", str(width), "-h", str(height),
               *view_args, "-o", str(png), str(pcb)]
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            if r.returncode == 0 and png.exists():
                written.append(png)
            else:
                print(f"render3d: {name} view failed: "
                      f"{(r.stderr or r.stdout)[-200:]}")
        except Exception as exc:  # noqa: BLE001
            print(f"render3d: {name} view error: {exc}")
    if pro_snapshot is not None and pro.read_bytes() != pro_snapshot:
        pro.write_bytes(pro_snapshot)
    if written:
        print(f"3D RENDERS: {len(written)} view(s) -> "
              f"{', '.join(str(p) for p in written)} (VISUAL-verify: LAW 1)")
    return written


def cmd(args) -> int:
    repo = Path(__file__).resolve().parents[2]
    pcb = repo / "carrier" / "Zynq_Carrier.kicad_pcb"
    if not pcb.exists():
        print(f"render3d: {pcb} not found — run `schgen board` first")
        return 1
    written = render(pcb, repo / "carrier" / "renders")
    return 0 if written else 1


if __name__ == "__main__":
    import argparse
    raise SystemExit(cmd(argparse.ArgumentParser().parse_args()))
