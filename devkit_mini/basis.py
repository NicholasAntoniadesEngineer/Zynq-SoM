"""Declared values and bind decisions, each with a registered basis."""

from __future__ import annotations

from dataclasses import dataclass

SOURCE_CLASSES = ("datasheet", "measured", "policy")

LIBRARY_BASIS_HOME = "subsystems/{name}/basis.py"


@dataclass(frozen=True)
class Basis:
    name: str
    value: str | float | int
    unit: str
    basis: str
    klass: str


@dataclass(frozen=True)
class Bind:
    name: str
    port: str
    net: str
    basis: str
    klass: str


REGISTRY: dict[str, Basis] = {}
BINDS: dict[str, Bind] = {}


def _admit(entry, seen: dict) -> None:
    if entry.klass not in SOURCE_CLASSES:
        raise AssertionError(
            f"basis: unknown source class {entry.klass!r} for {entry.name!r}")
    if not entry.basis.strip():
        raise AssertionError(f"basis: empty basis for {entry.name!r}")
    prior = seen.get(entry.name)
    if prior is not None and prior != entry:
        raise AssertionError(f"basis: conflicting registration {entry.name!r}")
    seen[entry.name] = entry


def register(name: str, value: str | float | int, unit: str, basis: str,
             klass: str) -> str | float | int:
    _admit(Basis(name, value, unit, basis, klass), REGISTRY)
    return value


def bind(subsystem: str, port: str, net: str, basis: str, klass: str) -> str:
    _admit(Bind(f"{subsystem}.{port}", port, net, basis, klass), BINDS)
    return net


def value(name: str) -> str | float | int:
    if name not in REGISTRY:
        raise AssertionError(f"basis: {name!r} is not registered")
    return REGISTRY[name].value
