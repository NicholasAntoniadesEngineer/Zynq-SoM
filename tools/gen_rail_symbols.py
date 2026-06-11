#!/usr/bin/env python3
"""Generate schgen-local rail power symbols (carrier/PLAN.md: assets are
ALWAYS generated, never hand-assembled).

The carrier needs power symbols for rails KiCad's stock ``power`` lib does
not carry (+3V3_SC and the FPGA bank rails +VCCO_13/33/34/35 from the SoM
contract). Each one is a faithful programmatic clone of the existing
``schgen:+VIN`` symbol (same up-arrow glyph, same hidden power_in pin at the
origin) with the name / value / pin-name / description rewritten. Idempotent:
re-running replaces any previously generated copy in place.

    PYTHONPATH=. python tools/gen_rail_symbols.py
"""

from __future__ import annotations

import copy
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from schgen import sexpr  # noqa: E402
from schgen.sexpr import Sym  # noqa: E402

LIB = REPO / "shared" / "symbols" / "schgen.kicad_sym"
TEMPLATE = "+VIN"
RAILS = ["+3V3_SC", "+VCCO_13", "+VCCO_33", "+VCCO_34", "+VCCO_35"]


def _rename(node: object, old: str, new: str) -> object:
    """Deep-rewrite every string equal to ``old`` (or prefixed ``old_``)."""
    if isinstance(node, list):
        return [_rename(x, old, new) for x in node]
    if isinstance(node, str) and not isinstance(node, Sym):
        if node == old:
            return new
        if node.startswith(f"{old}_"):           # sub-symbol names "+VIN_0_1"
            return f"{new}_{node[len(old) + 1:]}"
        if node == f"Power symbol: {old} rail":
            return f"Power symbol: {new} rail"
    return node


def main() -> int:
    doc = sexpr.loads(LIB.read_text())
    blocks = [n for n in doc if isinstance(n, list) and n
              and n[0] == Sym("symbol")]
    by_name = {b[1]: b for b in blocks}
    if TEMPLATE not in by_name:
        raise SystemExit(f"template symbol {TEMPLATE!r} not in {LIB}")
    for rail in RAILS:
        clone = _rename(copy.deepcopy(by_name[TEMPLATE]), TEMPLATE, rail)
        if rail in by_name:
            doc[doc.index(by_name[rail])] = clone
            print(f"replaced {rail}")
        else:
            doc.append(clone)
            print(f"added {rail}")
        by_name[rail] = clone
    LIB.write_text(sexpr.dumps(doc) + "\n")
    print(f"wrote {LIB}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
