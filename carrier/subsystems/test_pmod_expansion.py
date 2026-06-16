"""BIND-PARITY guard for the carrier pmod_expansion ADAPTER.

The carrier pmod_expansion subsystem is a THIN ADAPTER: it imports the project-
agnostic library subsystem ``subsystems/pmod_expansion/`` and BINDS its abstract
ports/rails to the carrier's real net names via the standard ``META`` contract.
The library's own electrical correctness is proven by
``subsystems/pmod_expansion/test_pmod_expansion.py``; this co-located test proves
the ONE thing the adapter is responsible for — that the bind is a faithful,
byte-stable rename and nothing else:

  * the adapter's circuit() is EXACTLY ``_lib.circuit(META)`` — same parts, same
    nets in the same insertion order (byte-identical emit), same NCs.
  * every carrier real net the META binds actually appears in the built circuit.
  * NO abstract library interface name leaks through the bind (the contract is
    fully applied — no half-bound externals).

It does NOT re-test the library electricals (SY6280 load-switch / ESD / ratings /
SPICE), which stay in the library package's own test and are aggregated by
``schgen board``. The SPICE subckt now lives ONLY in the library
(``subsystems/pmod_expansion/pmod_expansion.cir``): the carrier ``.cir`` was
de-bloated away together with the adapter folder (the library owns it), so the
old carrier-.cir parse check is gone with the file it tested.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

from schgen.core.model import NetClass

NAME = "pmod_expansion"
HERE = Path(__file__).resolve().parent          # carrier/subsystems/ (flat adapter)
REPO = HERE.parents[1]                            # repo root
CARRIER = HERE.parents[0]                         # carrier/


def _resolve_library_imports() -> None:
    """Make the bare ``subsystems`` package the adapter imports resolve to the
    TOP-LEVEL library (``<repo>/subsystems``), not to ``carrier/subsystems``.

    pytest roots carrier tests at ``carrier/`` (carrier has no ``__init__.py``),
    so ``carrier/`` lands first on sys.path and ``carrier/subsystems/__init__.py``
    gets imported AS the top-level ``subsystems`` package — which would shadow the
    library with the carrier adapter package and break the adapter's
    ``from subsystems.<name> import <name>``. We pin the repo root ahead of it and
    evict ONLY the poisoned ``subsystems`` / ``subsystems.<name>`` library-name
    cache entries that point into ``carrier/`` (never any test module), so the
    adapter import re-resolves to the real library. Pytest-only; the board build
    runs under ``PYTHONPATH=.`` where the repo root already wins, untouched.
    """
    if str(REPO) in sys.path:
        sys.path.remove(str(REPO))
    sys.path.insert(0, str(REPO))
    for mod in ("subsystems", f"subsystems.{NAME}", f"subsystems.{NAME}.{NAME}"):
        m = sys.modules.get(mod)
        if m is None:
            continue
        f = getattr(m, "__file__", "") or ""
        paths = [str(x) for x in (getattr(m, "__path__", []) or [])]
        if str(CARRIER) in f or any(str(CARRIER) in p for p in paths):
            del sys.modules[mod]


def _load(path: Path, modname: str):
    _resolve_library_imports()
    spec = importlib.util.spec_from_file_location(modname, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def adapter():
    return _load(HERE / f"{NAME}.py", f"_carrier_adapter_{NAME}")


@pytest.fixture(scope="module")
def lib():
    return _load(REPO / "subsystems" / NAME / f"{NAME}.py", f"_lib_{NAME}")


def test_adapter_is_thin_bind_of_library(adapter, lib):
    """The adapter circuit equals the library circuit built with the adapter's
    META — identical parts and identical net insertion order (byte-stable emit)."""
    a = adapter.circuit()
    b = lib.circuit(adapter.META)
    assert a.name == b.name == NAME
    assert set(a.parts) == set(b.parts)
    assert list(a.nets) == list(b.nets)
    assert {str(p) for p in a.nc_pins} == {str(p) for p in b.nc_pins}


def test_carrier_real_names_present(adapter):
    """Every carrier real net the META binds to appears in the built circuit
    (the bind landed), including the source + manually-gated rails + Pmod IOs."""
    a = adapter.circuit()
    for real in set(adapter.META["bind"].values()):
        assert real in a.nets, real
    for real in ("+3V3", "+3V3_PMODX", "PMODX_IO1", "PMODX_IO8"):
        assert real in a.nets, real


def test_no_abstract_interface_leak(adapter):
    """No abstract library interface name survives the bind: every externally-
    visible (non-SIGNAL) net is a carrier real net the META produced, never a
    library abstract one the META was supposed to rebind (no PMOD_IO* leaks)."""
    a = adapter.circuit()
    bind = adapter.META["bind"]
    externals = {n.name for n in a.nets.values()
                 if n.net_class is not NetClass.SIGNAL}
    leaked = {abs_ for abs_ in bind if bind[abs_] != abs_ and abs_ in externals}
    assert not leaked, f"abstract interface leaked through bind: {leaked}"
    assert externals <= set(bind.values()), externals - set(bind.values())
