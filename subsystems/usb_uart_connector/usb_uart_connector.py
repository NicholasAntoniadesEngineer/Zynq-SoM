"""usb_uart_connector — USB-C UFP (device) receptacle + ESD for a USB-UART side (LIBRARY).

PROJECT-AGNOSTIC, REUSABLE subsystem. A self-contained package (netlist + README
+ SPICE subckt + local test) that declares its interface as ABSTRACT port + rail
names and knows NOTHING about any consuming board — no carrier net names, no
``carrier/nets.py`` / ``som_interface.json`` reads. A project consumes it by
calling :func:`circuit` with the STANDARD ``meta`` dict (see
:mod:`schgen.core.subsystem`): ``bind`` rebinds every externally-visible net to
its real board name, ``expects`` adds per-port linker deferrals, ``notes``
restores house-style prose. Standalone (``meta=None``) it keeps the abstract
names so this package's ``test_usb_uart_connector.py`` runs offline.

Reference circuit: a USB 2.0 device-role (UFP) USB-C receptacle (TYPE-C-31-M-12)
that supplies a downstream USB-UART bridge over a USBLC6-2SC6-protected data
pair. The exposed ports are a peer pair for a bridge's USB side:

  - VBUS    : the receptacle 5 V VBUS (a downstream bridge senses cable-attach
              through its own self-powered divider — so the port carries the
              connector VBUS, with a 10u bulk/bypass per the USB-C UFP spec).
  - USB_DP / USB_DM : the protected USB 2.0 HS data pair (90 ohm diff), behind
              the ESD array, to the bridge's USB data pins.

DEVICE-role (UFP) Type-C — the CC pins carry 5.1k Rd PULLDOWNS to GND (NOT a
host port's 56k Rp): this is what tells a source to apply VBUS. Per CC pin one
Rd; the source's Rp + our Rd form the attach divider. USB 2.0 on a Type-C device
shorts the two flip-orientation contacts of each data line (DP1=DP2, DN1=DN2) so
the cable works either way up. SBU1/SBU2 are unused on a USB2 console -> author
NC. Shell (EH) -> CHASSIS_GND.

ESD — the port mates an EXTERNAL cable, so the data pair runs through a
USBLC6-2SC6 low-capacitance TVL/diode array (1<->6 / 3<->4 passthrough idiom):
connector side DP/DM on U1.1/U1.3, the protected pair (-> the exposed ports) on
U1.6/U1.4, VBUS clamp ref on U1.5, GND on U1.2.

ABSTRACT INTERFACE (see README.md for the full table) — the names a project
binds:

  rails (GROUND):
    GND          ground (receptacle GND pads + ESD/CC/cap returns).
    CHASSIS_GND  receptacle shell / shield bond (chassis earth).
  ports (PORT):
    VBUS         the receptacle 5 V VBUS the port presents to a downstream
                 bridge's VBUS-sense (also the ESD array VBUS clamp ref + 10u
                 bulk). A PORT (not a sourced rail): this is a UFP/device port —
                 it SINKS, it does not source VBUS.
    USB_DP/USB_DM the USB 2.0 HS data pair (90 ohm diff, typed usb_hs_pair),
                 behind the USBLC6-2SC6 ESD array.

DESIGN NOTES (datasheet + role contract): see README.md "Design notes".

Parts — all live-verified on the JLC parts API 2026-06-13 (carrier-standard,
referenced from the global parts/ lib via use_part(), never vendored):
  - TYPE-C-31-M-12  C165948 (Korean Hroparts) — the standard USB-C receptacle.
  - USBLC6-2SC6     C7519 (ST) — the standard USB data ESD array.
  - 5.1k Rd x2      0603WAF5101T5E C23186 (UNI-ROYAL 0603 5%) — JLC BASIC. USB-C
    Rd spec is 5.1k +/-20%, so 5% Basic is correct.
  - 10u bulk        C15850 (0805) — the board-standard bulk cap.
"""

from __future__ import annotations

from schgen.core.model import Circuit
from schgen.core.subsystem import Meta

R0603 = "Resistor_SMD:R_0603_1608Metric"
C0805 = "Capacitor_SMD:C_0805_2012Metric"

LCSC_RD = "C23186"   # 0603WAF5101T5E 5.1k, JLC Basic, stock 4.5M (live 2026-06-13)
LCSC_10U = "C15850"  # 10u 0805, the board-standard bulk cap (used board-wide)

# ---- the abstract interface (the REUSE contract) ------------------------------
# Externally-visible net names a consuming project binds. RAILS classify as
# GROUND by name (GND/CHASSIS_GND), exactly as the bound carrier grounds do, so a
# standalone build and a bound build share net classes. PORTS are declared with
# c.port(...) — VBUS is a PORT (a UFP/device port SINKS VBUS, it does not source
# it), so it is bound to the consumer's real receptacle-VBUS net, not a rail.
RAILS = ("GND", "CHASSIS_GND")
PORTS = ("VBUS", "USB_DP", "USB_DM")
INTERFACE = RAILS + PORTS

# Nominal / worst-case voltage of each abstract net — the subsystem's own
# electrical contract, NOT a board value. Used by the local test to derate the
# bulk/bypass cap without depending on a board power tree: the receptacle VBUS is
# a 5 V USB source (USB 2.0 BC1.2 worst-case ~5.25 V; the 10u on it is 0805 25 V).
RAIL_WORST_V = {"GND": 0.0, "CHASSIS_GND": 0.0, "VBUS": 5.25}


def circuit(meta: "Meta | dict | None" = None) -> Circuit:
    """Build the usb_uart_connector subsystem netlist with ABSTRACT names.

    ``meta`` is the STANDARD subsystem adapter contract (see
    :mod:`schgen.core.subsystem`) — a single dict a consuming project's adapter
    declares. Keys this subsystem reads (all optional; ``meta=None`` ->
    standalone abstract names for the local test):

      ``bind``    ``{abstract_name: project_net}`` rebinds the externally-visible
                  nets (the :data:`INTERFACE` names) to a project's real board
                  names. Applied last (order-preserving => byte-identical sheet).
      ``expects`` ``{abstract_port: deferral}`` attaches an EXPLICIT linker
                  deferral to a port — a project declares which of its sheets
                  will bind a deferred port (e.g. the peer bridge sheet binds
                  VBUS / USB_DP / USB_DM).
    """
    meta = Meta(meta)
    c = Circuit("usb_uart_connector", "USB-C UFP console port -> CP2102N")
    j1 = c.use_part("TYPE-C-31-M-12", ref="J1")
    u1 = c.use_part("USBLC6-2SC6", ref="U1")

    # ---- VBUS: receptacle 5 V (both stacked VBUS pads) -> ESD array VBUS
    # clamp ref + the exposed VBUS-sense port + a 10u bulk/bypass (USB-C UFP
    # VBUS decoupling, Cbus per the spec)
    c.part("C1", "Device:C", "10u", C0805, LCSC=LCSC_10U)
    c.port("VBUS", "J1.VBUS", "U1.5", "C1.1", **meta.expect_kw("VBUS"))  # peer to bridge VBUS sense
    c.net("GND", "C1.2")

    # ---- data pair through the ESD array (1<->6, 3<->4 passthrough), with
    # the Type-C flip pairs shorted for USB 2.0 (works either orientation)
    c.net("USB_UART_DP_CONN", "J1.DP1", "J1.DP2", "U1.1")
    c.net("USB_UART_DM_CONN", "J1.DN1", "J1.DN2", "U1.3")
    c.port("USB_DP", "U1.6", **meta.expect_kw("USB_DP"))        # protected pair -> the bridge ports
    c.port("USB_DM", "U1.4", **meta.expect_kw("USB_DM"))
    # USB 2.0 HS differential pair (90 ohm). Typed with the ABSTRACT complement;
    # Circuit.bind (via meta.finish) rebinds pair_with so the bound pair's two
    # ends agree and the SI gate sees the project pair.
    c.port_type("USB_DP", kind="usb_hs_pair", pair_with="USB_DM")
    c.net("GND", "U1.2")

    # ---- CC: 5.1k Rd pulldowns to GND on BOTH CC pins = USB device/UFP role
    # (a source's Rp + this Rd advertise attach + sink current; NOT the host
    # port's 56k Rp). One Rd per CC pin per the USB Type-C spec.
    for ref, cc in (("R1", "J1.CC1"), ("R2", "J1.CC2")):
        c.part(ref, "Device:R", "5.1k", R0603, LCSC=LCSC_RD)
        c.net(f"USB_UART_{ref}_CC", f"{ref}.1", cc)
        c.net("GND", f"{ref}.2")

    # ---- shield / unused
    c.net("CHASSIS_GND", "J1.EH")        # all four shell pads by NAME
    c.net("GND", "J1.GND")               # both stacked GND pads
    c.nc("J1.SBU1", "J1.SBU2")           # SBU unused on a USB2 console

    # power-tree budget: this is a UFP/device port — it SINKS, it does not
    # source VBUS; the only +3V3/+5V draw on this sheet is none (the Rd's pull
    # the source's CC, a downstream bridge's own divider senses VBUS). No c.draws.
    return meta.finish(c)            # applies meta["bind"] (if any); rebinds the
    #                                  usb_hs_pair complement too (pure rename)
