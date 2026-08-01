"""microsd project bind — circuit + component basis: subsystems/microsd/."""

from __future__ import annotations

from carrier.basis import bind
from schgen.core.model import Circuit
from subsystems.microsd import microsd as _lib

_SUB = "microsd"
_J1_MAP = "som_j1_connector (STM32 GPIO function map)"

_VDD_HOST = bind(
    _SUB, "+VDD_HOST", "+1V8",
    "TXS02612 VCCA host-side reference. The SoM SDIO_* nets run straight to the "
    "Zynq at 1.8 V, so the A-side reference is the carrier +1V8 rail.",
    "datasheet")

_VDD_CARD = bind(
    _SUB, "+VDD_CARD", "+3V3_SD",
    "TXS02612 VCCB(0/1) card side on the bringup-gated +3V3_SD rail (SY6280 "
    "cell 5): slot VDD, both VCCB, every card pull, the bulk and the TPD6E001 "
    "ESD VCC. DEFAULT/HIGH-SPEED SD only — no UHS-I S18 switch (SD-1).",
    "datasheet")

_SD_BUS = {
    port: bind(_SUB, port, net,
               "Port-A SoM SDIO contract net at 1.8 V, verbatim. The card-side "
               "twins stay library-private SD_CARD_* nets — binding a card-side "
               "name here would short the translator.",
               "policy")
    for port, net in (("SD_CLK", "SDIO_CLK"), ("SD_CMD", "SDIO_CMD"),
                      ("SD_D0", "SDIO_D0"), ("SD_D1", "SDIO_D1"),
                      ("SD_D2", "SDIO_D2"), ("SD_D3", "SDIO_D3"))
}

META = {
    "bind": {
        "+VDD_HOST": _VDD_HOST,
        "+VDD_CARD": _VDD_CARD,
        "GND": "GND",
        **_SD_BUS,
        "CD_N": "SD_CARD_DETECT",
    },
    "expects": {
        "CD_N": _J1_MAP,
    },
    "notes": {
        "draws_card": "SD card write burst ~200 mA + pull-ups + "
                      "TXS02612 VCCB",
        "draws_host": "TXS02612 VCCA (SoM-side level)",
    },
}


def circuit() -> Circuit:
    return _lib.circuit(META)
