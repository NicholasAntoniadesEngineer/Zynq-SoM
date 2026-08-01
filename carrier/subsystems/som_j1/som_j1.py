from __future__ import annotations

import importlib.util
from pathlib import Path

_GEN_PATH = Path(__file__).resolve().parents[2] / "som_conn_gen.py"
_spec = importlib.util.spec_from_file_location("som_conn_gen", _GEN_PATH)
_gen = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_gen)


def circuit():
    return _gen.connector_circuit(
        "J1", "som_j1", "SoM J1: power / USB / STM32 / JTAG / SDIO / ETH MDI")
