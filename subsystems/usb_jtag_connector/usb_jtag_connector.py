"""usb_jtag_connector — USB-C UFP receptacle + ESD for a USB device port (LIBRARY).

PROJECT-AGNOSTIC, REUSABLE subsystem. A self-contained package (netlist + README
+ SPICE subckt + local test) that declares its interface as ABSTRACT port + rail
names and knows NOTHING about any consuming board — no carrier net names, no
``carrier/nets.py`` / ``som_interface.json`` reads. A project consumes it by
calling :func:`circuit` with the STANDARD ``meta`` dict (see
:mod:`schgen.core.subsystem`): ``bind`` rebinds every externally-visible net to
its real board name, ``expects`` adds per-port linker deferrals, ``notes``
restores house-style prose. Standalone (``meta=None``) it keeps the abstract
names so this package's ``test_usb_jtag_connector.py`` runs offline.

Reference circuit: a USB 2.0 device-role (UFP) USB-C receptacle (TYPE-C-31-M-12)
supplies a downstream consumer (e.g. a USB bridge) over a protected data pair +
its own 5 V VBUS. Splitting the receptacle onto its own sheet keeps neither the
connector sheet nor the consumer sheet dense.

DEVICE-role (UFP) Type-C — the CC pins carry 5.1k Rd PULLDOWNS to GND (NOT a
host's 56k Rp): this tells the host to apply VBUS. USB 2.0 on a Type-C device
shorts the two flip-orientation contacts of each data line (DP1=DP2, DN1=DN2) so
the cable works either way up. SBU1/2 unused on a USB2 debug link -> NC. Shell
(EH) -> CHASSIS_GND.

ESD — the port mates an EXTERNAL cable, so the data pair runs through a
USBLC6-2SC6 low-capacitance array (the 1<->6 / 3<->4 pass-through idiom):
connector-side DP/DM on U1.1/U1.3, the protected pair (-> the consumer) on
U1.6/U1.4, VBUS clamp ref on U1.5 (<=5.25 V), GND on U1.2. The USBLC6 is a SHUNT
array, so it adds NO series element on the data lines — only the ~3.5 pF clamp
tap (suits a consumer whose datasheet forbids a SERIES R on the data lines).
LAW-0 honoured.

ABSTRACT INTERFACE (see README.md for the full table) — the names a project
binds:

  rails (POWER/GROUND):
    +VBUS         the receptacle 5 V VBUS (a POWER rail so it merges by NAME onto
                  the consumer's supply input — the consumer is self-powered, so
                  alive only with the cable plugged). The port SINKS this; the
                  5 V is the cable host's own supply (an external source).
    GND           ground.
    CHASSIS_GND   receptacle shell / shield bond (chassis earth).
  ports (PORT):
    USB_DP/USB_DM the USB 2.0 HS data pair to the consumer (90 ohm diff, typed
                  usb_hs_pair), behind the USBLC6-2SC6 ESD array.

DESIGN NOTES (datasheet + role contract): see README.md "Design notes".

AUTHORING V2 reference sheet: actives come from parts/ via use_part() (no inline
lib ids / footprints / LCSC for generated parts) and connect by pin NAME —
"J1.VBUS" nets BOTH stacked VBUS pads, exactly like the symbol.
"""

from __future__ import annotations

from schgen.core.model import Circuit
from schgen.core.subsystem import Meta

R0603 = "Resistor_SMD:R_0603_1608Metric"
C0805 = "Capacitor_SMD:C_0805_2012Metric"

LCSC_RD = "C23186"     # 5.1k Rd, JLC Basic
LCSC_10U = "C15850"    # 10u 0805 bulk

# ---- the abstract interface (the REUSE contract) ------------------------------
# Externally-visible net names a consuming project binds. RAILS classify as
# POWER/GROUND by name (a leading '+' = POWER; GND/CHASSIS_GND = GROUND), exactly
# as the bound carrier rails do, so a standalone build and a bound build share
# net classes. PORTS are declared with c.port(...).
RAILS = ("+VBUS", "GND", "CHASSIS_GND")
PORTS = ("USB_DP", "USB_DM")
INTERFACE = RAILS + PORTS

# The downstream consumer the protected data pair feeds. Default prose for the
# usb_hs_pair linker deferral; a project overrides it via
# meta["expects"]["USB_DP"] to name its own consuming sheet.
CONSUMER = "usb consumer (downstream device)"

# Nominal / worst-case voltage of each abstract RAIL — the subsystem's own
# electrical contract, NOT a board value. Used by the local test to derate the
# VBUS bulk cap without depending on a board power tree:
#   +VBUS = the receptacle 5 V VBUS (USB default 5 V).
RAIL_WORST_V = {"+VBUS": 5.0, "GND": 0.0, "CHASSIS_GND": 0.0}


def circuit(meta: "Meta | dict | None" = None) -> Circuit:
    """Build the usb_jtag_connector subsystem netlist with ABSTRACT names.

    ``meta`` is the STANDARD subsystem adapter contract (see
    :mod:`schgen.core.subsystem`) — a single dict a consuming project's adapter
    declares. Keys this subsystem reads (all optional; ``meta=None`` ->
    standalone abstract names for the local test):

      ``bind``    ``{abstract_name: project_net}`` rebinds the externally-visible
                  nets (the :data:`INTERFACE` names) to a project's real board
                  names. Applied last (order-preserving => byte-identical sheet).
      ``expects`` ``{abstract_port: deferral}`` attaches an EXPLICIT linker
                  deferral to a port — a project declares which of its sheets
                  will bind the deferred USB pair (the downstream consumer).
    """
    meta = Meta(meta)
    c = Circuit("usb_jtag_connector",
                "USB-C UFP debug port -> CH347T (protected)")
    c.use_part("TYPE-C-31-M-12", ref="J1")
    c.use_part("USBLC6-2SC6", ref="U1")

    # ---- VBUS: receptacle 5 V (both stacked pads) -> ESD clamp ref + a 10u
    # bulk; published as +VBUS, the consumer's self-powered island source.
    c.part("C1", "Device:C", "10u", C0805, LCSC=LCSC_10U)
    c.net("+VBUS", "J1.VBUS", "U1.5", "C1.1")    # U1.5 = VBUS clamp ref
    c.net("GND", "C1.2")

    # ---- data pair through the ESD array (1<->6, 3<->4 pass-through), the
    # Type-C flip pairs shorted for USB 2.0 (works either orientation)
    c.net("DBG_USB_DP_CONN", "J1.DP1", "J1.DP2", "U1.1")
    c.net("DBG_USB_DM_CONN", "J1.DN1", "J1.DN2", "U1.3")
    c.port("USB_DP", "U1.6")                      # protected pair -> the consumer
    c.port("USB_DM", "U1.4")
    # USB 2.0 HS differential pair (90 ohm). Typed with the ABSTRACT complement;
    # Circuit.bind (via meta.finish) re-points pair_with so the bound pair's two
    # ends agree and the SI gate sees the project pair. The linker deferral
    # (which consuming sheet binds the pair) is a project concern -> meta expects.
    c.port_type("USB_DP", kind="usb_hs_pair", pair_with="USB_DM",
                expect=meta.expects.get("USB_DP", CONSUMER))
    c.net("GND", "U1.2")

    # ---- CC: 5.1k Rd pulldowns on BOTH CC pins = USB device/UFP role
    for ref, cc in (("R1", "J1.CC1"), ("R2", "J1.CC2")):
        c.part(ref, "Device:R", "5.1k", R0603, LCSC=LCSC_RD)
        c.net(f"DBG_{ref}_CC", f"{ref}.1", cc)
        c.net("GND", f"{ref}.2")

    # ---- shield / unused
    c.net("CHASSIS_GND", "J1.EH")                 # all four shell pads
    c.net("GND", "J1.GND")                        # both stacked GND pads
    c.nc("J1.SBU1", "J1.SBU2")                    # SBU unused on a USB2 link

    # power-tree: a UFP/device port — it SINKS, it does not source VBUS. The
    # 5 V it brings in (+VBUS) is the cable's own supply (an external host
    # source); the consumer's load is declared on the consuming sheet. So this
    # subsystem declares NO draw of its own — only a probe on the VBUS rail.
    c.testpoint("+VBUS")                          # the debug-USB VBUS rail

    return meta.finish(c)            # applies meta["bind"] (if any); rebinds the
    #                                  usb_hs_pair complement + the TP value too
