"""DEF-J: tests for the congestion auto-pagination primitives (place/model).

The LAW-0 chokepoint is Circuit.subset(): it MUST refuse to cut a SIGNAL net
across pages (that would be a silent OPEN). partition_pages must keep SIGNAL-
connected parts together and never over-split a single blob. (The full buck +
power_som placement is exercised by `schgen board` / scripts/check.sh.)"""

from __future__ import annotations

import pytest

from schgen.core.model import Circuit, PartitionError
from schgen.core.symbols import Library
from schgen.layout import place


def _two_R_on_signal():
    """R1,R2 share a SIGNAL net SIG (R1.1,R2.1); R*.2 -> GND. Splitting {R1}|{R2}
    cuts SIG."""
    c = Circuit("t", "t")
    for r in ("R1", "R2"):
        c.part(r, "Device:R", "10k", "Resistor_SMD:R_0603_1608Metric")
        c.net("SIG", f"{r}.1")
        c.net("GND", f"{r}.2")
    return c


def test_subset_refuses_to_cut_a_signal_net():
    c = _two_R_on_signal()
    with pytest.raises(PartitionError):
        c.subset({"R1"}, page=1)        # SIG would span R1's page + R2's page


def test_subset_keeps_whole_signal_net_ok():
    c = _two_R_on_signal()
    sub = c.subset({"R1", "R2"}, page=1)   # SIG fully inside -> no cut
    assert "SIG" in sub.nets and len(sub.nets["SIG"].pins) == 2
    assert sub.name == "t.1"


def test_subset_cuts_power_and_ground_freely():
    # a rail/GND net is allowed to span pages (it merges by name) — only its
    # local pins are carried, no PartitionError.
    c = Circuit("t", "t")
    for r in ("R1", "R2"):
        c.part(r, "Device:R", "10k", "Resistor_SMD:R_0603_1608Metric")
        c.net("+3V3", f"{r}.1")
        c.net("GND", f"{r}.2")
    sub = c.subset({"R1"}, page=1)          # +3V3/GND cross — that's fine
    assert sub.nets["+3V3"].pins == [p for p in sub.nets["+3V3"].pins
                                     if p.ref == "R1"]


def test_partition_pages_single_blob_returns_self():
    # a fully SIGNAL-connected circuit is one indivisible blob -> no split.
    c = _two_R_on_signal()
    assert place.partition_pages(c, Library()) == [c]
