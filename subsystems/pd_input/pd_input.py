"""pd_input — USB-C PD power INLET subsystem (LIBRARY): Type-C receptacle +
TPS26631 eFuse (OVP / soft-start) + USBLC6 data ESD.

PROJECT-AGNOSTIC, REUSABLE subsystem (sibling of ``subsystems/usb_pd/``): a
self-contained package (netlist + README + SPICE subckt + local test) that
declares its interface as ABSTRACT port + rail names and knows NOTHING about
any consuming board — no carrier net names, no ``carrier/nets.py`` reads. A
project consumes it via the STANDARD ``meta`` dict (see
:mod:`schgen.core.subsystem`): ``bind`` rebinds every externally-visible net to
its real board name, ``expects`` adds per-port linker deferrals, ``notes``
restores house-style prose. Standalone (``meta=None``) the abstract names stay,
so this package's ``test_pd_input.py`` runs offline.

PAIRS WITH ``subsystems/usb_pd`` (the FUSB302B CC PHY): this subsystem OWNS the
receptacle + the inlet eFuse; the CC lines and the RAW (pre-eFuse) VBUS-sense
cross to the PHY. Keep ``CC1``/``CC2`` as PORTS and the raw inlet VBUS as the
``+VBUS_CONN`` rail (usb_pd binds its own ``+VBUS_SENSE`` to the SAME board
net) so the two subsystems meet on identical bound names.

Reference circuit (USB-C PD 20 V / 3 A inlet):
  * TYPE-C-31-M-12 receptacle: VBUS/GND stacked pads, CC1/CC2 out, the FS data
    pair through a USBLC6-2SC6 ESD array, SBU unused, shell to CHASSIS_GND.
  * TPS26631 eFuse between the raw receptacle VBUS (+VBUS_CONN) and the board
    bulk (+VBUS_OUT): OVP divider, ILIM, dVdT soft-start, MODE/PGTH straps,
    open-drain FLT# out, EP/GND to ground; SMBJ22A TVS + DS-minimum 100n at the
    inlet, the dVdT-charged 10u behind the fuse.

Every datasheet number / part choice is documented in the carrier ADAPTER
(``carrier/subsystems/pd_input.py``) and ``README.md`` here. The netlist is a
faithful copy of the original hand-written carrier sheet with the EXTERNAL net
names abstracted; all parts/refs/values/LCSC/footprints/NCs are verbatim.

ABSTRACT INTERFACE (see README.md for the full table) — the names a project
binds:

  rails (POWER / GROUND):
    +VBUS_CONN    RAW receptacle VBUS, AHEAD of the eFuse (TVS + inlet 100n +
                  the eFuse IN/IN_SYS/UVLO/OVP-top). The PD PHY binds its own
                  VBUS-sense to this SAME net for attach detection. Worst case
                  rides the live cable VBUS (20 V contract +5% = 21 V).
    +VBUS_OUT     FUSED output rail — the dVdT-charged board bulk starts here
                  (eFuse OUT + the 10u). What the rest of the board consumes.
    +VDD_LOGIC    always-on logic rail (3.3 V class): the FLT# pull-up AND the
                  USBLC6 data-ESD clamp reference. MUST be alive whenever the
                  fault can be read / the data pair is active — NEVER the inlet
                  VBUS (clamping a 3.3 V data pair to a 20 V rail is destructive).
    GND           ground.
    CHASSIS_GND   connector shell / earth island (shell pads only).
  ports (PORT):
    CC1, CC2      Type-C CC lines from the receptacle, crossing to the PD PHY
                  (FUSB302B owns Rd/Rp + BMC) and to the host CC-sense pins.
    USB_D_P/N     USB FS data pair to the host PHY, POST-ESD (USBLC6 channel
                  output). Typed usb_hs_pair, cable-flip paired.
    FLT_N         eFuse open-drain fault flag to a host expander port (pulled
                  to +VDD_LOGIC). expect= is project-specific (meta["expects"]).
"""

from __future__ import annotations

from schgen.core.model import Circuit
from schgen.core.subsystem import Meta

C0603 = "Capacitor_SMD:C_0603_1608Metric"
C1210 = "Capacitor_SMD:C_1210_3225Metric"
R0603 = "Resistor_SMD:R_0603_1608Metric"
TVS_FP = "Diode_SMD:D_SMB"

# ---- the abstract interface (the REUSE contract) ------------------------------
# Externally-visible net names a consuming project binds. RAILS classify as
# POWER/GROUND by name (the '+' prefix + GND/CHASSIS_GND), exactly as the bound
# carrier rails do, so a standalone build and a bound build share net classes.
RAILS = ("+VBUS_CONN", "+VBUS_OUT", "+VDD_LOGIC", "GND", "CHASSIS_GND")
PORTS = ("CC1", "CC2", "USB_D_P", "USB_D_N", "FLT_N")
INTERFACE = RAILS + PORTS

# Default power-tree draw note. pd_input is the board's power INLET (it sources
# rails rather than drawing a budgeted load), so the original carrier sheet
# declared no c.draws(); the note is provided for parity with the contract and a
# project may override the prose via meta["notes"]["draws"].
DRAWS_NOTE = ("USB-C PD inlet: sources +VBUS_OUT through the eFuse; the FLT# "
              "pull-up + USBLC6 clamp draw is <0.5 mA off +VDD_LOGIC")

# Nominal / worst-case voltage of each abstract RAIL — the subsystem's own
# electrical contract, NOT a board value. Used by the local test to derate the
# bypass caps without depending on a board power tree:
#   +VBUS_CONN / +VBUS_OUT both ride the live cable VBUS, worst case 21.0 V
#   (20 V PD contract + 5% source tolerance); +VDD_LOGIC is 3.3 V class. The
#   local test asserts every inlet/output cap is rated for the rail it sits on
#   (the 50 V X7R parts clear the 21 V rail with >2x margin).
RAIL_WORST_V = {
    "+VBUS_CONN": 21.0, "+VBUS_OUT": 21.0, "+VDD_LOGIC": 3.3,
    "GND": 0.0, "CHASSIS_GND": 0.0,
}


def circuit(meta: "Meta | dict | None" = None) -> Circuit:
    """Build the pd_input subsystem netlist with ABSTRACT port/rail names.

    ``meta`` is the STANDARD subsystem adapter contract (see
    :mod:`schgen.core.subsystem`) — a single dict a consuming project's adapter
    declares. Keys this subsystem reads (all optional; ``meta=None`` ->
    standalone abstract names for the local test):

      ``bind``    ``{abstract_name: project_net}`` rebinds the externally-visible
                  nets (the :data:`INTERFACE` names) to a project's real board
                  names. Applied last (order-preserving => byte-identical sheet).
                  The usb_hs_pair pair_with payload on USB_D_P/N is rebound by
                  the core, so type the pair in ABSTRACT names here.
      ``expects`` ``{abstract_port: deferral}`` attaches an EXPLICIT linker
                  deferral to a port — a project declares which of its sheets
                  will bind the deferred FLT_N (the eFuse fault expander port).
      ``notes``   ``{"draws": prose}`` the power-tree draw-note prose (a project
                  may cite its own dossier wording; defaults to :data:`DRAWS_NOTE`).
    """
    meta = Meta(meta)
    c = Circuit("pd_input", "Power inlet: USB-C PD 20V/3A + TPS26631 eFuse")
    c.use_part("TYPE-C-31-M-12", ref="J1")
    c.use_part("TPS26631PWPR", ref="U1")
    c.use_part("USBLC6-2SC6", ref="U2")        # FS data-pair ESD array

    # ---- receptacle VBUS -> +VBUS_CONN: TVS + the DS-minimum inlet 100n ----
    c.part("C1", "Device:C", "100n", C0603, LCSC="C14663")
    c.part("D1", "Device:D_Zener", "SMBJ22A", TVS_FP, LCSC="C10214")
    c.net("+VBUS_CONN", "J1.VBUS", "C1.1", "D1.1",     # both stacked pads
          "U1.IN", "U1.IN_SYS", "U1.UVLO")             # UVLO unused -> IN_SYS
    c.net("GND", "J1.GND", "C1.2", "D1.2")             # both stacked pads
    c.nc("U1.B_GATE", "U1.DRV")          # no reverse-blocking FET (Fig 8-8)

    # ---- eFuse straps: OVP divider, ILIM, dVdT, MODE/PGTH ------------------
    c.part("R3", "Device:R", "100k", R0603, LCSC="C25803")
    c.part("R4", "Device:R", "5.49k", R0603, LCSC="C188263")   # PD-1: widen OVP
    c.net("PD_OVP_SET", "U1.OVP", "R3.2", "R4.1")      # trip 23.06 V typ
    c.net("+VBUS_CONN", "R3.1")
    c.part("R5", "Device:R", "5.1k", R0603, LCSC="C23186")
    c.net("PD_ILIM_SET", "U1.ILIM", "R5.1")            # I_OL = 18/5.1k = 3.5 A
    c.part("C3", "Device:C", "47n", C0603, LCSC="C1622")
    c.net("PD_DVDT", "U1.dVdT", "C3.1")                # slew 1.02 V/ms
    c.net("GND", "U1.GND", "U1.EP", "U1.MODE",         # MODE=GND: auto-retry
          "U1.PGTH",                                   # PGTH=GND: dVdT-only
          "R4.2", "R5.2", "C3.2")
    c.nc("U1.SHDN#", "U1.IMON", "U1.PGOOD")            # unused per DS
    # FLT# (open-drain fault) -> host expander port. The TPS26631 is the board's
    # ONLY +VBUS_OUT protection device; pull-up to +VDD_LOGIC (an always-on
    # logic rail), NOT the inlet VBUS (an expander IO abs-max is well below the
    # 20 V contract). expect= (which sheet binds FLT_N) is project-specific and
    # carried by meta["expects"].
    c.part("R6", "Device:R", "100k", R0603, LCSC="C25803")
    c.port("FLT_N", "U1.FLT#", "R6.2", **meta.expect_kw("FLT_N"))
    c.net("+VDD_LOGIC", "R6.1")

    # ---- eFuse OUT -> +VBUS_OUT: the dVdT-charged board bulk starts here ----
    c.part("C2", "Device:C", "10u", C1210, LCSC="C596319")   # 50V X7R
    c.net("+VBUS_OUT", "U1.OUT", "C2.1")
    c.net("GND", "C2.2")

    # ---- CC lines to the PD PHY (usb_pd) + host CC sense -------------------
    c.port("CC1", "J1.CC1")
    c.port("CC2", "J1.CC2")

    # ---- FS data to the host PHY (device/dual-role port), cable-flip paired -
    # The PD PHY only protects the CC lines; the data pair reaches the host PHY
    # with no ESD without this. Insert a USBLC6-2SC6 array at the receptacle:
    # connector pads on one channel I/O (1/3), PHY-side on that channel's other
    # pin (6/4), VBUS->pin5, GND->pin2.
    c.net("PD_USB_DP_CONN", "J1.DP1", "J1.DP2", "U2.1")   # both flip pads -> ESD
    c.net("PD_USB_DN_CONN", "J1.DN1", "J1.DN2", "U2.3")
    c.port("USB_D_P", "U2.6")                             # PHY-side, post-ESD
    c.port("USB_D_N", "U2.4")
    c.port_type("USB_D_P", kind="usb_hs_pair", pair_with="USB_D_N")
    # ESD clamp rail = +VDD_LOGIC, NOT the 20 V inlet VBUS. The USBLC6-2SC6 pin 5
    # is the VBUS-referenced rail clamp (~5.25 V standoff / ~6 V breakdown). The
    # protected pair is a 3.3 V-domain FS data pair, so the clamp must reference
    # a <=5.25 V always-on rail — tying pin 5 to the inlet VBUS (20 V contract)
    # would hold that internal TVS in continuous avalanche: destructive AND it
    # defeats the data ESD function.
    c.net("+VDD_LOGIC", "U2.5")
    c.net("GND", "U2.2")

    # ---- SBU unused; shell to chassis -------------------------------------
    c.nc("J1.SBU1", "J1.SBU2")
    c.net("CHASSIS_GND", "J1.EH")                        # all four shell pads

    # coverage gate: probe the raw inlet AND the fused rail — the first bring-up
    # question is "is the fault before or after the eFuse?"
    c.testpoint("+VBUS_CONN")
    c.testpoint("+VBUS_OUT")
    c.waive_tp("CHASSIS_GND", "chassis island is probeable at every "
               "connector shell tab (USB-C/HDMI/magjack); no pad needed")

    # power-tree note (parity with the contract; pd_input sources rather than
    # draws a budgeted load — the original sheet declared no c.draws()).
    _ = meta.note("draws", DRAWS_NOTE)
    return meta.finish(c)            # applies meta["bind"] (if any), returns c
