"""Provenance-record machinery: no board facts, only the shape of a record."""

from __future__ import annotations

from dataclasses import dataclass, field

SOURCE_CLASSES = ("datasheet", "measured", "policy")


@dataclass(frozen=True)
class Declaration:
    name: str
    value: str | float | int
    unit: str
    basis: str
    klass: str

    @property
    def gist(self) -> str:
        return f"{self.value!r} {self.unit}/{self.klass}"


@dataclass(frozen=True)
class Bind:
    name: str
    port: str
    net: str
    basis: str
    klass: str

    @property
    def gist(self) -> str:
        return f"{self.net!r}/{self.klass}"


def _admit(record: Declaration | Bind, seen: dict) -> None:
    if record.klass not in SOURCE_CLASSES:
        raise AssertionError(
            f"basis: unknown source class {record.klass!r} for {record.name!r}")
    if not record.basis.strip():
        raise AssertionError(f"basis: empty basis for {record.name!r}")
    prior = seen.get(record.name)
    if prior is not None and prior != record:
        raise AssertionError(
            f"basis: conflicting registration {record.name!r} — "
            f"{prior.gist} vs {record.gist}")
    seen[record.name] = record


@dataclass
class Registry:
    units: tuple[str, ...]
    entries: dict[str, Declaration] = field(default_factory=dict)
    binds: dict[str, Bind] = field(default_factory=dict)

    def register(self, name: str, value: str | float | int, unit: str,
                 basis: str, klass: str) -> str | float | int:
        if unit not in self.units:
            raise AssertionError(f"basis: unknown unit {unit!r} for {name!r}")
        _admit(Declaration(name, value, unit, basis, klass), self.entries)
        return value

    def bind(self, subsystem: str, port: str, net: str, basis: str,
             klass: str) -> str:
        _admit(Bind(f"{subsystem}.{port}", port, net, basis, klass), self.binds)
        return net
