"""WAVE-12 sizing-search BINDING-CONSTRAINT probe (scratch tooling).

Logs every outline candidate the search tries: did the REAL pack succeed, what
did the estimator read, what was the LAW-5 budget. Answers whether the emitted
board area is PACK-bound (no smaller outline holds the blocks) or BUDGET-bound
(smaller outlines pack but the estimated cross-airwire exceeds the budget) —
i.e. whether the estimator's measured +200..+320 mm upper-bound bias costs area.

Usage: python3 scripts/w12_bound.py <tag> [sheet ...]
"""
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from schgen.generate import floorplan as fp  # noqa: E402

CAND: list = []
_orig_ap = fp._attempt_pack
_orig_ce = fp._cross_estimator


def _ap(plan, *a, **kw):
    r = _orig_ap(plan, *a, **kw)
    CAND.append({"w": fp.BOARD_W, "h": fp.BOARD_H, "packed": bool(r),
                 "free": bool(plan.punch_free), "est": None})
    return r


def _ce(plan, zg, sheets):
    ev = _orig_ce(plan, zg, sheets)

    def wrapped(blocks, only_sheet=None):
        v = ev(blocks, only_sheet)
        if only_sheet is None and CAND:
            CAND[-1]["est"] = round(v, 1)
        return v

    return wrapped


fp._attempt_pack = _ap
fp._cross_estimator = _ce

tag = sys.argv[1]
sheets = sys.argv[2:]
SPEC = REPO / "carrier" / "floorplan.json"
orig = SPEC.read_bytes()
try:
    if sheets:
        d = json.loads(orig)
        for s in sheets:
            d["interior"].setdefault(s, {})["layer"] = "either"
        SPEC.write_text(json.dumps(d, indent=1) + "\n")
    from schgen.generate.pcb.placement import build_model
    build_model()
finally:
    SPEC.write_bytes(orig)

from schgen.verify.ratsnest_gate import CROSS_K as K  # noqa: E402

uniq: dict = {}
for c in CAND:
    key = (c["free"], c["w"], c["h"])
    prev = uniq.get(key)
    if prev is None or (c["est"] is not None and prev["est"] is None):
        uniq[key] = c
rows = sorted(uniq.values(), key=lambda c: (c["free"], c["w"] * c["h"]))
print("W12BOUND " + json.dumps({"tag": tag, "K": K, "n_calls": len(CAND),
                                "cands": rows}))
