"""Unit tests for plan_pin_specs (Phase 1 — pin classification).

The classifier must produce EXACTLY one PinSpec per pin per owner with
exactly one role. The tests check:

  - Each role's classification rule (CLUSTER, GND, EDGE_LABEL,
    POWER_SYMBOL, LOCAL_LABEL, NC) on synthetic minimal Block fixtures.
  - The partition is total: across every block in
    ``projects/carrier/blocks/``, sum of len(pin_specs) equals sum of
    len(geometry.all_pins(...)) for every IC + connector. No pin can
    appear twice, no pin can be missing.

The cross-block test also catches drift between the planner and the
reactive ``_classify_pin`` in ``place.py`` because the same priority
order is encoded in both functions.
"""

from __future__ import annotations

import pytest

from zynq_eda.core.layout.geometry import SymbolGeometryCache
from zynq_eda.core.layout.plan import (
    PinSpec,
    _classify_ic_pin,
    _classify_connector_pin,
    _is_gnd_pin_name,
    _resolve_ic_pin_net,
    plan_pin_specs,
)


# ---------------------------------------------------------------------------
# Helpers for synthetic Block fixtures
# ---------------------------------------------------------------------------


def _carrier_blocks_and_geometry():
    """Load every carrier block + a real geometry cache.

    Returns (blocks_dict, geometry_cache) where blocks_dict maps block
    name → Block instance. Used by the cross-block partition test.
    """
    from zynq_eda.projects.carrier.board import (
        SHARED_SYMBOL_LIBRARIES,
        build_blocks,
    )
    cache = SymbolGeometryCache()
    cache.register_libraries(SHARED_SYMBOL_LIBRARIES)
    blocks = {b.name: b for b in build_blocks()}
    return blocks, cache


# ---------------------------------------------------------------------------
# _is_gnd_pin_name
# ---------------------------------------------------------------------------


def test_is_gnd_pin_name_matches_canonical():
    for name in ("GND", "VSS", "GNDA", "AGND", "DGND"):
        assert _is_gnd_pin_name(name)
        assert _is_gnd_pin_name(name.lower())


def test_is_gnd_pin_name_matches_suffixed():
    for name in ("GND_EP", "VSS_2", "DGND_PAD"):
        assert _is_gnd_pin_name(name)


def test_is_gnd_pin_name_rejects_unrelated():
    for name in ("VDD", "GND_OK_BUT_NO", "PIN1"):
        # GND_OK_BUT_NO actually MATCHES because it starts with "GND_"
        if name == "GND_OK_BUT_NO":
            assert _is_gnd_pin_name(name)
            continue
        assert not _is_gnd_pin_name(name)


# ---------------------------------------------------------------------------
# _resolve_ic_pin_net
# ---------------------------------------------------------------------------


def _make_ic_instance(
    *,
    pin_net_overrides=(),
    net_overrides=(),
    power_input_net="",
    power_output_net="",
    external_parts=(),
    external_part_net_remap=(),
):
    """Build a fake IcInstance just for classifier testing.

    We don't use real refcircuits because constructing them requires
    a part_mpn, lcsc, datasheet_url etc. — orthogonal to the classifier.
    Instead we use a SimpleNamespace-style stand-in.
    """
    from types import SimpleNamespace
    return SimpleNamespace(
        reference="U1",
        lib_id="lib:Sym",
        power_input_net=power_input_net,
        power_output_net=power_output_net,
        net_overrides=net_overrides,
        external_part_net_remap=external_part_net_remap,
        refcircuit=SimpleNamespace(
            pin_net_overrides=pin_net_overrides,
            external_parts=external_parts,
        ),
    )


def test_resolve_ic_pin_net_uses_overrides_first():
    ic = _make_ic_instance(
        pin_net_overrides=(("SCL", "I2C_SCL"),),
        power_input_net="+3V3",
    )
    assert _resolve_ic_pin_net("SCL", ic) == "I2C_SCL"


def test_resolve_ic_pin_net_per_instance_overrides_win():
    ic = _make_ic_instance(
        pin_net_overrides=(("SCL", "REFCIRCUIT_NET"),),
        net_overrides=(("SCL", "INSTANCE_NET"),),
    )
    assert _resolve_ic_pin_net("SCL", ic) == "INSTANCE_NET"


def test_resolve_ic_pin_net_power_input_fallback():
    ic = _make_ic_instance(power_input_net="+3V3")
    assert _resolve_ic_pin_net("VDD", ic) == "+3V3"


def test_resolve_ic_pin_net_power_output_fallback():
    ic = _make_ic_instance(power_output_net="+1V8")
    assert _resolve_ic_pin_net("OUT", ic) == "+1V8"


def test_resolve_ic_pin_net_empty_when_unknown():
    ic = _make_ic_instance()
    assert _resolve_ic_pin_net("RESERVED", ic) == ""


# ---------------------------------------------------------------------------
# _classify_ic_pin
# ---------------------------------------------------------------------------


def test_classify_ic_pin_cluster_when_in_external_parts():
    ic = _make_ic_instance()
    role, net = _classify_ic_pin("VDD", ic, {}, in_cluster=True)
    assert role == "CLUSTER"


def test_classify_ic_pin_gnd():
    ic = _make_ic_instance()
    role, net = _classify_ic_pin("GND", ic, {}, in_cluster=False)
    assert role == "GND"
    assert net == "GND"


def test_classify_ic_pin_edge_label():
    declared = {"SCL_OUT": object()}
    ic = _make_ic_instance(
        pin_net_overrides=(("SCL", "SCL_OUT"),),
    )
    role, net = _classify_ic_pin("SCL", ic, declared, in_cluster=False)
    assert role == "EDGE_LABEL"
    assert net == "SCL_OUT"


def test_classify_ic_pin_power_symbol():
    ic = _make_ic_instance(
        pin_net_overrides=(("VDD_PIN", "+3V3"),),
    )
    role, net = _classify_ic_pin("VDD_PIN", ic, {}, in_cluster=False)
    assert role == "POWER_SYMBOL"
    assert net == "+3V3"


def test_classify_ic_pin_local_label():
    ic = _make_ic_instance(
        pin_net_overrides=(("FB", "FEEDBACK_NODE"),),
    )
    role, net = _classify_ic_pin("FB", ic, {}, in_cluster=False)
    assert role == "LOCAL_LABEL"
    assert net == "FEEDBACK_NODE"


def test_classify_ic_pin_nc_when_no_net():
    ic = _make_ic_instance()
    role, net = _classify_ic_pin("RESERVED", ic, {}, in_cluster=False)
    assert role == "NC"
    assert net == ""


# ---------------------------------------------------------------------------
# _classify_connector_pin
# ---------------------------------------------------------------------------


def _make_connector_instance(*, external_parts=()):
    from types import SimpleNamespace
    return SimpleNamespace(
        reference="J1",
        lib_id="lib:Conn",
        rotation=0.0,
        pin_to_net=(),
        refcircuit=SimpleNamespace(external_parts=external_parts),
    )


def test_classify_connector_pin_cluster():
    from zynq_eda.core.model.refcircuit import ExternalPart
    conn = _make_connector_instance(
        external_parts=(ExternalPart(
            from_pin="SHIELD", to_net="CHASSIS_GND", part_token="1M_0402_1%",
            quantity=1,
        ),),
    )
    role, net = _classify_connector_pin(
        "SHIELD", conn, pin_to_net={}, declared_nets={}, in_cluster=True,
    )
    assert role == "CLUSTER"
    assert net == "CHASSIS_GND"


def test_classify_connector_pin_gnd_by_name():
    conn = _make_connector_instance()
    role, _net = _classify_connector_pin(
        "GND", conn, pin_to_net={}, declared_nets={}, in_cluster=False,
    )
    assert role == "GND"


def test_classify_connector_pin_edge_label():
    conn = _make_connector_instance()
    declared = {"USB_DP": object()}
    role, net = _classify_connector_pin(
        "D+", conn, pin_to_net={"D+": "USB_DP"},
        declared_nets=declared, in_cluster=False,
    )
    assert role == "EDGE_LABEL"
    assert net == "USB_DP"


def test_classify_connector_pin_power_symbol():
    conn = _make_connector_instance()
    role, net = _classify_connector_pin(
        "VBUS", conn, pin_to_net={"VBUS": "+5V"},
        declared_nets={}, in_cluster=False,
    )
    assert role == "POWER_SYMBOL"


def test_classify_connector_pin_local_label():
    conn = _make_connector_instance()
    role, net = _classify_connector_pin(
        "TX", conn, pin_to_net={"TX": "UART_TX"},
        declared_nets={}, in_cluster=False,
    )
    assert role == "LOCAL_LABEL"


def test_classify_connector_pin_nc_when_unmapped():
    conn = _make_connector_instance()
    role, net = _classify_connector_pin(
        "RESERVED", conn, pin_to_net={}, declared_nets={}, in_cluster=False,
    )
    assert role == "NC"


# ---------------------------------------------------------------------------
# plan_pin_specs — cross-block partition test
# ---------------------------------------------------------------------------


def test_plan_pin_specs_one_spec_per_pin_per_block():
    """Every IC + connector pin on every carrier block becomes exactly
    one PinSpec.

    This is the bedrock invariant of Phase 1: the classification is a
    total partition of all pins. If a pin appears twice or is missing,
    downstream phases will produce inconsistent results.
    """
    blocks, geometry = _carrier_blocks_and_geometry()
    for block_name, block in blocks.items():
        specs = plan_pin_specs(block, geometry)

        # Each (owner_ref, pin_number) tuple appears exactly once.
        keys = [(s.owner_ref, s.pin_number) for s in specs]
        assert len(keys) == len(set(keys)), (
            f"block {block_name}: duplicate (owner, pin_number) in pin_specs"
        )

        # Total pin count matches geometry's enumeration.
        expected_total = 0
        for ic in block.ics:
            expected_total += sum(
                1 for _ in geometry.all_pins(ic.lib_id, rotation=0.0)
            )
        for conn in block.connectors:
            expected_total += sum(
                1 for _ in geometry.all_pins(
                    conn.lib_id, rotation=conn.rotation,
                )
            )
        assert len(specs) == expected_total, (
            f"block {block_name}: pin_specs has {len(specs)} entries but "
            f"geometry reports {expected_total} pins across "
            f"{len(block.ics)} ICs + {len(block.connectors)} connectors"
        )


def test_plan_pin_specs_role_partition_is_exclusive():
    """Every PinSpec has exactly one role; the role is one of the
    six declared values."""
    blocks, geometry = _carrier_blocks_and_geometry()
    for block_name, block in blocks.items():
        specs = plan_pin_specs(block, geometry)
        for s in specs:
            assert s.role in (
                "CLUSTER", "GND", "EDGE_LABEL", "POWER_SYMBOL",
                "LOCAL_LABEL", "NC",
            ), f"block {block_name}: unexpected role {s.role!r} on {s.pin_name}"


def test_plan_pin_specs_cluster_destinations_count_matches_slot_count():
    """CLUSTER PinSpecs' cluster_destinations length matches
    cluster_slot_count. The PinSpec.__post_init__ guard enforces this;
    this test confirms the planner respects it across all blocks."""
    blocks, geometry = _carrier_blocks_and_geometry()
    for block_name, block in blocks.items():
        specs = plan_pin_specs(block, geometry)
        for s in specs:
            if s.role == "CLUSTER":
                assert len(s.cluster_destinations) == s.cluster_slot_count, (
                    f"block {block_name}: pin {s.pin_name} on {s.owner_ref}: "
                    f"destinations={s.cluster_destinations}, "
                    f"slot_count={s.cluster_slot_count}"
                )
                # slot_count must be > 0
                assert s.cluster_slot_count > 0


def test_plan_pin_specs_non_cluster_has_no_slots():
    blocks, geometry = _carrier_blocks_and_geometry()
    for block_name, block in blocks.items():
        specs = plan_pin_specs(block, geometry)
        for s in specs:
            if s.role != "CLUSTER":
                assert s.cluster_slot_count == 0
                assert s.cluster_destinations == ()


def test_plan_pin_specs_matches_reactive_classifier_for_ics():
    """For every IC on every carrier block, the planner's role assignment
    must match the reactive ``_classify_pin`` in place.py.

    This is the side-by-side test from the PR 2 plan: it confirms the
    planner produces exactly the same per-pin partition the reactive
    pipeline has been building, so PR 2 is risk-free (no behaviour
    change can leak through the planner that wasn't already present).
    """
    from zynq_eda.core.layout.place import _classify_pin

    blocks, geometry = _carrier_blocks_and_geometry()
    for block_name, block in blocks.items():
        declared_nets = {n.name: n for n in block.external_nets}
        planner_specs = {
            (s.owner_ref, s.pin_name): s
            for s in plan_pin_specs(block, geometry)
            if s.owner_kind == "ic"
        }

        for ic in block.ics:
            cluster_pins = {ep.from_pin for ep in ic.refcircuit.external_parts}
            for pin_info in geometry.all_pins(ic.lib_id, rotation=0.0):
                pin_name = str(pin_info["name"])
                reactive_role, reactive_net = _classify_pin(
                    pin_name, ic, declared_nets,
                    in_cluster=(pin_name in cluster_pins),
                )
                key = (ic.reference, pin_name)
                planner_spec = planner_specs.get(key)
                assert planner_spec is not None, (
                    f"block {block_name}: planner missing PinSpec for "
                    f"{ic.reference}/{pin_name}"
                )
                assert planner_spec.role == reactive_role, (
                    f"block {block_name}: {ic.reference}/{pin_name}: "
                    f"planner role {planner_spec.role!r} vs reactive "
                    f"{reactive_role!r}"
                )
                # CLUSTER net_name uses the resolved override net; the
                # reactive classifier returns the same thing (via
                # _compute_pin_net inside _classify_pin's CLUSTER branch).
                # For non-CLUSTER roles, net_name must match exactly.
                if planner_spec.role != "CLUSTER":
                    assert planner_spec.net_name == reactive_net, (
                        f"block {block_name}: {ic.reference}/{pin_name}: "
                        f"planner net {planner_spec.net_name!r} vs reactive "
                        f"{reactive_net!r}"
                    )


def test_plan_pin_specs_external_part_remap_applied():
    """When an IC declares external_part_net_remap, the planner's
    CLUSTER pin's cluster_destinations should reflect the remap."""
    # usb_pd's U1 (FUSB302) has external_part_net_remap=(("+3V3_SC", "+3V3"),)
    # so any cluster external going to "+3V3_SC" should land as "+3V3".
    blocks, geometry = _carrier_blocks_and_geometry()
    usb_pd = blocks["usb_pd"]
    specs = plan_pin_specs(usb_pd, geometry)
    u1_specs = [s for s in specs if s.owner_ref == "U1" and s.role == "CLUSTER"]
    # Confirm at least some CLUSTER pins exist on U1.
    assert u1_specs, "expected FUSB302 to have CLUSTER pins"
    # Confirm no destination is still "+3V3_SC" (the catalog name).
    for s in u1_specs:
        for dest in s.cluster_destinations:
            assert dest != "+3V3_SC", (
                f"U1 pin {s.pin_name}: cluster destination {dest!r} should "
                f"have been remapped to '+3V3' by external_part_net_remap"
            )
