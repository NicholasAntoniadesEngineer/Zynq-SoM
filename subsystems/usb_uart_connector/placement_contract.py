"""LIGHTWEIGHT PLACEMENT CONTRACT (D6) — ``usb_uart_connector`` subsystem, data only.

LIGHTWEIGHT TIER (Decision D6, AI_LAYOUT_ROUTING_CONCEPT.md "Contract COVERAGE
AUDIT 2026-07-04"): a USB-C UFP receptacle + ESD for a USB-UART side — a
connector-only protection cell, lightweight (same shape as usb_jtag_connector).
Covers ONLY PORT-ENTRY ESD (the USBLC6 on the USB2 HS data pair at the
receptacle). NO invented electrical requirements, NO composition / ``external``
block. NOT wired into the engine (``_WIRED_SHEETS`` untouched) — authored data
for the red-on-before proof via ``discover_contract`` / ``check_all``.
RED-ON-BEFORE IS EXPECTED (the scattered packer violates it).

Schema + gate: ``subsystems/usb_pd/placement_contract.py`` (proximity + same_side
exemplar) and ``schgen/verify/placement_contract_gate.py``. Refs are LIBRARY
refs (usb_uart_connector.py's J1/U1), carried to board refs by the same per-sheet
band rename the netlist uses.

usb_uart_connector actives (usb_uart_connector.py, netlist-verified):
    J1  TYPE-C-31-M-12  USB-C UFP receptacle (the user-touchable port)
    U1  USBLC6-2SC6     low-cap ESD array on the HS data pair (1<->6 / 3<->4
                        passthrough): connector-side DP/DM on U1.1/U1.3, the
                        protected pair to the bridge on U1.6/U1.4, VBUS clamp ref
                        on U1.5, GND on U1.2.

USB_UART_CONNECTOR IS AN ESD-ONLY CELL. The only active part is the passive
USBLC6 array — no powered IC with a decoupling rail — so this contract has NO
decoupling structure. C1 (10u) is the +VBUS bulk on the receptacle rail, not an
IC per-pin bypass, so it is left to the packer (camera/microsd precedent for
connector-rail decoupling). A strike enters at the USB-C receptacle, so the
USBLC6 is the port-entry protection and belongs tight to J1. same_side keeps the
array on the connector's side (a separate same_side keyed on U1 would find no
members, so it is omitted; camera precedent).

USBLC6 pins: 1/3 = line side, 6/4 = protected, 5 = VBUS ref, 2 = GND.
"""

from __future__ import annotations

CONTRACT: dict = {
    "contract": "placement/lightweight-v0",
    "subsystem": "usb_uart_connector",
    "sheet": "usb_uart_connector",
    "tier": "lightweight",
    "citations": [],
    "roles": {
        "J1": "usbc_receptacle", "U1": "esd_array",
    },
    "structures": [
        # ---- PORT-ENTRY ESD: the USBLC6 HS-pair array near the receptacle ------
        {"type": "proximity", "anchor": "J1",
         "members": ["U1"], "max_mm": 5.0, "same_side": True,
         "basis": "judgment:5.0 — ESD at port entry (lightweight tier)"},
    ],
}
