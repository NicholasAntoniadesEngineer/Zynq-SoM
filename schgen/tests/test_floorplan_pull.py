from __future__ import annotations

import json

import pytest

from schgen.generate.floorplan import FloorplanSpecError, load_floorplan_spec


def _write_spec(tmp_path, interior_usb_pd: dict):
    spec = {
        "outline": "auto",
        "edges": {"N": ["pd_input"]},
        "interior": {"usb_pd": interior_usb_pd},
    }
    p = tmp_path / "floorplan.json"
    p.write_text(json.dumps(spec))
    return p


_NAMES = {"pd_input", "usb_pd", "power"}


def _pull(**over) -> dict:
    base = {"to": "pd_input", "weight": 60.0, "face": "inboard",
            "exclusive": True, "basis": "D11 edge-seat override (test)"}
    base.update(over)
    return base


def test_pull_parses(tmp_path):
    p = _write_spec(tmp_path, {"near": "pd_input", "pull": _pull()})
    spec = load_floorplan_spec(p, valid_names=_NAMES)
    assert spec is not None
    got = spec.interior["usb_pd"]
    assert got["near"] == "pd_input"
    assert got["pull"]["to"] == "pd_input"
    assert got["pull"]["exclusive"] is True
    assert got["pull"]["weight"] == 60.0


def test_pull_unknown_key_rejected(tmp_path):
    p = _write_spec(tmp_path, {"near": "pd_input",
                               "pull": _pull(wieght=60.0)})
    with pytest.raises(FloorplanSpecError, match="pull"):
        load_floorplan_spec(p, valid_names=_NAMES)


def test_pull_nonpositive_weight_rejected(tmp_path):
    p = _write_spec(tmp_path, {"near": "pd_input", "pull": _pull(weight=0.0)})
    with pytest.raises(FloorplanSpecError, match="weight"):
        load_floorplan_spec(p, valid_names=_NAMES)


def test_pull_missing_basis_rejected(tmp_path):
    p = _write_spec(tmp_path, {"near": "pd_input", "pull": _pull(basis="")})
    with pytest.raises(FloorplanSpecError, match="basis"):
        load_floorplan_spec(p, valid_names=_NAMES)


def test_pull_unknown_target_rejected(tmp_path):
    p = _write_spec(tmp_path, {"near": "pd_input",
                               "pull": _pull(to="nosuch")})
    with pytest.raises(FloorplanSpecError, match="nosuch"):
        load_floorplan_spec(p, valid_names=_NAMES)


def test_pull_inboard_requires_edge_target(tmp_path):
    p = _write_spec(tmp_path, {"near": "power",
                               "pull": _pull(to="power", face="inboard")})
    with pytest.raises(FloorplanSpecError, match="inboard"):
        load_floorplan_spec(p, valid_names=_NAMES)


def test_pull_exclusive_requires_matching_near(tmp_path):
    p = _write_spec(tmp_path, {"side": "E", "pull": _pull()})
    with pytest.raises(FloorplanSpecError, match="exclusive"):
        load_floorplan_spec(p, valid_names=_NAMES)


def test_pull_bad_face_rejected(tmp_path):
    p = _write_spec(tmp_path, {"near": "pd_input",
                               "pull": _pull(face="outboard")})
    with pytest.raises(FloorplanSpecError, match="face"):
        load_floorplan_spec(p, valid_names=_NAMES)


def test_spec_without_pull_still_parses(tmp_path):
    p = _write_spec(tmp_path, {"near": "pd_input"})
    spec = load_floorplan_spec(p, valid_names=_NAMES)
    assert spec is not None and "pull" not in spec.interior["usb_pd"]


def test_edge_seat_blocks_hack_is_gone():
    import schgen.generate.floorplan as fp
    assert not hasattr(fp, "_EDGE_SEAT_BLOCKS")
    assert not hasattr(fp, "_EDGE_SEAT_ZONE_W")


def test_carrier_spec_carries_the_usb_pd_pull():
    from schgen.generate.floorplan import FLOORPLAN_SPEC
    raw = json.loads(FLOORPLAN_SPEC.read_text())
    usb = raw["interior"]["usb_pd"]
    assert usb.get("near") == "pd_input"
    pull = usb.get("pull")
    assert isinstance(pull, dict), "P3 migration missing"
    assert pull["to"] == "pd_input" and pull["exclusive"] is True
    assert pull["weight"] == 60.0
    assert pull["basis"]
