"""HDMI TX/RX topology tests."""

from __future__ import annotations

from scripts.carrier.blocks import all_block_factories


def test_hdmi_tx_has_no_io_to_hier_bypass() -> None:
    block = all_block_factories()["hdmi_tx"]()
    bypass_wires = [
        wire
        for wire in block.wires
        if min(wire.start.x, wire.end.x) < 80.0
        and max(wire.start.x, wire.end.x) > 250.0
    ]
    assert not bypass_wires, (
        "hdmi_tx must not wire IO symbol directly to right-edge hier stubs"
    )


def test_hdmi_tx_wires_through_tpd_region() -> None:
    block = all_block_factories()["hdmi_tx"]()
    tpd_region_wires = [
        wire
        for wire in block.wires
        if 110.0 <= wire.start.x <= 145.0 or 110.0 <= wire.end.x <= 145.0
    ]
    assert len(tpd_region_wires) >= 8
