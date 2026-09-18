"""Transitional differential coverage for the batched native ratsnest stage."""
import random

from schgen.core import native
from schgen.generate.ratsnest import (
    _mst_edges_py,
    cross_airwire_length,
    net_mst_edges,
)


def reference_lengths(nets, edges):
    cross = total = 0.0
    count = 0
    for name, pads in sorted(nets.items()):
        for a, b in edges[name]:
            xa, ya, _, sa = pads[a]
            xb, yb, _, sb = pads[b]
            length = native.module().hypot_xy(xa, ya, xb, yb)
            total += length
            if sa != sb:
                cross += length
                count += 1
    return round(cross, 1), round(total, 1), count


def test_batched_ratsnest_matches_reference():
    rng = random.Random(314159)
    for _ in range(80):
        nets = {
            name: [(rng.randrange(-50, 50) / 10, rng.randrange(-50, 50) / 10,
                    str(i), str(rng.randrange(4)))
                   for i in range(rng.randrange(25))]
            for name in ("z", "β", "A", "empty")
        }
        nets["empty"] = []
        expected = {name: _mst_edges_py(pads) for name, pads in sorted(nets.items())}
        got = net_mst_edges(None, nets)
        assert got == expected
        assert list(got) == sorted(nets)
        lengths = reference_lengths(nets, expected)
        assert cross_airwire_length(None, nets, got) == lengths
        assert cross_airwire_length(None, nets) == lengths


def test_airwire_rounding_and_supplied_edges():
    for distance in (0.05, 0.15, 0.25, 1.25, 2.55, 123.45):
        nets = {"tie": [(0.0, 0.0, "A", "s1"), (distance, 0.0, "B", "s2")]}
        edges = {"tie": [(1, 0), (0, 1)]}
        assert cross_airwire_length(None, nets, edges) == reference_lengths(nets, edges)
