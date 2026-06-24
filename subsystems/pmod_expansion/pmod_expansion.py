"""pmod_expansion — one Digilent-standard Pmod (2x6, 2.54 mm, 3.3 V) breakout LIBRARY.

PROJECT-AGNOSTIC, REUSABLE subsystem. A self-contained package (netlist + README
+ SPICE subckt + local test) that declares its interface as ABSTRACT port + rail
names and knows NOTHING about any consuming board — no carrier net names, no
``carrier/nets.py`` / ``som_interface.json`` reads. A project consumes it by
calling :func:`circuit` with the STANDARD ``meta`` dict (see
:mod:`schgen.core.subsystem`): ``bind`` rebinds every externally-visible net to
its real board name, ``expects`` adds per-port linker deferrals, ``notes``
restores house-style prose. Standalone (``meta=None``) it keeps the abstract
names so this package's ``test_pmod_expansion.py`` runs offline.

Reference circuit: a single host-side Pmod port — 8 IO + 2x VCC(3.3 V) + 2x GND
on a right-angle 2x6 socket at the board edge — fed by a MANUALLY-GATED 3.3 V
rail so a powered-down peripheral is never back-fed, with a low-capacitance
TPD4E1U06 TVS clamp on every cable-facing IO.

POWER GATE. U1 (SY6280AAC) gates the input rail ``+VDD_PMOD`` -> the switched
rail ``+VSW_PMOD`` (ILIM = 6800/13k = 523 mA vs the Digilent ~100 mA/module
budget). Its enable is LOCAL and defaults OFF: SW1 (DSHP04, position 1) closes
``+VDD_PMOD`` onto the internal ``EN_PMODX`` net and a 100k pulldown holds it low
until a human flips the switch. So a peripheral that is itself unpowered cannot
be back-fed from this port, AND the port is dark at power-up until deliberately
enabled. A status LED on the gated output shows enable at a glance.

ESD PROTECTION (cable-facing). The port mates an EXTERNAL cable/peripheral, so
each of the 8 IO carries a low-capacitance TPD4E1U06 TVS clamp (0.8 pF, C124691)
— a pure GND-referenced shunt from the cable-facing socket net into the array
(LAW-0: the clamp is a shunt, NEVER in series with the signal). Two TPD4E1U06
(4 channels each) cover the 8 IO; the 5.5 V working voltage / IEC 61000-4-2 ±8 kV
rating references the 3.3 V LVCMOS levels safely, and the 0.8 pF junction is low
enough not to slow the LVCMOS33 edges. The host PL pin lands directly on the
socket pad alongside its clamp (the placer's connector+pure-clamp shunt idiom).

OPTIONAL DIGILENT 200R SERIES DAMPING (DNP stuffing option). Some Pmod hosts add
a ~200R series resistor per IO for short-circuit / ringing protection. That is a
DOCUMENTED DNP STUFFING OPTION (NOT populated): the ESD clamp is the primary
protection, the eight IO are plain LVCMOS33 GPIO, and a populated 200R inline
would be a BOM-line + a layout-pad change with zero netlist churn. If LP/strobe
ringing is observed at bring-up, stuff an 0603 200R (C8218 Basic) in series
between the host PL pin and the socket pad on each IO.

Pmod pin numbering is row-major (Digilent spec): top row 1-6 = IO1-4, GND, VCC;
bottom row 7-12 = IO5-8, GND, VCC. The DS1024-2x6R2 footprint is zigzag-
numbered (odd pads one row, even pads the other), so PAD maps logical Pmod
positions onto connector pads.

ABSTRACT INTERFACE (see README.md for the full table) — the names a project
binds:

  rails (POWER/GROUND):
    +VDD_PMOD     the input rail the SY6280 load switch gates (3.3 V class).
    +VSW_PMOD     the SWITCHED / gated output rail this port provides to the
                  Pmod peripheral (= U1.OUT). Dark until the manual enable is
                  flipped — a peripheral cannot be back-fed from this port.
    GND           ground.
  ports (PORT):
    PMOD_IO1..8   the eight Digilent Pmod IO. Plain LVCMOS33 GPIO bound to the
                  host's free GPIO pins; each carries its own GND-referenced
                  TPD4E1U06 ESD clamp at the cable-facing socket.
"""

from __future__ import annotations

from schgen.core.model import Circuit
from schgen.core.subsystem import Meta

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

# ---- the abstract interface (the REUSE contract) ------------------------------
# Externally-visible net names a consuming project binds. RAILS classify as
# POWER/GROUND by name (a leading '+' = POWER; GND = GROUND), exactly as the
# bound carrier rails do, so a standalone build and a bound build share net
# classes. PORTS are declared with c.port(...).
RAILS = ("+VDD_PMOD", "+VSW_PMOD", "GND")
PORTS = ("PMOD_IO1", "PMOD_IO2", "PMOD_IO3", "PMOD_IO4",
         "PMOD_IO5", "PMOD_IO6", "PMOD_IO7", "PMOD_IO8")
INTERFACE = RAILS + PORTS

# Default power-tree draw note. A project may override the prose via
# meta["notes"]["draws_pmod"] to cite its own dossier wording (keeping its
# derived power-tree artifact byte-stable). One Pmod host port ~100 mA module
# budget (Digilent Pmod spec) + the status LED (~3.9 mA) on the gated rail.
DRAWS_PMOD_A = 0.104
DRAWS_PMOD_NOTE = ("1x Pmod module budget ~100 mA (Digilent spec) + status LED")

# Nominal / worst-case voltage of each abstract RAIL — the subsystem's own
# electrical contract, NOT a board value. Used by the local test to derate the
# bypass/bulk caps without depending on a board power tree:
#   +VDD_PMOD / +VSW_PMOD = 3.3 V class (LVCMOS33 Pmod).
RAIL_WORST_V = {"+VDD_PMOD": 3.3, "+VSW_PMOD": 3.3, "GND": 0.0}

# Pmod logical position (1-12, row-major per the Digilent spec) -> connector
# pad number (zigzag, columns left-to-right at the mating face).
PAD = {p: 2 * p - 1 for p in range(1, 7)}            # top row 1-6 -> odd pads
PAD.update({p: 2 * (p - 6) for p in range(7, 13)})   # bottom 7-12 -> even pads

# Pmod IO index (1-8) -> logical socket position (1-4 top, 5-8 bottom).
IO_POS = {1: 1, 2: 2, 3: 3, 4: 4, 5: 7, 6: 8, 7: 9, 8: 10}

# the eight ABSTRACT IO ports feeding the eight socket IO, in socket order.
IO_PORTS = list(PORTS)

# TPD4E1U06 channel pins: D1+ (1), D2+ (3), D1- (6), D2- (4) are the 4 IO
# clamps; GND on pin 2, NC on pin 5. IO 1-4 -> U2, IO 5-8 -> U3.
ESD_CH = ["1", "3", "6", "4"]   # the four channels of one TPD4E1U06


def circuit(meta: "Meta | dict | None" = None) -> Circuit:
    """Build the pmod_expansion subsystem netlist with ABSTRACT port/rail names.

    ``meta`` is the STANDARD subsystem adapter contract (see
    :mod:`schgen.core.subsystem`) — a single dict a consuming project's adapter
    declares. Keys this subsystem reads (all optional; ``meta=None`` ->
    standalone abstract names for the local test):

      ``bind``    ``{abstract_name: project_net}`` rebinds the externally-visible
                  nets (the :data:`INTERFACE` names) to a project's real board
                  names. Applied last (order-preserving => byte-identical sheet).
      ``expects`` ``{abstract_port: deferral}`` attaches an EXPLICIT linker
                  deferral to a port — a project declares which of its sheets
                  will bind a deferred port (e.g. the PMOD_IO* land on a
                  generated SoM connector sheet).
      ``notes``   ``{"draws_pmod": prose}`` the power-tree draw-note prose (a
                  project may cite its own dossier wording; defaults to
                  :data:`DRAWS_PMOD_NOTE`).
    """
    meta = Meta(meta)
    c = Circuit("pmod_expansion",
                "Pmod expansion (2x6, bank 13, ESD, gated 3V3)")

    # ===== manual power gate: SY6280 +VDD_PMOD -> +VSW_PMOD, default-OFF =====
    c.use_part("SY6280AAC", ref="U1")
    c.net("+VDD_PMOD", "U1.IN")
    c.net("+VSW_PMOD", "U1.OUT")
    c.net("GND", "U1.GND")
    c.net("EN_PMODX", "U1.EN")
    rset = c.part(c.auto_ref("R"), "Device:R", "13k", R0603, LCSC=LCSC_13K)
    c.net("BS_ISET_PMODX", "U1.ISET", f"{rset.ref}.1")   # ILIM = 6800/13k
    c.net("GND", f"{rset.ref}.2")
    # IN decoupling: 100n HF + a local 10u bulk. The SY6280 datasheet (Pin
    # Description: "IN ... decoupled with a 10uF capacitor to GND"; App Info: "a
    # 10uF ceramic capacitor from VIN to GND is strongly recommended" — without
    # it an output short rings the input, and there is no local input bulk here
    # since the buck's rail bulk sits upstream of any inlet shunt) — audit
    # expansion-1.
    for cap in c.decouple("U1.IN", "100n", footprint=C0603):
        cap.fields["LCSC"] = LCSC_100N
    cin = c.part(c.auto_ref("C"), "Device:C", "10u", C0805, LCSC=LCSC_10U)
    c.net("+VDD_PMOD", f"{cin.ref}.1")
    c.net("GND", f"{cin.ref}.2")
    # OUT: local 100n HF. The datasheet-recommended 10u OUT bulk is already met
    # by cblk on +VSW_PMOD (= U1.OUT, same net) at the Pmod power pins below.
    for cap in c.decouple("U1.OUT", "100n", footprint=C0603):
        cap.fields["LCSC"] = LCSC_100N

    # manual enable: DSHP04 pos 1 closes +VDD_PMOD -> EN_PMODX; 100k pulldown =
    # OFF at power-up. Positions 2-4 spare (commons bused, even pins NC).
    c.use_part("DSHP04TSGER", ref="SW1")
    c.net("+VDD_PMOD", "SW1.1", "SW1.3", "SW1.5", "SW1.7")
    c.net("EN_PMODX", "SW1.8")
    rpd = c.part(c.auto_ref("R"), "Device:R", "100k", R0603, LCSC=LCSC_100K)
    c.net("EN_PMODX", f"{rpd.ref}.1")
    c.net("GND", f"{rpd.ref}.2")
    c.nc("SW1.2", "SW1.4", "SW1.6")

    # status LED on the gated output (lit = Pmod port enabled)
    d = c.part(c.auto_ref("D"), "Device:LED", "red", LED_FP, LCSC=LCSC_RED)
    rl = c.part(c.auto_ref("R"), "Device:R", "330R", R0603, LCSC=LCSC_330R)
    c.net("+VSW_PMOD", f"{d.ref}.2")
    c.net("BS_PG_PMODX", f"{d.ref}.1", f"{rl.ref}.1")
    c.net("GND", f"{rl.ref}.2")

    # ===== the Pmod socket + cable-facing ESD clamp on every IO =============
    c.use_part("DS1024-2x6R2", ref="J1")           # zigzag pads stay numeric
    c.use_part("TPD4E1U06DBVR", ref="U2", value="TPD4E1U06")   # IO 1-4 clamp
    c.use_part("TPD4E1U06DBVR", ref="U3", value="TPD4E1U06")   # IO 5-8 clamp

    for io in range(1, 9):
        som_port = IO_PORTS[io - 1]
        # host GPIO pin (port) lands on the socket pad + its ESD clamp channel.
        # The clamp is a GND-referenced shunt (the placer's connector +
        # pure-clamp idiom), NEVER in series with the signal (LAW-0).
        esd_ref = "U2" if io <= 4 else "U3"
        esd_pin = ESD_CH[(io - 1) % 4]
        c.port(som_port, f"J1.{PAD[IO_POS[io]]}", f"{esd_ref}.{esd_pin}",
               **meta.expect_kw(som_port))

    # both ESD arrays grounded (pin 2 = GND); pin 5 = NC (4-channel part)
    c.net("GND", "U2.2", "U3.2")
    c.nc("U2.5", "U3.5")

    # ===== Pmod power pins (positions 5/11 = GND, 6/12 = VCC) + bypass =======
    cbyp = c.part(c.auto_ref("C"), "Device:C", "100n", C0603, LCSC=LCSC_100N)
    cblk = c.part(c.auto_ref("C"), "Device:C", "10u", C0805, LCSC=LCSC_10U)
    c.net("+VSW_PMOD", f"J1.{PAD[6]}", f"J1.{PAD[12]}",
          f"{cbyp.ref}.1", f"{cblk.ref}.1")
    c.net("GND", f"J1.{PAD[5]}", f"J1.{PAD[11]}",
          f"{cbyp.ref}.2", f"{cblk.ref}.2")

    # ---- coverage + budget --------------------------------------------------
    c.testpoint("+VSW_PMOD")                        # the gated module rail
    # power-tree budget: one Pmod host port ~100 mA module budget (Digilent
    # Pmod spec) + the status LED (~3.9 mA) on the gated rail.
    c.draws("+VSW_PMOD", DRAWS_PMOD_A,
            meta.note("draws_pmod", DRAWS_PMOD_NOTE))

    return meta.finish(c)            # applies meta["bind"] (if any), returns c
