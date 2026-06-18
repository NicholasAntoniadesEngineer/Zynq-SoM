"""render3d — 3D board renders for VISUAL verification (LAW 1, extended to 3D).

`schgen render3d` (also run best-effort by `schgen board`) shells out to
``kicad-cli pcb render`` to write a top and a perspective 3D view of the placed
board to ``carrier/renders/3d_top.png`` + ``carrier/renders/3d_persp.png``. These
are NOT golden-checked (a raytraced PNG is not byte-deterministic) — they exist
so every component's 3D body can be eyeballed (does every part have a model? do
the connectors / ICs sit right? any part floating or mis-oriented?). The model3d
gate counts coverage; this render is the human check the gate can't be.

Best-effort + portable: it auto-detects the installed KiCad 3D-model library and
the ``KICAD<major>_3DMODEL_DIR`` var the footprints reference, and if kicad-cli
or the model library is absent it WARNS and skips (never fails the build).
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

# Common install locations for the stock KiCad 3D-model library, newest first.
_MODEL_DIR_CANDIDATES = (
    "/Applications/KiCad/KiCad.app/Contents/SharedSupport/3dmodels",
    "/usr/share/kicad/3dmodels",
    "/usr/local/share/kicad/3dmodels",
)


def _kicad_major() -> int:
    """Major version of the installed kicad-cli (for the KICAD<N>_3DMODEL_DIR
    var name the footprints use). Falls back to 10."""
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
    """Render top + perspective 3D views. Returns the written PNGs (possibly
    empty if skipped). Never raises — a missing kicad-cli / model dir WARNS."""
    if shutil.which("kicad-cli") is None:
        print("render3d: kicad-cli not found — skipping 3D render")
        return []
    model_dir = find_model_dir()
    if model_dir is None:
        print("render3d: KiCad 3D-model library not found — skipping 3D render")
        return []
    var = f"KICAD{_kicad_major()}_3DMODEL_DIR"
    # our part .wrl models reference ${KIPRJMOD}/../parts/<MPN>/<MPN>.wrl;
    # KIPRJMOD is the .kicad_pcb's project dir (carrier/) — pass it so kicad-cli
    # resolves them (the GUI sets KIPRJMOD itself).
    kiprjmod = str(pcb.resolve().parent)
    out_dir.mkdir(parents=True, exist_ok=True)
    # top + bottom (so the BOTTOM-side passives — incl. the under-SoM rail
    # decoupling — are actually inspectable, LAW 5/6) + a perspective hero view.
    views = (("top", ["--side", "top"]),
             ("bottom", ["--side", "bottom"]),
             ("persp", ["--perspective"]))
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
