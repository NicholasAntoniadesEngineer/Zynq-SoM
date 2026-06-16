"""som_j1 — SoM mezzanine connector J1, GENERATED from carrier/som_interface.json.

Power/USB/STM32/JTAG/SDIO/ethernet-MDI contract pins; every pin bound to its
contract net verbatim (see carrier/som_conn_gen.py for the layout + rules).
NO hand-typed pinout — regenerate the contract with ``schgen som-interface``
after any SoM change and this sheet follows.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

# foldered package layout: this file is carrier/subsystems/som_j1/som_j1.py,
# so the shared generator is two levels up at carrier/som_conn_gen.py.
_GEN_PATH = Path(__file__).resolve().parents[2] / "som_conn_gen.py"
_spec = importlib.util.spec_from_file_location("som_conn_gen", _GEN_PATH)
_gen = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_gen)


def circuit():
    return _gen.connector_circuit(
        "J1", "som_j1", "SoM J1: power / USB / STM32 / JTAG / SDIO / ETH MDI")

