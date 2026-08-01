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
    assert r.n_checks > 10


def _hdmi_det_divider(r_top: str, r_bot: str) -> Circuit:
    c = Circuit("sp", "sp")
    c.part("R1", "Device:R", r_top, "")
    c.part("R2", "Device:R", r_bot, "")
    c.net("HDMI_RX_5V", "R1.1")
    c.net("HDMI_RX_5V_DET", "R1.2", "R2.1")
    c.net("GND", "R2.2")
    return c


def test_divider_over_window_fails():
    c = _hdmi_det_divider("10k", "100k")
    r = spice.extract_checks([_sheet("sp", c)])
    assert not r.ok, "a 4.77 V node into a 3.465 V abs-max bank must FAIL"
    assert any("HDMI_RX_5V_DET" in e and "abs-max" in e for e in r.errors), \
        r.errors


def test_divider_in_window_passes():
    c = _hdmi_det_divider("10k", "10k")
    r = spice.extract_checks([_sheet("sp", c)])
    assert r.ok, r.errors
    det = [ch for ch in r.checks if "HDMI_RX_5V_DET" in ch.name]
    assert len(det) == 2 and all(ch.ok for ch in det), det
