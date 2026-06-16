"""LOCAL test for the carrier-LOCAL ``mechanical`` package.

``mechanical`` is a CARRIER-LOCAL, project-specific sheet (NOT a reusable
library subsystem and NOT a thin adapter) — it owns the board-mechanical fab-art
that has no electrical interface to bind: the four M3 corner mounting holes and
their CHASSIS_GND bond. It is the home the four holes moved to when they left the
``rj45_connector`` jack sheet so the per-subsystem PCB ratsnest stops bundling
them with the Ethernet jack (they now form their OWN corner-forced mechanical
cluster).

What this test proves about the sheet ITSELF (offline, no kicad-cli, no board):
  * the four M3 mounting holes are present (H1..H4), all bonded to CHASSIS_GND;
  * CHASSIS_GND is a GROUND net (a mounting hole is a chassis/earth bond, never a
    rail — :meth:`Circuit.mounting_hole` itself rejects a non-GROUND net, LAW 0);
  * the holes are BOM-excluded fab-art (no BOM line);
  * model completeness — every part pin is netted-or-NC (no silent floats);
  * there is NO netlisted GND<->CHASSIS_GND bond part on this sheet: the
    single-point chassis bond is a PCB-layout copper stitch, NOT a netlisted
    device (a netlisted bond would DC-merge two deliberately-separate nets, LAW
    0). So GND must not even appear as a declared net here.

Board-level gates (the full netlist merge, board ERC, the LAW-5 PCB ratsnest /
placement gate that proves the holes are a corner cluster, the golden render)
stay aggregated by ``schgen board``.
"""

from __future__ import annotations

from schgen.core.model import Circuit, NetClass
from schgen.core.symbols import Library

import carrier.subsystems.mechanical as pkg
from carrier.subsystems.mechanical import circuit, N_MOUNTING_HOLES


def test_package_reexports_circuit():
    assert callable(pkg.circuit)
    assert pkg.N_MOUNTING_HOLES == 4
    assert set(pkg.__all__) == {"circuit", "N_MOUNTING_HOLES"}


def test_sheet_identity():
    c = circuit()
    assert isinstance(c, Circuit)
    assert c.name == "mechanical"


def test_four_mounting_holes_all_on_chassis_gnd():
    """The four M3 corner holes (H1..H4) are present and ALL bond to
    CHASSIS_GND — the chassis island, kept separate from signal GND."""
    c = circuit()
    holes = sorted(ref for ref in c.parts if ref.startswith("H"))
    assert holes == ["H1", "H2", "H3", "H4"], holes
    assert len(holes) == N_MOUNTING_HOLES
    ch = c.nets["CHASSIS_GND"]
    chassis_pins = {str(p) for p in ch.pins}
    for h in holes:
        assert f"{h}.1" in chassis_pins, (h, chassis_pins)


def test_chassis_gnd_is_a_ground_net():
    """CHASSIS_GND classes as GROUND (so :meth:`mounting_hole` accepts it — a
    hole is a chassis/earth bond, never a rail, LAW 0)."""
    c = circuit()
    assert c.nets["CHASSIS_GND"].net_class is NetClass.GROUND


def test_holes_are_bom_excluded_fab_art():
    """Mounting holes are plated chassis-bond fab-art, never a BOM line."""
    c = circuit()
    for h in ("H1", "H2", "H3", "H4"):
        assert c.parts[h].fields.get("BOM") == "exclude", h


def test_no_netlisted_chassis_bond_part():
    """The GND<->CHASSIS_GND single-point star is a PCB-layout copper STITCH, not
    a netlisted part. A netlisted bond would DC-merge two deliberately-separate
    nets (LAW 0), so this sheet declares ONLY CHASSIS_GND — no GND net, no bond
    resistor/ferrite/jumper across the two."""
    c = circuit()
    assert "GND" not in c.nets, sorted(c.nets)
    assert set(c.nets) == {"CHASSIS_GND"}, sorted(c.nets)
    # the only parts are the four holes (no bonding device)
    assert sorted(c.parts) == ["H1", "H2", "H3", "H4"], sorted(c.parts)


def test_model_complete_every_pin_netted_or_nc():
    """Model completeness — every physical pin is netted or NC (no silent
    floats), the same hard check the board build runs (LAW 0)."""
    lib = Library()
    c = circuit()
    c.validate({r: lib.pin_numbers(p.lib_id) for r, p in c.parts.items()})
    assert c.nc_pins == set(), c.nc_pins
