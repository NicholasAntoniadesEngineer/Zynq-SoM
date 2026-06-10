"""Cluster-passive utility helpers reused by the predictive planner.

This module used to host the reactive cluster placer
(``cluster_ic_externals``) and a stack of supporting functions. The
predictive planner in :mod:`zynq_eda.core.layout.plan` now performs all
cluster geometry; only the pure lookup helpers below are still needed,
because they encode the catalog mapping
``part_token → (lib_id, value, footprint, ref-prefix)`` and the
geometry-aware ``power-symbol rotation`` rule.

Anything more complex than these helpers should live in
``plan.py`` — the reactive helpers have been removed.
"""

from __future__ import annotations

from typing import Literal


PassiveKind = Literal["cap", "res", "diode", "other"]


def passive_kind(part_token: str) -> PassiveKind:
    """Classify a registry part token as ``cap`` / ``res`` / ``diode`` / ``other``."""
    lowered = part_token.lower()
    if "schottky" in lowered or lowered.startswith("ss"):
        return "diode"
    cap_markers = (
        "n_0402", "n_0603", "u_0402", "u_0603", "u_1206", "p_0402",
        "_x7r", "_x5r", "_c0g",
    )
    if any(marker in lowered for marker in cap_markers):
        return "cap"
    res_markers = ("k_0402", "k_0603", "r_0402", "r_0603", "_1%")
    if any(marker in lowered for marker in res_markers):
        return "res"
    return "other"


def passive_lib_id(part_token: str) -> str:
    """Return the KiCad ``lib_id`` for a passive given its part token."""
    kind = passive_kind(part_token)
    return {
        "cap":   "Device:C",
        "res":   "Device:R",
        "diode": "Device:D_Schottky",
        "other": "Device:R",
    }[kind]


def passive_value(part_token: str) -> str:
    """Extract the symbol's ``Value`` field text from a part token.

    Prefers the canonical ``BOMPart.value`` from the parts registry when
    the token is registered (e.g. ``R_SENSE_10mR_2010_1%`` -> ``0R01``
    rather than the heuristic-derived ``R``). Falls back to a
    split-on-underscore heuristic for tokens that aren't in the registry
    yet — useful during incremental authoring.

    Examples:
        "100n_0402_X7R"          -> "100n"
        "10k_0402_1%"            -> "10k"
        "R_SENSE_10mR_2010_1%"   -> "0R01"  (via registry)
        "schottky_SS14"          -> "SS14"
    """
    try:
        from zynq_eda.catalog.registry.parts_registry import get_part
        return get_part(part_token).value
    except (KeyError, ImportError):
        pass
    parts = part_token.split("_")
    if not parts:
        return part_token
    if parts[0].lower() == "schottky":
        return parts[-1] if len(parts) > 1 else parts[0]
    return parts[0]


def passive_footprint(part_token: str) -> str:
    """Best-effort KiCad footprint for the part token.

    Prefers the registry's ``BOMPart.footprint`` so wide-package shunts
    (e.g. ``R_SENSE_10mR_2010_1%`` -> 2010 / 5025Metric) and other
    non-default packages emit correct footprints. Falls back to a
    per-passive-kind default for tokens missing from the registry.
    """
    try:
        from zynq_eda.catalog.registry.parts_registry import get_part
        return get_part(part_token).footprint
    except (KeyError, ImportError):
        pass
    kind = passive_kind(part_token)
    if kind == "cap":
        return "Capacitor_SMD:C_0402_1005Metric"
    if kind == "diode":
        return "Diode_SMD:D_SMA"
    return "Resistor_SMD:R_0402_1005Metric"


def passive_ref_prefix(part_token: str) -> str:
    """Return the designator prefix (``C`` / ``R`` / ``D``) for a part token."""
    kind = passive_kind(part_token)
    return {"cap": "C", "res": "R", "diode": "D", "other": "R"}[kind]


def _outward_power_symbol_rotation(
    *,
    lib_id: str,
    pin_side: Literal["left", "right", "top", "bottom"],
    geometry_cache,
) -> float:
    """Pick the KiCad rotation that makes a power symbol's body extend OUTWARD.

    "Outward" means away from the cap/IC the symbol is attached to.
    KiCad's stock power symbols come in two natural orientations:

      * **body-down** (e.g. ``power:GND``, ``power:Earth``) — the pin
        tip sits at the top of the symbol with the body extending
        DOWN on the page at rotation 0.
      * **body-up** (e.g. ``power:+3V3``, ``power:+5V``, ``power:+1V8``)
        — the pin tip sits at the bottom with the body extending UP
        at rotation 0.

    We detect which one we have by inspecting the symbol's bbox
    (returned by the geometry cache) — if the body's centre is below
    the anchor (positive page Y), the symbol is body-down; otherwise
    body-up. From there, the rotation that points the body outward is
    fully determined by ``pin_side``.

    Falls back to ``0.0`` when the geometry cache can't resolve the
    library symbol (the validator will then surface the resulting
    overlap; better that than a silent mis-placement).
    """
    if geometry_cache is None:
        return 0.0
    try:
        bbox = geometry_cache.bounding_box(lib_id, rotation=0.0)
    except Exception:
        return 0.0
    body_center_y = (bbox.min_y + bbox.max_y) / 2.0
    if body_center_y > 0.0:
        # Body-down symbol (GND-style): default body extends to page +Y.
        return {
            "top":    180.0,
            "bottom": 0.0,
            "left":   180.0,
            "right":  180.0,
        }[pin_side]
    # Body-up symbol (+3V3-style): default body extends to page -Y.
    return {
        "top":    0.0,
        "bottom": 180.0,
        "left":   0.0,
        "right":  0.0,
    }[pin_side]
