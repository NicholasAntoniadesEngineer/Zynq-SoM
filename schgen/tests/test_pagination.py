from __future__ import annotations

import pytest

from schgen.core.model import Circuit, PartitionError
from schgen.core.symbols import Library
from schgen.layout import place


def _two_R_on_signal():
    c = Circuit("t", "t")
    for r in ("R1", "R2"):
        c.part(r, "Device:R", "10k", "Resistor_SMD:R_0603_1608Metric")
        c.net("SIG", f"{r}.1")
        c.net("GND", f"{r}.2")
    return c


def test_subset_refuses_to_cut_a_signal_net():
    c = _two_R_on_signal()
    with pytest.raises(PartitionError):
        c.subset({"R1"}, page=1)


def test_subset_keeps_whole_signal_net_ok():
    c = _two_R_on_signal()
    sub = c.subset({"R1", "R2"}, page=1)
    assert "SIG" in sub.nets and len(sub.nets["SIG"].pins) == 2
    assert sub.name == "t.1"


def test_subset_cuts_power_and_ground_freely():
    c = Circuit("t", "t")
    for r in ("R1", "R2"):
        c.part(r, "Device:R", "10k", "Resistor_SMD:R_0603_1608Metric")
        c.net("+3V3", f"{r}.1")
        c.net("GND", f"{r}.2")
    sub = c.subset({"R1"}, page=1)
    assert sub.nets["+3V3"].pins == [p for p in sub.nets["+3V3"].pins
                                     if p.ref == "R1"]


def test_partition_pages_single_blob_returns_self():
    c = _two_R_on_signal()
    assert place.partition_pages(c, Library()) == [c]
