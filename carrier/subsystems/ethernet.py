"""ethernet — HX5008NLT 1000BASE-T magnetics + Bob-Smith termination.

The wire-heavy stress test: the PHY-side MDI pairs (SoM PHY) and line-side
MDI pairs (RJ45) are PORT nets; the four line-side centre taps each carry a
75R || 1n/2kV pair down to a single BS_COMMON trunk (IEEE 802.3 Sec 40.7.1),
which bypasses to CHASSIS_GND through one shared 1n/2kV safety cap. Chassis
ground stays a separate net from signal GND (star-bonded elsewhere).

Pin->net intent follows the carrier's hand-audited ethernet block
(zynq_eda/projects/carrier/blocks/ethernet.py + hx5008nlt/refcircuit.py):
pins 1-8 PHY pairs, 19-26 line (TD) pairs, 9-12 line-side centre taps,
13 the magjack's own BS tap, 14 shield/odd-tap GND. The HX5008NLT symbol
is a schgen-local re-pin (shared/symbols/schgen.kicad_sym): centre taps on
the bottom edge so the Bob-Smith ladder drops straight onto a horizontal
trunk — junction dots only where the SAME net taps in (LAW 0).

Internal nets (CT0..CT3, BS_COMMON) are fully DRAWN; each carries one local
net-name label on its wire because kicad-cli's netlist export omits unnamed
nets (the netlist gate could not otherwise see a purely-drawn net). That is
naming, not label-bussing — connectivity is 100% copper.

PHY-side centre taps are not exposed (RTL8211F drives its own common-mode
bias — refcircuit.py "no_external_required"), so per the old block there
are no PHY-side 100n caps on this sheet.

C1..C5 are GENUINE 1 nF / 2 kV X7R parts (IEC 60950/62368 hi-pot), value
drawn "1n" for schematic economy — PLAN round-5 decision, closing the
mechanical-debt flag (the first live-match C1588 was a 50 V 0603 part:
fine electrically at DC, USELESS as a 2 kV barrier). Pick, LIVE-verified
on the JLC parts API 2026-06-12 (the API's own attribute line reads
"1nF 2kV X7R +/-10% 1206"): C9196, FH/Fenghua 1206B102K202NT, 1206,
JLC BASIC, stock 1,369,013, $0.036 @ 1. Alternates (same query): Walsin
1206B102K202 C77494 (21,004, Ext, $0.015), Walsin 1206B102K202CT C303946
(2,517, Ext); 1808 land pattern if creepage is later preferred: FH
1808B102K202NT C81332 (29,722, Ext, $0.113). All five caps carry the
rating — including C5, the single BS_COMMON -> CHASSIS_GND element that
IS the isolation barrier (the round-5 note said "x4", but shipping C5 at
50 V would defeat the other four; flagged honestly here).
"""

from __future__ import annotations

from schgen.core.model import Circuit

LIB_ID = "schgen:HX5008NLT"
FOOTPRINT = "Package_SO:SOIC-24W_7.5x15.4mm_P1.27mm"
R_FP = "Resistor_SMD:R_0603_1608Metric"
C_FP = "Capacitor_SMD:C_1206_3225Metric"   # 2 kV rating needs the 1206 body
LCSC_1N_2KV = "C9196"   # FH 1206B102K202NT (docstring: live-verified 2 kV)

# pin number -> PORT net. PHY side uses the SoM contract spellings VERBATIM
# (carrier/som_interface.json: ETH_PHY_MDI0_P .. ETH_PHY_MDI3_N) — the linker
# binds by exact name; the old ZYNQ_ETH_MDI_0_P spelling was name drift.
# Line side goes to the RJ45 connector subsystem (wave 2).
PHY_PORTS = {
    1: "ETH_PHY_MDI0_P", 2: "ETH_PHY_MDI0_N",
    3: "ETH_PHY_MDI1_P", 4: "ETH_PHY_MDI1_N",
    5: "ETH_PHY_MDI2_P", 6: "ETH_PHY_MDI2_N",
    7: "ETH_PHY_MDI3_P", 8: "ETH_PHY_MDI3_N",
}
LINE_PORTS = {
    19: "ETH_LINE_MDI_0_P", 20: "ETH_LINE_MDI_0_N",
    21: "ETH_LINE_MDI_1_P", 22: "ETH_LINE_MDI_1_N",
    23: "ETH_LINE_MDI_2_P", 24: "ETH_LINE_MDI_2_N",
    25: "ETH_LINE_MDI_3_P", 26: "ETH_LINE_MDI_3_N",
}


def circuit() -> Circuit:
    c = Circuit("ethernet", "Ethernet: HX5008NLT magnetics + Bob-Smith")
    # LCSC C962544 = genuine Pulse HX5008NLT (live-verified 2026-06-11:
    # Extended, stock 10 — LOW; clone fallback HX5008NLTP-CND C47575004,
    # stock 419, same 1:1 350uH single-port footprint class)
    # SRC-1: C962544 is single-source @ stock ~10 (a procurement landmine);
    # the HX5008NLTP-CND clone C47575004 (stock ~419, same 1:1 350uH single-
    # port SOIC-24W class) is now a FIRST-CLASS second source the preflight
    # stock-floor gate falls back to, not just a comment. ALT_LCSC is a hidden
    # field (not a BOM column), so this is board-neutral.
    c.part("T1", LIB_ID, "HX5008NLT", FOOTPRINT,
           LCSC="C962544", ALT_LCSC="C47575004")

    for pin, net in PHY_PORTS.items():
        c.port(net, f"T1.{pin}")
    for pin, net in LINE_PORTS.items():
        c.port(net, f"T1.{pin}")

    # typed ports: every MDI pair is 100R differential (1000BASE-T).
    # PHY side binds to the SoM contract; line side awaits the RJ45 subsystem.
    for n in range(4):
        c.port_type(f"ETH_PHY_MDI{n}_P", kind="diff_pair",
                    pair_with=f"ETH_PHY_MDI{n}_N", impedance=100)
        c.port_type(f"ETH_LINE_MDI_{n}_P", kind="diff_pair",
                    pair_with=f"ETH_LINE_MDI_{n}_N", impedance=100,
                    expect="rj45_connector (wave 2)")

    # Bob-Smith: per line-side centre tap, 75R || 1n(2kV) into BS_COMMON
    # (75R = C4275 Basic stock 833k, live-verified 2026-06-11; 1n 2kV 1206
    # = C9196 Basic stock 1.37M, live-verified 2026-06-12 — round-5 fix,
    # rating provenance in the docstring)
    for n in range(4):
        c.part(f"R{n + 1}", "Device:R", "75R", R_FP, LCSC="C4275")
        c.part(f"C{n + 1}", "Device:C", "1n", C_FP, LCSC=LCSC_1N_2KV)
        c.net(f"CT{n}", f"T1.{9 + n}", f"R{n + 1}.1", f"C{n + 1}.1")
        c.net("BS_COMMON", f"R{n + 1}.2", f"C{n + 1}.2")

    # single shared 1n/2kV from the BS trunk to the chassis island —
    # THE isolation barrier element, same 2 kV part (docstring note);
    # the magjack's own BS tap (pin 13) rides the same trunk
    c.part("C5", "Device:C", "1n", C_FP, LCSC=LCSC_1N_2KV)
    c.net("BS_COMMON", "T1.13", "C5.1")
    c.net("CHASSIS_GND", "C5.2")
    c.net("GND", "T1.14")
    return c
