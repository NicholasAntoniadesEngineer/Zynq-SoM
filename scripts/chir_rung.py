"""Wave-9 chirality ladder rung runner (scratch tooling, worktree-local).

Usage: python3 scripts/chir_rung.py <tag> [sheet ...]
Patches carrier/floorplan.json (adds "layer": "either" to each named sheet's
interior entry), runs `schgen board --no-render`, prints ONE summary line
from reports/board_verdicts.json + the board md5, then RESTORES the spec
byte-exactly. No sheets = control rung (no patch)."""
import hashlib
import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SPEC = REPO / "carrier" / "floorplan.json"
PCB = REPO / "carrier" / "Zynq_Carrier.kicad_pcb"
VERD = REPO / "carrier" / "reports" / "board_verdicts.json"

BASE = REPO / "carrier" / "reports" / "fallback_baseline.json"

tag = sys.argv[1]
sheets = sys.argv[2:]
orig = SPEC.read_bytes()
orig_base = BASE.read_bytes()
try:
    if sheets:
        d = json.loads(orig)
        for s in sheets:
            d["interior"].setdefault(s, {})["layer"] = "either"
        SPEC.write_text(json.dumps(d, indent=1) + "\n")
    r = subprocess.run([sys.executable, "-m", "schgen", "board",
                        "--no-render"], capture_output=True, text=True,
                       cwd=REPO)
    ok = "BOARD: PASS" in r.stdout
    v = json.loads(VERD.read_text())
    rn = v["ratsnest"]
    pcb_text = PCB.read_text()
    md5 = hashlib.md5(pcb_text.encode()).hexdigest()
    fb = v.get("fallbacks", {})
    reds = [k for k, val in v.items()
            if isinstance(val, dict) and val.get("ok") is False]
    print(f"RUNG {tag}: pass={ok} md5={md5} "
          f"{v['board_w']:g}x{v['board_h']:g} "
          f"area={v['board_w'] * v['board_h']:g} cross={rn['cross_mm']} "
          f"vias={pcb_text.count(chr(10) + chr(9) + '(via')} "
          f"n_top={rn['n_top']} n_bottom={rn['n_bottom']} "
          f"fallbacks={fb} reds={reds}")
    if not ok:
        tail = "\n".join(r.stdout.splitlines()[-12:])
        print(f"RUNG {tag} STDOUT TAIL:\n{tail}\n{r.stderr[-2000:]}")
finally:
    SPEC.write_bytes(orig)
    BASE.write_bytes(orig_base)
