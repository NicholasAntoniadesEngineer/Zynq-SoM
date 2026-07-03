"""T1 P3 — the floorplan.json PULL knob (the promoted `_EDGE_SEAT_BLOCKS`
hack; spec T1_COMPOSITION_SPEC.md P3, decision D-1).

RED-ON-BEFORE: ``test_pull_parses`` fails on the pre-P3 loader (the
``keys - {"side", "near"}`` rejection) — captured in the phase evidence —
and goes green with the pull schema landed. Every invariant has a rejection
test (typo key, non-positive weight, inboard off-edge, exclusive/near
mismatch, missing basis). The migration itself is proven byte-identical at
the phase gate (board + FLOORPLAN.svg/MD hashes).
"""

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
    """A valid exclusive pull parses; the spec round-trips it into
    FloorplanSpec.interior verbatim. RED on the pre-P3 loader."""
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
                               "pull": _pull(wieght=60.0)})   # typo key
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
    """face=inboard aims at an edge block's inner face — meaningless for an
    interior target ('power' is not on any edge list here)."""
    p = _write_spec(tmp_path, {"near": "power",
                               "pull": _pull(to="power", face="inboard")})
    with pytest.raises(FloorplanSpecError, match="inboard"):
        load_floorplan_spec(p, valid_names=_NAMES)


def test_pull_exclusive_requires_matching_near(tmp_path):
    """exclusive replicates the `_anchor` edge-seat branch, which fires only
    when the block's near/zone anchor IS the pulled edge block — a mismatched
    exclusive pull would silently do nothing (the :1492 precondition)."""
    p = _write_spec(tmp_path, {"side": "E", "pull": _pull()})
    with pytest.raises(FloorplanSpecError, match="exclusive"):
        load_floorplan_spec(p, valid_names=_NAMES)


def test_pull_bad_face_rejected(tmp_path):
    p = _write_spec(tmp_path, {"near": "pd_input",
                               "pull": _pull(face="outboard")})
    with pytest.raises(FloorplanSpecError, match="face"):
        load_floorplan_spec(p, valid_names=_NAMES)


def test_spec_without_pull_still_parses(tmp_path):
    """The knob is OPTIONAL — a pre-P3 spec (side/near only) is untouched."""
    p = _write_spec(tmp_path, {"near": "pd_input"})
    spec = load_floorplan_spec(p, valid_names=_NAMES)
    assert spec is not None and "pull" not in spec.interior["usb_pd"]


def test_edge_seat_blocks_hack_is_gone():
    """P3 deletes the `_EDGE_SEAT_BLOCKS` / `_EDGE_SEAT_ZONE_W` module
    constants — the spec data (pull knob) is the only seat authority."""
    import schgen.generate.floorplan as fp
    assert not hasattr(fp, "_EDGE_SEAT_BLOCKS")
    assert not hasattr(fp, "_EDGE_SEAT_ZONE_W")


def test_carrier_spec_carries_the_usb_pd_pull():
    """The migrated carrier/floorplan.json: usb_pd KEEPS near=pd_input and
    carries the exclusive pull with the D11 basis (reviewed-JSON-diff rule)."""
    from schgen.generate.floorplan import FLOORPLAN_SPEC
    raw = json.loads(FLOORPLAN_SPEC.read_text())
    usb = raw["interior"]["usb_pd"]
    assert usb.get("near") == "pd_input"
    pull = usb.get("pull")
    assert isinstance(pull, dict), "P3 migration missing"
    assert pull["to"] == "pd_input" and pull["exclusive"] is True
    assert pull["weight"] == 60.0     # == the deleted _EDGE_SEAT_ZONE_W
    assert pull["basis"]
