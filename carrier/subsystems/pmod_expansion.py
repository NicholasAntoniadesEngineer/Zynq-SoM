"""pmod_expansion — one Digilent-standard Pmod (2x6, 2.54 mm, 3.3 V) breakout.

Stream-C C2. A single host-side Pmod port: 8 IO + 2x VCC(3.3 V) + 2x GND on a
right-angle 2x6 socket at the board edge, the 8 IO bound to genuinely-FREE
Zynq PL bank-13 pins, the 3.3 V it provides taken from a MANUALLY-GATED rail so
a powered-down peripheral is never back-fed (constraint C1).

PIN ALLOCATION (verified free vs every existing subsystem + the wave-3
FUNCTION_MAP before claiming — these eight bank-13 pairs read "unclaimed
(wave-3 function map)" in the prior XDC, used by NO other sheet):
  PMODX_IO1/2 = IO_L13_MRCC_P/N_13  (J2.29/27)
  PMODX_IO3/4 = IO_L23_P/N_13       (J2.33/31)
  PMODX_IO5/6 = IO_L14_P/N_SRCC_13  (J2.41/39)
  PMODX_IO7/8 = IO_L12_MRCC_P/N_13  (J2.49/47)
The carrier already SOURCES +VCCO_13 = +3V3 (som_conn_gen VCCO_RAIL_MAP), so
bank 13 runs LVCMOS33 — the Pmod's 3.3 V level-safety is structural, no level
translation needed. The som_j2 connector sheet renames each raw contract net
to the PMODX_IO* function port (som_conn_gen.FUNCTION_MAP), so these ports bind
J2<->this sheet; the XDC constrains each ball automatically. None of L12/L13/
L14 lose their MRCC/SRCC clock capability (Pmod IO is plain GPIO).

POWER GATE (C1: "a manual power enable like the previous"). U1 (SY6280AAC)
gates +3V3 -> +3V3_PMODX exactly like the board_aux / bring-up module switches
(ILIM = 6800/13k = 523 mA vs the Digilent ~100 mA/module budget), but its
enable is LOCAL and defaults OFF: SW1 (DSHP04, position 1) closes +3V3 onto
EN_PMODX and a 100k pulldown holds it low until a human flips the switch. So a
peripheral that is itself unpowered (its own 3V3 down) cannot be back-fed from
this port, AND the port is dark at power-up until deliberately enabled. A
status LED on the gated output shows enable at a glance (board_aux idiom).

ESD PROTECTION (cable-facing). The port mates an EXTERNAL cable/peripheral, so
each of the 8 IO carries a low-capacitance TPD4E1U06 TVS clamp (0.8 pF, C124691)
— a pure GND-referenced shunt from the cable-facing socket net into the array
(LAW-0: the clamp is a shunt, NEVER in series with the signal). Two TPD4E1U06
(4 channels each) cover the 8 IO; the 5.5 V working voltage / IEC 61000-4-2 ±8 kVc
rating references the 3.3 V LVCMOS levels safely, and the 0.8 pF junction is low
enough not to slow the LVCMOS33 edges. The SoM PL pin lands directly on the
socket pad alongside its clamp (the placer's connector+pure-clamp shunt idiom —
same as the HDMI-RX TMDS / camera FFC ESD topology).

OPTIONAL DIGILENT 200R SERIES DAMPING (DNP stuffing option). Some Pmod hosts add
a ~200R series resistor per IO for short-circuit / ringing protection. That is a
DOCUMENTED DNP STUFFING OPTION here (the camera / hdmi_rx DNP-reservation idiom),
NOT populated on rev A: the ESD clamp is the primary protection, the eight bank-13
IO are plain LVCMOS33 GPIO, and a populated 200R inline would be a BOM-line + a
layout-pad change with zero netlist churn. If LP/strobe ringing is observed at
bring-up, stuff an 0603 200R (C8218 Basic) in series between the J2 PL pin and
the socket pad on each IO.

Pmod pin numbering is row-major (Digilent spec): top row 1-6 = IO1-4, GND, VCC;
bottom row 7-12 = IO5-8, GND, VCC. The DS1024-2x6R2 footprint is zigzag-
numbered (odd pads one row, even pads the other), so PAD maps logical Pmod
positions onto connector pads — same convention as the existing pmod.py host
ports.
"""

from __future__ import annotations

from schgen.core.model import Circuit

R0603 = "Resistor_SMD:R_0603_1608Metric"
C0603 = "Capacitor_SMD:C_0603_1608Metric"
C0805 = "Capacitor_SMD:C_0805_2012Metric"
LED_FP = "LED_SMD:LED_0603_1608Metric"

LCSC_100N = "C14663"     # 100n X7R 0603
LCSC_10U = "C15850"     # 10u 0805 bulk
LCSC_13K = "C22797"     # 13k 1% 0603 -> SY6280 ILIM 523 mA
LCSC_100K = "C25803"    # 100k 1% 0603 (EN pulldown + LED net is separate)
LCSC_330R = "C23138"    # 330R 0603 (status LED)
LCSC_RED = "C2286"      # KT-0603R red LED (JLC Basic)

J2_MAP = "som_j2_connector (PL bank 13, +VCCO_13=+3V3, LVCMOS33)"

# Pmod logical position (1-12, row-major per the Digilent spec) -> connector
# pad number (zigzag, columns left-to-right at the mating face).
PAD = {p: 2 * p - 1 for p in range(1, 7)}            # top row 1-6 -> odd pads
PAD.update({p: 2 * (p - 6) for p in range(7, 13)})   # bottom 7-12 -> even pads

# Pmod IO index (1-8) -> logical socket position (1-4 top, 5-8 bottom).
IO_POS = {1: 1, 2: 2, 3: 3, 4: 4, 5: 7, 6: 8, 7: 9, 8: 10}

# the eight FREE bank-13 PL function nets (som_conn_gen.FUNCTION_MAP) feeding
# the eight IO, in socket order. Verified free above.
IO_PORTS = ["PMODX_IO1", "PMODX_IO2", "PMODX_IO3", "PMODX_IO4",
            "PMODX_IO5", "PMODX_IO6", "PMODX_IO7", "PMODX_IO8"]

# TPD4E1U06 channel pins: D1+ (1), D2+ (3), D1- (6), D2- (4) are the 4 IO
# clamps; GND on pin 2, NC on pin 5. IO 1-4 -> U2, IO 5-8 -> U3.
ESD_CH = ["1", "3", "6", "4"]   # the four channels of one TPD4E1U06


def circuit() -> Circuit:
    c = Circuit("pmod_expansion",
                "Pmod expansion port (2x6, bank 13, low-cap ESD, "
                "manual-gated 3V3)")

    # ===== manual power gate: SY6280 +3V3 -> +3V3_PMODX, default-OFF (C1) =====
    c.use_part("SY6280AAC", ref="U1")
    c.net("+3V3", "U1.IN")
    c.net("+3V3_PMODX", "U1.OUT")
    c.net("GND", "U1.GND")
    c.net("EN_PMODX", "U1.EN")
    rset = c.part(c.auto_ref("R"), "Device:R", "13k", R0603, LCSC=LCSC_13K)
    c.net("BS_ISET_PMODX", "U1.ISET", f"{rset.ref}.1")   # ILIM = 6800/13k
    c.net("GND", f"{rset.ref}.2")
    # IN decoupling: 100n HF + a local 10u bulk. The SY6280 datasheet (Pin
    # Description: "IN ... decoupled with a 10uF capacitor to GND"; App Info: "a
    # 10uF ceramic capacitor from VIN to GND is strongly recommended" — without
    # it an output short rings the input, and there is no local input bulk here
    # since the buck's +3V3 bulk sits upstream of the INA shunt) — audit
    # expansion-1.
    for cap in c.decouple("U1.IN", "100n", footprint=C0603):
        cap.fields["LCSC"] = LCSC_100N
    cin = c.part(c.auto_ref("C"), "Device:C", "10u", C0805, LCSC=LCSC_10U)
    c.net("+3V3", f"{cin.ref}.1")
    c.net("GND", f"{cin.ref}.2")
    # OUT: local 100n HF. The datasheet-recommended 10u OUT bulk is already met
    # by cblk on +3V3_PMODX (= U1.OUT, same net) at the Pmod power pins below.
    for cap in c.decouple("U1.OUT", "100n", footprint=C0603):
        cap.fields["LCSC"] = LCSC_100N

    # manual enable: DSHP04 pos 1 closes +3V3 -> EN_PMODX; 100k pulldown = OFF
    # at power-up. Positions 2-4 spare (commons bused, even pins NC).
    c.use_part("DSHP04TSGER", ref="SW1")
    c.net("+3V3", "SW1.1", "SW1.3", "SW1.5", "SW1.7")
    c.net("EN_PMODX", "SW1.8")
    rpd = c.part(c.auto_ref("R"), "Device:R", "100k", R0603, LCSC=LCSC_100K)
    c.net("EN_PMODX", f"{rpd.ref}.1")
    c.net("GND", f"{rpd.ref}.2")
    c.nc("SW1.2", "SW1.4", "SW1.6")

    # status LED on the gated output (lit = Pmod port enabled)
    d = c.part(c.auto_ref("D"), "Device:LED", "red", LED_FP, LCSC=LCSC_RED)
    rl = c.part(c.auto_ref("R"), "Device:R", "330R", R0603, LCSC=LCSC_330R)
    c.net("+3V3_PMODX", f"{d.ref}.2")
    c.net("BS_PG_PMODX", f"{d.ref}.1", f"{rl.ref}.1")
    c.net("GND", f"{rl.ref}.2")

    # ===== the Pmod socket + cable-facing ESD clamp on every IO =============
    c.use_part("DS1024-2x6R2", ref="J1")           # zigzag pads stay numeric
    c.use_part("TPD4E1U06DBVR", ref="U2", value="TPD4E1U06")   # IO 1-4 clamp
    c.use_part("TPD4E1U06DBVR", ref="U3", value="TPD4E1U06")   # IO 5-8 clamp

    for io in range(1, 9):
        som_port = IO_PORTS[io - 1]
        # SoM bank-13 PL pin (port) lands on the socket pad + its ESD clamp
        # channel. The clamp is a GND-referenced shunt (the placer's connector
        # + pure-clamp idiom), NEVER in series with the signal (LAW-0).
        esd_ref = "U2" if io <= 4 else "U3"
        esd_pin = ESD_CH[(io - 1) % 4]
        c.port(som_port, f"J1.{PAD[IO_POS[io]]}", f"{esd_ref}.{esd_pin}",
               expect=J2_MAP)

    # both ESD arrays grounded (pin 2 = GND); pin 5 = NC (4-channel part)
    c.net("GND", "U2.2", "U3.2")
    c.nc("U2.5", "U3.5")

    # ===== Pmod power pins (positions 5/11 = GND, 6/12 = VCC) + bypass =======
    cbyp = c.part(c.auto_ref("C"), "Device:C", "100n", C0603, LCSC=LCSC_100N)
    cblk = c.part(c.auto_ref("C"), "Device:C", "10u", C0805, LCSC=LCSC_10U)
    c.net("+3V3_PMODX", f"J1.{PAD[6]}", f"J1.{PAD[12]}",
          f"{cbyp.ref}.1", f"{cblk.ref}.1")
    c.net("GND", f"J1.{PAD[5]}", f"J1.{PAD[11]}",
          f"{cbyp.ref}.2", f"{cblk.ref}.2")

    # ---- coverage + budget --------------------------------------------------
    c.testpoint("+3V3_PMODX")                       # the gated module rail
    # power-tree budget: one Pmod host port ~100 mA module budget (Digilent
    # Pmod spec) + the status LED (~3.9 mA) on the gated rail.
    c.draws("+3V3_PMODX", 0.104,
            "1x Pmod module budget ~100 mA (Digilent spec) + status LED")
    return c
