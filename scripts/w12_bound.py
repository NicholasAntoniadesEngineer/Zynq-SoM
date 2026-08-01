"""Usage: python3 scripts/w12_bound.py <tag> [sheet ...] — pack-vs-budget probe."""
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

SPEC = REPO / "carrier" / "floorplan.json"
SPEC_INDENT = 1
EST_DECIMALS = 1

CAND: list = []


def _instrument(fp):
    orig_attempt_pack = fp._attempt_pack
    orig_cross_estimator = fp._cross_estimator

    def attempt_pack(plan, *a, **kw):
        r = orig_attempt_pack(plan, *a, **kw)
        CAND.append({"w": fp.BOARD_W, "h": fp.BOARD_H, "packed": bool(r),
                     "free": bool(plan.punch_free), "est": None})
        return r

    def cross_estimator(plan, zg, sheets):
        ev = orig_cross_estimator(plan, zg, sheets)

        def wrapped(blocks, only_sheet=None):
            v = ev(blocks, only_sheet)
            if only_sheet is None and CAND:
                CAND[-1]["est"] = round(v, EST_DECIMALS)
            return v

        return wrapped

    fp._attempt_pack = attempt_pack
    fp._cross_estimator = cross_estimator


def _spec_with_either_side(spec_bytes, sheets):
    d = json.loads(spec_bytes)
    for s in sheets:
        d["interior"].setdefault(s, {})["layer"] = "either"
    return json.dumps(d, indent=SPEC_INDENT) + "\n"


def _distinct_outlines():
    uniq: dict = {}
    for c in CAND:
        key = (c["free"], c["w"], c["h"])
        prev = uniq.get(key)
        if prev is None or (c["est"] is not None and prev["est"] is None):
            uniq[key] = c
    return sorted(uniq.values(), key=lambda c: (c["free"], c["w"] * c["h"]))


def main(tag, sheets):
    from schgen.generate import floorplan as fp
    _instrument(fp)
    orig = SPEC.read_bytes()
    try:
        if sheets:
            SPEC.write_text(_spec_with_either_side(orig, sheets))
        from schgen.generate.pcb.placement import build_model
        build_model()
    finally:
        SPEC.write_bytes(orig)
    from schgen.verify.ratsnest_gate import CROSS_K
    print("W12BOUND " + json.dumps({"tag": tag, "K": CROSS_K,
                                    "n_calls": len(CAND),
                                    "cands": _distinct_outlines()}))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2:])
