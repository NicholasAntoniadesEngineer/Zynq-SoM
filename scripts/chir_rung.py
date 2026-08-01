"""Usage: python3 scripts/chir_rung.py <tag> [sheet ...]  (no sheets = control)."""
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

SPEC_INDENT = 1
VIA_LINE_PREFIX = "\n\t(via"
STDOUT_TAIL_LINES = 12
STDERR_TAIL_CHARS = 2000

tag = sys.argv[1]
sheets = sys.argv[2:]
orig = SPEC.read_bytes()
orig_base = BASE.read_bytes()
try:
    if sheets:
        d = json.loads(orig)
        for s in sheets:
            d["interior"].setdefault(s, {})["layer"] = "either"
        SPEC.write_text(json.dumps(d, indent=SPEC_INDENT) + "\n")
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
          f"vias={pcb_text.count(VIA_LINE_PREFIX)} "
          f"n_top={rn['n_top']} n_bottom={rn['n_bottom']} "
          f"fallbacks={fb} reds={reds}")
    if not ok:
        tail = "\n".join(r.stdout.splitlines()[-STDOUT_TAIL_LINES:])
        print(f"RUNG {tag} STDOUT TAIL:\n{tail}\n{r.stderr[-STDERR_TAIL_CHARS:]}")
finally:
    SPEC.write_bytes(orig)
    BASE.write_bytes(orig_base)
