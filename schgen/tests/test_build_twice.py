"""END-TO-END build-twice determinism test (T1 P1 — the determinism instrument
every later composition phase cites).

Component-level determinism existed (``test_pcb.py`` proves the shelf packer is
deterministic), but nothing proved the WHOLE chain — netlist -> shared zone
packer -> floorplan plan (with its ``fp.BOARD_W/H`` global rebinding) -> place
-> LEVER-L4 -> emit — yields byte-identical ``.kicad_pcb`` text twice in a row.
The 2026-06-19 ``fp.BOARD_W/H`` data race and any future ordering bug in the
composition legalizer would show up exactly here.

COST: two full ``build_model()`` + ``emit_pcb`` runs (~2-4 min). NOT part of the
default fast suite: gated behind ``SCHGEN_BOARD_TESTS=1`` (the phase regression
bar runs it explicitly: ``SCHGEN_BOARD_TESTS=1 pytest schgen/tests/
test_build_twice.py``). MANDATORY at every T1 phase gate — a phase claiming
byte-determinism without this run is unproven.

The second build reuses in-process caches (symbol/footprint parse caches); the
cross-PROCESS repeat (a second ``schgen board``) is run at each phase gate and
compared by artifact hash — this test is the in-process half of that proof.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

import pytest

_ENABLED = os.environ.get("SCHGEN_BOARD_TESTS") == "1"


@pytest.mark.skipif(not _ENABLED,
                    reason="slow end-to-end build; set SCHGEN_BOARD_TESTS=1 "
                           "(mandatory at every T1 phase gate)")
def test_board_build_twice_is_byte_identical(tmp_path: Path):
    from schgen.generate.pcb.emit import emit_pcb
    from schgen.generate.pcb.placement import build_model

    hashes: list[str] = []
    sizes: list[tuple[float, float]] = []
    for i in (1, 2):
        model = build_model()
        out = tmp_path / f"board_{i}.kicad_pcb"
        emit_pcb(model, out)
        hashes.append(hashlib.sha256(out.read_bytes()).hexdigest())
        sizes.append((model.board_w, model.board_h))

    assert sizes[0] == sizes[1], (
        f"board size nondeterministic: {sizes[0]} vs {sizes[1]} "
        f"(the fp.BOARD_W/H race class)")
    assert hashes[0] == hashes[1], (
        "emitted .kicad_pcb bytes differ between two in-process builds — "
        "the placement chain is nondeterministic")
