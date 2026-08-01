from __future__ import annotations

from schgen.core.model import Circuit, NetClass
from schgen.core.symbols import Library

import devkit_mini.subsystems.mechanical as pkg
from devkit_mini.subsystems.mechanical import circuit, N_MOUNTING_HOLES


def test_package_reexports_circuit():
    assert callable(pkg.circuit)
    assert pkg.N_MOUNTING_HOLES == 4
    assert set(pkg.__all__) == {"circuit", "N_MOUNTING_HOLES"}


def test_sheet_identity():
    c = circuit()
    assert isinstance(c, Circuit)
    assert c.name == "mechanical"


def test_four_mounting_holes_all_on_chassis_gnd():
    c = circuit()
    holes = sorted(ref for ref in c.parts if ref.startswith("H"))
    assert holes == ["H1", "H2", "H3", "H4"], holes
    assert len(holes) == N_MOUNTING_HOLES
    ch = c.nets["CHASSIS_GND"]
    chassis_pins = {str(p) for p in ch.pins}
    for h in holes:
        assert f"{h}.1" in chassis_pins, (h, chassis_pins)


def test_chassis_gnd_is_a_ground_net():
    c = circuit()
    assert c.nets["CHASSIS_GND"].net_class is NetClass.GROUND


def test_holes_are_bom_excluded_fab_art():
    c = circuit()
    for h in ("H1", "H2", "H3", "H4"):
        assert c.parts[h].fields.get("BOM") == "exclude", h


def test_no_netlisted_chassis_bond_part():
    """A netlisted bond would DC-merge two deliberately separate nets (LAW 0)."""
    c = circuit()
    assert "GND" not in c.nets, sorted(c.nets)
    assert set(c.nets) == {"CHASSIS_GND"}, sorted(c.nets)
    assert sorted(c.parts) == ["H1", "H2", "H3", "H4"], sorted(c.parts)


def test_model_complete_every_pin_netted_or_nc():
    lib = Library()
    c = circuit()
    c.validate({r: lib.pin_numbers(p.lib_id) for r, p in c.parts.items()})
    assert c.nc_pins == set(), c.nc_pins
