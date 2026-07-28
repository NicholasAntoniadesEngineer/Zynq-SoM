"""som_j3 — SoM mezzanine connector J3, GENERATED from devkit_mini/som_interface.json.

FPGA bank 33/34/35 IO + VCCO rails; every pin bound to its contract net
verbatim (see devkit_mini/som_conn_gen.py). NO hand-typed pinout.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

# foldered package layout: this file is devkit_mini/subsystems/som_j3/som_j3.py,
# so the shared generator is two levels up at devkit_mini/som_conn_gen.py.
_GEN_PATH = Path(__file__).resolve().parents[2] / "som_conn_gen.py"
_spec = importlib.util.spec_from_file_location("som_conn_gen", _GEN_PATH)
_gen = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_gen)


def circuit():
    return _gen.connector_circuit(
        "J3", "som_j3", "SoM J3: FPGA bank 33/34/35 IO + VCCO rails")

