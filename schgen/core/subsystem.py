"""subsystem — the STANDARD adapter<->library contract for reusable subsystems.

A reusable subsystem lives in ``subsystems/<name>/<name>.py`` and exposes a
top-level ``circuit(meta=None)``. It is PROJECT-AGNOSTIC: it declares its
interface as ABSTRACT port + rail names and knows nothing about any board. A
consuming project supplies a THIN ADAPTER (e.g. ``carrier/subsystems/<name>.py``)
that declares ONE module-level ``META`` dict and forwards it::

    META = {
        "bind":    {"+VDD_LOGIC": "+3V3_SC", "GND": "GND", ...},
        "expects": {"I2C_SDA": "som_j1 (GPIO function map)", ...},
        "buses":   {"i2c": "STM32_I2C2"},
        "notes":   {"draws": "FUSB302B VDD (<1 mA); ..."},
    }

    def circuit():
        return _lib.circuit(META)

The library's ``circuit(meta=None)`` reads that dict through :class:`Meta`, which
standardizes the shape so EVERY subsystem + adapter follow an identical contract.
Standalone (``meta=None``) every accessor returns the library default, so the
package's own ``test_<name>.py`` runs offline with the abstract names.

Standard keys (all optional; a typo'd top-level key is a hard error so a meta
dict can never be silently half-ignored):

  ``bind``     ``{abstract_net: real_net}`` — rename the externally-visible
               POWER/GROUND/PORT nets to a project's real names. Applied LAST by
               :meth:`Meta.finish` via :meth:`Circuit.bind` (order-preserving =>
               byte-identical sheet; rejects SIGNAL rebind / unknown / collision).
  ``expects``  ``{abstract_port: deferral_string}`` — attach an EXPLICIT linker
               deferral to a port (the project declares which of its sheets will
               bind a deferred port). Forwarded into ``c.port(..., expect=...)``
               via :meth:`Meta.expect_kw`.
  ``buses``    ``{role: real_bus_name}`` — rename a named bus group (e.g.
               ``{"i2c": "STM32_I2C2"}``) so a consuming board can place this
               subsystem on one of its own named buses. Read with
               :meth:`Meta.bus`.
  ``notes``    ``{key: prose}`` — house-style prose overrides a project restores
               so its derived artifacts (power-tree note, etc.) stay stable
               (e.g. ``{"draws": "..."}``). Read with :meth:`Meta.note`.
"""

from __future__ import annotations

from typing import Any

from schgen.core.model import Circuit, CircuitError

# The only legal top-level keys of a subsystem META dict.
META_KEYS = ("bind", "expects", "buses", "notes")
# The keys whose value must be a mapping (str -> str).
_DICT_KEYS = ("bind", "expects", "buses", "notes")


class Meta:
    """Typed, validated view over a subsystem ``META`` dict (see module docstring).

    Constructed from a plain dict, ``None`` (standalone), or another :class:`Meta`
    (idempotent). Unknown top-level keys raise :class:`CircuitError` so a typo
    like ``"bus"`` for ``"buses"`` can never be silently dropped.
    """

    __slots__ = ("bind_map", "expects", "_buses", "_notes")

    def __init__(self, meta: "Meta | dict[str, Any] | None" = None):
        if isinstance(meta, Meta):
            self.bind_map = meta.bind_map
            self.expects = meta.expects
            self._buses = meta._buses
            self._notes = meta._notes
            return
        meta = meta or {}
        if not isinstance(meta, dict):
            raise CircuitError(
                f"subsystem meta must be a dict, got {type(meta).__name__}")
        bad = set(meta) - set(META_KEYS)
        if bad:
            raise CircuitError(
                f"unknown subsystem meta key(s) {sorted(bad)} — legal keys are "
                f"{list(META_KEYS)}")
        for k in _DICT_KEYS:
            v = meta.get(k)
            if v is not None and not isinstance(v, dict):
                raise CircuitError(
                    f"subsystem meta[{k!r}] must be a dict, got "
                    f"{type(v).__name__}")
        self.bind_map: dict[str, str] | None = meta.get("bind")
        self.expects: dict[str, str] = dict(meta.get("expects") or {})
        self._buses: dict[str, str] = dict(meta.get("buses") or {})
        self._notes: dict[str, str] = dict(meta.get("notes") or {})

    def bus(self, role: str, default: str) -> str:
        """The real net-group name for a named bus ``role`` (``buses[role]``),
        or ``default`` (the library's own abstract bus name) when unbound."""
        return self._buses.get(role, default)

    def note(self, key: str, default: str) -> str:
        """House-style prose override ``notes[key]`` or the library ``default``."""
        return self._notes.get(key, default)

    def expect_kw(self, port: str) -> dict[str, str]:
        """``{"expect": deferral}`` for a port that has one in ``expects``, else
        ``{}`` — splat into a ``c.port(...)`` call: ``c.port(p, pin,
        **meta.expect_kw(p))``."""
        e = self.expects.get(port)
        return {"expect": e} if e else {}

    def finish(self, c: Circuit) -> Circuit:
        """Apply ``bind`` (if any) and return the circuit. Call this as the last
        line of every library ``circuit()``: ``return meta.finish(c)``."""
        if self.bind_map:
            c.bind(self.bind_map)
        return c
