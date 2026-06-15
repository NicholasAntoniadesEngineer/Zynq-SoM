"""usb_pd — FUSB302B USB Type-C / Power-Delivery sink-PHY subsystem (LIBRARY).

PROJECT-AGNOSTIC, REUSABLE subsystem. This is the first exemplar of the
``subsystems/<name>/`` library: a self-contained package (netlist + README +
SPICE subckt + local test) that declares its interface as ABSTRACT port + rail
names and knows NOTHING about any consuming board — no carrier net names, no
``carrier/nets.py`` / ``som_interface.json`` reads. A project consumes it by
calling :func:`circuit` with a ``bind`` map ``{abstract_name: project_net}``
that rebinds every externally-visible net to its real board name; standalone
(no bind) it keeps the abstract names so this package's ``test_usb_pd.py`` runs
offline.

Reference circuit per the onsemi FUSB302B datasheet: VDD bypassed 100n + 10u,
VBUS sense bypassed 100n, 200p filter caps on each CC line. VCONN sourcing is
unused by design -> both VCONN pins are explicit author no-connects.

ABSTRACT INTERFACE (see README.md for the full table) — the names a project
binds:

  rails (POWER/GROUND):
    +VDD_LOGIC    FUSB302B VDD logic supply (3.3 V class). MUST be an always-on
                  rail that exists BEFORE PD negotiation — the PHY brings the
                  20 V in, so it cannot depend on a rail it creates.
    +VBUS_SENSE   raw receptacle VBUS for the VBUS-sense pin (U1.2), taken
                  AHEAD of any inlet eFuse so the PHY observes vSafe5V/vbus at
                  the connector for attach detection.
    GND           ground.
  ports (PORT):
    CC1, CC2      Type-C CC lines to the receptacle (FUSB302B owns Rd/Rp, vRd
                  sensing, BMC PHY, VCONN switching). 200p analog filter caps
                  to GND live here.
    I2C_SDA/SCL   the control bus to the system MCU (0x22). Open-drain; bus
                  pull-ups are SHARED and live ONCE on the bus, NOT here.
    INT_N         open-drain interrupt to the MCU (wire-OR shareable). Its
                  pull-up is shared and lives ONCE on the net, NOT here.

DESIGN NOTES (datasheet + bring-up contract): see README.md "Design notes".

Stock symbol Interface_USB:FUSB302BMPX (WQFN-14 + EP): stacked duplicate pins
4 (VDD), 9/15 (GND/EP), 11 (CC1), 14 (CC2) are declared on the same nets as
their visible twins — the netlist gate proves KiCad sees all of them.
"""

from __future__ import annotations

from schgen.core.model import Circuit

# DELIBERATE symbol override (use_part lib_id=): keep the stock stacked-pin
# KiCad drawing + the stock footprint; MPN/LCSC/datasheet come from
# parts/FUSB302BMPX/ and can never drift from the library.
LIB_ID = "Interface_USB:FUSB302BMPX"
FOOTPRINT = "Package_DFN_QFN:WQFN-14-1EP_2.5x2.5mm_P0.5mm_EP1.45x1.45mm"

# ---- the abstract interface (the REUSE contract) ------------------------------
# Externally-visible net names a consuming project binds. RAILS classify as
# POWER/GROUND by name (the '+' prefix + GND), exactly as the bound carrier
# rails do, so a standalone build and a bound build share net classes.
RAILS = ("+VDD_LOGIC", "+VBUS_SENSE", "GND")
PORTS = ("CC1", "CC2", "I2C_SDA", "I2C_SCL", "INT_N")
INTERFACE = RAILS + PORTS

# The control bus this PHY sits on (datasheet I2C, 400 kHz, slave 0x22). The bus
# NAME is a project-level grouping (the linker groups SDA/SCL by it) and may be
# overridden via circuit(i2c_bus=...) so a consuming board can place this PHY on
# one of its named buses; the default is the abstract name for standalone use.
I2C_BUS = "USB_PD_I2C"
I2C_SPEED_HZ = 400_000

# Default power-tree draw note (FUSB302B IDD < 1 mA). A project may override the
# prose via circuit(draws_note=...) to cite its own dossier wording.
DRAWS_NOTE = ("FUSB302B VDD (<1 mA); INT_N/I2C pull-ups are shared and live "
              "off-subsystem")
DRAWS_A = 0.002

# Nominal / worst-case voltage of each abstract RAIL — the subsystem's own
# electrical contract, NOT a board value (a project may run +VDD_LOGIC at any
# 3.3 V-class rail; +VBUS_SENSE rides the live cable VBUS). Used by the local
# test to derate the bypass caps without depending on a board power tree:
#   +VBUS_SENSE worst case = 21.0 V (20 V PD contract + 5% source tolerance);
#   +VDD_LOGIC  = 3.3 V class. The local test asserts every cap is rated for
#   the rail it sits on (FUSB302B abs-max on the VBUS-sense pin is 28 V).
RAIL_WORST_V = {"+VDD_LOGIC": 3.3, "+VBUS_SENSE": 21.0, "GND": 0.0}
VBUS_SENSE_PIN_ABSMAX_V = 28.0   # FUSB302B U1.2 abs-max (datasheet)


def circuit(bind: dict[str, str] | None = None,
            expects: dict[str, str] | None = None,
            i2c_bus: str = I2C_BUS,
            draws_note: str = DRAWS_NOTE) -> Circuit:
    """Build the usb_pd subsystem netlist with ABSTRACT port/rail names.

    ``bind``       ``{abstract_name: project_net}`` rebinds the externally-
                   visible nets (the :data:`INTERFACE` names) to a consuming
                   project's real board names. Omitted -> the abstract names
                   stand (standalone / local test). See :meth:`Circuit.bind`.
    ``expects``    ``{abstract_port: deferral_string}`` attaches an EXPLICIT
                   linker deferral (``PortType.expect``) to a port — a project
                   declares which of its sheets will bind a deferred port.
    ``i2c_bus``    the I2C bus-group NAME for SDA/SCL (a project-level grouping;
                   defaults to the abstract :data:`I2C_BUS`).
    ``draws_note`` the power-tree draw-note prose (a project may cite its own
                   dossier wording; defaults to :data:`DRAWS_NOTE`).

    ``i2c_bus`` / ``draws_note`` exist so a project can reproduce its own
    house-style metadata (bus name, dossier prose) WITHOUT the library knowing
    any board specifics — keeping the library project-agnostic while letting a
    consumer's derived artifacts (constraints CSV, power-tree note) stay stable.
    """
    expects = expects or {}
    c = Circuit("usb_pd", "USB-PD: FUSB302B Type-C controller")
    # LCSC C132291 (from parts/FUSB302BMPX) — live-verified: Extended, stocked.
    c.use_part("FUSB302BMPX", ref="U1", lib_id=LIB_ID, footprint=FOOTPRINT)

    # power — +VDD_LOGIC is an ALWAYS-ON rail that must exist BEFORE PD
    # negotiation (the PHY brings the 20 V in, so it cannot depend on a rail it
    # creates). +VBUS_SENSE is the RAW receptacle VBUS, AHEAD of any inlet
    # eFuse, for attach detection at the connector.
    c.net("+VDD_LOGIC", "U1.3", "U1.4")            # VDD (+ stacked pin 4)
    c.net("+VBUS_SENSE", "U1.2")                   # VBUS sense (raw, pre-eFuse)
    c.net("GND", "U1.8", "U1.9", "U1.15")
    for cap, lcsc in zip(c.decouple("U1.3", "100n", "10u"),  # C1, C2
                         ("C14663", "C15850")):              # both Basic
        cap.fields["LCSC"] = lcsc
    for cap in c.decouple("U1.2", "100n"):         # C3 on +VBUS_SENSE
        cap.fields["LCSC"] = "C14663"

    # Type-C CC lines to the connector (external interface) + 200p filters.
    # (200p = C113796, YAGEO NP0 0603, Extended.)
    cc1 = c.port("CC1", "U1.10", "U1.11", **_expect("CC1", expects))
    cc2 = c.port("CC2", "U1.1", "U1.14", **_expect("CC2", expects))
    for net in (cc1, cc2):
        ref = c.auto_ref("C")
        c.part(ref, "Device:C", "200p", LCSC="C113796")
        c.net(net.name, f"{ref}.1")
        c.net("GND", f"{ref}.2")

    # I2C + interrupt to the host MCU. The PHY is an open-drain slave (0x22):
    # SDA/SCL pull-ups are SHARED on the bus and live ONCE off-subsystem; the
    # INT_N pull-up is likewise shared (open-drain, wire-OR shareable). NONE are
    # placed here (one pull-up per net, house rule).
    c.port("I2C_SDA", "U1.7",
           kind="i2c", role="sda", bus=i2c_bus, speed_hz=I2C_SPEED_HZ,
           **_expect("I2C_SDA", expects))
    c.port("I2C_SCL", "U1.6",
           kind="i2c", role="scl", bus=i2c_bus, speed_hz=I2C_SPEED_HZ,
           **_expect("I2C_SCL", expects))
    c.port("INT_N", "U1.5", **_expect("INT_N", expects))

    # VCONN sourcing unused by design.
    c.nc("U1.12", "U1.13")

    # power-tree budget: FUSB302B IDD < 1 mA (datasheet). No pull-up here -> no
    # extra draw on +VDD_LOGIC.
    c.draws("+VDD_LOGIC", DRAWS_A, draws_note)

    if bind:
        c.bind(bind)
    return c


def _expect(port: str, expects: dict[str, str]) -> dict[str, str]:
    """Forward an optional per-port linker deferral into the port() kwargs."""
    e = expects.get(port)
    return {"expect": e} if e else {}
