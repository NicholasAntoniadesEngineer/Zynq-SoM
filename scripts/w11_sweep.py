"""Wave-11 ordinary-via-row sweep (scratch tooling, worktree-local).

Usage: python3 scripts/w11_sweep.py <mm> [sheet ...]
Patches schgen/core/quantize.py's EST_VIA_ORDINARY_MM to <mm> (and, when
sheets are named, adds "layer": "either" to each one's floorplan.json interior
entry), runs `schgen board --no-render`, prints ONE summary line, then RESTORES
both files byte-exactly. The registered basis string is left untouched — this
is a MEASUREMENT harness, not a landing.
"""
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
QUANT = REPO / "schgen" / "core" / "quantize.py"
SPEC = REPO / "carrier" / "floorplan.json"
BASE = REPO / "carrier" / "reports" / "fallback_baseline.json"
PCB = REPO / "carrier" / "Zynq_Carrier.kicad_pcb"
VERD = REPO / "carrier" / "reports" / "board_verdicts.json"

mm = sys.argv[1]
sheets = sys.argv[2:]
orig_q = QUANT.read_bytes()
orig_s = SPEC.read_bytes()
orig_b = BASE.read_bytes()
try:
    src = orig_q.decode()
    new, n = re.subn(r"^EST_VIA_ORDINARY_MM = .*$",
                     f"EST_VIA_ORDINARY_MM = {mm}", src, flags=re.M)
    if n != 1:
        raise SystemExit(f"EST_VIA_ORDINARY_MM not found ({n} matches)")
    QUANT.write_text(new)
    if sheets:
        d = json.loads(orig_s)
        for s in sheets:
            d["interior"].setdefault(s, {})["layer"] = "either"
        SPEC.write_text(json.dumps(d, indent=1) + "\n")
    r = subprocess.run([sys.executable, "-m", "schgen", "board",
                        "--no-render"], capture_output=True, text=True,
                       cwd=REPO)
    ok = "BOARD: PASS" in r.stdout
    v = json.loads(VERD.read_text())
    txt = PCB.read_text()
    reds = [k for k, val in v.items()
            if isinstance(val, dict) and val.get("ok") is False]
    print(f"SWEEP ord={mm} sheets={','.join(sheets) or '-'}: pass={ok} "
          f"md5={hashlib.md5(txt.encode()).hexdigest()} "
          f"{v['board_w']:g}x{v['board_h']:g} "
          f"area={v['board_w'] * v['board_h']:g} "
          f"cross={v['ratsnest']['cross_mm']} "
          f"n_bottom={v['ratsnest']['n_bottom']} "
          f"fb={v.get('fallbacks', {}).get('punch_free_plan_rejected')} "
          f"reds={reds}")
    if not ok:
        print("STDOUT TAIL:\n" + "\n".join(r.stdout.splitlines()[-10:]))
        print(r.stderr[-1500:])
finally:
    QUANT.write_bytes(orig_q)
    SPEC.write_bytes(orig_s)
    BASE.write_bytes(orig_b)
