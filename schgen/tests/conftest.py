"""Pytest bootstrap: guarantee the repo root (which contains the ``schgen``
package) is importable no matter the invocation cwd.

The fast unit suite under ``schgen/tests/`` imports the engine as
``import schgen.model`` etc. pytest already inserts the rootdir on sys.path
for this package layout, but pinning it here makes the suite robust when run
from a sub-directory or by an IDE that sets a different rootdir. No engine
code is touched; this only adjusts the import path.
"""

from __future__ import annotations

import copy
import sys
from pathlib import Path

import pytest

_ROOT = str(Path(__file__).resolve().parents[2])   # schgen/tests/ -> repo root
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


@pytest.fixture(scope="session")
def _pristine_carrier_model():
    """One shared ``build_model()`` per process. ``test_build_twice`` proves the
    build is byte-identical run-to-run, so this single build equals what every
    consumer would have built itself; consumers never see this object directly
    (``carrier_model`` hands each module its own deep copy)."""
    from schgen.generate.pcb.placement import build_model
    return build_model()


@pytest.fixture(scope="module")
def carrier_model(_pristine_carrier_model):
    """Per-module deep copy of the shared board model — identical semantics to
    the per-module ``build_model()`` each consumer ran before, at deepcopy cost."""
    return copy.deepcopy(_pristine_carrier_model)


_EMIT_HEAVY = {"test_bottom_convention", "test_return_stitch_gate",
               "test_connector_descriptors"}


@pytest.hookimpl(tryfirst=True)
def pytest_collection_modifyitems(items):
    # traps: unpinned consumers build PER WORKER; sans tryfirst xdist reads groups first
    for item in items:
        if "carrier_model" not in getattr(item, "fixturenames", ()):
            continue
        grp = "a" if item.path.stem in _EMIT_HEAVY else "b"
        item.add_marker(pytest.mark.xdist_group(f"carrier_model_{grp}"))
