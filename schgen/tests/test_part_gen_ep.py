"""DEF-A: tests for the pipeline-generated exposed-pad synthesis (part_gen).

Locks: the EP number/idiom; the allowlist gate (only listed LCSCs synthesize,
others get None -> byte-identical); the EP is skipped when the land already
carries one; and an end-to-end regen of the allowlisted MPQ4423HGQ-Z grows a
symbol pin 9 + footprint pad 9 + .py PINS ('9','EP','passive')."""

from __future__ import annotations

from pathlib import Path

from schgen import part_gen
from schgen.part_gen import PinInfo, synth_ep_pin, synth_ep_pad_nodes, _ep_number

_REPO = Path(__file__).resolve().parents[2]
_EIGHT = [PinInfo(str(n), f"P{n}", "passive") for n in range(1, 9)]


def test_ep_number_is_max_plus_one():
    assert _ep_number(_EIGHT) == "9"
    assert _ep_number(_EIGHT[:5]) == "6"


def test_synth_ep_pin_allowlisted():
    pin = synth_ep_pin({"lcsc": "C3192119"}, _EIGHT)
    assert pin == PinInfo("9", "EP", "passive")


def test_synth_ep_pin_not_allowlisted_is_none():
    assert synth_ep_pin({"lcsc": "C0000000"}, _EIGHT) is None
    assert synth_ep_pin({"lcsc": ""}, _EIGHT) is None


def test_synth_ep_pin_skipped_when_land_already_has_ep():
    pins = [*_EIGHT, PinInfo("9", "EP", "passive")]
    assert synth_ep_pin({"lcsc": "C3192119"}, pins) is None


def test_synth_ep_pad_small_is_single_full_stack_pad():
    nodes = synth_ep_pad_nodes("9", "C3192119")
    assert len(nodes) == 1                       # < PASTE_RELIEF_MIN -> no grid
    pad = nodes[0]
    assert pad[1] == "9"
    layers = next(n for n in pad if isinstance(n, list) and n[0] == "layers")
    assert set(layers[1:]) == {"F.Cu", "F.Paste", "F.Mask"}


def test_add_part_synthesizes_ep_end_to_end(tmp_path):
    cached = _REPO / "parts" / "MPQ4423HGQ-Z" / "MPQ4423HGQ-Z.easyeda.json"
    if not cached.exists():
        return                                   # part not present; skip
    out = part_gen.add_part("C3192119", parts_dir=tmp_path, from_json=cached)
    sym = (out / "MPQ4423HGQ-Z.kicad_sym").read_text()
    mod = (out / "MPQ4423HGQ-Z.kicad_mod").read_text()
    py = (out / "MPQ4423HGQ-Z.py").read_text()
    assert '"EP"' in sym and '"9"' in sym        # symbol EP pin
    assert '"9"' in mod                          # footprint EP pad
    assert "('9', 'EP', 'passive')" in py        # .py PINS row
