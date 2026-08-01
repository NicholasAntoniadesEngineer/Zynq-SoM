from __future__ import annotations

from carrier.basis import register
from schgen.core.model import Circuit

R_FP = "Resistor_SMD:R_0603_1608Metric"
C_FP = "Capacitor_SMD:C_0603_1608Metric"
LED_FP = "LED_SMD:LED_0603_1608Metric"

LCSC_100N = "C14663"
LCSC_4K7 = "C23162"
LCSC_100K = "C25803"
LCSC_13K = "C22797"
LCSC_330R = "C23138"
LCSC_RED = "C2286"

SC_I2C = "STM32_I2C2 management bus (bringup_rails / usb_pd / power_mon)"
AUX_BUS = "board_services (the gated peripherals on the isolated AUX bus)"

ISET_R = register("board_aux.iset", "13k", "ohm",
                  "SY6280 current limit ILIM = 6800/13k = 523 mA, over the "
                  "200 mA QWIIC budget. LCSC C22797.",
                  "datasheet")

EN_PULLDOWN = register(
    "board_aux.en_pulldown", "100k", "ohm",
    "Holds EN_AUX low so the gate is OFF at power-up until a human closes SW1 "
    "pos 1 (constraint C1). LCSC C25803.",
    "datasheet")

DECAP = register("board_aux.decap", "100n", "F",
                 "SY6280 and PCA9306 per-pin bypass. LCSC C14663.", "datasheet")

OUT_BULK = register(
    "board_aux.out_bulk", "10u", "F",
    "Hold-up on the gated +3V3_AUX rail for the 200 mA QWIIC load. The SY6280 "
    "datasheet recommends an output cap and only the 100n was fitted (audit "
    "2026-06-19); its soft-start tolerates 10u. 0805 25 V, LCSC C15850.",
    "datasheet")

LED_BALLAST = register("board_aux.led_ballast", "330R", "ohm",
                       "KT-0603R status LED ballast, ~3.9 mA from +3V3_AUX. "
                       "LCSC C23138.", "datasheet")

ISO_EN_PULLUP = register(
    "board_aux.iso_en_pullup", "100k", "ohm",
    "Ties the PCA9306 EN to +3V3_AUX so the switch OPENS whenever the gated "
    "rail is down — that isolation is what stops the powered-down peripherals "
    "back-powering the always-on trunk through their ESD diodes (LAW 0). "
    "LCSC C25803.",
    "datasheet")

AUX_BUS_PULLUP = register(
    "board_aux.bus_pullup", "4k7", "ohm",
    "AUX-side I2C pulls to the gated rail; the PCA9306 requires pulls on BOTH "
    "sides. LCSC C23162.",
    "datasheet")

I2C_SPEED_HZ = register("board_aux.i2c_speed", 400_000, "Hz",
                        "Fast-mode on both sides of the isolator.", "datasheet")

AUX_DRAW_A = register(
    "board_aux.aux_draw", 0.006, "A",
    "This sheet's own +3V3_AUX load: status LED 3.9 mA + the two 4k7 bus "
    "pull-ups. The peripherals declare their own on board_services.",
    "datasheet")


def circuit() -> Circuit:
    c = Circuit("board_aux",
                "Board services: gated +3V3_AUX rail + PCA9306 I2C isolator")

    c.use_part("SY6280AAC", ref="U1")
    c.net("+3V3", "U1.IN")
    c.net("+3V3_AUX", "U1.OUT")
    c.net("GND", "U1.GND")
    c.net("EN_AUX", "U1.EN")
    rset = c.part(c.auto_ref("R"), "Device:R", ISET_R, R_FP, LCSC=LCSC_13K)
    c.net("BS_ISET_AUX", "U1.ISET", f"{rset.ref}.1")
    c.net("GND", f"{rset.ref}.2")
    for cap in c.decouple("U1.IN", DECAP, footprint=C_FP):
        cap.fields["LCSC"] = LCSC_100N
    for cap in c.decouple("U1.OUT", DECAP, footprint=C_FP):
        cap.fields["LCSC"] = LCSC_100N
    cblk = c.part(c.auto_ref("C"), "Device:C", OUT_BULK,
                  "Capacitor_SMD:C_0805_2012Metric", LCSC="C15850")
    c.net("+3V3_AUX", f"{cblk.ref}.1")
    c.net("GND", f"{cblk.ref}.2")

    c.use_part("DSHP04TSGER", ref="SW1")
    c.net("+3V3", "SW1.1", "SW1.3", "SW1.5", "SW1.7")
    c.net("EN_AUX", "SW1.8")
    rpd = c.part(c.auto_ref("R"), "Device:R", EN_PULLDOWN, R_FP, LCSC=LCSC_100K)
    c.net("EN_AUX", f"{rpd.ref}.1")
    c.net("GND", f"{rpd.ref}.2")
    c.nc("SW1.2", "SW1.4", "SW1.6")

    d = c.part(c.auto_ref("D"), "Device:LED", "red", LED_FP, LCSC=LCSC_RED)
    rl = c.part(c.auto_ref("R"), "Device:R", LED_BALLAST, R_FP, LCSC=LCSC_330R)
    c.net("+3V3_AUX", f"{d.ref}.2")
    c.net("BS_PG_AUX", f"{d.ref}.1", f"{rl.ref}.1")
    c.net("GND", f"{rl.ref}.2")

    c.use_part("PCA9306DCUR", ref="U2")
    c.net("GND", "U2.GND")
    c.net("+3V3_SC", "U2.VREF1")
    for cap in c.decouple("U2.VREF1", DECAP, footprint=C_FP):
        cap.fields["LCSC"] = LCSC_100N
    c.port("STM32_I2C2_SCL", "U2.SCL1", kind="i2c", role="scl",
           bus="STM32_I2C2", speed_hz=I2C_SPEED_HZ, expect=SC_I2C)
    c.port("STM32_I2C2_SDA", "U2.SDA1", kind="i2c", role="sda",
           bus="STM32_I2C2", speed_hz=I2C_SPEED_HZ, expect=SC_I2C)
    c.net("+3V3_AUX", "U2.VREF2")
    c.port("AUX_I2C_SCL", "U2.SCL2", kind="i2c", role="scl",
           bus="AUX_I2C", speed_hz=I2C_SPEED_HZ, expect=AUX_BUS)
    c.port("AUX_I2C_SDA", "U2.SDA2", kind="i2c", role="sda",
           bus="AUX_I2C", speed_hz=I2C_SPEED_HZ, expect=AUX_BUS)
    c.net("AUX_ISO_EN", "U2.EN")
    c.pullup("U2.EN", ISO_EN_PULLUP, "+3V3_AUX",
             footprint=R_FP).fields["LCSC"] = LCSC_100K
    c.pullup("U2.SCL2", AUX_BUS_PULLUP, "+3V3_AUX",
             footprint=R_FP).fields["LCSC"] = LCSC_4K7
    c.pullup("U2.SDA2", AUX_BUS_PULLUP, "+3V3_AUX",
             footprint=R_FP).fields["LCSC"] = LCSC_4K7
    for cap in c.decouple("U2.VREF2", DECAP, footprint=C_FP):
        cap.fields["LCSC"] = LCSC_100N

    c.draws("+3V3_AUX", AUX_DRAW_A, "status LED 3.9mA + 2x4k7 AUX-bus pull-ups")
    c.testpoint("+3V3_AUX")
    c.testpoint("AUX_I2C_SCL")
    c.testpoint("AUX_I2C_SDA")
    return c
