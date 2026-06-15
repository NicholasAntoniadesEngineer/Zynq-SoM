"""ethernet — HX5008NL 1000BASE-T magnetics + Bob-Smith termination.

The HX5008NL (Pulse, LCSC C962544) is a 24-pad single-port 1:1 gigabit
magnetics module. The pinout below is the FAITHFUL part dossier
(parts/HX5008NLT/, `schgen part add C962544`), verified pad-for-pad against
the Pulse datasheet PS-0118.001-D Rev A, Sheet 2 (the SCHEMATIC page):

      CHIP / PHY side                MEDIA / RJ45 side
      1  TCT1                        24 MCT1
      2  TD1+   3  TD1-              23 MX1+   22 MX1-
      4  TCT2                        21 MCT2
      5  TD2+   6  TD2-              20 MX2+   19 MX2-
      7  TCT3                        18 MCT3
      8  TD3+   9  TD3-              17 MX3+   16 MX3-
      10 TCT4                        15 MCT4
      11 TD4+  12 TD4-              14 MX4+   13 MX4-

Per channel: the CHIP differential pair (TDn+/-) faces the SoM PHY
(RTL8211F via J1 ETH_PHY_MDIx); the MEDIA pair (MXn+/-) faces the RJ45 jack
(ETH_LINE_MDI_x). The datasheet states all channels are IN PHASE input ->
output across the 1:1 winding, so + couples to + (MDIx_P <-> LINE_x_P).

Bob-Smith / IEEE 802.3 §40.7.1 HF termination is on the four MEDIA centre
taps MCT1..MCT4: each 75R || 1n(2kV) -> a shared BS_COMMON trunk, which
bypasses to CHASSIS_GND through one 1n/2kV safety cap (C5). Chassis ground
is a separate net from signal GND (star-bonded elsewhere).

The four CHIP-side centre taps (TCT1..TCT4) are left unconnected on the
carrier: the RTL8211F is a voltage-mode-driver PHY that self-biases its own
transmit common mode, and the SoM exposes only the MDI pairs across J1 (no
CT-bias path crosses the mezzanine). [refcircuit: "no_external_required".]

HISTORY (fixed 2026-06-15): this sheet previously used a hand-built
schgen-local "HX5008NLT" symbol with an INVENTED numbering — PHY pairs on
pins 1-8, line pairs on 19-26, centre taps on 9-12 — that matched neither
the silicon nor the 24-pad footprint. It used pins 25/26 that DO NOT EXIST
on a 24-pad part (the 4th gigabit pair landed on no copper = hard OPEN),
wired the chip MDI pairs onto centre taps, and shorted the media signals
MX4+/MX4- (real pins 14/13) to GND/BS_COMMON. Gigabit was non-functional.
Replaced with the faithful C962544 dossier; the footprint-pad-coverage gate
now blocks any symbol pin that has no pad.

C1..C5 are GENUINE 1 nF / 2 kV X7R parts (IEC 60950/62368 hi-pot), value
drawn "1n" for schematic economy. Pick, LIVE-verified on the JLC parts API
2026-06-12 ("1nF 2kV X7R +/-10% 1206"): C9196, FH/Fenghua 1206B102K202NT,
1206, JLC BASIC, stock 1,369,013. All five caps carry the rating — C5 is
the single BS_COMMON -> CHASSIS_GND element that IS the isolation barrier.
"""

from __future__ import annotations

from schgen.core.model import Circuit

R_FP = "Resistor_SMD:R_0603_1608Metric"
C_FP = "Capacitor_SMD:C_1206_3225Metric"   # 2 kV rating needs the 1206 body
LCSC_1N_2KV = "C9196"   # FH 1206B102K202NT (docstring: live-verified 2 kV)

# Channel -> faithful HX5008NLT dossier pin NUMBERS (= Pulse datasheet):
#   td_p/td_n  CHIP differential pair  -> SoM PHY  ETH_PHY_MDI{ch}
#   mx_p/mx_n  MEDIA differential pair -> RJ45     ETH_LINE_MDI_{ch}
#   mct        MEDIA centre tap        -> Bob-Smith trunk
#   tct        CHIP centre tap         -> NC (PHY self-biases)
#            ch  td_p td_n  mx_p mx_n  mct  tct
CHANNELS = [(0,   2,   3,   23,  22,  24,  1),
            (1,   5,   6,   20,  19,  21,  4),
            (2,   8,   9,   17,  16,  18,  7),
            (3,  11,  12,   14,  13,  15, 10)]


def circuit() -> Circuit:
    c = Circuit("ethernet", "Ethernet: HX5008NL magnetics + Bob-Smith")
    # genuine Pulse HX5008NLT, LCSC C962544 (single-source @ low stock — the
    # HX5008NLTP-CND clone C47575004 is the preflight stock-floor fallback;
    # ALT_LCSC is a hidden field, board-neutral).
    t1 = c.use_part("HX5008NLT", ref="T1")
    t1.fields["ALT_LCSC"] = "C47575004"

    for ch, td_p, td_n, mx_p, mx_n, mct, tct in CHANNELS:
        # CHIP differential pair -> SoM PHY MDI lane
        c.port(f"ETH_PHY_MDI{ch}_P", f"T1.{td_p}")
        c.port(f"ETH_PHY_MDI{ch}_N", f"T1.{td_n}")
        # MEDIA differential pair -> RJ45 line MDI pair
        c.port(f"ETH_LINE_MDI_{ch}_P", f"T1.{mx_p}")
        c.port(f"ETH_LINE_MDI_{ch}_N", f"T1.{mx_n}")
        # CHIP-side centre tap: no external connection on the carrier
        c.nc(f"T1.{tct}")

    # typed ports: every MDI pair is 100R differential (1000BASE-T).
    for n in range(4):
        c.port_type(f"ETH_PHY_MDI{n}_P", kind="diff_pair",
                    pair_with=f"ETH_PHY_MDI{n}_N", impedance=100)
        c.port_type(f"ETH_LINE_MDI_{n}_P", kind="diff_pair",
                    pair_with=f"ETH_LINE_MDI_{n}_N", impedance=100,
                    expect="rj45_connector (wave 2)")

    # Bob-Smith: each MEDIA centre tap -> 75R || 1n(2kV) into BS_COMMON
    # (75R = C4275 Basic; 1n 2kV 1206 = C9196 Basic — provenance in docstring)
    for ch, td_p, td_n, mx_p, mx_n, mct, tct in CHANNELS:
        c.part(f"R{ch + 1}", "Device:R", "75R", R_FP, LCSC="C4275")
        c.part(f"C{ch + 1}", "Device:C", "1n", C_FP, LCSC=LCSC_1N_2KV)
        c.net(f"MCT{ch + 1}", f"T1.{mct}", f"R{ch + 1}.1", f"C{ch + 1}.1")
        c.net("BS_COMMON", f"R{ch + 1}.2", f"C{ch + 1}.2")

    # single shared 1n/2kV from the BS trunk to the chassis island —
    # THE isolation barrier element (same 2 kV part)
    c.part("C5", "Device:C", "1n", C_FP, LCSC=LCSC_1N_2KV)
    c.net("BS_COMMON", "C5.1")
    c.net("CHASSIS_GND", "C5.2")
    return c
