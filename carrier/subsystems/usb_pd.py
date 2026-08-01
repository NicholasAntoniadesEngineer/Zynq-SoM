"""usb_pd project bind — circuit + component basis: subsystems/usb_pd/."""

from __future__ import annotations

from carrier.basis import bind
from schgen.core.model import Circuit
from subsystems.usb_pd import usb_pd as _lib

_SUB = "usb_pd"
_J1_MAP = "som_j1_connector (wave 3 STM32 GPIO function map)"

_VDD_LOGIC = bind(
    _SUB, "+VDD_LOGIC", "+3V3_SC",
    "FUSB302B VDD/INT ride the always-on SoM system-controller rail, NEVER a "
    "DIP-gated carrier rail: PD negotiation must complete BEFORE any gated rail "
    "exists, since the board boots on default 5 V VBUS (bringup dossier R1).",
    "policy")

_VBUS_SENSE = bind(
    _SUB, "+VBUS_SENSE", "+VBUS_IN",
    "Raw receptacle VBUS AHEAD of the TPS26631 inlet eFuse: attach detection "
    "needs vSafe5V at the connector, not the dVdT-ramped rail behind the eFuse. "
    "AMX-1: U1.2 sits at its 21.0 V recommended max (abs max 28 V) on the legal "
    "20 V+5% contract; +VBUS_IN is bounded only by the pd_input SMBJ22A.",
    "datasheet")

_CC1 = bind(
    _SUB, "CC1", "STM32_USB_CC1",
    "PD-CC-1 firmware contract: the FUSB302B OWNS CC1/CC2 (Rd/Rp, vRd sensing, "
    "BMC PHY, VCONN). SC firmware must hold STM32 PB6/PB4 input-only — enabling "
    "native UCPD double-terminates and garbles BMC framing. The SC talks PD "
    "only over I2C 0x22 + INT_N.",
    "datasheet")
_CC2 = bind(_SUB, "CC2", "STM32_USB_CC2",
            "Twin of CC1 — see the PD-CC-1 contract on usb_pd.CC1.", "datasheet")

_INT_N = bind(
    _SUB, "INT_N", "SC_INT_N",
    "G2 (wave3_function_map 1.1): the FUSB302 INT and the TCA9535 INT# wire-OR "
    "onto ONE shared SC interrupt (STM32_GPIO4 = PA15). ONE pull-up per net — "
    "the bringup_rails 10k is the only one, none here.",
    "policy")

_I2C = {
    port: bind(_SUB, port, net,
               "Shared STM32_I2C2 trunk; the 4k7 pull-ups to +3V3_SC live ONCE "
               "on bringup_rails with the TCA9535, never duplicated here.",
               "policy")
    for port, net in (("I2C_SDA", "STM32_I2C2_SDA"),
                      ("I2C_SCL", "STM32_I2C2_SCL"))
}

META = {
    "bind": {
        "+VDD_LOGIC": _VDD_LOGIC,
        "+VBUS_SENSE": _VBUS_SENSE,
        "GND": "GND",
        "CC1": _CC1,
        "CC2": _CC2,
        **_I2C,
        "INT_N": _INT_N,
    },
    "expects": {
        "I2C_SDA": _J1_MAP,
        "I2C_SCL": _J1_MAP,
        "INT_N": _J1_MAP,
    },
    "buses": {"i2c": "STM32_I2C2"},
    "notes": {"draws": "FUSB302B VDD (<1 mA); SC_INT_N pulled on bringup_rails "
                       "(G2 wire-OR, single 10k)"},
}


def circuit() -> Circuit:
    return _lib.circuit(META)
