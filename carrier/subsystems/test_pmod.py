from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

from schgen.core.model import NetClass

NAME = "pmod"
HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
CARRIER = HERE.parents[0]


def _resolve_library_imports() -> None:
    """The test rootdir precedes the repo root on sys.path and shadows `subsystems`."""
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
    a = adapter.circuit()
    b = lib.circuit(adapter.META)
    assert a.name == b.name == NAME
    assert set(a.parts) == set(b.parts)
    assert list(a.nets) == list(b.nets)
    assert {str(p) for p in a.nc_pins} == {str(p) for p in b.nc_pins}


def test_carrier_real_names_present(adapter):
    a = adapter.circuit()
    for real in set(adapter.META["bind"].values()):
        assert real in a.nets, real
    for real in ("+3V3_PMOD", "IO_L2_P_13", "IO_L5P_13", "IO_L9_DQS_P_13",
                 "IO_L10_N_13"):
        assert real in a.nets, real


def test_no_abstract_interface_leak(adapter):
    a = adapter.circuit()
    bind = adapter.META["bind"]
    externals = {n.name for n in a.nets.values()
                 if n.net_class is not NetClass.SIGNAL}
    leaked = {abs_ for abs_ in bind if bind[abs_] != abs_ and abs_ in externals}
    assert not leaked, f"abstract interface leaked through bind: {leaked}"
    assert externals <= set(bind.values()), externals - set(bind.values())
