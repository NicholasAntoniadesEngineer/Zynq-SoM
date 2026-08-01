"""hdmi_rx project bind — circuit + component basis: subsystems/hdmi_rx/."""

from __future__ import annotations

from carrier.basis import bind
from schgen.core.model import Circuit
from subsystems.hdmi_rx import hdmi_rx as _lib

__all__ = ["circuit", "META"]

_SUB = "hdmi_rx"
_J23_MAP = "som_j2_j3_connector (wave 3 FPGA bank function map)"

_VDD_LOGIC = bind(
    _SUB, "+VDD_LOGIC", "+3V3_HDMI_RX",
    "Gated module rail carrying ONLY the CEC 27k pull-up (~0.12 mA when CEC is "
    "driven low). The EEPROM and the EDID WC# write-protect are cable-5V-fed "
    "(COMP-1), so nothing else draws here.",
    "policy")

_TMDS = {
    f"TMDS_RX_{lane}_{s}": bind(
        _SUB, f"TMDS_RX_{lane}_{s}", f"HDMI_RX_{lane}_{s}",
        "DC-coupled connector -> Zynq HR bank 33; each lane stays ONE net "
        "through the low-cap ESD shunt (HDMIRX-1). The 2x49.9R/pair sink "
        "termination lives at the FPGA-bank end, NOT this sheet — an HR bank "
        "does not self-terminate TMDS_33 (SI-HDMIRX-TERM).",
        "datasheet")
    for lane in ("D2", "D1", "D0", "CLK") for s in ("P", "N")
}

_5V_DET = bind(
    _SUB, "HDMI_5V_DET", "HDMI_RX_5V_DET",
    "Cable-5V presence detect through a 10k/15k divider: 3.15 V at a 5.25 V "
    "cable rail, LVCMOS33-safe into a 3V3 FPGA bank input.",
    "datasheet")

_CEC = bind(_SUB, "CEC", "HDMI_RX_CEC",
            "3V3-domain CEC to the FPGA with the spec 27k pull-up to the gated "
            "module rail.", "datasheet")

META = {
    "bind": {
        "+VDD_LOGIC": _VDD_LOGIC,
        "GND": "GND",
        "CHASSIS_GND": "CHASSIS_GND",
        **_TMDS,
        "HDMI_5V_DET": _5V_DET,
        "CEC": _CEC,
    },
    "expects": {
        "TMDS_RX_D2_P": _J23_MAP,
        "TMDS_RX_D1_P": _J23_MAP,
        "TMDS_RX_D0_P": _J23_MAP,
        "TMDS_RX_CLK_P": _J23_MAP,
        "HDMI_5V_DET": _J23_MAP,
        "CEC": _J23_MAP,
    },
    "notes": {"draws": "CEC 27k pull-up (EEPROM + EDID WC# are cable-5V-fed)"},
}


def circuit() -> Circuit:
    return _lib.circuit(META)
