"""pmod — 2x Digilent-standard Pmod host ports (DS1024 2x6, LVCMOS33) — LIBRARY.

PROJECT-AGNOSTIC, REUSABLE subsystem (see subsystems/usb_pd/ for the worked
exemplar). Two plain Digilent-standard Pmod HOST ports: each a 2x6 right-angle
FEMALE 2.54 mm socket at the board edge (CONNFLY DS1024-2x6R2, the spec-exact
part; BOOMELE C36191 straight female is the committed stock fallback). Every IO
carries the Digilent-standard 200R series protection resistor between the host
signal and the socket pin AND a low-capacitance TPD4E1U06 (0.8 pF) GND-referenced
ESD shunt clamp on the SoM-side (FPGA-pin) net just inboard of that resistor (two
4-channel arrays per port, shunt to GND -> LAW-0): series-R + shunt-TVS at the
protected pin holds the bank-13 IO at Vclamp. Each port's VCC pins get a 100n +
10u local bypass.
It declares its interface as ABSTRACT port + rail names and knows NOTHING about
any consuming board — no board net names, no som_interface.json reads. A project
consumes it by calling :func:`circuit` with the STANDARD ``meta`` dict (see
:mod:`schgen.core.subsystem`): ``bind`` rebinds every externally-visible net to
its real board name, ``expects`` adds per-port linker deferrals, ``notes``
restores house-style prose. Standalone (``meta=None``) it keeps the abstract
names so this package's ``test_pmod.py`` runs offline.

Pmod pin numbering is row-major per the Digilent spec (top row 1-6, bottom row
7-12; 1-4 = IO1-4, 5 = GND, 6 = VCC, 7-10 = IO5-8, 11 = GND, 12 = VCC) — NOT the
generic 2x6 zigzag. The generated DS1024-2x6R2 footprint IS zigzag-numbered
(odd pads = one row, even pads = the other, vertical column pairs (2k-1, 2k)),
so PAD maps Pmod positions onto connector pads: top-row position p -> pad 2p-1,
bottom-row position p -> pad 2(p-6). Verify odd-row = top row against the
DS1024 datasheet drawing at layout.

ABSTRACT INTERFACE (see README.md for the full table) — the names a project
binds:

  rails (POWER/GROUND):
    +VCC_PMOD     the Pmod-module VCC rail (3.3 V class). Feeds both ports' VCC
                  pins (positions 6/12) with a 100n + 10u local bypass per port.
                  Typically a bring-up-gated module rail (Pmod spec budgets
                  ~100 mA per attached module).
    GND           ground (positions 5/11 of each socket).
  ports (PORT):
    PMOD0_SIG1..8, PMOD1_SIG1..8   the 16 host-side IO signals, one per Pmod IO
                  pin. Each enters through a 200R series resistor (Digilent
                  protection) onto the socket IO pin; the resistor->pin span is a
                  PRIVATE internal SIGNAL net (PMOD{n}_IO{m}) and is never bound.

DESIGN NOTES (datasheet + bring-up contract): see README.md "Design notes".

The DS1024-2x6R2 socket is a faithful zigzag-numbered connector symbol from the
global parts library (use_part keeps the stock drawing + footprint); the 200R
series resistors and bypass caps are inline passives.
"""

from __future__ import annotations

from schgen.core.model import Circuit
from schgen.core.subsystem import Meta

R0603 = "Resistor_SMD:R_0603_1608Metric"
C0603 = "Capacitor_SMD:C_0603_1608Metric"
C0805 = "Capacitor_SMD:C_0805_2012Metric"

# Pmod logical position (1-12, row-major per the Digilent spec) -> connector
# pad number (zigzag, columns left-to-right at the mating face).
PAD = {p: 2 * p - 1 for p in range(1, 7)}        # top row 1-6 -> odd pads
PAD.update({p: 2 * (p - 6) for p in range(7, 13)})  # bottom 7-12 -> even pads

# Pmod IO index (1-8) -> logical position on the socket.
IO_POS = {1: 1, 2: 2, 3: 3, 4: 4, 5: 7, 6: 8, 7: 9, 8: 10}

# TPD4E1U06 (0.8 pF, C124691) channel pins D1+/D2+/D1-/D2- = 1/3/6/4; GND = pin 2,
# NC = pin 5. Two 4-channel arrays clamp the 8 IO of each cable-facing port — the
# same low-cap shunt the peer pmod_expansion port uses (audit 2026-06-19 MEDIUM).
ESD_CH = ["1", "3", "6", "4"]
LCSC_TPD = "C124691"

# The two host ports and their abstract host-signal prefix. Each port has 8 IO
# host signals (PMOD{p}_SIG{io}) that bind to a project's real bank signals.
PORTS_DEF = (("J1", "PMOD0"), ("J2", "PMOD1"))

# ---- the abstract interface (the REUSE contract) ------------------------------
# Externally-visible net names a consuming project binds. RAILS classify as
# POWER/GROUND by name (the '+' prefix + GND); the per-IO host signals classify
# as PORT — exactly as the bound carrier nets do, so a standalone build and a
# bound build share net classes.
RAILS = ("+VCC_PMOD", "GND")
PORTS = tuple(f"{port}_SIG{io}"
              for _jref, port in PORTS_DEF
              for io in range(1, 9))
INTERFACE = RAILS + PORTS

# Default power-tree draw note: 2 host ports x ~100 mA module budget (Digilent
# Pmod spec). A project may override the prose via meta["notes"]["draws"].
DRAWS_NOTE = "2x Pmod module budget ~100 mA each"
DRAWS_A = 0.200

# Nominal voltage of each abstract RAIL — the subsystem's own electrical
# contract, used by the local test to derate the bypass caps without a board
# power tree. +VCC_PMOD is a 3.3 V-class Pmod-module rail.
RAIL_NOM_V = {"+VCC_PMOD": 3.3, "GND": 0.0}


def circuit(meta: "Meta | dict | None" = None) -> Circuit:
    """Build the pmod subsystem netlist with ABSTRACT port/rail names.

    ``meta`` is the STANDARD subsystem adapter contract (see
    :mod:`schgen.core.subsystem`) — a single dict a consuming project's adapter
    declares. Keys this subsystem reads (all optional; ``meta=None`` ->
    standalone abstract names for the local test):

      ``bind``    ``{abstract_name: project_net}`` rebinds the externally-visible
                  nets (the :data:`INTERFACE` names) to a project's real board
                  names. Applied last (order-preserving => byte-identical sheet).
      ``expects`` ``{abstract_port: deferral}`` attaches an EXPLICIT linker
                  deferral to a host-signal port — a project declares which of
                  its sheets binds the deferred bank signals (e.g. a generated
                  SoM-connector sheet).
      ``notes``   ``{"draws": prose}`` the power-tree draw-note prose (a project
                  may cite its own dossier wording; defaults to :data:`DRAWS_NOTE`).
    """
    meta = Meta(meta)
    draws_note = meta.note("draws", DRAWS_NOTE)
    c = Circuit("pmod", "2x Pmod host ports (bank 13, 200R series, gated 3V3)")
    vcc_pins: list[str] = []
    gnd_pins: list[str] = []
    esd_gnd: list[str] = []
    esd_nc: list[str] = []
    rnum = 1
    for pidx, (jref, port) in enumerate(PORTS_DEF):
        c.use_part("DS1024-2x6R2", ref=jref)   # zigzag pads stay numeric
        # low-cap ESD: each cable-facing IO socket net carries a TPD4E1U06 (0.8 pF)
        # GND-referenced SHUNT clamp at the socket (cable side of the 200R), NEVER
        # in series with the signal (LAW-0) — two 4-channel arrays per port.
        esd_lo = f"U{2 * pidx + 1}"            # clamps IO1-4
        esd_hi = f"U{2 * pidx + 2}"            # clamps IO5-8
        c.use_part("TPD4E1U06DBVR", ref=esd_lo, value="TPD4E1U06")
        c.use_part("TPD4E1U06DBVR", ref=esd_hi, value="TPD4E1U06")

        # ---- IOs: host signal (port) -> 200R -> socket pin -----------------
        # The TPD4E1U06 ESD clamp shunts the SoM-side (FPGA-pin) net to GND just
        # inboard of the 200R series resistor: the resistor limits the strike
        # current into the clamp+pin and the clamp holds the bank-13 IO at Vclamp,
        # so the FPGA IO is protected (series-R + shunt-TVS at the protected pin).
        # The clamp rides the BOUND signal net, NOT the socket leg -> each socket
        # leg stays the clean 2-pin float chain the placer expects (a 4-channel
        # array on the socket leg would mesh the float-net lineariser).
        for io in range(1, 9):
            ref = f"R{rnum}"
            rnum += 1
            c.part(ref, "Device:R", "200R", R0603, LCSC="C8218")
            esd_ref = esd_lo if io <= 4 else esd_hi
            c.port(f"{port}_SIG{io}", f"{ref}.1",
                   f"{esd_ref}.{ESD_CH[(io - 1) % 4]}",
                   **meta.expect_kw(f"{port}_SIG{io}"))
            c.net(f"{port}_IO{io}", f"{ref}.2", f"{jref}.{PAD[IO_POS[io]]}")

        # ---- power pins (positions 5/11 = GND, 6/12 = VCC) -----------------
        gnd_pins += [f"{jref}.{PAD[5]}", f"{jref}.{PAD[11]}"]
        vcc_pins += [f"{jref}.{PAD[6]}", f"{jref}.{PAD[12]}"]
        esd_gnd += [f"{esd_lo}.2", f"{esd_hi}.2"]      # array GND (pin 2)
        esd_nc += [f"{esd_lo}.5", f"{esd_hi}.5"]       # array NC (pin 5)

    # module rail: both ports' VCC + 100n/10u per port
    c.part("C1", "Device:C", "100n", C0603, LCSC="C14663")
    c.part("C2", "Device:C", "10u", C0805, LCSC="C15850")
    c.part("C3", "Device:C", "100n", C0603, LCSC="C14663")
    c.part("C4", "Device:C", "10u", C0805, LCSC="C15850")
    # +VCC_PMOD is the Pmod-module rail (a POWER net with its own symbol).
    c.net("+VCC_PMOD", *vcc_pins, "C1.1", "C2.1", "C3.1", "C4.1")
    c.net("GND", *gnd_pins, *esd_gnd, "C1.2", "C2.2", "C3.2", "C4.2")
    c.nc(*esd_nc)

    # power-tree budget: 2 host ports x ~100 mA module budget (Digilent Pmod spec)
    c.draws("+VCC_PMOD", DRAWS_A, draws_note)
    return meta.finish(c)            # applies meta["bind"] (if any), returns c
