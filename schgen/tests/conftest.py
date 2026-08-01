from __future__ import annotations

import copy
import sys
from pathlib import Path

import pytest

_ROOT = str(Path(__file__).resolve().parents[2])
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


@pytest.fixture(scope="session")
def _pristine_carrier_model():
    from schgen.generate.pcb.placement import build_model
    return build_model()


@pytest.fixture(scope="module")
def carrier_model(_pristine_carrier_model):
    return copy.deepcopy(_pristine_carrier_model)


_EMIT_HEAVY = {"test_bottom_convention", "test_return_stitch_gate",
               "test_connector_descriptors"}


@pytest.hookimpl(tryfirst=True)
def pytest_collection_modifyitems(items):
    # trap: without tryfirst xdist reads groups first and every worker rebuilds
    for item in items:
        if "carrier_model" not in getattr(item, "fixturenames", ()):
            continue
        grp = "a" if item.path.stem in _EMIT_HEAVY else "b"
        item.add_marker(pytest.mark.xdist_group(f"carrier_model_{grp}"))
