"""user_io — 4 user LEDs (gated rail) + 4 user buttons on PL bank 13.

Per carrier/research/user_io.md: LEDs are active-low sinks — anode on the
bring-up-gated +3V3_USER_LED rail (PLAN stage 2: "enable user LEDs"),
cathode through 1k to the PL pin, so the rail gate kills all four
regardless of fabric state. The "0603 distinct colors all-Basic" ask is
live-verified INFEASIBLE (Basic 0603 = red/white only): red+white Basic,
green+blue Extended, one footprint. Buttons are active-low tacts
(TS-1187A, contacts 1/2 signal, 3/4 GND) with 10k pull-ups to the UNgated
+3V3 (= +VCCO_13 level) so they read correctly whenever PL is alive.

Pin allocation (dossier section 1, chosen so all clock pairs and the plain
pairs L16/L17/L18/L23 stay free; bank-13 ledger after this sheet: 19 free).
NOTE the dossier's board-level flag: lcd(34) + pmod(16) + user_io(8) > 43
bank-13 IOs — the LCD bus must move (proposal: J3 bank 34) before wave-3.
"""

from __future__ import annotations

from schgen.model import Circuit

R0603 = "Resistor_SMD:R_0603_1608Metric"
C0603 = "Capacitor_SMD:C_0603_1608Metric"
LED_FP = "LED_SMD:LED_0603_1608Metric"
TACT = "TS-1187A-B-A-B:TS-1187A-B-A-B"

BRINGUP = "bringup (gated +3V3_USER_LED rail, stage 2)"
J2_MAP = "som_j2_connector"

# (ref, color, LCSC, PL net verbatim from som_interface.json, J2 pin)
LEDS = [
    ("D1", "red", "C2286", "IO_25_13"),       # J2.23, true singleton
    ("D2", "green", "C12624", "IO_L6_P_13"),  # J2.21, mate is VREF pin
    ("D3", "blue", "C2288", "IO_L24_P_13"),   # J2.10, one plain pair spent
    ("D4", "white", "C2290", "IO_L24_N_13"),  # J2.7
]
BUTTONS = [
    ("SW1", "IO_L15_P_13"),                   # J2.9, singleton P-pins:
    ("SW2", "IO_L19_P_13"),                   # J2.12, N halves not on J2,
    ("SW3", "IO_L21_P_13"),                   # J2.13, worthless as pairs
    ("SW4", "IO_L22_P_13"),                   # J2.19
]


def circuit() -> Circuit:
    c = Circuit("user_io", "User IO: 4 LEDs (gated rail) + 4 buttons, bank 13")

    # ---- LEDs: +3V3_USER_LED -> LED -> 1k -> PL pin (active-low sink) ------
    led_anodes: list[str] = []
    for i, (dref, color, lcsc, net) in enumerate(LEDS, start=1):
        rref = f"R{i}"
        c.part(dref, "Device:LED", color, LED_FP, LCSC=lcsc)
        c.part(rref, "Device:R", "1k", R0603, LCSC="C21190")
        c.net(f"USER_LED{i}_K", f"{dref}.1", f"{rref}.1")
        c.port(net, f"{rref}.2", expect=J2_MAP)
        led_anodes.append(f"{dref}.2")

    # +3V3_USER_LED is the bring-up-gated module rail (SY6280 #8 on
    # bringup_modules): a POWER net with its own symbol, like +5V_USB.
    c.part("C1", "Device:C", "100n", C0603, LCSC="C1591")
    c.net("+3V3_USER_LED", *led_anodes, "C1.1")
    c.net("GND", "C1.2")

    # ---- buttons: pin + 10k pull-up to +3V3, contacts close to GND ---------
    for i, (sref, net) in enumerate(BUTTONS, start=5):
        rref = f"R{i}"
        c.part(sref, TACT, "USER", TACT, LCSC="C318884")
        c.part(rref, "Device:R", "10k", R0603, LCSC="C25804")
        c.port(net, f"{sref}.1", f"{sref}.2", f"{rref}.2", expect=J2_MAP)
        c.net("+3V3", f"{rref}.1")
        c.net("GND", f"{sref}.3", f"{sref}.4")
    return c
