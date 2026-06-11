"""som_j3 — SoM mezzanine connector J3, GENERATED from carrier/som_interface.json.

FPGA bank 33/34/35 IO + VCCO rails; every pin bound to its contract net
verbatim (see carrier/som_conn_gen.py). NO hand-typed pinout.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

_GEN_PATH = Path(__file__).resolve().parents[1] / "som_conn_gen.py"
_spec = importlib.util.spec_from_file_location("som_conn_gen", _GEN_PATH)
_gen = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_gen)


def circuit():
    return _gen.connector_circuit(
        "J3", "som_j3", "SoM J3: FPGA bank 33/34/35 IO + VCCO rails")


def placer(c, lib, sp):
    return _gen.connector_placer(c, lib, sp)
