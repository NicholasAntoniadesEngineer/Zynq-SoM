"""Cross-cluster wire routing on a placed sheet.

Until Wave B, every cross-cluster wire (power-symbol stubs, signal
overrides, GND attachments routed between distant clusters) was emitted
as a direct point-to-point segment. With dense placements that strategy
crosses symbol bodies and label text, producing visual overlaps the
validator surfaces.

:mod:`zynq_eda.core.route.router` provides a minimal occupancy-aware
orthogonal router that picks the first non-colliding L-bend or double-L
between two grid-aligned points, consulting the live
:class:`~zynq_eda.core.layout.occupancy.Occupancy` index.
"""

from zynq_eda.core.route.router import route_orthogonal

__all__ = ("route_orthogonal",)
