"""Connectivity validator: every symbol pin must be electrically attached.

This validator is the **electrical twin of** :func:`validate_overlap`.
Where the overlap validator is the geometric LAW (no two bodies may
crowd), this one is the electrical LAW: **no pin may float**. A pin's
absolute connection point must coincide with at least one of:

  * a **wire** — the pin coincides with a wire **endpoint**. A pin lying
    on a wire's *interior* (the wire passes over/through it, or overshoots
    past it) is **NOT** connected by KiCad unless a junction is placed at
    that point — verified empirically: an overshooting trunk wire that
    crosses a resistor pin 1.27 mm short of its end reads as
    ``pin_not_connected`` in ERC. So mid-wire taps connect only via the
    junction case below; a bare crossing does not,
  * a **label** — local / hierarchical / global label anchored at the
    pin (the net name attaches there),
  * a **no-connect** marker — the pin is *intentionally* unconnected
    (this satisfies KiCad's ERC and is NOT a defect),
  * **another symbol's pin** — a direct pin-to-pin abut, or
  * a **junction** dot.

Any pin with none of these is FLOATING and reported — exactly the
condition KiCad's ERC reports as ``pin_not_connected``. The whole point
is to turn "is the schematic fully wired?" from a slow, post-emit
``kicad-cli sch erc`` round-trip into a **fast in-memory invariant** the
placement/routing engine can be gated on, just like overlap. A layout
this validator passes is, by construction, one KiCad's ERC passes for
``pin_not_connected``.

No exemptions. When a pin is reported floating, the fix lives in the
router / labeler that should have attached it (land the wire ON the pin
tip, or drop the net label / NC there) — **never** in this file, and
**never** by widening the coincidence tolerance. The tolerance models
KiCad's own (essentially exact, on a snapped grid); loosening it would
call genuinely-disconnected pins "connected" and ship a broken netlist.

Severity is controlled by ``strict`` (mirrors :func:`validate_overlap`):

  * ``strict=True``  — every floating pin is an ``"error"`` (gates emission).
  * ``strict=False`` — every floating pin is a ``"warning"`` (advisory).
"""

from __future__ import annotations

from dataclasses import dataclass

from zynq_eda.core.layout.geometry import SymbolGeometryCache
from zynq_eda.core.model.grid import Point
from zynq_eda.core.model.sheet import PlacedWire, Sheet
from zynq_eda.core.validate.report import Severity, ValidationResult


# ---- Tolerance -------------------------------------------------------------

CONNECT_EPS_MM: float = 0.05
"""Coincidence tolerance (mm) for "a thing is AT this pin".

Every coordinate the engine emits is grid-snapped, and KiCad's own
connectivity test is effectively exact, so this is deliberately tight —
about a twentieth of the finest 1.27 mm grid step. A wire endpoint that
lands a whole grid step (0.635/1.27 mm) away from a pin is a genuine
miss that KiCad's ERC flags as ``pin_not_connected``; widening this
tolerance to absorb such a miss would be softening the LAW and is
forbidden. The router must land the wire ON the pin.
"""


# ---- Pin enumeration -------------------------------------------------------

@dataclass(frozen=True)
class _Pin:
    ref: str
    number: str
    name: str
    point: Point


def _enumerate_pins(
    sheet: Sheet, geometry: SymbolGeometryCache
) -> tuple[list[_Pin], list[ValidationResult]]:
    """Every placed symbol's pins, with absolute connection points.

    Fails LOUD (a finding) for any symbol whose pin geometry can't be
    resolved — never silently skips it, which would exempt that symbol's
    pins from the connectivity LAW.
    """
    pins: list[_Pin] = []
    errors: list[ValidationResult] = []
    for sym in sheet.symbols:
        try:
            pos_by_num = geometry.absolute_pin_positions(
                sym.lib_id, sym.position, sym.rotation
            )
            name_by_num = {
                str(p["number"]): str(p["name"])
                for p in geometry.all_pins(sym.lib_id, sym.rotation)
            }
        except Exception as exc:  # noqa: BLE001
            errors.append(ValidationResult(
                rule_id="connectivity.pin_geometry_unresolved",
                severity="error",
                message=(
                    f"cannot resolve pins for symbol {sym.reference!r} "
                    f"({sym.lib_id!r}): {exc} — its pins are NOT "
                    f"connectivity-checked; failing loud rather than exempting"
                ),
                location=f"{sheet.name}.kicad_sch",
            ))
            continue
        for number, pt in pos_by_num.items():
            pins.append(_Pin(
                ref=sym.reference,
                number=str(number),
                name=name_by_num.get(str(number), ""),
                point=pt,
            ))
    return pins, errors


# ---- Coincidence helpers ---------------------------------------------------

def _at_wire_endpoint(p: Point, wire: PlacedWire, eps: float) -> bool:
    """True iff point ``p`` coincides with a wire **endpoint**.

    Deliberately NOT the interior case: KiCad does not electrically tap a
    pin that a wire merely passes over (it must end on the pin, or carry a
    junction there). Treating interior coincidence as "connected" is what
    let overshooting trunk wires masquerade as connections; the validator
    must mirror ERC, which flags such pins as ``pin_not_connected``.
    """
    return (
        (abs(p.x - wire.start.x) < eps and abs(p.y - wire.start.y) < eps)
        or (abs(p.x - wire.end.x) < eps and abs(p.y - wire.end.y) < eps)
    )


def _near(p: Point, q: Point, eps: float) -> bool:
    return abs(p.x - q.x) < eps and abs(p.y - q.y) < eps


def _dist(p: Point, q: Point) -> float:
    return ((p.x - q.x) ** 2 + (p.y - q.y) ** 2) ** 0.5


# ---- Public entry point ----------------------------------------------------

def validate_connectivity(
    sheet: Sheet,
    *,
    geometry: SymbolGeometryCache,
    strict: bool = False,
) -> list[ValidationResult]:
    """Report every floating pin (KiCad ``pin_not_connected``), in memory.

    Args:
        sheet: the placed :class:`Sheet` to validate.
        geometry: symbol geometry cache (required — pin positions come
            from it; the same source the whole engine and the overlap
            validator trust).
        strict: ``True`` → each floating pin is an ``"error"``; ``False``
            → a ``"warning"``.

    Returns:
        Ordered list of :class:`ValidationResult`, one per floating pin,
        each naming the symbol + pin and the distance to the nearest
        connection provider (so a near-miss grid offset is visible at a
        glance, distinct from a total miss).
    """
    severity: Severity = "error" if strict else "warning"
    pins, results = _enumerate_pins(sheet, geometry)
    eps = CONNECT_EPS_MM

    # Connection providers, gathered once.
    wires = list(sheet.wires)
    label_pts: list[Point] = (
        [l.position for l in sheet.labels]
        + [h.position for h in sheet.hierarchical_labels]
        + [g.position for g in sheet.global_labels]
    )
    nc_pts = [n.position for n in sheet.no_connects]
    junction_pts = [j.position for j in sheet.junctions]
    pin_pts = [pin.point for pin in pins]

    for i, pin in enumerate(pins):
        p = pin.point
        if any(_at_wire_endpoint(p, w, eps) for w in wires):
            continue
        if any(_near(p, q, eps) for q in label_pts):
            continue
        if any(_near(p, q, eps) for q in nc_pts):
            continue
        if any(_near(p, q, eps) for q in junction_pts):
            continue
        # Pin-to-pin abut: another DISTINCT pin coincident with this one.
        if any(j != i and _near(p, q, eps) for j, q in enumerate(pin_pts)):
            continue

        # Floating. Characterise the nearest miss for the diagnostic.
        candidates: list[tuple[float, str]] = []
        for w in wires:
            candidates.append((_dist(p, w.start), "wire-end"))
            candidates.append((_dist(p, w.end), "wire-end"))
        for q in label_pts:
            candidates.append((_dist(p, q), "label"))
        for j, q in enumerate(pin_pts):
            if j != i:
                candidates.append((_dist(p, q), "pin"))
        nearest_txt = ""
        if candidates:
            d, kind = min(candidates, key=lambda c: c[0])
            nearest_txt = f"; nearest {kind} {d:.2f}mm away"

        name_txt = f" [{pin.name}]" if pin.name else ""
        results.append(ValidationResult(
            rule_id="connectivity.pin_floating",
            severity=severity,
            message=(
                f"pin {pin.ref} {pin.number}{name_txt} @ "
                f"({p.x:.2f}, {p.y:.2f}) is not attached to any wire, label, "
                f"no-connect, or pin{nearest_txt}"
            ),
            location=f"{sheet.name}.kicad_sch",
        ))

    return results
