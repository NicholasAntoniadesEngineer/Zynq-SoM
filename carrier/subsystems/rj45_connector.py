"""rj45_connector — plain 8P8C RJ45 jack (NO integrated magnetics).

Wave-2 line-side connector for the ethernet sheet. The carrier already
carries the DISCRETE 1000BASE-T magnetics on the ethernet sheet (Pulse
HX5008NLT) plus the Bob-Smith termination, so THIS jack is a PLAIN
transformerless 8P8C — the line-side MDI pairs come straight off the
magjack's secondary and land on the eight contacts.

Part — KH-5224-8P8C-D (Shenzhen Kinghelm), LCSC C2828085, live-verified on
the JLC parts API 2026-06-13:
  - JLC class Extended (RJ45 jacks have no Basic stock on JLC — every 8P8C
    in the catalogue is Extended; this is the highest-stock plain shielded
    LED jack), stock 239, ~$0.34 @ 1.
  - Confirmed PLAIN (no transformer): the EasyEDA CAD pin table is 13 pins —
    1..8 = the eight T568 contacts, 9/10 = left LED (LED-L+/LED-L-),
    11/12 = right LED (LED-R+/LED-R-), 13 = SHELL. A magjack would expose
    16+ transformer/centre-tap pins; this has none. Through-hole, shielded.

Contact -> MDI mapping is the IEEE 802.3 / TIA-568 1000BASE-T order:
  BI_DA = contacts 1,2  -> ETH_LINE_MDI_0_P/N
  BI_DB = contacts 3,6  -> ETH_LINE_MDI_1_P/N
  BI_DC = contacts 4,5  -> ETH_LINE_MDI_2_P/N
  BI_DD = contacts 7,8  -> ETH_LINE_MDI_3_P/N
These eight nets are the ethernet sheet's deferred LINE_PORTS (verbatim
spellings, read from ethernet.py); declaring them here as PORTs gives the
ethernet side its peer, so its `expect="rj45_connector (wave 2)"` deferrals
resolve to BOUND on both sheets.

LEDs — the two LEDs are INTEGRATED in the jack housing (the symbol pins
LED-L+/LED-L-/LED-R+/LED-R- are the internal LED anodes/cathodes, so NO
external discrete LED part is added — that would be two LEDs in series). The
magnetics block exposes no PHY link/activity logic on this sheet (HX5008NLT
is passive magnetics; the RTL8211F PHY's LED pins live on the SoM side and
the SoM contract does not export them), so each jack LED is driven as a
steady PORT-PRESENT indication off the always-on +3V3 rail through one 330R
(~(3.3-2.0)/330 ~= 4 mA): LED-L+/- and LED-R+/- both lit. Documented
honestly: this is a power-on indicator, NOT a PHY-driven link/act blink.

Shield/shell (pin 13) -> CHASSIS_GND, the chassis island the ethernet sheet's
C5 isolation barrier bonds to (kept separate from signal GND, star-bonded
elsewhere — same idiom as usbc_otg.py's J2.EH).

This sheet also hosts the board's four M3 corner mounting holes (H1..H4), each
a plated, BOM-excluded hole bonded to CHASSIS_GND — co-located with the shield
entry so every CHASSIS_GND fab-art item lives on one sheet (see below).
"""

from __future__ import annotations

from schgen.core.model import Circuit

R_FP = "Resistor_SMD:R_0603_1608Metric"

LCSC_330R = "C23138"   # 0603WAF3300T5E, JLC Basic, stock 1.36M (live 2026-06-13)

# contact pin number -> line-side MDI PORT net. Spellings copied VERBATIM from
# ethernet.py LINE_PORTS — the linker binds by exact name (a typo would be an
# unbound-port ERROR, not a silent open).
MDI_CONTACTS = {
    1: "ETH_LINE_MDI_0_P", 2: "ETH_LINE_MDI_0_N",   # BI_DA
    3: "ETH_LINE_MDI_1_P", 6: "ETH_LINE_MDI_1_N",   # BI_DB
    4: "ETH_LINE_MDI_2_P", 5: "ETH_LINE_MDI_2_N",   # BI_DC
    7: "ETH_LINE_MDI_3_P", 8: "ETH_LINE_MDI_3_N",   # BI_DD
}


def circuit() -> Circuit:
    c = Circuit("rj45_connector", "RJ45 8P8C jack (plain, ext. magnetics)")
    j1 = c.use_part("KH-5224-8P8C-D", ref="J1")

    # eight T568 contacts -> ethernet line-side MDI pairs (the ethernet sheet's
    # deferred LINE_PORTS; same-named PORT here binds them on both sides)
    for pin, net in MDI_CONTACTS.items():
        c.port(net, f"J1.{pin}")
    for n in range(4):
        c.port_type(f"ETH_LINE_MDI_{n}_P", kind="diff_pair",
                    pair_with=f"ETH_LINE_MDI_{n}_N", impedance=100)

    # the jack's two INTEGRATED LEDs as a steady port-present indicator off the
    # always-on +3V3 rail, 330R each (~(3.3-2.0)/330 ~= 4 mA). Drive the
    # housing LED anode (LED-x+) from +3V3 via the series R; cathode (LED-x-)
    # to GND. NO discrete Device:LED — the diode lives inside J1 (see docstring).
    rl = c.part("R1", "Device:R", "330R", R_FP, LCSC=LCSC_330R)
    c.net("+3V3", f"{rl.ref}.1")
    c.net("RJ45_LED_L", f"{rl.ref}.2", "J1.9")          # 330R -> LED-L+ (anode)
    c.net("GND", "J1.10")                               # LED-L- (cathode)
    rr = c.part("R2", "Device:R", "330R", R_FP, LCSC=LCSC_330R)
    c.net("+3V3", f"{rr.ref}.1")
    c.net("RJ45_LED_R", f"{rr.ref}.2", "J1.11")         # 330R -> LED-R+ (anode)
    c.net("GND", "J1.12")                               # LED-R- (cathode)

    # shield/shell -> chassis island (same separate-net idiom as usbc_otg J2.EH)
    c.net("CHASSIS_GND", "J1.13")

    # 4x M3 corner mounting holes -> CHASSIS_GND (ASSEMBLY_NOTES: plated, double
    # as assembly tooling holes). Real netlisted copper (H1..H4, BOM-excluded);
    # placed here, the shield-entry sheet, so all CHASSIS_GND fab-art lives in
    # one place and the chassis bond stays netlist-verifiable. mounting_hole()
    # rejects any non-GROUND net (LAW 0: a hole is a chassis bond, never a rail).
    for _ in range(4):
        c.mounting_hole("CHASSIS_GND")

    # power-tree budget: two 330R/3V3 indicator LEDs (~8 mA total) off +3V3
    c.draws("+3V3", 0.008, "RJ45 housing LEDs (2x 330R port-present indicator)")
    return c
