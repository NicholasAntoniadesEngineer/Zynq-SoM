"""LIGHTWEIGHT PLACEMENT CONTRACT (D6) for the ``camera`` subsystem — data only.

LIGHTWEIGHT TIER (Decision D6, AI_LAYOUT_ROUTING_CONCEPT.md "Phase L"): the six
critical subsystems (power, power_som, usb_pd, ethernet, hdmi_rx, motor_sense)
carry DEEP datasheet-grounded contracts; "the rest get lightweight contracts"
covering ONLY the two portable, netlist-derivable electrical truths:

  1. per-pin SUPPLY-RAIL DECOUPLING proximity (every IC bypass cap tight to the
     IC's supply pin, same side), and
  2. PORT-ENTRY ESD (a protection part on connector-adjacent nets kept near its
     connector).

NO invented electrical requirements, NO composition/``external`` block (those
are for the critical-six only). This contract is NOT wired into the engine
(``placement_contract_gate._WIRED_SHEETS`` is untouched); it is authored data,
discoverable via ``discover_contract`` / ``check_all`` for the red-on-before
proof. RED-ON-BEFORE IS EXPECTED: the scattered value-sorted PCB packer does not
satisfy it until a template lands.

Schema + gate: see ``subsystems/usb_pd/placement_contract.py`` (the ``proximity``
+ ``same_side`` exemplar) and ``schgen/verify/placement_contract_gate.py``.
Refs are LIBRARY refs (camera.py's J1/U1/U2/...); the gate carries them to board
refs with the same per-sheet band rename the netlist uses.

CAMERA IS AN ESD-ONLY CELL. The only active parts are the two TI TPD4E02B04DQAR
low-cap ESD arrays (U1 = CSI D0/D1, U2 = CSI CLK + the two spare channels on the
cable-facing I2C control lines) — there is NO powered IC with a decoupling rail,
so this contract has NO decoupling structure. C1 (100n) / C2 (10u) are the gated
+VDD_CAM bypass at the connector, not an IC's per-pin bypass, so they are left to
the packer (lightweight tier = per-IC decoupling only). The ESD arrays clamp the
user-facing FFC lines jack -> host, so they are the port-entry protection.

TPD4E02B04DQAR pin map (USON-10): 1/2/4/5 = IO1..IO4, 3/8 = GND, 6/7/9/10 = NC.
"""

from __future__ import annotations

CONTRACT: dict = {
    "contract": "placement/lightweight-v0",
    "subsystem": "camera",
    "sheet": "camera",
    "tier": "lightweight",
    "citations": [],
    "roles": {
        "J1": "ffc_connector",
        "U1": "esd_array", "U2": "esd_array",
    },
    "structures": [
        # ---- PORT-ENTRY ESD: the two TPD4E02B04 arrays near the FFC (J1) -------
        # Both arrays sit on the user-touchable FFC lines (U1 = CSI D0/D1, U2 =
        # CSI CLK + the spare I2C-control channels); a strike enters at J1, so the
        # clamp belongs at the port entry. Universal per-member (both arrays).
        # (the proximity's own same_side clause keeps the arrays on J1's side —
        # a separate same_side structure would key on U1/U2 as ANCHORS and find
        # no members, so it is omitted; the clause below carries the requirement.)
        {"type": "proximity", "anchor": "J1",
         "members": ["U1", "U2"], "max_mm": 5.0, "same_side": True,
         "basis": "judgment:5.0 — ESD at port entry (lightweight tier)"},
    ],
}
