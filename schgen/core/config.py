"""Centralized home for the cross-cutting tunable constants.

These few numbers control geometry/placement/verification behaviour and were
previously scattered across ``layout/`` and ``verify/``. Each is defined ONCE
here with its meaning, units, and the reasoning behind the chosen value, and is
imported back at its original site. A reviewer tuning the build now has one
file to read instead of hunting through five modules — and there is exactly one
source of truth per knob, so the value cannot drift between call sites.

VALUES ARE UNCHANGED from their historical definitions; this module only
relocates and documents them.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Routing / placement grid
# ---------------------------------------------------------------------------
# The 1.27 mm (50 mil) schematic grid. This is the HARD pin-grid invariant of
# the symbol library and is defined canonically in :mod:`schgen.core.symbols`
# (every pin connection point must land on it, enforced at symbol LOAD). The
# router (layout/route.py) and placer (layout/place.py) snap all geometry to it.
# It is re-exported here — not re-literalled — so routing/placement read the
# grid from one config surface while symbols.py remains the single owner of the
# value (a second ``1.27`` literal would be a second source of truth to drift).
from schgen.core.symbols import GRID  # noqa: F401  (re-exported tunable)

# ---------------------------------------------------------------------------
# Text-metric over-estimation (layout/textmetrics.py)
# ---------------------------------------------------------------------------
# Claimed glyph advance per character, as a fraction of the text size, for the
# KiCad stroke font. SUBTLETY: KiCad's true AVERAGE advance is ~1.0 * size, but
# text bounding boxes here are deliberate OVER-estimates used to space parts and
# judge collisions — so this is tuned to the WORST-CASE-ish narrow run, not the
# average. Lowering it toward the real average would UNDER-bound wide text and
# hide collisions; it is intentionally conservative on the small side because
# the height over-claim (LINE_H) already pads the other axis generously.
CHAR_W = 0.95

# ---------------------------------------------------------------------------
# 3D-model misplacement threshold (verify/model3d_gate.py)
# ---------------------------------------------------------------------------
# HARD position check: a placed 3D model body's XY bbox must overlap its
# footprint's pad-copper bbox by at least this fraction, else the model is
# flagged MISPLACED (the EasyEDA c_origin unit-mismatch plants a body off its
# pads — e.g. a SOT-23 5.4 mm away at 0% overlap). 0.20 is a deep margin below
# every legit part (connectors/caps overlap >=0.5; centered ICs ~1.0), so it
# bites only the genuine offset bug, never a real housing overhang.
MISPLACED_OVERLAP = 0.20

# ---------------------------------------------------------------------------
# Cross-subsystem airwire budget coefficient (verify/ratsnest_gate.py)
# ---------------------------------------------------------------------------
# The absolute cross-subsystem airwire budget is CROSS_K * sqrt(board_area_mm2)
# * n_subsystems. At the clustered 235x215 / 30-subsystem board the budget is
# ~20.2 m vs ~15.7 m actual (passes); the old 165x155 hairball's budget would be
# ~14.4 m vs its ~26.8 m actual (FAILS). So 3.0 bites a board-spanning placement
# but passes a clustered one.
CROSS_K = 3.0

# ---------------------------------------------------------------------------
# Visual-gate default clearance (verify/visual_gate.py)
# ---------------------------------------------------------------------------
# Default mm of mandatory whitespace padding between any two render primitives
# (text/body/wire) in the zero-overlap visual gate. Anything closer than this is
# a FAIL. 0.2 mm is the minimum legible gap at the schematic's text size; it is
# a function default so callers can tighten it, never relax it (LAW 4).
VISUAL_CLEARANCE_MM = 0.2
