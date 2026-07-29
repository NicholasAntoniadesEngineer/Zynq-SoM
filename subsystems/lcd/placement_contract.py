"""LIGHTWEIGHT PLACEMENT CONTRACT (D6) for the ``lcd`` subsystem — data only.

LIGHTWEIGHT TIER (Decision D6, AI_LAYOUT_ROUTING_CONCEPT.md "Phase L"): the six
critical subsystems carry DEEP datasheet-grounded contracts; "the rest get
lightweight contracts" covering ONLY (1) per-pin SUPPLY-RAIL DECOUPLING proximity
and (2) PORT-ENTRY ESD. NO invented electrical requirements, NO composition /
``external`` block (critical-six only). NOT wired into the engine (``_WIRED_SHEETS``
untouched) — authored data for the red-on-before proof via ``discover_contract`` /
``check_all``. RED-ON-BEFORE IS EXPECTED (the scattered packer violates it).

Schema + gate: ``subsystems/usb_pd/placement_contract.py`` (proximity + same_side
exemplar) and ``schgen/verify/placement_contract_gate.py``. Refs are LIBRARY refs
(lcd.py's U1/U2/C.../J1), carried to board refs by the same per-sheet band rename
the netlist uses.

lcd actives (lcd.py, netlist-verified):
    U1  SY7201ABC        backlight boost WLED driver; IN = pin 6 (+VBOOST_IN)
    U2  USBLC6-2SC6      touch-I2C ESD array at the FFC (J1)
    L1/D1/C2/R1/R4       boost power train (chained below).

DECOUPLING derived from the netlist: the SY7201 IN pin (pin 6) is bypassed by
C1 (10u bulk) + C5 (1u HF) on +VBOOST_IN (lcd.py: "SY7201 IN decoupling: C1 10u
bulk + a dedicated 1u HF ceramic at the pin"). U2 (USBLC6) has only a clamp-
reference pin (+VDD_TP_CLAMP, pin 5) with no bypass cap of its own -> no
decoupling structure for U2; it is covered by the port-entry ESD structure.

CENSUS WAVE 2026-07-29 — the panel housekeeping graduates from ungated:
    C3 (100n) + C4 (10u)  panel +VDD_LCD bypass/bulk (lcd_backlight.md 3.1
              "10uF + 100n on panel VDD"); the rail enters the panel at FFC
              pad 4 (J1.4 = +VDD_LCD net with C3.1/C4.1) -> both held at the
              FFC power-entry pad, HF tighter than bulk (house family).
    R7 (22R)  pixel-clock source-series damping (lcd.py: "host-side port ->
              22R -> FFC pin 30, resistor at the source/host end"): R7.1 =
              LCD_PCLK_PANEL = J1.30 — the netlist puts the resistor DIRECTLY
              on the FFC pad net, so it is held at pad 30 (short post-R stub
              into the FFC; the ~33 MHz PCLK is the sheet's highest edge
              rate).
    R2/R3 (4k7)  touch-I2C pull-ups on the PROTECTED bus nets (R2.1 =
              LCD_CTP_SDA = U2.6, R3.1 = LCD_CTP_SCL = U2.4) — each held at
              its USBLC6 protected-side pin so the open-drain bus keeps its
              pulls inside the touch cluster.
    R5 (100k) TP_RST hold-down (R5.1 = LCD_CTP_RST = J1.39) at its FFC pad.
    R6 (10k)  LCD_DISP default-ON pull-up (R6.1 = LCD_DISP = J1.31) at its
              FFC pad.

SY7201ABC pins used: 1 LX, 2 GND, 3 FB, 4 EN/PWM, 5 OVP, 6 IN.
USBLC6-2SC6 pins: 1/3 = unprotected I/O, 6/4 = protected I/O, 5 = VBUS clamp
    ref, 2 = GND.
AFC07-S40FCA-00 FFC pads used: 4 = +VDD_LCD, 30 = LCD_PCLK_PANEL, 31 =
    LCD_DISP, 39 = LCD_CTP_RST (dossier footprint, bare-number pads).
"""

from __future__ import annotations

# SY7201 boost input pin (authored by NUMBER, footprint-revision-independent).
_U1_IN = "6"
# FFC pads (bare numbers) + USBLC6 protected-side pins.
_J1_VDD, _J1_PCLK, _J1_DISP, _J1_RST = "4", "30", "31", "39"
_U2_SDA, _U2_SCL = "6", "4"

CONTRACT: dict = {
    "contract": "placement/lightweight-v0",
    "subsystem": "lcd",
    "sheet": "lcd",
    "tier": "lightweight",
    "citations": [],
    "roles": {
        "U1": "boost_ic", "U2": "esd_array", "J1": "ffc_connector",
        "C1": "boost_in_bulk", "C5": "boost_in_hf",
        "L1": "boost_l", "D1": "boost_d", "C2": "vled_cap",
        "R1": "iset_fb", "R4": "en_pulldown",
        "C3": "panel_vdd_hf", "C4": "panel_vdd_bulk",
        "R7": "pclk_series_term",
        "R2": "ctp_sda_pullup", "R3": "ctp_scl_pullup",
        "R5": "ctp_rst_pulldown", "R6": "disp_pullup",
    },
    "structures": [
        # ---- DECOUPLING: SY7201 IN-pin bypass (C1 10u + C5 1u) tight to pin 6 --
        # Generic per-pin bypass proximity: both input caps within 2 mm of the
        # boost IN pin, same side as the driver (short input loop).
        {"type": "proximity", "anchor": "U1", "anchor_pins": [_U1_IN],
         "members": ["C1", "C5"], "max_mm": 2.0, "same_side": True,
         "basis": "judgment:2.0 — generic per-pin bypass proximity "
                  "(D6 lightweight tier)"},
        # ---- PORT-ENTRY ESD: the USBLC6 touch-I2C array near the FFC (J1) ------
        {"type": "proximity", "anchor": "J1",
         "members": ["U2"], "max_mm": 5.0, "same_side": True,
         "basis": "judgment:5.0 — ESD at port entry (lightweight tier)"},
        # ---- BOOST SWITCHING CHAIN: U1.LX -> L1 -> D1 -> C2 -------------------
        # 2026-07-28 audit: the boost loop was TORN (U1-to-L1 37.5mm, input cap
        # to inductor 35.6mm) because L1/D1/C2 carried no structure at all — a
        # switching converter's hot loop left to the leftover band. Chain the
        # loop tight; whole-part anchors (no pin-number guessing on SOT-23-6).
        {"type": "proximity", "anchor": "U1",
         "members": ["L1"], "max_mm": 3.0, "same_side": True,
         "basis": "boost LX hot loop — inductor at the switch pin|judgment:3.0"},
        {"type": "proximity", "anchor": "L1",
         "members": ["D1"], "max_mm": 4.0, "same_side": True,
         "basis": "catch diode on the LX node beside the inductor|judgment:4.0"},
        {"type": "proximity", "anchor": "D1",
         "members": ["C2"], "max_mm": 4.0, "same_side": True,
         "basis": "VLED output cap closes the boost loop|judgment:4.0"},
        {"type": "proximity", "anchor": "U1", "anchor_pins": ["3"],
         "members": ["R1"], "max_mm": 4.0,
         "basis": "ISET/FB current-sense return at the FB pin; rode the far "
                  "half, measured 30mm|judgment:4.0"},
        {"type": "proximity", "anchor": "U1", "anchor_pins": ["4"],
         "members": ["R4"], "max_mm": 8.0,
         "basis": "EN/PWM pull-down with its pin; measured 42.6mm|judgment:8.0"},
        # ---- PANEL VDD: 100n HF + 10u bulk at the FFC power-entry pad ---------
        # lcd_backlight.md 3.1 ("10uF + 100n on panel VDD"); the rail feeds the
        # panel through FFC pad 4, so the pair decouples AT the entry. No mm in
        # the note -> judgment (HF 5.0, bulk 8.0 — house connector-cap family).
        {"type": "proximity", "anchor": "J1", "anchor_pins": [_J1_VDD],
         "members": ["C3"], "max_mm": 5.0, "same_side": True,
         "basis": "lcd_backlight.md 3.1 panel-VDD 100n at the FFC power entry"
                  "|judgment:5.0"},
        {"type": "proximity", "anchor": "J1", "anchor_pins": [_J1_VDD],
         "members": ["C4"], "max_mm": 8.0, "same_side": True,
         "basis": "lcd_backlight.md 3.1 panel-VDD 10u bulk at the FFC power "
                  "entry|judgment:8.0"},
        # ---- PCLK SERIES DAMPING: R7 held at FFC pad 30 -----------------------
        # lcd.py wires R7.1 DIRECTLY to J1.30 (LCD_PCLK_PANEL is a 2-pin net);
        # holding the resistor at the pad keeps the post-R stub into the FFC
        # short so the damped edge (~33 MHz, the sheet's fastest line) launches
        # clean into the flex. No datasheet mm -> judgment 8.0.
        {"type": "proximity", "anchor": "J1", "anchor_pins": [_J1_PCLK],
         "members": ["R7"], "max_mm": 8.0, "same_side": True,
         "basis": "PCLK 22R source-series damping at its FFC pad (lcd.py "
                  "host-end series R; 2-pin LCD_PCLK_PANEL net)|judgment:8.0"},
        # ---- TOUCH-I2C PULL-UPS at the protected-side ESD pins ----------------
        # Open-drain bus pulls kept inside the touch cluster: each at its
        # USBLC6 protected pin (R2 -> U2.6 SDA, R3 -> U2.4 SCL).
        {"type": "proximity", "anchor": "U2", "anchor_pins": [_U2_SDA],
         "members": ["R2"], "max_mm": 8.0, "same_side": True,
         "basis": "CTP SDA 4k7 pull-up with the protected bus node"
                  "|judgment:8.0"},
        {"type": "proximity", "anchor": "U2", "anchor_pins": [_U2_SCL],
         "members": ["R3"], "max_mm": 8.0, "same_side": True,
         "basis": "CTP SCL 4k7 pull-up with the protected bus node"
                  "|judgment:8.0"},
        # ---- TOUCH RST hold-down + DISP default-ON straps at their pads -------
        {"type": "proximity", "anchor": "J1", "anchor_pins": [_J1_RST],
         "members": ["R5"], "max_mm": 8.0, "same_side": True,
         "basis": "TP_RST 100k hold-down at its FFC pad (reset held until the "
                  "host releases)|judgment:8.0"},
        {"type": "proximity", "anchor": "J1", "anchor_pins": [_J1_DISP],
         "members": ["R6"], "max_mm": 8.0, "same_side": True,
         "basis": "LCD_DISP 10k default-ON pull-up at its FFC pad"
                  "|judgment:8.0"},
        # ---- SAME SIDE: the boost's input caps on the driver's side -----------
        {"type": "same_side", "ics": ["U1"],
         "basis": "judgment — bypass co-located with its IC (lightweight tier)"},
    ],
}
