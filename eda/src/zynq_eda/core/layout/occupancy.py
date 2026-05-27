"""Live occupancy index for collision-aware placement.

The :class:`Occupancy` index is the live, mutable counterpart to the
post-hoc overlap validator. The placement subroutines push every
:class:`~zynq_eda.core.layout.bbox.BBox` they emit into the index, and
subsequent placements consult the index to find non-colliding positions.

Design choices:

  * Backed by a flat list of bboxes — sheets contain at most a few
    hundred primitives, so an O(N^2) scan during ``collides()`` is well
    under 1 ms per call and not worth the complexity of a spatial
    index (R-tree, grid hash). If we ever scale to thousands of
    primitives per page we can swap the implementation behind this
    same interface without touching call sites.
  * Owner-aware: many helpers need to exclude a primitive's "own"
    bboxes from the collision check (e.g. when offsetting a label
    away from a wire, the label's wire-tap junction is allowed to
    coincide with the label's anchor wire). :meth:`collides` and
    :meth:`find_free_offset` accept an ``ignore_owners`` set.
  * Kind-aware: similar story for ignoring whole categories
    (e.g. ignoring ``"junction"`` bboxes when placing a label, since a
    junction is just a 0.4 mm dot and labels happily sit next to one).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Iterator, Sequence

from zynq_eda.core.layout.bbox import BBox, BBoxKind


@dataclass
class Occupancy:
    """A mutable list-of-bboxes index used while a sheet is being placed.

    Construct empty, then ``add()`` each :class:`BBox` as placement
    helpers produce primitives. Query with :meth:`collides` or use the
    convenience :meth:`find_free_offset` to pick a non-colliding offset
    from a candidate list.
    """

    _bboxes: list[BBox] = field(default_factory=list)

    # ---- mutation ----------------------------------------------------------

    def add(self, bbox: BBox) -> None:
        """Append a bbox to the index. No deduplication."""
        self._bboxes.append(bbox)

    def extend(self, bboxes: Iterable[BBox]) -> None:
        """Append every bbox in ``bboxes``."""
        for bbox in bboxes:
            self._bboxes.append(bbox)

    def clear(self) -> None:
        """Drop every stored bbox."""
        self._bboxes.clear()

    def remove_by_owner(self, owner_prefix: str) -> int:
        """Drop every stored bbox whose owner_id startswith ``owner_prefix``.

        Returns the number of bboxes removed. Used by placement helpers
        that temporarily reserve a slot with a placeholder bbox during
        sibling-aware text positioning, then release it once the real
        symbol is placed.
        """
        before = len(self._bboxes)
        self._bboxes = [
            b for b in self._bboxes if not b.owner_id.startswith(owner_prefix)
        ]
        return before - len(self._bboxes)

    # ---- querying ----------------------------------------------------------

    def collides(
        self,
        candidate: BBox,
        ignore_owners: set[str] | frozenset[str] = frozenset(),
        ignore_kinds: set[BBoxKind] | frozenset[BBoxKind] = frozenset(),
        padding_mm: float = 0.0,
    ) -> list[BBox]:
        """Return every stored bbox that intersects ``candidate``.

        Pass ``ignore_owners`` to skip bboxes whose ``owner_id`` is in
        the set (e.g. a label and its own wire share owner "VBUS_J3").
        Pass ``ignore_kinds`` to skip categories of primitives wholesale
        (e.g. ``{"junction"}`` for label placement).

        ``padding_mm`` is forwarded to :meth:`BBox.intersects` — passing
        a positive value reports near-misses (boxes within ``padding_mm``
        of each other) as collisions.
        """
        hits: list[BBox] = []
        for existing in self._bboxes:
            if existing.owner_id in ignore_owners:
                continue
            if existing.kind in ignore_kinds:
                continue
            if candidate.intersects(existing, padding_mm=padding_mm):
                hits.append(existing)
        return hits

    def find_free_offset(
        self,
        bbox: BBox,
        candidate_offsets: Sequence[tuple[float, float]],
        ignore_owners: set[str] | frozenset[str] = frozenset(),
        ignore_kinds: set[BBoxKind] | frozenset[BBoxKind] = frozenset(),
        padding_mm: float = 0.0,
    ) -> tuple[float, float] | None:
        """Try each ``(dx, dy)`` in order; return the first that fits.

        ``candidate_offsets`` is a sequence of (dx, dy) pairs in
        millimetres. For each pair, the function translates ``bbox`` by
        that offset and tests it against the index; the first offset
        whose translated bbox does NOT collide is returned. If every
        offset collides, returns ``None``.

        Use this as the foundation for label-placement helpers: pass an
        ordered list of (dx, dy) preferences (e.g. ``[(0, 0), (0, 2.54),
        (2.54, 0), (0, -2.54), (-2.54, 0), ...]``) and the index picks
        the first non-colliding slot.
        """
        for dx, dy in candidate_offsets:
            translated = bbox.translate(dx, dy)
            if not self.collides(
                translated,
                ignore_owners=ignore_owners,
                ignore_kinds=ignore_kinds,
                padding_mm=padding_mm,
            ):
                return (dx, dy)
        return None

    # ---- container protocol ------------------------------------------------

    def __len__(self) -> int:
        return len(self._bboxes)

    def __iter__(self) -> Iterator[BBox]:
        return iter(self._bboxes)

    def __contains__(self, bbox: BBox) -> bool:
        return bbox in self._bboxes
