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

# Approved physical-model repair only. Keep the original board digest and
# compare every other byte; do not bless a newly generated PCB wholesale.
_OLD_MODEL = b'''(model
			"${KICAD10_3DMODEL_DIR}/Package_DFN_QFN.3dshapes/WQFN-14-1EP_2.5x2.5mm_P0.5mm_EP1.45x1.45mm.step"
			(offset
				(xyz 0 0 0)
			)
			(scale
				(xyz 1 1 1)
			)
			(rotate
				(xyz 0 0 0)
			)
		)'''
_REPAIRED_MODEL = _OLD_MODEL.replace(
    b"${KICAD10_3DMODEL_DIR}/Package_DFN_QFN.3dshapes/WQFN-14-1EP_2.5x2.5mm_P0.5mm_EP1.45x1.45mm.step",
    b"${KIPRJMOD}/../parts/FUSB302BMPX/FUSB302BMPX.wrl",
).replace(b"(rotate\n\t\t\t\t(xyz 0 0 0)", b"(rotate\n\t\t\t\t(xyz 0 0 90)")


def _before_model_repair(data: bytes) -> bytes:
    assert data.count(_REPAIRED_MODEL) == 1, "required FUSB302 model repair drifted"
    assert _OLD_MODEL not in data, "obsolete missing model is still referenced"
    return data.replace(_REPAIRED_MODEL, _OLD_MODEL, 1)


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
    # The contract covers official artifacts, not ignored local/cloud-sync
    # duplicates. Include baseline AND current tracked paths so deleting a
    # required render cannot silently shrink the comparison set.
    rels = {"carrier/Zynq_Carrier.kicad_pcb", "carrier/renders/golden.json"}
    commands = (["ls-tree", "-r", "--name-only", "-z", _MASTER, "--", "carrier/renders"],
                ["ls-files", "-z", "--", "carrier/renders"])
    for args in commands:
        paths = subprocess.run(["git", "-C", str(_REPO), *args],
                               capture_output=True, check=True).stdout
        for raw in paths.split(b"\0"):
            path = Path(raw.decode("utf-8"))
            if path.suffix == ".png" and path.parent.as_posix() in {
                    "carrier/renders", "carrier/renders/ratsnest",
                    "carrier/renders/assembly"}:
                rels.add(path.as_posix())
    return sorted(rels)


def test_pcb_md5_matches_committed_baseline():
    pcb = _REPO / "carrier" / "Zynq_Carrier.kicad_pcb"
    got = _md5_bytes(_before_model_repair(pcb.read_bytes()))
    assert got == _PCB_MD5, f"PCB md5 drifted {got} != {_PCB_MD5}"


def test_official_renders_are_byte_identical_to_master():
    rels = _render_rels()
    assert len(rels) >= 10
    drifted: list[str] = []
    for rel in rels:
        ours = (_REPO / rel).read_bytes()
        theirs = _git_bytes(rel)
        if rel == "carrier/Zynq_Carrier.kicad_pcb":
            ours = _before_model_repair(ours)
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
