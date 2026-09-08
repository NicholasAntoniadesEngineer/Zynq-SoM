from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

from PIL import Image

_REPO = Path(__file__).resolve().parents[2]
_MASTER = "origin/master"
_PCB_MD5 = "06308484dd95ffb65b09ef456bd64547"
_GOLDEN_DIST_MAX = 0


def _md5_bytes(data: bytes) -> str:
    return hashlib.md5(data).hexdigest()


def _git_bytes(rel: str) -> bytes:
    proc = subprocess.run(
        ["git", "-C", str(_REPO), "show", f"{_MASTER}:{rel}"],
        capture_output=True)
    if proc.returncode != 0:
        raise RuntimeError(
            f"baseline missing {rel} on {_MASTER}: "
            f"{proc.stderr.decode('utf-8', 'replace')}")
    return proc.stdout


def _ahash(data: bytes) -> str:
    im = Image.open(__import__("io").BytesIO(data)).convert("L").resize((16, 16))
    pixels = list(im.getdata())
    avg = sum(pixels) / len(pixels)
    return "".join("1" if value > avg else "0" for value in pixels)


def _hamming(left: str, right: str) -> int:
    return sum(a != b for a, b in zip(left, right, strict=False))


def _render_rels() -> list[str]:
    render_dir = _REPO / "carrier" / "renders"
    rels = ["carrier/Zynq_Carrier.kicad_pcb", "carrier/renders/golden.json"]
    for png in sorted(render_dir.glob("*.png")):
        rels.append(str(png.relative_to(_REPO)))
    for png in sorted((render_dir / "ratsnest").glob("*.png")):
        rels.append(str(png.relative_to(_REPO)))
    for png in sorted((render_dir / "assembly").glob("*.png")):
        rels.append(str(png.relative_to(_REPO)))
    return rels


def test_pcb_md5_matches_committed_baseline():
    pcb = _REPO / "carrier" / "Zynq_Carrier.kicad_pcb"
    got = _md5_bytes(pcb.read_bytes())
    assert got == _PCB_MD5, f"PCB md5 drifted {got} != {_PCB_MD5}"


def test_official_renders_are_byte_identical_to_master():
    rels = _render_rels()
    assert len(rels) >= 10
    drifted: list[str] = []
    for rel in rels:
        ours = (_REPO / rel).read_bytes()
        theirs = _git_bytes(rel)
        if ours != theirs:
            drifted.append(
                f"{rel}: branch={_md5_bytes(ours)} master={_md5_bytes(theirs)}")
    assert drifted == [], (
        "rendered artifacts drifted from master baseline:\n  "
        + "\n  ".join(drifted))


def test_golden_ahash_matches_committed_pngs():
    golden = json.loads((_REPO / "carrier" / "renders" / "golden.json").read_text())
    assert golden, "golden.json is empty"
    drifted: list[str] = []
    for name, old in sorted(golden.items()):
        png = _REPO / "carrier" / "renders" / f"{name}.png"
        if not png.is_file():
            drifted.append(f"{name}: PNG missing")
            continue
        dist = _hamming(_ahash(png.read_bytes()), old)
        if dist > _GOLDEN_DIST_MAX:
            drifted.append(f"{name}: ahash drift {dist}/256")
    assert drifted == [], (
        "golden.json ahash drifted:\n  " + "\n  ".join(drifted))
