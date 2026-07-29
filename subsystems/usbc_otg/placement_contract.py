"""LIGHTWEIGHT PLACEMENT CONTRACT (D6) for the ``usbc_otg`` subsystem — data only.

LIGHTWEIGHT TIER (Decision D6, AI_LAYOUT_ROUTING_CONCEPT.md "Phase L"): the six
critical subsystems carry DEEP datasheet-grounded contracts; "the rest get
lightweight contracts" covering ONLY (1) per-pin SUPPLY-RAIL DECOUPLING proximity
and (2) PORT-ENTRY ESD. NO invented electrical requirements, NO composition /
``external`` block (critical-six only). NOT wired into the engine (``_WIRED_SHEETS``
untouched) — authored data for the red-on-before proof via ``discover_contract`` /
``check_all``. RED-ON-BEFORE IS EXPECTED (the scattered packer violates it).

Schema + gate: ``subsystems/usb_pd/placement_contract.py`` (proximity + same_side
exemplar) and ``schgen/verify/placement_contract_gate.py``. Refs are LIBRARY refs
(usbc_otg.py's J2/U1/U2/C...), carried to board refs by the same per-sheet band
rename the netlist uses.

usbc_otg parts (usbc_otg.py, netlist-verified):
    J2  TYPE-C-31-M-12   USB-C receptacle (the user-touchable port)
    U1  TPS2051C         VBUS power switch; OUT=1, GND=2, FLT#=3, EN=4, IN=5
                         (pin nets: 1=USB_VBUS, 3=USBOTG_FLT_N, 4=VBUS_OUT_EN)
    U2  USBLC6-2SC6      D+/D- ESD array at the receptacle

DECOUPLING derived from the netlist:
    C1 (100n)  the TPS2051 input bypass at IN (pin 5) — the only part with U1
               on its +5V_USB rail, unambiguous.
    C2 (22u) + C3 (100u)  the VBUS hot-plug bulk at the port VBUS pad stacks
               (TPS2051C DS 150uF ref).

CENSUS WAVE 2026-07-29 — the port role/strap network graduates from ungated:
    R1/R2 (56k)  CC Rp pull-ups, VBUS -> CC1/CC2 (USB Type-C spec Rp for
               Default USB power, pull-up to 4.75-5.5 V = 56 kohm +-5%; the
               spec numbers the VALUE, not a mm). Each Rp terminates its CC
               pad's stub: CC1 = pad A5, CC2 = pad B5 (dossier footprint).
    R3 (100k)  FLT# pull-up: R3.2 = USBOTG_FLT_N = U1.3 (open-drain flag at
               its pin), R3.1 = +3V3_SC.
    R5 (100k)  EN default-OFF pulldown: R5.1 = VBUS_OUT_EN = U1.4 (the strap
               that holds the port un-powered at power-on), R5.2 = GND.
    R4 (1k)    USB_ID host-role strap (R4.1 = USB_ID -> the SoM PHY, R4.2 =
               GND) — no IC pin on this sheet; grouped with its port so the
               ID net stays inside the port zone.

TPS2051C pins used: OUT=1, FLT#=3, EN=4, IN=5. USBLC6 pins: 1/3 line side,
6/4 protected, 5 = VBUS clamp ref, 2 = GND.
"""

from __future__ import annotations

# TPS2051C pins (authored by NUMBER, footprint-revision-independent).
_U1_IN = "5"
_U1_FLT = "3"
_U1_EN = "4"

CONTRACT: dict = {
    "contract": "placement/lightweight-v0",
    "subsystem": "usbc_otg",
    "sheet": "usbc_otg",
    "tier": "lightweight",
    "citations": ["USB Type-C spec (Rp 56k default-USB, pull-up to VBUS)"],
    "roles": {
        "J2": "usbc_receptacle", "U1": "vbus_switch", "U2": "esd_array",
        "C1": "switch_in_bypass",
        "R1": "cc_rp", "R2": "cc_rp",
        "R3": "flt_pullup", "R5": "en_pulldown", "R4": "id_strap",
    },
    "structures": [
        # ---- DECOUPLING: TPS2051 input bypass at IN (pin 5) --------------------
        {"type": "proximity", "anchor": "U1", "anchor_pins": [_U1_IN],
         "members": ["C1"], "max_mm": 2.0, "same_side": True,
         "basis": "judgment:2.0 — generic per-pin bypass proximity "
                  "(D6 lightweight tier)"},
        # ---- PORT-ENTRY ESD: the USBLC6 D+/D- array near the receptacle --------
        {"type": "proximity", "anchor": "J2",
         "members": ["U2"], "max_mm": 5.0, "same_side": True,
         "basis": "judgment:5.0 — ESD at port entry (lightweight tier)"},
        # ---- SAME SIDE: the switch's input bypass on the switch's side ---------
        {"type": "same_side", "ics": ["U1"],
         "basis": "judgment — bypass co-located with its IC (lightweight tier)"},
        {"type": "proximity", "anchor": "J2", "anchor_pins": ["A4B9", "B4A9"],
         "members": ["C2", "C3"], "max_mm": 8.0,
         "basis": "hot-plug hold-up bulk at the port VBUS (TPS2051C DS 150uF "
                  "ref); measured ~14mm|judgment:8.0"},
        # ---- CC Rp pull-ups, each at ITS OWN CC pad (census wave) --------------
        {"type": "proximity", "anchor": "J2", "anchor_pins": ["A5"],
         "members": ["R1"], "max_mm": 8.0, "same_side": True,
         "basis": "USB Type-C spec Rp=56k default-USB (spec numbers no mm) — "
                  "Rp terminates the CC1 stub at the pad|judgment:8.0"},
        {"type": "proximity", "anchor": "J2", "anchor_pins": ["B5"],
         "members": ["R2"], "max_mm": 8.0, "same_side": True,
         "basis": "USB Type-C spec Rp=56k default-USB (spec numbers no mm) — "
                  "Rp terminates the CC2 stub at the pad|judgment:8.0"},
        # ---- switch straps at their pins: FLT# pull-up + EN pulldown -----------
        {"type": "proximity", "anchor": "U1", "anchor_pins": [_U1_FLT],
         "members": ["R3"], "max_mm": 6.0, "same_side": True,
         "basis": "open-drain FLT# pull-up with its pin|judgment:6.0"},
        {"type": "proximity", "anchor": "U1", "anchor_pins": [_U1_EN],
         "members": ["R5"], "max_mm": 6.0, "same_side": True,
         "basis": "EN default-OFF pulldown with its pin (power-on safety "
                  "strap)|judgment:6.0"},
        # ---- USB_ID role strap grouped with its port ---------------------------
        {"type": "proximity", "anchor": "J2",
         "members": ["R4"], "max_mm": 12.0, "same_side": True,
         "basis": "OTG ID host-role strap kept inside the port zone (no IC pin "
                  "on this sheet)|judgment:12.0"},
    ],
}
