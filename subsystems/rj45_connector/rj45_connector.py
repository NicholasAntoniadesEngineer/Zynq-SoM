"""rj45_connector — plain 8P8C RJ45 jack (NO integrated magnetics) (LIBRARY).

PROJECT-AGNOSTIC, REUSABLE subsystem (the ``subsystems/<name>/`` library layout;
see ``subsystems/usb_pd/`` for the worked exemplar and ``subsystems/ethernet/``
for the diff-pair sibling whose MEDIA-side pairs face THIS jack). It declares its
interface as ABSTRACT port + rail names and knows NOTHING about any consuming
board — no carrier net names. A project consumes it by calling :func:`circuit`
with the STANDARD ``meta`` dict (see :mod:`schgen.core.subsystem`): ``bind``
rebinds every externally-visible net to its real board name, ``expects`` adds
per-port linker deferrals, ``notes`` restores house-style prose. Standalone
(``meta=None``) it keeps the abstract names so this package's
``test_rj45_connector.py`` runs offline.

The line-side RJ45 jack downstream of an Ethernet magnetics block (the
``ethernet`` subsystem carries DISCRETE 1000BASE-T magnetics + Bob-Smith
termination on a separate sheet), so THIS jack is a PLAIN transformerless 8P8C —
the line-side MDI pairs come straight off the magnetics secondary and land on the
eight contacts.

Part — KH-5224-8P8C-D (Shenzhen Kinghelm), LCSC C2828085, live-verified on the
JLC parts API 2026-06-13:
  - JLC class Extended (RJ45 jacks have no Basic stock on JLC — every 8P8C in the
    catalogue is Extended; this is the highest-stock plain shielded LED jack),
    stock 239, ~$0.34 @ 1.
  - Confirmed PLAIN (no transformer): the EasyEDA CAD pin table is 13 pins —
    1..8 = the eight T568 contacts, 9/10 = left LED (LED-L+/LED-L-), 11/12 =
    right LED (LED-R+/LED-R-), 13 = SHELL. A magjack would expose 16+
    transformer/centre-tap pins; this has none. Through-hole, shielded.

Contact -> MDI mapping is the IEEE 802.3 / TIA-568 1000BASE-T order:
  BI_DA = contacts 1,2  -> RJ45_MDI0_P/N
  BI_DB = contacts 3,6  -> RJ45_MDI1_P/N
  BI_DC = contacts 4,5  -> RJ45_MDI2_P/N
  BI_DD = contacts 7,8  -> RJ45_MDI3_P/N
These eight nets are the line-side MDI pairs — the same pairs the ``ethernet``
magnetics subsystem exposes media-side (MXn). Declaring them here as PORTs gives
that subsystem its peer, so its media-side ``expect=`` deferrals resolve to
BOUND on both sheets once a project binds the two to the same real nets.

LEDs — the two LEDs are INTEGRATED in the jack housing (the symbol pins
LED-L+/LED-L-/LED-R+/LED-R- are the internal LED anodes/cathodes, so NO external
discrete LED part is added — that would be two LEDs in series). The magnetics
block exposes no PHY link/activity logic on this sheet (the magnetics are
passive; a PHY's LED pins, if any, live on the host/SoM side), so each jack LED
is driven as a steady PORT-PRESENT indication off the always-on LED supply rail
through one 330R (~(3.3-2.0)/330 ~= 4 mA): LED-L+/- and LED-R+/- both lit.
Documented honestly: this is a power-on indicator, NOT a PHY-driven link/act
blink. RJ45_LED_L / RJ45_LED_R are PRIVATE internal SIGNAL wiring (the R -> LED
anode node) — never part of the abstract interface.

Shield/shell (pin 13) -> CHASSIS_GND, the chassis island a board's isolation
barrier bonds to (kept separate from signal GND, star-bonded by the consuming
board).

This sheet also hosts four M3 corner mounting holes (H1..H4), each a plated,
BOM-excluded hole bonded to CHASSIS_GND — co-located with the shield entry so
every CHASSIS_GND fab-art item lives on one sheet.
"""

from __future__ import annotations

from schgen.core.model import Circuit
from schgen.core.subsystem import Meta

R_FP = "Resistor_SMD:R_0603_1608Metric"

LCSC_330R = "C23138"   # 0603WAF3300T5E, JLC Basic, stock 1.36M (live 2026-06-13)

# ---- the abstract interface (the REUSE contract) ------------------------------
# Externally-visible net names a consuming project binds. The rails are the LED
# indicator supply (+VLED, a POWER rail by the leading '+'), signal GND, and the
# chassis-ground island (CHASSIS_GND, a GROUND, kept separate from signal GND).
# The PORTS are the four line-side differential MDI pairs that cross the sheet
# boundary to the magnetics. The two housing-LED anode nodes (RJ45_LED_L/R) are
# PRIVATE SIGNAL wiring and are never part of the contract.
RAILS = ("+VLED", "GND", "CHASSIS_GND")
# line-side (magnetics-facing) differential MDI pairs
MDI_PORTS = (
    "RJ45_MDI0_P", "RJ45_MDI0_N",
    "RJ45_MDI1_P", "RJ45_MDI1_N",
    "RJ45_MDI2_P", "RJ45_MDI2_N",
    "RJ45_MDI3_P", "RJ45_MDI3_N",
)
PORTS = MDI_PORTS
INTERFACE = RAILS + PORTS

# contact pin number -> line-side MDI PORT net (IEEE 802.3 / TIA-568 order).
MDI_CONTACTS = {
    1: "RJ45_MDI0_P", 2: "RJ45_MDI0_N",   # BI_DA
    3: "RJ45_MDI1_P", 6: "RJ45_MDI1_N",   # BI_DB
    4: "RJ45_MDI2_P", 5: "RJ45_MDI2_N",   # BI_DC
    7: "RJ45_MDI3_P", 8: "RJ45_MDI3_N",   # BI_DD
}

# Default power-tree draw note (two 330R/+VLED indicator LEDs, ~8 mA total off
# the LED supply). A project may override the prose via meta["notes"]["draws"].
DRAWS_NOTE = "RJ45 housing LEDs (2x 330R port-present indicator)"
DRAWS_A = 0.008


def circuit(meta: "Meta | dict | None" = None) -> Circuit:
    """Build the rj45_connector subsystem netlist with ABSTRACT port/rail names.

    ``meta`` is the STANDARD subsystem adapter contract (see
    :mod:`schgen.core.subsystem`) — a single dict a consuming project's adapter
    declares. Keys this subsystem reads (all optional; ``meta=None`` ->
    standalone abstract names for the local test):

      ``bind``    ``{abstract_name: project_net}`` rebinds the externally-visible
                  nets (the :data:`INTERFACE` names) to a project's real board
                  names. Applied last (order-preserving => byte-identical sheet).
      ``expects`` ``{abstract_port: deferral}`` attaches an EXPLICIT linker
                  deferral to a port — a project declares which of its sheets
                  will bind a deferred port (e.g. the magnetics sheet that binds
                  the line-side MDI pairs). Only the P net of a pair need be
                  named; the reciprocal N inherits the deferral.
      ``notes``   ``{"draws": prose}`` the power-tree draw-note prose (a project
                  may cite its own dossier wording; defaults to :data:`DRAWS_NOTE`).

    There is no named bus, so ``buses`` carries no library default here.
    """
    meta = Meta(meta)
    draws_note = meta.note("draws", DRAWS_NOTE)
    c = Circuit("rj45_connector", "RJ45 8P8C jack (plain, ext. magnetics)")
    j1 = c.use_part("KH-5224-8P8C-D", ref="J1")

    # eight T568 contacts -> line-side MDI pairs (the magnetics sheet's deferred
    # media-side pairs; same-named PORT on both sides binds them on a board). The
    # P net of each pair may carry a project's linker deferral via meta.expect_kw
    # (a project declares which sheet binds these); the reciprocal N inherits it.
    for pin, net in MDI_CONTACTS.items():
        c.port(net, f"J1.{pin}")
    for n in range(4):
        c.port_type(f"RJ45_MDI{n}_P", kind="diff_pair",
                    pair_with=f"RJ45_MDI{n}_N", impedance=100,
                    **meta.expect_kw(f"RJ45_MDI{n}_P"))

    # the jack's two INTEGRATED LEDs as a steady port-present indicator off the
    # always-on +VLED rail, 330R each (~(3.3-2.0)/330 ~= 4 mA). Drive the housing
    # LED anode (LED-x+) from +VLED via the series R; cathode (LED-x-) to GND. NO
    # discrete Device:LED — the diode lives inside J1 (see docstring).
    rl = c.part("R1", "Device:R", "330R", R_FP, LCSC=LCSC_330R)
    c.net("+VLED", f"{rl.ref}.1")
    c.net("RJ45_LED_L", f"{rl.ref}.2", "J1.9")          # 330R -> LED-L+ (anode)
    c.net("GND", "J1.10")                               # LED-L- (cathode)
    rr = c.part("R2", "Device:R", "330R", R_FP, LCSC=LCSC_330R)
    c.net("+VLED", f"{rr.ref}.1")
    c.net("RJ45_LED_R", f"{rr.ref}.2", "J1.11")         # 330R -> LED-R+ (anode)
    c.net("GND", "J1.12")                               # LED-R- (cathode)

    # shield/shell -> chassis island (a separate net from any signal GND)
    c.net("CHASSIS_GND", "J1.13")

    # 4x M3 corner mounting holes -> CHASSIS_GND (plated, double as assembly
    # tooling holes). Real netlisted copper (H1..H4, BOM-excluded); placed here,
    # the shield-entry sheet, so all CHASSIS_GND fab-art lives in one place and
    # the chassis bond stays netlist-verifiable. mounting_hole() rejects any
    # non-GROUND net (LAW 0: a hole is a chassis bond, never a rail).
    for _ in range(4):
        c.mounting_hole("CHASSIS_GND")

    # power-tree budget: two 330R/+VLED indicator LEDs (~8 mA total) off +VLED
    c.draws("+VLED", DRAWS_A, draws_note)
    return meta.finish(c)          # applies meta["bind"] (if any), returns c
