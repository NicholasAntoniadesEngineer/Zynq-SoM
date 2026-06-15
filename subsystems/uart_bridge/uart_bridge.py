"""uart_bridge — CP2102N USB-to-UART bridge, self-powered at 3.3 V (LIBRARY).

PROJECT-AGNOSTIC, REUSABLE subsystem. A self-contained ``subsystems/<name>/``
package (netlist + README + SPICE subckt + local test) that declares its
interface as ABSTRACT port + rail names and knows NOTHING about any consuming
board — no carrier net names, no ``carrier/nets.py`` / ``som_interface.json``
reads. A project consumes it by calling :func:`circuit` with the STANDARD
``meta`` dict (see :mod:`schgen.core.subsystem`): ``bind`` rebinds every
externally-visible net to its real board name, ``expects`` adds per-port linker
deferrals, ``notes`` restores house-style prose. Standalone (``meta=None``) it
keeps the abstract names so this package's ``test_uart_bridge.py`` runs offline.

Reference circuit per the SiLabs CP2102N datasheet (self-powered config):
VREGIN + VDD + VIO tied directly to the +VDD_IO rail (3.3 V class); decoupling
100n + 10u on VREGIN, 100n on VDD, 100n on VIO; ~RST pulled up 1k to the rail;
VBUS sensed through a 22k1 / 47k5 divider from the UART USB connector's OWN 5 V
VBUS (port USB_VBUS; datasheet self-powered VBUS divider) with the mid-point on
the VBUS pin. D+/D- go to the USB connector (ports USB_DP/USB_DM); the four UART
signals are brought out bridge-relative (UART_TXD/RXD/RTS_N/CTS_N — a project's
crossover to a host UART happens in its bind map). All GPIO / modem-control /
suspend pins are unused by design -> explicit author no-connects.

Symbol: the FAITHFUL generated dossier symbol parts/CP2102N-A02-GQFN24R/
(`schgen part add C969151`) — the "0 hand-built symbols" law. part_gen's box
rules lay the 25 pins out for the placer (power VDD/VBUS on the top edge,
GND/NC on the bottom, the addressable signals split left/right); the QFN
exposed pad lands as pin 25 = the second GND pad of the faithful footprint,
netted to GND below alongside its twin pin 2.

ABSTRACT INTERFACE (see README.md for the full table) — the names a project
binds:

  rails (POWER/GROUND):
    +VDD_IO   CP2102N self-powered logic/IO supply (3.3 V class), tied to
              VREGIN + VDD + VIO. Bypassed 100n+10u (VREGIN), 100n (VDD), 100n
              (VIO); the 1k ~RST pull-up sits here too.
    GND       ground (pin 2 + the QFN exposed pad, pin 25).
  ports (PORT):
    USB_VBUS  the UART USB connector's OWN 5 V VBUS (cable-attach sense). Sensed
              via a 22k1/47k5 divider to GND; NOT a board input rail.
    USB_DP/DM the USB 2.0 HS data pair to the receptacle (90R differential).
    UART_TXD  bridge TXD output  (pin 21).
    UART_RXD  bridge RXD input   (pin 20).
    UART_RTS_N bridge ~RTS output (pin 19, active-low flow control).
    UART_CTS_N bridge ~CTS input  (pin 18, active-low flow control).

DESIGN NOTES (datasheet + bring-up contract): see README.md "Design notes".
"""

from __future__ import annotations

from schgen.core.model import Circuit
from schgen.core.subsystem import Meta

# ---- the abstract interface (the REUSE contract) ------------------------------
# Externally-visible net names a consuming project binds. RAILS classify as
# POWER/GROUND by name (the '+' prefix + GND), exactly as the bound carrier
# rails do, so a standalone build and a bound build share net classes.
RAILS = ("+VDD_IO", "GND")
PORTS = ("USB_VBUS", "USB_DP", "USB_DM",
         "UART_TXD", "UART_RXD", "UART_RTS_N", "UART_CTS_N")
INTERFACE = RAILS + PORTS

# Default house-style metadata a project may override via meta["notes"]:
#   the power-tree draw note (CP2102N active ICC ~14 mA typ, DS table 4.3) and
#   the design-rule reset-waiver reason (open-drain RST, 1k pull-up, internal
#   POR). A consuming project may cite its own dossier wording without the
#   library knowing any board specifics — keeping the library project-agnostic
#   while a consumer's derived artifacts (power-tree note) stay byte-stable.
DRAWS_NOTE = "CP2102N active ~14 mA typ + RST 1k pull-up"
DRAWS_A = 0.015
RESET_WAIVER = "open-drain RST: 1k pull-up only, internal POR; no RC cap"


def circuit(meta: "Meta | dict | None" = None) -> Circuit:
    """Build the uart_bridge subsystem netlist with ABSTRACT port/rail names.

    ``meta`` is the STANDARD subsystem adapter contract (see
    :mod:`schgen.core.subsystem`) — a single dict a consuming project's adapter
    declares. Keys this subsystem reads (all optional; ``meta=None`` ->
    standalone abstract names for the local test):

      ``bind``    ``{abstract_name: project_net}`` rebinds the externally-visible
                  nets (the :data:`INTERFACE` names) to a project's real board
                  names. Applied last (order-preserving => byte-identical sheet).
      ``expects`` ``{abstract_port: deferral}`` attaches an EXPLICIT linker
                  deferral to a port — a project declares which of its sheets
                  will bind a deferred port (the USB ports bind on the project's
                  USB-UART connector sheet; the UART ports on its host-UART map).
      ``notes``   ``{"draws": prose}`` the power-tree draw-note prose (a project
                  may cite its own dossier wording; defaults to :data:`DRAWS_NOTE`).
    """
    meta = Meta(meta)
    draws_note = meta.note("draws", DRAWS_NOTE)
    c = Circuit("uart_bridge", "UART bridge: CP2102N USB-UART")
    # CP2102N-A02-GQFN24R — LCSC C969151, live-verified 2026-06-11:
    # Extended, stock 24,473 (the non-reel -GQFN24 C1550551 is at 0). The
    # FAITHFUL dossier symbol/footprint (parts/CP2102N-A02-GQFN24R/, 25 pins
    # incl the QFN exposed pad as pin 25 = the second GND, 29-pad footprint)
    # is used directly — NO lib_id override (the "0 hand-built symbols" law).
    # The dossier's EasyEDA pin NUMBERS match the SiLabs datasheet 1:1, so the
    # by-number netting below is unchanged (pin 2 + EP pin 25 = GND).
    c.use_part("CP2102N-A02-GQFN24R", ref="U1", value="CP2102N-A02")

    # power: VIO(5) + VDD(6) + VREGIN(7) tied directly to +VDD_IO (self-powered);
    # GND pin 2 + stacked hidden twin 25
    c.net("+VDD_IO", "U1.5", "U1.6", "U1.7")
    c.net("GND", "U1.2", "U1.25")
    for cap, lcsc in zip(c.decouple("U1.7", "100n", "10u"),     # C1, C2
                         ("C14663", "C15850")):                 # both Basic
        cap.fields["LCSC"] = lcsc
    for cap in c.decouple("U1.6", "100n"):   # C3 on VDD
        cap.fields["LCSC"] = "C14663"
    for cap in c.decouple("U1.5", "100n"):   # C4 on VIO
        cap.fields["LCSC"] = "C14663"

    # reset pull-up (RST is open-drain, needs the external pull to VDD33)
    c.net("CP2102N_RST_N", "U1.9")
    c.pullup("U1.9", "1k", "+VDD_IO").fields["LCSC"] = "C21190"   # R1, Basic

    # VBUS sense divider, datasheet self-powered config: senses the UART
    # USB connector's OWN 5 V VBUS (the cable-attach detect this pin is
    # for). FIX 2026-06-11, caught by the schgen spice gate: this divider
    # was authored from a board VIN — after PD negotiation that rail is 20 V
    # and the divider would put 13.6 V on a 5.8 V abs-max pin, destroying the
    # bridge. USB_VBUS is the USB-UART receptacle's own VBUS.
    # USB_VBUS -[22k1]- CP2102N_VBUS_SNS -[47k5]- GND, mid to pin 8
    # (22.1k = C25961, 47.5k = C23061 — both UNI-ROYAL 1% 0603, Extended,
    # stock 87k/91k live-verified 2026-06-11)
    c.port("USB_VBUS", **meta.expect_kw("USB_VBUS"))
    c.net("CP2102N_VBUS_SNS", "U1.8")
    c.series("USB_VBUS", "CP2102N_VBUS_SNS", "22k1") \
        .fields["LCSC"] = "C25961"                  # R2
    c.series("CP2102N_VBUS_SNS", "GND", "47k5") \
        .fields["LCSC"] = "C23061"                  # R3

    # USB data to the connector — a 90R differential pair (USB 2.0 HS); the USB
    # receptacle is a project-side connector sheet. Typed inline with the ABSTRACT
    # complement; Circuit.bind (via meta.finish) rebinds pair_with so the bound
    # pair's two ends agree and the SI gate sees the project pair.
    c.port("USB_DP", "U1.3")
    c.port("USB_DM", "U1.4")
    c.port_type("USB_DP", kind="usb_hs_pair", pair_with="USB_DM",
                expect=meta.expects.get("USB_DP"))

    # UART signals, brought out BRIDGE-RELATIVE (TXD/RXD = bridge data out/in,
    # RTS_N/CTS_N = bridge active-low flow control out/in). A project's crossover
    # to its host UART (bridge TXD -> host RXD, etc.) happens in its bind map;
    # the library stays host-agnostic. Each port is deferred to whichever project
    # sheet carries the host-UART function map (via meta["expects"]).
    c.port("UART_TXD", "U1.21", **meta.expect_kw("UART_TXD"))    # bridge TXD out
    c.port("UART_RXD", "U1.20", **meta.expect_kw("UART_RXD"))    # bridge RXD in
    c.port("UART_RTS_N", "U1.19", **meta.expect_kw("UART_RTS_N"))  # bridge ~RTS out
    c.port("UART_CTS_N", "U1.18", **meta.expect_kw("UART_CTS_N"))  # bridge ~CTS in

    # unused by design: ~RI/CLK, GPIO.0-3, SUSPEND/~SUSPEND, ~DSR/~DTR/~DCD,
    # and the two physical NC pins (10, 16)
    c.nc("U1.1", "U1.10", "U1.11", "U1.12", "U1.13", "U1.14", "U1.15",
         "U1.16", "U1.17", "U1.22", "U1.23", "U1.24")

    # round-4 coverage gate: the console UART is THE bring-up bus — probe
    # both directions at the bridge. TP creation order is the placer's TP1/TP2
    # ordering, so it must be STABLE under the bind: TP1 = the bridge RXD line,
    # TP2 = the bridge TXD line (this is the order a project's host-side names
    # land in after the TXD<->RXD crossover bind — see carrier adapter).
    c.testpoint("UART_RXD")
    c.testpoint("UART_TXD")

    # power-tree budget (round 4): CP2102N active ICC ~14 mA typ (DS table
    # 4.3) + 1k RST pull-up, self-powered from +VDD_IO
    c.draws("+VDD_IO", DRAWS_A, draws_note)
    # design-rule waiver (verification P1): CP2102N_RST_N is a defined-high
    # open-drain RST with the 1k external pull-up only — no RC cap by design
    # (the CP2102N has its own internal POR; a runtime reset is host-driven).
    c.waive_reset("CP2102N_RST_N", RESET_WAIVER)

    return meta.finish(c)            # applies meta["bind"] (if any); rebinds the
    #                                  usb_hs_pair complement too (pure rename)
