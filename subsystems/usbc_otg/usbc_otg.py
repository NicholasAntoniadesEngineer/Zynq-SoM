"""usbc_otg — USB 2.0 High-Speed OTG port (USB-C receptacle, host-capable) LIBRARY.

PROJECT-AGNOSTIC, REUSABLE subsystem. A self-contained package (netlist + README
+ SPICE subckt + local test) that declares its interface as ABSTRACT port + rail
names and knows NOTHING about any consuming board — no carrier net names, no
``carrier/nets.py`` / ``som_interface.json`` reads. A project consumes it by
calling :func:`circuit` with the STANDARD ``meta`` dict (see
:mod:`schgen.core.subsystem`): ``bind`` rebinds every externally-visible net to
its real board name, ``expects`` adds per-port linker deferrals, ``notes``
restores house-style prose. Standalone (``meta=None``) it keeps the abstract
names so this package's ``test_usbc_otg.py`` runs offline.

Reference circuit: TYPE-C-31-M-12 receptacle -> USBLC6-2SC6 ESD array on the
data pair -> system USB HS PHY (abstract ports ``USB_DP`` / ``USB_DM``). VBUS is
sourced by a TPS2051C current-limited power switch from a host-supply rail
(abstract ``+VBUS_SUPPLY``), enabled by the system's ``VBUS_EN`` with the fault
flag (``FLT_N``) pulled up to logic and ported. CC1/CC2 carry 56k Rp pull-ups to
the sourced VBUS advertising default-USB host power; ``USB_ID`` is strapped low
through 1k = host role for this port (a dual-role / device port lives elsewhere).

ABSTRACT INTERFACE (see README.md for the full table) — the names a project
binds:

  rails (POWER/GROUND):
    +VBUS_SUPPLY  host VBUS supply feeding the TPS2051C power switch IN (the
                  rail the port SOURCES onto the cable, current-limited).
    +VDD_LOGIC    logic-domain rail (3.3 V class) for the open-drain fault-flag
                  pull-up — chosen so FLT# stays readable even when +VBUS_SUPPLY
                  is gated OFF and within the downstream expander's IO abs-max.
    GND           ground.
    CHASSIS_GND   receptacle shell / shield bond (chassis earth).
  ports (PORT):
    USB_DP/USB_DM the USB 2.0 HS data pair to the system PHY (90 ohm diff,
                  typed usb_hs_pair), behind the USBLC6-2SC6 ESD array.
    VBUS          the connector VBUS the port sources/senses (TPS2051 OUT + the
                  receptacle VBUS pads; also the CC Rp reference + ESD VBUS pin).
    VBUS_EN       active-high enable for the VBUS power switch (held OFF by a
                  100k pulldown until the host drives it high).
    FLT_N         open-drain over-current fault flag from the power switch.
    USB_ID        OTG ID, strapped low through 1k = host role for this port.

DESIGN NOTES (datasheet + role contract): see README.md "Design notes".

AUTHORING V2 reference sheet: actives come from parts/ via use_part() (no inline
lib ids / footprints / LCSC for generated parts) and connect by pin NAME —
"J2.VBUS" nets BOTH stacked VBUS pads, exactly like the symbol.
"""

from __future__ import annotations

from schgen.core.model import Circuit
from schgen.core.subsystem import Meta

R0603 = "Resistor_SMD:R_0603_1608Metric"
C0603 = "Capacitor_SMD:C_0603_1608Metric"
C0805 = "Capacitor_SMD:C_0805_2012Metric"

# ---- the abstract interface (the REUSE contract) ------------------------------
# Externally-visible net names a consuming project binds. RAILS classify as
# POWER/GROUND by name (a leading '+' = POWER; GND/CHASSIS_GND = GROUND), exactly
# as the bound carrier rails do, so a standalone build and a bound build share
# net classes. PORTS are declared with c.port(...).
RAILS = ("+VBUS_SUPPLY", "+VDD_LOGIC", "GND", "CHASSIS_GND")
PORTS = ("USB_DP", "USB_DM", "VBUS", "VBUS_EN", "FLT_N", "USB_ID")
INTERFACE = RAILS + PORTS

# Default power-tree draw notes. A project may override the prose via
# meta["notes"]["draws_vbus"] / meta["notes"]["draws_flt"] to cite its own
# dossier wording (keeping its derived power-tree artifact byte-stable).
DRAWS_VBUS_A = 0.500
DRAWS_VBUS_NOTE = ("downstream USB device budget, TPS2051C current-limited")
DRAWS_FLT_A = 0.0005
DRAWS_FLT_NOTE = ("FLT# 100k pull-up on the logic rail")

# Nominal / worst-case voltage of each abstract RAIL — the subsystem's own
# electrical contract, NOT a board value. Used by the local test to derate the
# bypass/bulk caps without depending on a board power tree:
#   +VBUS_SUPPLY = 5 V USB host supply; VBUS rides the same 5 V it sources.
#   +VDD_LOGIC   = 3.3 V class.
RAIL_WORST_V = {"+VBUS_SUPPLY": 5.0, "+VDD_LOGIC": 3.3, "GND": 0.0,
                "CHASSIS_GND": 0.0, "VBUS": 5.0}


def circuit(meta: "Meta | dict | None" = None) -> Circuit:
    """Build the usbc_otg subsystem netlist with ABSTRACT port/rail names.

    ``meta`` is the STANDARD subsystem adapter contract (see
    :mod:`schgen.core.subsystem`) — a single dict a consuming project's adapter
    declares. Keys this subsystem reads (all optional; ``meta=None`` ->
    standalone abstract names for the local test):

      ``bind``    ``{abstract_name: project_net}`` rebinds the externally-visible
                  nets (the :data:`INTERFACE` names) to a project's real board
                  names. Applied last (order-preserving => byte-identical sheet).
      ``expects`` ``{abstract_port: deferral}`` attaches an EXPLICIT linker
                  deferral to a port — a project declares which of its sheets
                  will bind a deferred port (e.g. VBUS_EN / USB_ID land on a
                  generated connector sheet; FLT_N lands on an IO expander).
      ``notes``   ``{"draws_vbus"|"draws_flt": prose}`` power-tree draw-note
                  prose (a project may cite its own dossier wording; defaults to
                  :data:`DRAWS_VBUS_NOTE` / :data:`DRAWS_FLT_NOTE`).
    """
    meta = Meta(meta)
    c = Circuit("usbc_otg", "USB 2.0 HS OTG port (Type-C, host)")
    j2 = c.use_part("TYPE-C-31-M-12", ref="J2")
    u1 = c.use_part("TPS2051CDBVR", ref="U1")
    u2 = c.use_part("USBLC6-2SC6", ref="U2")

    # ---- VBUS: +VBUS_SUPPLY -> TPS2051 -> connector VBUS (= sense VBUS)
    # +VBUS_SUPPLY is the (typically host-gated) module rail feeding the switch:
    # a POWER net with its own power symbol.
    c.net("+VBUS_SUPPLY", "U1.IN")
    c.port("VBUS", "U1.OUT", "J2.VBUS")         # OUT + sense (both pads)
    # EN default-OFF: TPS2051C EN is active-high; a 100k pulldown holds the host
    # VBUS switch OFF until the host explicitly drives VBUS_EN high. Without it
    # EN floats and the port could source 5 V on the bus at power-on before the
    # host has decided the OTG role (a dual-role port lives elsewhere).
    c.part("R5", "Device:R", "100k", R0603, LCSC="C25803")
    c.port("VBUS_EN", "U1.EN(EN#)", "R5.1", **meta.expect_kw("VBUS_EN"))
    c.net("GND", "U1.GND", "R5.2")
    # fault flag: TPS2051C FLT# is open-drain, reported to the host via FLT_N.
    # The pull-up is railed to +VDD_LOGIC (a 3.3 V-class logic rail) so the flag
    # stays within the downstream reader's IO abs-max AND readable even with the
    # +VBUS_SUPPLY module rail gated OFF (the flag is valid low when the port is
    # unpowered) — strictly better than a switched-rail pull.
    c.part("R3", "Device:R", "100k", R0603, LCSC="C25803")
    c.port("FLT_N", "U1.FLT#", "R3.2", **meta.expect_kw("FLT_N"))
    c.net("+VDD_LOGIC", "R3.1")
    # input bypass + VBUS bulk per TPS2051 datasheet
    for cap in c.decouple("U1.IN", "100n"):     # C14663 Basic, 20.6M stock
        cap.fields["LCSC"] = "C14663"
    # VBUS bulk = C2 (22uF MLCC, HF companion) + C3 (100uF/16V aluminium
    # electrolytic, bias-STABLE hold-up). The MLCC alone derates to ~15-20uF at
    # 5 V bias — below the USB 2.0 host-port minimum (120uF) / TPS2051C DS 150uF
    # ref — so a device hot-plug could droop VBUS<4.4 V. The electrolytic's
    # capacitance does NOT bias-derate, so it carries the bulk; more MLCC would
    # just re-derate (audit 2026-06-19/20, CLOSED with a verified part).
    # C970684 = DMBJ RVT1C101M0605 100uF 16V SMD, VERIFIED via the LCSC/EasyEDA
    # API + part-add (faithful footprint + 3D). PAD 1 = + (silk "+" marker by the
    # left pad), PAD 2 = - — VBUS on +, GND on -.
    c.part("C2", "Device:C", "22u", C0805, LCSC="C45783")
    c.net("VBUS", "C2.1")
    c.net("GND", "C2.2")
    cblk = c.use_part("RVT1C101M0605_100UF_16V", ref="C3", value="100u")
    c.net("VBUS", f"{cblk.ref}.1")              # + terminal (pad 1)
    c.net("GND", f"{cblk.ref}.2")               # - terminal (pad 2)

    # ---- data pair through the ESD array (pass-through 1<->6, 3<->4)
    c.net("USBC_DP_CONN", "J2.DP1", "J2.DP2", "U2.1")
    c.net("USBC_DM_CONN", "J2.DN1", "J2.DN2", "U2.3")
    c.port("USB_DP", "U2.6", **meta.expect_kw("USB_DP"))
    c.port("USB_DM", "U2.4", **meta.expect_kw("USB_DM"))
    # USB 2.0 HS differential pair (90 ohm). Typed with the ABSTRACT complement;
    # Circuit.bind (via meta.finish) rebinds pair_with so the bound pair's two
    # ends agree and the SI gate sees the project pair.
    c.port_type("USB_DP", kind="usb_hs_pair", pair_with="USB_DM")
    c.net("VBUS", "U2.5")
    c.net("GND", "U2.2")

    # ---- CC host advertising: 56k Rp to VBUS (default USB power)
    for ref, cc in (("R1", "J2.CC1"), ("R2", "J2.CC2")):
        # 56k 1% 0603 = 0603WAF5602T5E, C23206 — live-verified 2026-06-11:
        # Basic, stock 289,495
        c.part(ref, "Device:R", "56k", R0603, LCSC="C23206")
        c.net("VBUS", f"{ref}.1")
        c.net(f"USBC_{ref}_CC", f"{ref}.2", cc)

    # ---- OTG ID strap: USB_ID through 1k to GND = HOST role for this port
    # (a dual-role / device port lives elsewhere).
    c.part("R4", "Device:R", "1k", R0603, LCSC="C21190")
    c.port("USB_ID", "R4.1", **meta.expect_kw("USB_ID"))
    c.net("GND", "R4.2")

    # ---- shield / unused
    c.net("CHASSIS_GND", "J2.EH")               # all four shell pads by NAME
    c.net("GND", "J2.GND")                      # both stacked GND pads
    c.nc("J2.SBU1", "J2.SBU2")                  # SBU unused on USB2 port

    # coverage gate: the VBUS switch enable (every EN is probeable)
    c.testpoint("VBUS_EN")

    # power-tree budget: one downstream USB 2.0 device budget (500 mA) through
    # the TPS2051C (0.5 A-class limited switch); CC Rp + ESD array are noise
    # next to it.
    c.draws("+VBUS_SUPPLY", DRAWS_VBUS_A, meta.note("draws_vbus", DRAWS_VBUS_NOTE))
    # the FLT# 100k pull-up on the logic rail (~33 uA when asserted)
    c.draws("+VDD_LOGIC", DRAWS_FLT_A, meta.note("draws_flt", DRAWS_FLT_NOTE))

    return meta.finish(c)            # applies meta["bind"] (if any); rebinds the
    #                                  usb_hs_pair complement too (pure rename)
