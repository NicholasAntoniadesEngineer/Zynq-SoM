"""board_aux — the manually-gated +3V3_AUX rail + its I2C isolator.

The INFRASTRUCTURE half of the board-services block (the peripherals it feeds
live on board_services). Kept on its own sheet so neither sheet is dense
enough to defeat the placer's rail-stub router.

POWER GATE (C1: "a manual power enable like the previous").  U1 (SY6280AAC)
gates +3V3 -> +3V3_AUX exactly like the ten bring-up module switches
(ILIM = 6800/13k = 523 mA), but its enable is LOCAL and defaults OFF: SW1
(DSHP04, position 1) closes +3V3 onto EN_AUX and a 100k pulldown holds EN_AUX
low until a human flips the switch. The gate is self-contained here rather
than threaded through the central bringup_en fabric, so the whole block is one
add / one revert and touches none of the dense rail-control sheets.

I2C ISOLATOR (LAW 0).  The board_services peripherals run off the GATED rail
but their bus is the always-on STM32_I2C2 management bus. Tying gated SDA/SCL
straight to that pulled-up bus would back-power the unpowered chips through
their ESD diodes. U2 (PCA9306) bridges the two: side 1 references +3V3_SC (the
always-on bus, pull-ups already on bringup_rails), side 2 references +3V3_AUX
with its own 4k7 pull-ups, and EN is pulled to +3V3_AUX so the switch OPENS
whenever the AUX rail is down — the peripherals are cleanly isolated when off.
The isolated bus AUX_I2C_SCL/SDA is published as a port for board_services.
"""

from __future__ import annotations

from schgen.core.model import Circuit

R_FP = "Resistor_SMD:R_0603_1608Metric"
C_FP = "Capacitor_SMD:C_0603_1608Metric"
LED_FP = "LED_SMD:LED_0603_1608Metric"

LCSC_100N = "C14663"        # 100n X7R 0603
LCSC_4K7 = "C23162"        # 4.7k 1% 0603 (AUX-bus pull-ups)
LCSC_100K = "C25803"       # 100k 1% 0603
LCSC_13K = "C22797"        # 13k 1% 0603 -> SY6280 ILIM 523 mA
LCSC_330R = "C23138"       # 330R 0603 (status LED)
LCSC_RED = "C2286"         # KT-0603R red LED (JLC Basic)

SC_I2C = "STM32_I2C2 management bus (bringup_rails / usb_pd / power_mon)"
AUX_BUS = "board_services (the gated peripherals on the isolated AUX bus)"


def circuit() -> Circuit:
    c = Circuit("board_aux",
                "Board services: gated +3V3_AUX rail + PCA9306 I2C isolator")

    # ===== manual power gate: SY6280 +3V3 -> +3V3_AUX, default-OFF (C1) =====
    c.use_part("SY6280AAC", ref="U1")
    c.net("+3V3", "U1.IN")
    c.net("+3V3_AUX", "U1.OUT")
    c.net("GND", "U1.GND")
    c.net("EN_AUX", "U1.EN")
    rset = c.part(c.auto_ref("R"), "Device:R", "13k", R_FP, LCSC=LCSC_13K)
    c.net("BS_ISET_AUX", "U1.ISET", f"{rset.ref}.1")     # ILIM = 6800/13k
    c.net("GND", f"{rset.ref}.2")
    for cap in c.decouple("U1.IN", "100n", footprint=C_FP):
        cap.fields["LCSC"] = LCSC_100N
    for cap in c.decouple("U1.OUT", "100n", footprint=C_FP):
        cap.fields["LCSC"] = LCSC_100N

    # manual enable: DSHP04 pos 1 closes +3V3 -> EN_AUX; 100k pulldown = OFF
    # at power-up. Positions 2-4 spare (commons bused, even pins NC).
    c.use_part("DSHP04TSGER", ref="SW1")
    c.net("+3V3", "SW1.1", "SW1.3", "SW1.5", "SW1.7")
    c.net("EN_AUX", "SW1.8")
    rpd = c.part(c.auto_ref("R"), "Device:R", "100k", R_FP, LCSC=LCSC_100K)
    c.net("EN_AUX", f"{rpd.ref}.1")
    c.net("GND", f"{rpd.ref}.2")
    c.nc("SW1.2", "SW1.4", "SW1.6")

    # status LED on the gated output (lit = AUX enabled; bring-up at a glance)
    d = c.part(c.auto_ref("D"), "Device:LED", "red", LED_FP, LCSC=LCSC_RED)
    rl = c.part(c.auto_ref("R"), "Device:R", "330R", R_FP, LCSC=LCSC_330R)
    c.net("+3V3_AUX", f"{d.ref}.2")
    c.net("BS_PG_AUX", f"{d.ref}.1", f"{rl.ref}.1")
    c.net("GND", f"{rl.ref}.2")

    # ===== PCA9306 I2C isolator: STM32_I2C2 (always-on) <-> AUX_I2C =========
    c.use_part("PCA9306DCUR", ref="U2")
    c.net("GND", "U2.GND")
    c.net("+3V3_SC", "U2.VREF1")                          # side 1 = SC bus ref
    for cap in c.decouple("U2.VREF1", "100n", footprint=C_FP):
        cap.fields["LCSC"] = LCSC_100N
    c.port("STM32_I2C2_SCL", "U2.SCL1", kind="i2c", role="scl",
           bus="STM32_I2C2", speed_hz=400_000, expect=SC_I2C)
    c.port("STM32_I2C2_SDA", "U2.SDA1", kind="i2c", role="sda",
           bus="STM32_I2C2", speed_hz=400_000, expect=SC_I2C)
    c.net("+3V3_AUX", "U2.VREF2")                         # side 2 = gated ref
    c.port("AUX_I2C_SCL", "U2.SCL2", kind="i2c", role="scl",
           bus="AUX_I2C", speed_hz=400_000, expect=AUX_BUS)
    c.port("AUX_I2C_SDA", "U2.SDA2", kind="i2c", role="sda",
           bus="AUX_I2C", speed_hz=400_000, expect=AUX_BUS)
    # EN -> +3V3_AUX: switch OPENS (isolated) whenever the AUX rail is down
    c.net("AUX_ISO_EN", "U2.EN")
    c.pullup("U2.EN", "100k", "+3V3_AUX", footprint=R_FP).fields["LCSC"] = \
        LCSC_100K
    # local AUX-bus pull-ups to the gated rail (PCA9306 needs pulls both sides)
    c.pullup("U2.SCL2", "4k7", "+3V3_AUX", footprint=R_FP).fields["LCSC"] = \
        LCSC_4K7
    c.pullup("U2.SDA2", "4k7", "+3V3_AUX", footprint=R_FP).fields["LCSC"] = \
        LCSC_4K7
    for cap in c.decouple("U2.VREF2", "100n", footprint=C_FP):
        cap.fields["LCSC"] = LCSC_100N

    # power-tree budget: this sheet's own +3V3_AUX load (status LED + the two
    # 4k7 bus pull-ups); the peripherals declare their own on board_services.
    c.draws("+3V3_AUX", 0.006, "status LED 3.9mA + 2x4k7 AUX-bus pull-ups")
    c.testpoint("+3V3_AUX")                               # the gated rail
    c.testpoint("AUX_I2C_SCL")                            # isolated bus probe
    c.testpoint("AUX_I2C_SDA")
    return c
