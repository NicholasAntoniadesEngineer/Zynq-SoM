"""Native binding/adapter contracts; all publication is into pytest scratch paths."""
from __future__ import annotations

import hashlib
import json
from dataclasses import FrozenInstanceError, asdict
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image, ImageStat

from schgen.core import native
from schgen.output import render, render3d
from schgen.verify import model3d_gate as gate

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "native/tests/data/render_models"
ORACLE = json.loads((DATA / "reference.json").read_text())
PDFS = json.loads((DATA / "pdf_reference.json").read_text())


def test_independent_fixtures_and_hardware_unchanged():
    hashes = {
        "reference.json":
            "c233558629102d5885d7dd3ad845e2894ee9107794b3ab57fa08b8fac6968a2c",
        "pdf_reference.json":
            "b9b583687e7e19e9eb25ac1afc38b1f30411ccd5163295894ceebc4362a95fe5",
        "raster_tiles.json":
            "93b0bd80feb38dc6d6d5218832cba80270d9e852a161c25102c260a94751971e",
        "asset_complete_reference.json":
            "2e4b5c6b812687c49f1d35d9d5104bfd38286252c0a78c5d92dd0ef8ee008830",
        "asset_complete.kicad_pcb":
            "b8f955497cbfa308efb7b37d853a8bdf686031854cd6ab41398714875b659e00",
    }
    for filename, digest in hashes.items():
        assert hashlib.sha256((DATA / filename).read_bytes()).hexdigest() == digest
    for filename, digest in ORACLE["assets"].items():
        assert hashlib.sha256((ROOT / filename).read_bytes()).hexdigest() == digest


@pytest.mark.parametrize("case", ORACLE["geometry"])
def test_native_geometry_matches_independent_python(case):
    measured = native.module().model3d_measure(
        case["mod"], case["clause"], case["model"], case["suffix"])
    for actual, expected in {
        "model_xy": "xy", "model_box": "box", "fab_xy": "fab",
        "pad_box": "pads", "misfit": "fit", "misplaced": "placed",
    }.items():
        value = case[expected]
        if isinstance(value, list):
            assert measured[actual] == pytest.approx(value, abs=1e-12)
        else:
            assert measured[actual] == value


@pytest.mark.parametrize("case", ORACLE["obj"])
def test_native_obj_conversion_exact(case):
    assert native.module().model3d_obj_to_wrl(case["input"]) == case["output"]


def test_real_gate_adapter_and_publication_exact(tmp_path):
    result = gate.run(tmp_path)
    assert asdict(result) == {**ORACLE["repository"]["fields"], "invalid": {}}
    assert result.line() == ORACLE["repository"]["line"]
    assert result.report() == ORACLE["repository"]["report"]
    assert (tmp_path / "model3d.txt").read_text() == result.report() + "\n"
    result.invalid["MUTANT"] = "unmeasurable"
    result.ok = False
    assert "MUTANT" in result.line() and "unmeasurable" in result.report()


def test_model_path_transport_and_empty_inventory_rejected(tmp_path, monkeypatch):
    assert isinstance(gate._model_dir(), Path)
    assert isinstance(render3d.find_model_dir(), Path)
    assert gate._resolve_model_path("bare.wrl", tmp_path) is None
    assert gate._resolve_model_path("${KIPRJMOD}/a.wrl", tmp_path) == (
        gate.PROJECT_ROOT / "a.wrl")
    monkeypatch.setattr(gate, "_PARTS_DIR", tmp_path)
    with pytest.raises(RuntimeError):
        gate.check()


@pytest.mark.parametrize("case", PDFS)
def test_native_first_page_crop_rotation_and_artwork(case, tmp_path):
    pdf = tmp_path / "input.pdf"
    png = tmp_path / "output.png"
    pdf.write_bytes(bytes.fromhex(case["pdf_hex"]))
    page = native.module().render_pdf_to_png(str(pdf), str(png), case["dpi"])
    assert (page["width_px"], page["height_px"]) == (
        case["width"], case["height"])
    assert page["page_w_mm"] == pytest.approx(case["page_w_mm"])
    assert page["page_h_mm"] == pytest.approx(case["page_h_mm"])
    with Image.open(png) as image:
        rgb = image.convert("RGB")
        red = [(x, y) for y in range(rgb.height) for x in range(rgb.width)
               if (lambda c: c[0] > 200 and c[1] < 50 and c[2] < 50)(
                   rgb.getpixel((x, y)))]
    assert red, "first page's red rectangle must actually be rendered"
    bounds = (min(x for x, _ in red), min(y for _, y in red),
              max(x for x, _ in red), max(y for _, y in red))
    assert bounds == pytest.approx(case["red_bounds"], abs=1)


def test_real_schematic_adapter_preserves_input(tmp_path):
    expected = json.loads((DATA / "render_reference.json").read_text())["sheet"]
    source = ROOT / expected["source"]
    before = source.read_bytes()
    png = tmp_path / "sheet.png"
    page = render.render_sheet_to_png(source, png, dpi=72)
    assert isinstance(page, render.PageRaster) and page.png_path == png
    assert (page.width_px, page.height_px) == (842, 596)
    assert page.page_w_mm == pytest.approx(expected["page_w_mm"], abs=1e-4)
    assert page.page_h_mm == pytest.approx(expected["page_h_mm"], abs=1e-4)
    assert page.mm_to_px(page.page_w_mm, page.page_h_mm) == pytest.approx(
        (page.width_px, page.height_px))
    with pytest.raises(FrozenInstanceError):
        page.dpi = 10
    assert source.read_bytes() == before


def _mini_board(tmp_path, model):
    pcb = tmp_path / "fixture.kicad_pcb"
    pcb.write_text((DATA / "asset_complete.kicad_pcb").read_text().replace(
        "@MODEL@", str(model)))
    return pcb


def test_real_eight_view_adapter_and_step_preserve_inputs(tmp_path, capsys):
    pcb = _mini_board(tmp_path, ROOT / "parts/AO3400A/AO3400A.wrl")
    project = pcb.with_suffix(".kicad_pro")
    project.write_text('{"meta":{"version":1}}\n')
    before = (pcb.read_bytes(), project.read_bytes())
    written = render3d.render(pcb, tmp_path / "renders", "basic", 240, 180)
    expected = json.loads((DATA / "asset_complete_reference.json").read_text())
    assert [p.name for p in written] == [x["name"] for x in expected["images"]]
    assert all(isinstance(p, Path) for p in written)
    assert "8" in capsys.readouterr().out
    tiles = json.loads((DATA / "raster_tiles.json").read_text())["asset-complete"]
    for path in written:
        with Image.open(path) as image:
            rgb = image.convert("RGB")
            assert rgb.size == (224, 168)
            actual = []
            for y in range(12):
                for x in range(16):
                    box = (x * rgb.width // 16, y * rgb.height // 12,
                           (x + 1) * rgb.width // 16,
                           (y + 1) * rgb.height // 12)
                    actual.extend(ImageStat.Stat(rgb.crop(box)).mean)
        errors = [abs(a - b) for a, b in zip(
            actual, tiles[path.name]["tiles"], strict=True)]
        assert sum(errors) / len(errors) < 2 and max(errors) < 20
    step = tmp_path / "assembly.step"
    native.module().render3d_export_step(str(pcb), str(step))
    assert step.stat().st_size > 1_000_000
    assert "ISO-10303-21;" in step.read_text()
    assert (pcb.read_bytes(), project.read_bytes()) == before


def test_missing_hardware_cannot_credit_stale_render(tmp_path):
    pcb = _mini_board(tmp_path, tmp_path / "missing.wrl")
    output = tmp_path / "renders"
    output.mkdir()
    stale = output / "3d_top.png"
    stale.write_bytes(b"stale output")
    with pytest.raises(RuntimeError, match="missing"):
        render3d.render(pcb, output, "basic", 240, 180)
    assert stale.read_bytes() == b"stale output"


def test_invalid_inputs_preserve_existing_output(tmp_path):
    png = tmp_path / "old.png"
    png.write_bytes(b"old bytes")
    with pytest.raises(RuntimeError):
        render.render_sheet_to_png(tmp_path / "missing.kicad_sch", png)
    pdf = tmp_path / "bad.pdf"
    pdf.write_bytes(b"garbage")
    with pytest.raises(RuntimeError):
        native.module().render_pdf_to_png(str(pdf), str(png), 72)
    assert png.read_bytes() == b"old bytes"


def test_partial_failure_and_cli_status_transport(tmp_path, monkeypatch, capsys):
    partial = SimpleNamespace(render3d_run=lambda *args: {
        "ok": False, "written": ["stale.png"],
        "failures": [{"view": "bottom", "diagnostic": "native failure"}],
    })
    monkeypatch.setattr(native, "module", lambda: partial)
    with pytest.raises(RuntimeError, match="bottom view failed: native failure"):
        render3d.render(tmp_path / "x.kicad_pcb", tmp_path)
    # The mocked binding never invokes KiCad or writes carrier output.
    assert render3d.cmd(None) == 1
    assert "native failure" in capsys.readouterr().out


def test_unavailable_native_is_not_a_python_fallback(tmp_path, monkeypatch):
    def unavailable():
        raise RuntimeError("native unavailable")
    monkeypatch.setattr(native, "module", unavailable)
    for call in (gate.check, render3d.find_model_dir,
                 lambda: render.render_sheet_to_png(tmp_path, tmp_path),
                 lambda: render3d.render(tmp_path, tmp_path)):
        with pytest.raises(RuntimeError, match="native unavailable"):
            call()
