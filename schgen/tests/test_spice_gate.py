"""Tests for the analog spot-check gate (schgen/verify/spice.py).

Locks: the CURRENT board passes (every auto-extracted divider/RC/FB/ISET check
inside its window, real check coverage); a synthetic named divider whose ratio
puts an LVCMOS33 bank input ABOVE its abs-max FAILS; and an in-window divider
passes. Pure/offline: the GATE layer is the closed-form analytic solution
(``extract_checks``); the optional ngspice cross-check is NOT invoked here, so
the test is deterministic with or without ngspice installed."""

from __future__ import annotations

import types

from schgen.core.model import Circuit
from schgen.verify import spice


def _sheet(name, c):
    return types.SimpleNamespace(name=name, circuit=c)


def test_current_board_passes_spice():
    from schgen.core.link import all_subsystem_paths, load_subsystem
    sheets = [load_subsystem(p.stem) for p in all_subsystem_paths()]
    r = spice.extract_checks(sheets)
    assert r.ok, f"unexpected analog spot-check violations: {r.errors}"
    assert r.n_checks > 10            # real divider/RC/FB coverage, not a no-op


def _hdmi_det_divider(r_top: str, r_bot: str) -> Circuit:
    # HDMI_RX_5V_DET is a NAMED divider: HDMI_RX_5V (5 V cable contract) -> R_top
    # -> mid -> R_bot -> GND, sensed into an LVCMOS33 bank. The gate evaluates the
    # abs-max subcheck at 5.25 V (cable max) and the VIH subcheck at 4.75 V.
    c = Circuit("sp", "sp")
    c.part("R1", "Device:R", r_top, "")
    c.part("R2", "Device:R", r_bot, "")
    c.net("HDMI_RX_5V", "R1.1")
    c.net("HDMI_RX_5V_DET", "R1.2", "R2.1")
    c.net("GND", "R2.2")
    return c


def test_divider_over_window_fails():
    # R_top=10k / R_bot=100k -> ratio 0.909; at 5.25 V the mid reads 4.77 V,
    # far over the LVCMOS33 abs-max (3.465 V) -> the gate must FAIL.
    c = _hdmi_det_divider("10k", "100k")
    r = spice.extract_checks([_sheet("sp", c)])
    assert not r.ok, "a 4.77 V node into a 3.465 V abs-max bank must FAIL"
    assert any("HDMI_RX_5V_DET" in e and "abs-max" in e for e in r.errors), \
        r.errors


def test_divider_in_window_passes():
    # R_top = R_bot = 10k -> ratio 0.5: 5.25 V -> 2.625 V (<= 3.465 abs-max) and
    # 4.75 V -> 2.375 V (>= 2.0 VIH). Both subchecks inside the window.
    c = _hdmi_det_divider("10k", "10k")
    r = spice.extract_checks([_sheet("sp", c)])
    assert r.ok, r.errors
    det = [ch for ch in r.checks if "HDMI_RX_5V_DET" in ch.name]
    assert len(det) == 2 and all(ch.ok for ch in det), det
