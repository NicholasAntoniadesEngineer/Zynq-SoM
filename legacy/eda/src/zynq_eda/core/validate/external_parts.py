"""Stage-0.5 validator: every ``ExternalPart.from_pin`` must reach a real pin.

A reference circuit attaches supporting parts (decoupling caps, pull-ups,
series resistors, dividers) to named pins via ``ExternalPart.from_pin``.
At layout time the planner enumerates the symbol's pins and matches each
``from_pin`` against them; a ``from_pin`` that names no real pin is
**silently dropped** (the part vanishes with no error). That has hidden
genuinely-missing supporting circuitry -- e.g. the microSD card-detect
pull-up (``from_pin="CD_SW"`` -- no such pin) and every FMC/SoM connector
decoupling cap (``from_pin="VCC_3V3"`` against bank symbols whose pins are
connector designators like ``C30``).

This check runs after blocks are built and the geometry cache is loaded,
BEFORE placement, and hard-fails with a diagnostic that names the offending
instance, its symbol, the bad pin, and the symbol's real pin names.

It validates at the INSTANCE level (block IC/connector -> ``lib_id``), and
dedups across instances that share a refcircuit: a refcircuit is sometimes
split across sibling bank sub-symbols (e.g. the LVDS FFC is instantiated as
a "signals" sub-symbol AND a "power" sub-symbol; a part whose ``from_pin``
lives on the power half is legitimately dropped on the signals half and
PLACED on the power half). Such a part is NOT missing. So a ``from_pin`` is
an error only if it resolves on NO instance sharing the same refcircuit --
i.e. the part is placed NOWHERE.
"""

from __future__ import annotations

from zynq_eda.core.layout.geometry import SymbolGeometryCache
from zynq_eda.core.model.block import Block
from zynq_eda.core.validate.report import ValidationResult


def validate_external_part_pins(
    blocks: list[Block],
    geometry: SymbolGeometryCache,
) -> list[ValidationResult]:
    """Return an ``error`` for every ``ExternalPart.from_pin`` that resolves
    to a real symbol pin on NONE of the instances sharing its refcircuit
    (the supporting part is placed nowhere and silently vanishes).

    Pin NAMES are rotation-invariant, so symbols are queried at rotation 0.
    """
    owners: list[tuple[Block, object, frozenset[str]]] = []
    symbol_errors: list[ValidationResult] = []
    for block in blocks:
        for owner in list(getattr(block, "ics", ())) + list(
            getattr(block, "connectors", ())
        ):
            refcircuit = getattr(owner, "refcircuit", None)
            if not (getattr(refcircuit, "external_parts", ()) or ()):
                continue
            try:
                real = frozenset(
                    str(p["name"]) for p in geometry.all_pins(owner.lib_id, 0.0)
                )
            except Exception as exc:
                symbol_errors.append(ValidationResult(
                    rule_id="external_parts.symbol_unreadable",
                    severity="error",
                    message=(
                        f"{block.name}/{owner.reference}: cannot read pins of "
                        f"symbol {owner.lib_id!r} to validate ExternalParts: {exc}"
                    ),
                    location=f"{block.name}",
                ))
                continue
            owners.append((block, owner, real))

    # Union of pins available across all instances sharing a refcircuit.
    placed_pins: dict[int, set[str]] = {}
    for _block, owner, real in owners:
        placed_pins.setdefault(id(owner.refcircuit), set()).update(real)

    results: list[ValidationResult] = list(symbol_errors)
    reported: set[tuple[int, str]] = set()
    for block, owner, real in owners:
        refcircuit = owner.refcircuit
        union = placed_pins.get(id(refcircuit), set())
        for ep in refcircuit.external_parts:
            if ep.from_pin in union:
                continue  # placed on some sibling instance -- not missing
            key = (id(refcircuit), ep.from_pin)
            if key in reported:
                continue
            reported.add(key)
            results.append(ValidationResult(
                rule_id="external_parts.from_pin_missing",
                severity="error",
                message=(
                    f"{block.name}/{owner.reference} ({owner.lib_id}): "
                    f"ExternalPart.from_pin {ep.from_pin!r} "
                    f"(part {ep.part_token!r}, part_mpn "
                    f"{getattr(refcircuit, 'part_mpn', '?')!r}) matches NO pin on "
                    f"any instance of this refcircuit -- the part is placed "
                    f"NOWHERE (silently dropped). Fix the refcircuit from_pin or "
                    f"the symbol. Pins available on this instance: {sorted(real)}"
                ),
                location=f"{block.name}",
            ))
    return results
