"""Transitional caller-owned input transport for the native document stages."""
from dataclasses import asdict
from schgen.core import native
from schgen.core.link import all_subsystem_paths, load_subsystem
from schgen.core.project import PROJECT_ROOT, REPO_ROOT
from schgen.generate import bringup_facts as bf
from schgen.verify.powertree import _native_sheets


def sheets():
    return [load_subsystem(p.stem) for p in all_subsystem_paths()]


def sources():
    return native.module().firmware_sources(str(REPO_ROOT), str(PROJECT_ROOT))


def inputs(rows=None, *, need_stm32=True):
    rows = sheets() if rows is None else rows
    pins = bf.stm32_pin_map() if need_stm32 else {"value": "", "nets": {}, "internal": {}}
    raw = {"value": pins["value"]}
    for key in ("nets", "internal"):
        raw[key] = {net: asdict(pin) for net, pin in pins[key].items()}
    return _native_sheets(rows), raw, sources()


def missing(kind):
    return native.module().firmware_docs_missing(_native_sheets(sheets()), kind)
