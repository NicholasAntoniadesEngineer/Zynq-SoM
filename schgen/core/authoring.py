"""Transport-only adapters for native parameterized circuit authoring.

Legacy constructors remain in their original modules for parity verification
and the source-based component-basis audit. They are never runtime fallbacks.
"""
from __future__ import annotations

from pathlib import Path

from schgen.core import native
from schgen.core.model import Circuit, CircuitError
from schgen.core.project import REPO_ROOT
from schgen.core.subsystem import Meta


def _engine():
    engine = native.module()
    # Always select this catalog: another extension client may have opened a
    # different one. Building catalogs belongs to the explicit build boundary.
    if not engine.catalog_open(str(native.catalog_path())):
        raise CircuitError(f"cannot open authoring catalog {native.catalog_path()}")
    return engine


def _call(function, *args):
    try:
        return function(*args)
    except (ValueError, RuntimeError) as exc:
        raise CircuitError(str(exc)) from exc


def meta_payload(meta: Meta | dict | None) -> dict:
    meta = Meta(meta)
    return {"bind": meta.bind_map, "expects": dict(meta.expects),
            "buses": dict(meta._buses), "notes": dict(meta._notes)}


def interface(name: str) -> tuple[str, ...]:
    return tuple(_call(native.module().author_subsystem_interface, name))


def circuit(name: str, meta: Meta | dict | None = None) -> Circuit:
    return Circuit.from_ir(_call(_engine().author_subsystem, name,
                                 meta_payload(meta), str(REPO_ROOT)))


def project_circuit(project: str, name: str, source: str,
                    meta: Meta | dict | None = None) -> Circuit:
    # Resolve against the imported module, not the process-selected project.
    # A detached adapter (for example a gate's temporary copy) need not have a
    # subsystems/ ancestor; its own directory is then its asset root. Never
    # substitute the original project's inputs or a cached circuit snapshot.
    source_path = Path(source).resolve()
    root = next((parent.parent for parent in source_path.parents
                 if parent.name == "subsystems"), source_path.parent)
    payload = None if meta is None else meta_payload(meta)
    return Circuit.from_ir(_call(_engine().author_project_subsystem, project,
                                 name, str(REPO_ROOT), str(root), payload))


def connector_circuit(project: str, jref: str, name: str, title: str,
                      pins: dict[str, str], mapping: dict, policy: dict) -> Circuit:
    return Circuit.from_ir(_call(_engine().author_som_connector, project, jref,
                                 name, title, pins, mapping, policy, str(REPO_ROOT)))
