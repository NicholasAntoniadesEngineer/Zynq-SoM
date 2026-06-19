"""usb_jtag — CH347T USB-JTAG/UART debug bridge, self-powered + isolated (LIBRARY).

PROJECT-AGNOSTIC, REUSABLE subsystem. A self-contained ``subsystems/<name>/``
package (netlist + README + SPICE subckt + local test) that declares its
interface as ABSTRACT port + rail names and knows NOTHING about any consuming
board — no carrier net names, no ``carrier/nets.py`` / ``som_interface.json``
reads. A project consumes it by calling :func:`circuit` with the STANDARD
``meta`` dict (see :mod:`schgen.core.subsystem`): ``bind`` rebinds every
externally-visible net to its real board name, ``expects`` adds per-port linker
deferrals, ``notes`` restores house-style prose. Standalone (``meta=None``) it
keeps the abstract names so this package's ``test_usb_jtag.py`` runs offline.

A USB cable plugged into the project's debug receptacle gives a host PC a target
JTAG programmer AND a console UART (one CH347 channel each, MODE 3) WITHOUT any
external pod — and it does so even when the target's main rails are OFF, because
the bridge runs entirely off its OWN debug-USB VBUS (a self-powered island) and
its JTAG IO is buffered so it never back-feeds an unpowered target.

PART CHOICE — CH347T over the FT2232H. The FT2232H is the canonical dual-channel
FTDI JTAG+UART bridge, but its 64-pin LQFP is far larger than any other carrier
IC and the schgen auto-placer cannot route a 64-pin part. The WCH CH347T
(TSSOP-20) is the direct, widely-used HS USB->JTAG+UART alternative (the standard
low-cost FPGA/CPU programmer chip): MODE 3 = "USB to high-speed single serial
port + USB to JTAG port" (DS v1A section 5.2 / 4.6) — exactly a JTAG programmer
+ a console UART in one. Built-in USB termination + EEPROM + POR, and TSSOP
side-only pins place cleanly.

PARTS (live JLC stock 2026-06-15, JLCPCB parts API):
  * U1  CH347T            C5122332 (1,953, TSSOP-20) — HS USB to JTAG + dual UART
        bridge (MODE 3 = JTAG + UART). Built-in USB-PHY + 1.5k pull-up + series
        matching (UD+/UD- go DIRECT to the bus, DS p.3 note), built-in power-on
        reset, built-in config EEPROM (NO external 93C56 needed).
  * Y1  1C208000BC0R      C57131   (32,856, SMD3225-4P) — 8 MHz crystal on XI/XO
        (DS section 5.1 quotes ~22 pF load caps, but this crystal is CL=12 pF,
        so 16 pF C0G matched caps are fitted — see the crystal block below).
  * U4  AP2112K-3.3TRG1   C51118   (87,465) — the self-powered-island LDO: debug
        USB VBUS (5 V) -> the 3.3 V island rail. AP2112K is the carrier's standard
        LDO family.
  * U2  SN74LVC125ADR     C7661    (7,330, SOIC-14) — quad 3-state buffer, the
        JTAG ISOLATION buffer (OE-gated; the contention proof below).
  (the USB-C UFP receptacle + the USBLC6-2SC6 D+/D- ESD live on a project-side
  connector sheet — the "connectors get their own sheet" idiom; that sheet
  publishes the VBUS rail + the protected USB pair for this bridge to consume.)

POWER — SELF-POWERED ISLAND. The whole bridge is powered from the island 3.3 V
rail, which U4 (AP2112K) regulates from the debug cable's OWN 5 V VBUS — NOT from
any target/board rail. So the bridge is ALIVE only while the debug USB cable is
plugged in, and it can program / console a target whose main rails are all OFF.
The CH347 is a single-supply 3.3 V part (DS section 5.1 / 6.2: VCC 3.0-3.6 V,
ICC ~38 mA typ): VCC(14) <- island rail with a 100n decoupling cap; built-in POR
(RST# pin 1 has an internal pull-up — only an optional external 10k is added for
noise immunity, NO RC by design).

MODE 3 STRAP (JTAG + UART). The CH347 latches its working mode from DTR1(10) and
RTS1(13) at power-on reset (DS section 5.2 table): MODE 3 = "DTR1 pulls down low,
RTS1 pulls down low". So both carry a 10k pulldown to GND here -> the bridge
always enumerates as one UART + one JTAG TAP. (Both pins have built-in pull-ups,
so the external 10k pulldowns must dominate -> 10k vs the ~40k internal.)

ISOLATION / CONTENTION PROOF (LAW-0). If the CH347 drove the target JTAG nets
directly it would (a) fight a JTAG pod plugged into the target's JTAG header, and
(b) back-feed the target's JTAG inputs when the target is OFF. U2 (SN74LVC125,
quad 3-state buffer) breaks both: the three CH347 JTAG OUTPUTS TCK/TDI/TMS pass
through three buffer gates whose OUTPUTS drive JTAG_TCK/JTAG_TDI/JTAG_TMS; the
fourth gate buffers JTAG_TDO back to the CH347 TDO INPUT. When the buffer is
DISABLED every output is Hi-Z. ALL FOUR OE# pins are tied to DBG_JTAG_OE_N, gated
by SW1 (DSHP04 pos 1): DEFAULT-OFF — a 100k pull-up to the island rail holds OE#
HIGH (outputs Hi-Z) until a human closes SW1 to pull OE# LOW. So power-up /
cable-just-plugged: OE# high -> buffer Hi-Z -> the header pod (or the target)
owns JTAG, ZERO contention by default; the user closes SW1 only when they intend
to program from the bridge -> exactly one JTAG master at a time. (CH347 TRST is
left NC — TRST is an OPTIONAL JTAG line per the CH347 DS section 5.6.)

ABSTRACT INTERFACE (see README.md for the full table) — the names a project
binds:

  rails (POWER/GROUND):
    +VBUS_USB    the debug USB cable's OWN 5 V VBUS, the LDO (U4) input. Alive
                 ONLY while the debug cable is plugged -> the whole bridge is too.
                 NOT a target/board rail.
    +3V3_ISLAND  the self-powered island 3.3 V rail (U4 output): powers the CH347,
                 the buffer, and all the pulls. A project may name this whatever
                 its local LDO-output net is; it never depends on a target rail.
    GND          ground.
  ports (PORT):
    USB_DP/DM    the ESD-protected USB 2.0 HS data pair from the project's debug
                 receptacle (the CH347 UD+/UD- take the bus DIRECTLY — DS forbids
                 a series R). A 90R HS pair; the receptacle/ESD are project-side.
    JTAG_TCK/TMS/TDI  the three buffered JTAG OUTPUTS to the target TAP.
    JTAG_TDO     the target TDO read back through the buffer (a buffer INPUT).
    UART_RXD     bridge UART RXD-side line (CH347 TXD1, pin 3 -> target RXD).
    UART_TXD     bridge UART TXD-side line (CH347 RXD1, pin 4 <- target TXD).

DESIGN NOTES (datasheet + bring-up contract): see README.md "Design notes".
"""

from __future__ import annotations

from schgen.core.model import Circuit
from schgen.core.subsystem import Meta

R0603 = "Resistor_SMD:R_0603_1608Metric"
C0603 = "Capacitor_SMD:C_0603_1608Metric"
C0805 = "Capacitor_SMD:C_0805_2012Metric"

LCSC_100N = "C14663"     # 100n X7R 0603
LCSC_1U = "C15849"      # 1u 0603 X7R (LDO Cin)
LCSC_10U = "C15850"     # 10u 0805 bulk
LCSC_16P = "C162205"    # 16p C0G/NP0 0603 50V (Murata GRM1885C1H160JA01D)
LCSC_10K = "C25804"     # 10k 1% 0603
LCSC_100K = "C25803"    # 100k 1% 0603 (OE default pull-up)

# ---- the abstract interface (the REUSE contract) ------------------------------
# Externally-visible net names a consuming project binds. RAILS classify as
# POWER/GROUND by name (the '+' prefix + GND), exactly as the bound carrier
# rails do, so a standalone build and a bound build share net classes.
RAILS = ("+VBUS_USB", "+3V3_ISLAND", "GND")
PORTS = ("USB_DP", "USB_DM",
         "JTAG_TCK", "JTAG_TDI", "JTAG_TMS", "JTAG_TDO",
         "UART_RXD", "UART_TXD")
INTERFACE = RAILS + PORTS

# Default house-style metadata a project may override via meta["notes"]:
#   the power-tree draw note (CH347 ICC ~38 mA typ, DS 6.2 + buffer + pulls) and
#   the design-rule reset-waiver reason (CH347 RST#: 10k pull-up + internal POR,
#   no RC cap). A consuming project may cite its own dossier wording without the
#   library knowing any board specifics — keeping the library project-agnostic
#   while a consumer's derived artifacts (power-tree note) stay byte-stable.
DRAWS_NOTE = ("CH347 ~38 mA typ (DS) + SN74LVC125 + RST/mode/OE pull network")
DRAWS_A = 0.045
RESET_WAIVER = ("CH347 RST#: 10k pull-up + the chip's built-in power-on reset "
                "(DS 5.1); no external RC cap fitted by design")


def circuit(meta: "Meta | dict | None" = None) -> Circuit:
    """Build the usb_jtag subsystem netlist with ABSTRACT port/rail names.

    ``meta`` is the STANDARD subsystem adapter contract (see
    :mod:`schgen.core.subsystem`) — a single dict a consuming project's adapter
    declares. Keys this subsystem reads (all optional; ``meta=None`` ->
    standalone abstract names for the local test):

      ``bind``    ``{abstract_name: project_net}`` rebinds the externally-visible
                  nets (the :data:`INTERFACE` names) to a project's real board
                  names. Applied last (order-preserving => byte-identical sheet).
      ``expects`` ``{abstract_port: deferral}`` attaches an EXPLICIT linker
                  deferral to a port — a project declares which of its sheets
                  will bind a deferred port (the USB pair binds on the project's
                  debug-USB connector sheet; the JTAG ports on its target JTAG
                  header; the UART ports on its host-UART function map).
      ``notes``   ``{"draws": prose}`` the power-tree draw-note prose (a project
                  may cite its own dossier wording; defaults to :data:`DRAWS_NOTE`).
    """
    meta = Meta(meta)
    draws_note = meta.note("draws", DRAWS_NOTE)
    c = Circuit("usb_jtag",
                "USB-JTAG/UART debug bridge: CH347T, self-powered + isolated")

    # =====================================================================
    # self-powered island LDO: debug-USB VBUS (+VBUS_USB, from the USB-C
    # receptacle on a project connector sheet) -> +3V3_ISLAND. +VBUS_USB is
    # alive ONLY with the debug cable plugged -> the whole bridge is too.
    # =====================================================================
    c.use_part("AP2112K-3.3TRG1", ref="U4")
    c.net("+VBUS_USB", "U4.VIN", "U4.EN")             # EN tied on (alive on VBUS)
    c.net("+3V3_ISLAND", "U4.VOUT")
    c.net("GND", "U4.GND")
    c.nc("U4.NC")
    for cap in c.decouple("U4.VIN", "1u", footprint=C0603):
        cap.fields["LCSC"] = LCSC_1U                  # LDO Cin
    for cap in c.decouple("U4.VOUT", "10u", footprint=C0805):
        cap.fields["LCSC"] = LCSC_10U                 # AP2112K needs >=1u Cout
    for cap in c.decouple("U4.VOUT", "100n", footprint=C0603):
        cap.fields["LCSC"] = LCSC_100N

    # =====================================================================
    # CH347T — the bridge (MODE 3 = JTAG + UART)
    # =====================================================================
    c.use_part("CH347T", ref="U1", value="CH347T")
    c.net("+3V3_ISLAND", "U1.14")                      # VCC (3.3 V single supply)
    c.net("GND", "U1.18")                              # GND
    for cap in c.decouple("U1.14", "100n", footprint=C0603):
        cap.fields["LCSC"] = LCSC_100N                # DS: ~0.1u on VCC

    # USB to the ESD-protected pair from the connector sheet (UD+ = 17, UD- =
    # 16). The CH347 UD+/UD- take the bus DIRECTLY (DS forbids a series R); the
    # USBLC6 on the connector sheet is a SHUNT array, no series element added.
    # Typed inline with the ABSTRACT complement; Circuit.bind (via meta.finish)
    # rebinds pair_with so the bound pair's two ends agree and the SI gate sees
    # the project pair (NO post-finish fixup).
    c.port("USB_DP", "U1.17")                         # protected UD+
    c.port("USB_DM", "U1.16")                         # protected UD-
    c.port_type("USB_DP", kind="usb_hs_pair", pair_with="USB_DM",
                expect=meta.expects.get("USB_DP"))

    # 8 MHz crystal on XI(19)/XO(20). The CH347 DS section 5.1 quotes "~22pF"
    # load caps, but that is GENERIC boilerplate assuming a ~CL=20pF crystal.
    # The crystal actually fitted (Y1 = KDS 1C208000BC0R, C57131) is cut for
    # CL=12pF, so the matched external cap per leg is Cext = 2*(CL - Cstray) =
    # 2*(12 - ~4) = 16pF C0G (22pF would over-load it and pull 8MHz slow).
    c.use_part("1C208000BC0R", ref="Y1", value="8MHz")
    c.net("DBG_XI", "U1.19", "Y1.1")                  # OSC1
    c.net("DBG_XO", "U1.20", "Y1.3")                  # OSC2
    c.net("GND", "Y1.2", "Y1.4")                      # crystal shield/NC pads
    for sig in ("DBG_XI", "DBG_XO"):
        cap = c.part(c.auto_ref("C"), "Device:C", "16p", C0603, LCSC=LCSC_16P)
        c.net(sig, f"{cap.ref}.1")
        c.net("GND", f"{cap.ref}.2")

    # RST#(1): built-in POR + internal pull-up; add an external 10k for noise
    # immunity (no RC cap by design — the CH347 has its own power-on reset)
    c.net("DBG_RST_N", "U1.1")
    c.pullup("U1.1", "10k", "+3V3_ISLAND").fields["LCSC"] = LCSC_10K

    # MODE 3 strap: DTR1(10) low + RTS1(13) low -> JTAG + UART (DS section 5.2).
    # Both have internal pull-ups; the 10k pulldowns dominate at reset.
    c.net("DBG_MODE_DTR1", "U1.10")
    c.net("DBG_MODE_RTS1", "U1.13")
    r_d = c.part(c.auto_ref("R"), "Device:R", "10k", R0603, LCSC=LCSC_10K)
    c.net("DBG_MODE_DTR1", f"{r_d.ref}.1")
    c.net("GND", f"{r_d.ref}.2")
    r_r = c.part(c.auto_ref("R"), "Device:R", "10k", R0603, LCSC=LCSC_10K)
    c.net("DBG_MODE_RTS1", f"{r_r.ref}.1")
    c.net("GND", f"{r_r.ref}.2")

    # unused: CTS1(2), GPIO/SCL(11), GPIO/SDA(12), ACT/DCD0(15), TRST(9 — NC,
    # the target dedicated-JTAG has no TRST line; OPTIONAL per the CH347 DS)
    c.nc("U1.2", "U1.9", "U1.11", "U1.12", "U1.15")

    # =====================================================================
    # Channel A = JTAG through the SN74LVC125 isolation buffer (contention
    # proof in the header). CH347 MODE-3 JTAG: TCK=6, TMS=5, TDI=7, TDO=8.
    # =====================================================================
    c.use_part("SN74LVC125ADR", ref="U2")
    c.net("+3V3_ISLAND", "U2.14")                      # VCC: buffer on the island
    c.net("GND", "U2.7")                               # GND
    for cap in c.decouple("U2.14", "100n", footprint=C0603):
        cap.fields["LCSC"] = LCSC_100N

    # CH347 channel-A JTAG pins (the buffer-INPUT side)
    c.net("DBG_FT_TCK", "U1.6")                        # TCK out
    c.net("DBG_FT_TMS", "U1.5")                        # TMS out
    c.net("DBG_FT_TDI", "U1.8")                        # TDI out  (pin8 TXD0/MOSI/TDI = bridge output)
    c.net("DBG_FT_TDO", "U1.7")                        # TDO in   (pin7 RTS0/MISO/TDO = bridge input)

    # SN74LVC125 pins by NUMBER: 1OE#=1,1A=2,1Y=3,2OE#=4,2A=5,2Y=6,GND=7,
    # 3Y=8,3A=9,3OE#=10,4Y=11,4A=12,4OE#=13,VCC=14.
    # gate 1: TCK (1A=2) -> 1Y(3) -> JTAG_TCK
    c.net("DBG_FT_TCK", "U2.2")
    c.port("JTAG_TCK", "U2.3", **meta.expect_kw("JTAG_TCK"))
    # gate 2: TDI (2A=5) -> 2Y(6) -> JTAG_TDI
    c.net("DBG_FT_TDI", "U2.5")
    c.port("JTAG_TDI", "U2.6", **meta.expect_kw("JTAG_TDI"))
    # gate 4: TMS (4A=12) -> 4Y(11) -> JTAG_TMS
    c.net("DBG_FT_TMS", "U2.12")
    c.port("JTAG_TMS", "U2.11", **meta.expect_kw("JTAG_TMS"))
    # gate 3 REVERSE: JTAG_TDO (3A=9) -> 3Y(8) -> CH347 TDO (it reads)
    c.port("JTAG_TDO", "U2.9", **meta.expect_kw("JTAG_TDO"))
    c.net("DBG_FT_TDO", "U2.8")

    # OE# (all four: 1OE#=1, 2OE#=4, 3OE#=10, 4OE#=13) = DBG_JTAG_OE_N:
    # default-HIGH via 100k -> outputs Hi-Z, closed by SW1 (DSHP04 pos 1) to
    # GND to ENABLE the bridge's JTAG. THE CONTENTION GUARD (see header):
    # default-off, USB-island powered.
    c.net("DBG_JTAG_OE_N", "U2.1", "U2.4", "U2.10", "U2.13")
    c.pullup("U2.1", "100k", "+3V3_ISLAND").fields["LCSC"] = LCSC_100K
    c.use_part("DSHP04TSGER", ref="SW1")
    c.net("DBG_JTAG_OE_N", "SW1.1")                   # pos 1 closes OE# -> GND
    c.net("GND", "SW1.8")
    c.nc("SW1.2", "SW1.3", "SW1.4", "SW1.5", "SW1.6", "SW1.7")

    # =====================================================================
    # Channel B = console UART1 to a free host-bank UART.
    # TXD1=3, RXD1=4 (2-wire console).
    # =====================================================================
    c.port("UART_RXD", "U1.3", **meta.expect_kw("UART_RXD"))  # TXD1 -> target RXD
    c.port("UART_TXD", "U1.4", **meta.expect_kw("UART_TXD"))  # RXD1 <- target TXD

    # ---- coverage + budget ----------------------------------------------
    # Declared in ABSTRACT names; Circuit.bind (via meta.finish) rebinds each
    # testpoint VALUE to the real net, so the placer's TP ordering is stable.
    c.testpoint("+3V3_ISLAND")                         # the USB island rail
    c.testpoint("UART_TXD")                            # console bring-up probe
    c.testpoint("UART_RXD")

    # power budget: everything rides +3V3_ISLAND, which U4 (AP2112K, 600 mA)
    # sources from +VBUS_USB. CH347 ICC ~38 mA typ (DS 6.2) + buffer + pulls.
    c.draws("+3V3_ISLAND", DRAWS_A, draws_note)

    # design-rule waiver: DBG_RST_N (CH347 RST#) is a defined-high reset with a
    # 10k pull-up only — NO RC cap by design. The CH347 has a built-in power-on
    # reset circuit (DS section 5.1) and RST# carries its own internal pull-up;
    # the external 10k is noise-immunity insurance. A runtime reset is host-/
    # driver-mediated over USB, not an RC ramp.
    c.waive_reset("DBG_RST_N", RESET_WAIVER)

    return meta.finish(c)            # applies meta["bind"] (if any); rebinds the
    #                                  usb_hs_pair complement + testpoints too
