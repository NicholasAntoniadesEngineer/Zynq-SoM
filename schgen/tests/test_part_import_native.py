"""Transitional API parity; all real writes stay inside pytest scratch paths."""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from pathlib import Path
from types import SimpleNamespace

import pytest

from schgen.core import sexpr
from schgen.partlib import part_gen as p

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "native/tests/data"
REFERENCES = sorted((DATA / "part_gen").glob("*.json"))
UTILITIES = json.loads((DATA / "part_import_utilities/python.json").read_text())


def _reference(path):
    reference = json.loads(path.read_text())
    payload = json.loads(reference["input"])
    return reference, payload.get("result", payload)


def test_recorded_corpus_complete_and_frozen():
    assert len(REFERENCES) == 62
    for line in (DATA / "part_import_utilities/SHA256SUMS").read_text().splitlines():
        digest, relative = line.split("  ", 1)
        assert hashlib.sha256((DATA / relative).read_bytes()).hexdigest() == digest


@pytest.mark.parametrize("path", REFERENCES, ids=lambda path: path.stem)
@pytest.mark.parametrize("variant", range(3))
def test_public_conversion_api_exact_recorded_python(path, variant):
    reference, result = _reference(path)
    info = p.part_info(result)
    pins = p.normalize_etypes(p.parse_pins(result), info["prefix"])
    ep = p.synth_ep_pin(info, pins)
    if ep is not None:
        pins.append(ep)
    name = p.safe_name(info["mpn"])
    assert name == reference["name"]
    expected = reference["variants"][variant]
    assert sexpr._dumps_py(p.gen_symbol(name, pins, info)) + "\n" == reference["symbol"]
    footprint, model = p.convert_footprint(
        result, name, info, expected["models"], ep_pin=ep)
    assert sexpr._dumps_py(footprint) + "\n" == expected["footprint"]
    assert model == expected["model"]
    assert p.gen_part_json(name, info, pins, expected["models"]) == expected["part_json"]


@pytest.mark.parametrize("case", UTILITIES["safe_names"])
def test_safe_name_live_inputs(case):
    assert p.safe_name(case["input"]) == case["output"]


@pytest.mark.parametrize("case", UTILITIES["groups"])
def test_pin_utilities_live_inputs(case):
    pins = [p.PinInfo(**pin) for pin in case["pins"]]
    assert asdict(p.group_pins(pins)) == case["groups"]
    assert p._ep_number(pins) == case["next"]
    for prefix, expected in case["normalized"].items():
        assert [asdict(pin) for pin in p.normalize_etypes(pins, prefix)] == expected
    ep = p.synth_ep_pin({"lcsc": "C3192119"}, pins)
    assert (asdict(ep) if ep is not None else None) == case["ep"]
    assert sexpr._dumps_py(p.gen_symbol("test", pins, UTILITIES["info"])) == case["symbol"]


def test_parse_fallbacks_and_native_error_class():
    case = UTILITIES["parse"]
    assert [asdict(pin) for pin in p.parse_pins(case["input"])] == case["pins"]
    with pytest.raises(p.PartGenError, match="no pins"):
        p.parse_pins({"dataStr": {"shape": []}})
    with pytest.raises(p.PartGenError, match="no footprint"):
        p.convert_footprint({}, "test", {}, [])
    with pytest.raises(p.PartGenError, match="must not be empty"):
        p.gen_part_json("test", {}, [], [])
    with pytest.raises(p.PartGenError, match="URL identifier"):
        p.fetch_cad("../../escape")  # Rejected before any live transport.


def test_package_specific_helpers_and_unknown_parts():
    assert [sexpr._dumps_py(node) for node in p.synth_ep_pad_nodes("99", "C3192119")] == UTILITIES["ep_pad"]
    assert [sexpr._dumps_py(node) for node in p.synth_silk_plus_nodes("C5365933")] == UTILITIES["silk"]
    assert p.synth_silk_plus_nodes("unknown") == []
    with pytest.raises(p.PartGenError, match="specification"):
        p.synth_ep_pad_nodes("9", "unknown")
    assert p.PACKAGE_EP["C3192119"].w == 1.0
    assert p.PACKAGE_SILK_PLUS["C5365933"].x == -5.6


@pytest.mark.parametrize("case", json.loads((DATA / "render_models/reference.json").read_text())["obj"])
def test_obj_compatibility_uses_existing_native_converter(case):
    assert p._obj_to_wrl(case["input"]) == case["output"]


def test_offline_add_preserves_cache_bytes_and_requires_overwrite(tmp_path):
    reference, _ = _reference(REFERENCES[0])
    source = tmp_path / "recorded.json"
    source.write_text(reference["input"])
    root = tmp_path / "parts"
    out = p.add_part(reference["lcsc"], parts_dir=root, from_json=source)
    assert out == root / reference["name"]
    assert (out / f"{out.name}.easyeda.json").read_bytes() == source.read_bytes()
    assert (out / f"{out.name}.kicad_sym").read_text() == reference["symbol"]
    with pytest.raises(p.PartGenError, match="overwrite"):
        p.add_part(reference["lcsc"], parts_dir=root, from_json=source)
    assert p.add_part(reference["lcsc"], parts_dir=root, from_json=source, overwrite=True) == out


def test_offline_cache_asset_reuse_is_ordered_and_not_rewritten(tmp_path):
    reference, _ = _reference(REFERENCES[0])
    source = tmp_path / "recorded.json"
    source.write_text(reference["input"])
    out = tmp_path / "parts" / reference["name"]
    out.mkdir(parents=True)
    payloads = {f"{out.name}.wrl": b"#VRML cached bytes\n", f"{out.name}.step": b"ISO-10303-21;\r\n"}
    for name, data in payloads.items():
        (out / name).write_bytes(data)
    p.add_part(reference["lcsc"], parts_dir=out.parent, from_json=source)
    metadata = json.loads((out / "part.json").read_text())
    assert metadata["models_3d"] == list(payloads)
    assert (out / f"{out.name}.kicad_mod").read_text() == reference["variants"][1]["footprint"]
    assert {name: (out / name).read_bytes() for name in payloads} == payloads


def test_cli_adapter_reports_missing_source_and_no_write(tmp_path, capsys):
    args = SimpleNamespace(lcsc_id="C1", name=None, parts_dir=tmp_path / "parts", from_json=tmp_path / "missing.json")
    assert p.cmd_part_add(args) == 1
    assert "cannot read" in capsys.readouterr().out
    assert not args.parts_dir.exists()


def test_missing_model_uuid_is_no_network_no_write(tmp_path):
    out = tmp_path / "not-created"
    assert p.fetch_3d_models("", out, "test") == []
    assert not out.exists()


def test_publication_refuses_symlink(tmp_path):
    reference, _ = _reference(REFERENCES[0])
    source = tmp_path / "recorded.json"
    source.write_text(reference["input"])
    out = tmp_path / "parts" / reference["name"]
    out.mkdir(parents=True)
    (out / "part.json").symlink_to(source)
    with pytest.raises(p.PartGenError, match="non-regular"):
        p.add_part(reference["lcsc"], parts_dir=out.parent, from_json=source, overwrite=True)
    assert source.read_text() == reference["input"]
    assert list(out.iterdir()) == [out / "part.json"]
