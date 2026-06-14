"""Tests for the SC bring-up firmware scaffold (`schgen scfw`).

These lock the two properties the generator must hold (same discipline as the
rest of schgen): the emitted scaffold is DETERMINISTIC (re-run -> byte-
identical, no timestamps) and the rail-sequencing order it derives matches the
power netlist / BRINGUP.md (+VIN -> +5V -> +3V3 -> +1V8, then the module gates,
with the watchdog C2 guard present). Offline: builds the model from the
authored netlists, no kicad-cli, no board build.
"""

from __future__ import annotations

import pytest

from schgen.generate import scfw


@pytest.fixture(scope="module")
def model():
    return scfw.Model()


def test_regulator_chain_order(model):
    # the derived sequencing must match BRINGUP.md Stage 2 exactly
    order = [(st.rail_in, st.rail_out) for st in model.chain]
    assert order == [("+VIN", "+5V"), ("+5V", "+3V3"), ("+3V3", "+1V8")]


def test_setpoints_derived(model):
    mv = {st.rail_out: round(st.vout * 1000) for st in model.chain}
    assert mv == {"+5V": 5020, "+3V3": 3310, "+1V8": 1800}


def test_always_on_rails_include_sc_and_inlet(model):
    # the always-on set is DERIVED (rails consumed but never produced) + the
    # SC's own rail -- it must contain +3V3_SC (pre-PD) and the +VIN inlet,
    # and must NOT contain any sequenced output rail.
    assert "+3V3_SC" in model.always_on
    assert "+VIN" in model.always_on
    produced = {st.rail_out for st in model.chain}
    assert not (set(model.always_on) & produced)


def test_module_gates_present(model):
    modules = {g.module for g in model.gates}
    # the BRINGUP.md Stage 4 module set (a representative subset)
    for m in ("HDMI_TX", "HDMI_RX", "LCD", "CAM", "SD", "USB", "PMOD"):
        assert m in modules


def test_i2c_map_addresses(model):
    assert model.expander.addr == 0x20
    assert [m.addr for m in model.monitors] == [0x40, 0x41]


def test_scaffold_is_deterministic(tmp_path):
    # two emissions into distinct dirs must be byte-identical (no timestamps,
    # no hashseed dependence within a single interpreter run)
    a, b = tmp_path / "a", tmp_path / "b"
    scfw.generate(a)
    scfw.generate(b)
    files_a = sorted(p.name for p in a.iterdir())
    files_b = sorted(p.name for p in b.iterdir())
    assert files_a == files_b
    for name in files_a:
        assert (a / name).read_bytes() == (b / name).read_bytes(), name


def test_no_zephyr_include_in_compiled_sources(tmp_path):
    # toolchain-agnostic mandate: NO compiled file may #include a zephyr header
    # (the reference port is a .txt, excluded).
    scfw.generate(tmp_path)
    for p in tmp_path.iterdir():
        if p.suffix in (".c", ".h"):
            text = p.read_text()
            assert "#include <zephyr" not in text, p.name
            assert '#include "zephyr' not in text, p.name


def test_watchdog_c2_guard_emitted(tmp_path):
    # C2: the stepper must not arm/kick the watchdog; the WDT impl must gate
    # kicks behind the armed latch.
    scfw.generate(tmp_path)
    seq = (tmp_path / "sc_seq.c").read_text()
    # structural guarantee: the stepper does not even include the WDT header,
    # so it CANNOT arm/kick during the sequence (a comment may mention C2).
    assert '#include "sc_wdt.h"' not in seq
    assert "sc_wdt_arm(" not in seq       # no arm call
    assert "sc_wdt_kick(" not in seq      # no kick call
    wdt = (tmp_path / "sc_wdt.c").read_text()
    assert "if (!s_wdt_armed) return" in wdt   # kicks are no-ops pre-arm
    app = (tmp_path / "sc_app.c").read_text()
    # the example arms the WDT only AFTER a successful sequence
    assert app.index("sc_seq_run") < app.index("sc_wdt_arm")


def test_expected_files_emitted(tmp_path):
    written = scfw.generate(tmp_path)
    names = {p.name for p in written}
    assert {"sc_hal.h", "sc_tables.h", "sc_tables.c", "sc_seq.h", "sc_seq.c",
            "sc_wdt.h", "sc_wdt.c", "sc_pd.h", "sc_pd.c", "sc_app.c",
            "sc_hal_zephyr.c.txt", "README.md"} <= names
