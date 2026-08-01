from __future__ import annotations

from typing import Any

from schgen.core.model import Circuit, CircuitError

META_KEYS = ("bind", "expects", "buses", "notes")
_DICT_KEYS = ("bind", "expects", "buses", "notes")


class Meta:
    __slots__ = ("bind_map", "expects", "_buses", "_notes")

    def __init__(self, meta: Meta | dict[str, Any] | None = None):
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
        return self._buses.get(role, default)

    def note(self, key: str, default: str) -> str:
        return self._notes.get(key, default)

    def expect_kw(self, port: str) -> dict[str, str]:
        e = self.expects.get(port)
        return {"expect": e} if e else {}

    def finish(self, c: Circuit) -> Circuit:
        """Apply ``bind`` and return the circuit; call this last in ``circuit()``."""
        if self.bind_map:
            c.bind(self.bind_map)
        return c
