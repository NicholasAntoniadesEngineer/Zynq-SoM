"""microsd — SD card slot behind a TXS02612 SDIO level translator (LIBRARY).

PROJECT-AGNOSTIC, REUSABLE subsystem (see subsystems/usb_pd/ for the worked
exemplar). A microSD push-push slot wired to a standard 3.3 V SD card, fed
through a TI **TXS02612** auto-direction SDIO level translator so a lower-voltage
host (the translator's A-side / VCCA domain) can talk to the fixed-3.3 V card
(the B0-side / VCCB domain). Card-side anti-float pulls, a TPD6E001 6-channel
ESD array across the user-facing card lines, and a card-detect report complete
the cell. It declares its interface as ABSTRACT port + rail names and knows
NOTHING about any consuming board — no board net names. A project consumes it by
calling :func:`circuit` with the STANDARD ``meta`` dict (see
:mod:`schgen.core.subsystem`): ``bind`` rebinds every externally-visible net to
its real board name, ``expects`` adds per-port linker deferrals, ``notes``
restores house-style prose. Standalone (``meta=None``) it keeps the abstract
names so this package's ``test_microsd.py`` runs offline.

The TXS02612 is a VOLTAGE-LEVEL TRANSLATOR with TWO independent supply rails —
each side is a DISTINCT abstract rail a project binds:
  +VDD_HOST   VCCA, the HOST-side reference (the lower host signalling voltage;
              the abstract host level is :data:`HOST_LEVEL_V`). Typically a few
              uA-class draw.
  +VDD_CARD   VCCB(0/1), the CARD-side rail — also feeds the slot VDD, every
              card-line pull-up, the ESD-array VCC and the bulk cap. The card is
              wired at a FIXED card-side voltage (see SD-1 below).

ABSTRACT INTERFACE (see README.md for the full table):

  rails (POWER/GROUND):
    +VDD_HOST   TXS02612 VCCA host-side reference (host signalling level).
    +VDD_CARD   TXS02612 VCCB card-side rail (slot VDD + pulls + ESD VCC + bulk).
    GND         ground.
  ports (PORT):
    SD_CLK, SD_CMD, SD_D0..SD_D3   the SD bus on the HOST (A) side of the
                  translator (typed sd_bus at :data:`HOST_LEVEL_V`). The card-side
                  twins are PRIVATE internal SIGNAL nets (SD_CARD_*) — never
                  externally bound.
    CD_N          card-detect: the slot switch closes to GND, pulled up, reported
                  to the host. Active-low presence indication.

DESIGN NOTES (datasheet + bring-up contract): see README.md "Design notes".

SD-2 (card-side pull value) — R1..R5 sit on the TXS02612's ACTIVE B0 ONE-SHOT
outputs, which already hold an internal pull-up (4 kohm high / 40 kohm low; TI
SCEA054A fig.1). A 10k external pull parallels the internal 40k while the output
drives low, lifting VOL and softening edges — SCEA054A Table 1 measures VOL
29 mV (no pull) -> 169 mV (~10k) -> 38 mV (100k); the note's guidance is
">50 kohm beneficial". So R1..R5 are 100k (LCSC C25803): a visible SD-spec
anti-float pull kept inside TI's >50k band. R6 (card-detect, NOT a TXS output)
stays 10k.

SD-1 (operating-mode note) — the card side is wired at a FIXED 3.3 V-class
rail, with no 1.8 V card-rail switch, so this slot supports only DEFAULT-speed
and HIGH-SPEED SD modes (3.3 V signalling); UHS-I (SDR50/SDR104/DDR50), which
mandates a 1.8 V signalling voltage switch (S18), is NOT available here. A host
SDIO controller MUST keep voltage-switching disabled — do NOT request S18 (CMD11
/ 1.8 V switch): the card rail is permanently 3.3 V, so a host that switched to
1.8 V would lose the card. The TPD6E001 VCC sets its clamp reference; bias it to
the card-side rail (not floating) so the clamp references the card rail rather
than a floating worst-case (TI SLLS546).
"""

from __future__ import annotations

from schgen.core.model import Circuit
from schgen.core.subsystem import Meta

R0603 = "Resistor_SMD:R_0603_1608Metric"
C0603 = "Capacitor_SMD:C_0603_1608Metric"
C0805 = "Capacitor_SMD:C_0805_2012Metric"

# ---- the abstract interface (the REUSE contract) ------------------------------
# Externally-visible net names a consuming project binds. RAILS classify as
# POWER/GROUND by name (the '+' prefix + GND), exactly as the bound carrier
# rails do, so a standalone build and a bound build share net classes.
RAILS = ("+VDD_HOST", "+VDD_CARD", "GND")
PORTS = ("SD_CLK", "SD_CMD", "SD_D0", "SD_D1", "SD_D2", "SD_D3", "CD_N")
INTERFACE = RAILS + PORTS

# The HOST-side (A / VCCA) signalling level — the translator's own electrical
# contract for the host domain, NOT a board value (a project may run +VDD_HOST
# at any host voltage the TXS02612 supports). Used to type the SD bus ports.
HOST_LEVEL_V = 1.8

# Worst-case voltage of each abstract RAIL — the subsystem's own electrical
# contract, NOT a board value (a project may run either rail at any voltage the
# TXS02612 supports). +VDD_HOST is the host-side reference (1.8 V class here);
# +VDD_CARD is the fixed 3.3 V-class card rail (SD-1). Used by the local test to
# derate the bypass caps without depending on a board power tree.
RAIL_WORST_V = {"+VDD_HOST": 1.8, "+VDD_CARD": 3.3, "GND": 0.0}

# Default power-tree draw notes. A project may override the prose via
# meta["notes"]["draws_card"] / ["draws_host"] to cite its own dossier wording.
DRAWS_CARD_NOTE = ("SD card write burst ~200 mA + pull-ups + TXS02612 VCCB")
DRAWS_CARD_A = 0.250
DRAWS_HOST_NOTE = "TXS02612 VCCA (host-side level)"
DRAWS_HOST_A = 0.005

# Abstract SD lane -> (TXS A-side pin, TXS B0-side pin, slot pin, ESD channel).
# The card-side net of each lane is a PRIVATE internal SIGNAL net derived from
# the lane suffix (SD_CARD_<suffix>), so the card side stays library-private.
LANES = {
    "SD_CLK": ("CLKA", "CLKB0", "CLK(SCLK)", "IO1"),
    "SD_CMD": ("CMDA", "CMDB0", "CMD(DI)", "IO2"),
    "SD_D0": ("DAT0A", "DAT0B0", "DAT0(D0)", "IO3"),
    "SD_D1": ("DAT1A", "DAT1B0", "DAT1(RSV)", "IO4"),
    "SD_D2": ("DAT2A", "DAT2B0", "DAT2(RSV)", "IO5"),
    "SD_D3": ("DAT3A", "DAT3B0", "CDDAT3(CS)", "IO6"),
}
PULLED = ("SD_CMD", "SD_D0", "SD_D1", "SD_D2", "SD_D3")


def circuit(meta: "Meta | dict | None" = None) -> Circuit:
    """Build the microsd subsystem netlist with ABSTRACT port/rail names.

    ``meta`` is the STANDARD subsystem adapter contract (see
    :mod:`schgen.core.subsystem`) — a single dict a consuming project's adapter
    declares. Keys this subsystem reads (all optional; ``meta=None`` ->
    standalone abstract names for the local test):

      ``bind``    ``{abstract_name: project_net}`` rebinds the externally-visible
                  nets (the :data:`INTERFACE` names) to a project's real board
                  names. Applied last (order-preserving => byte-identical sheet).
      ``expects`` ``{abstract_port: deferral}`` attaches an EXPLICIT linker
                  deferral to a port (e.g. CD_N binding on a connector sheet).
      ``notes``   ``{"draws_card"/"draws_host": prose}`` the power-tree draw-note
                  prose (a project may cite its own dossier wording; defaults to
                  :data:`DRAWS_CARD_NOTE` / :data:`DRAWS_HOST_NOTE`).
    """
    meta = Meta(meta)
    draws_card_note = meta.note("draws_card", DRAWS_CARD_NOTE)
    draws_host_note = meta.note("draws_host", DRAWS_HOST_NOTE)
    c = Circuit("microsd", "microSD slot (1.8V SoM <-> 3.3V card, TXS02612)")
    c.use_part("TXS02612RTWR", ref="U1")
    c.use_part("TF-01A", ref="J1")
    c.use_part("TPD6E001RSER", ref="U2")

    # ---- lanes: HOST(A side, port) -> TXS -> card(B0 side) + ESD ----------
    # The card-side net is a PRIVATE internal SIGNAL net (SD_CARD_<suffix>),
    # never externally bound — only the host-side port is part of the interface.
    for net, (a, b0, slot, esd) in LANES.items():
        c.port(net, f"U1.{a}", **meta.expect_kw(net))
        card = f"SD_CARD_{net.split('_', 1)[1]}"
        c.net(card, f"U1.{b0}", f"J1.{slot}", f"U2.{esd}")
        c.port_type(net, kind="sd_bus", level_v=HOST_LEVEL_V)

    # card-side anti-float pull-ups. SD-2 (electrical audit): these sit on the
    # TXS02612's ACTIVE B0 ONE-SHOT outputs, which already carry an internal
    # pull-up (4 kohm driving high / 40 kohm driving low; TI SCEA054A fig.1).
    # An external pull PARALLELS that internal 40 kohm while driving low, lifting
    # VOL and degrading edges. SCEA054A Table 1 (same TXS one-shot architecture)
    # measures this directly: VOL = 29 mV (no external R) -> 169 mV at ~10 kohm
    # -> 38 mV at 100 kohm; the note's rule is ">50 kohm beneficial". So a 10k
    # pull here was the wrong value. RAISE to 100k (LCSC C25803): keeps a visible
    # SD-spec anti-float pull while staying in TI's >50 kohm band (VOL ~38 mV,
    # within ~9 mV of the no-pull baseline) — the zero-regret fix vs deleting the
    # pulls (the TXS internal pulls already cover anti-float). R6 card-detect is
    # NOT on a TXS output and stays 10k.
    pull_pins = []
    for i, net in enumerate(PULLED, start=1):
        ref = f"R{i}"
        c.part(ref, "Device:R", "100k", R0603, LCSC="C25803")
        card = f"SD_CARD_{net.split('_', 1)[1]}"
        c.net(card, f"{ref}.2")
        pull_pins.append(f"{ref}.1")

    # card detect: switch closes to GND, pulled up, reported to the host
    c.part("R6", "Device:R", "10k", R0603, LCSC="C25804")
    c.port("CD_N", "J1.CD", "R6.2", **meta.expect_kw("CD_N"))
    pull_pins.append("R6.1")

    # ---- power -------------------------------------------------------------
    c.net("+VDD_HOST", "U1.VCCA")                # VCCA, host-side level
    for cap in c.decouple("U1.VCCA", "100n"):    # C14663 Basic, 20.6M stock
        cap.fields["LCSC"] = "C14663"
    # card-side rail +VDD_CARD (a POWER net with its own symbol): slot VDD +
    # both VCCB + every pull-up + bulk + ESD-array VCC (SD-1)
    c.part("C2", "Device:C", "100n", C0603, LCSC="C14663")
    c.part("C3", "Device:C", "22u", C0805, LCSC="C45783")
    c.net("+VDD_CARD", "J1.VDD", "U1.VCCB0", "U1.VCCB1", "C2.1", "C3.1",
          "U2.VCC", *pull_pins)
    c.net("GND", "C2.2", "C3.2")
    # SD-1 (electrical audit): the TPD6E001 VCC sets its clamp reference; a
    # floating VCC gives the WORST-CASE clamp on the user-facing card lines
    # (TI SLLS546). Bias it to the card-side rail +VDD_CARD and bypass locally.
    for cap in c.decouple("U2.VCC", "100n"):     # C14663 Basic, 18.1M stock
        cap.fields["LCSC"] = "C14663"

    # SEL low selects port B0; EP + both TXS GND pins + slot VSS/GND pads
    c.net("GND", "U1.SEL", "U1.EP", "U1.GND",
          "J1.VSS", "J1.GND", "U2.GND")

    # unused TXS port B1 + ESD spares
    c.nc("U1.DAT2B1", "U1.DAT3B1", "U1.CMDB1", "U1.CLKB1",
         "U1.DAT0B1", "U1.DAT1B1")
    c.nc("U2.NC")                  # NC pads 4/9 only (VCC biased per SD-1)

    # round-4 coverage gate: SD CMD/CLK probed on the host (A) side
    # (where the level translator's timing actually matters)
    c.testpoint("SD_CMD")
    c.testpoint("SD_CLK")

    # power-tree budget (round 4): SD card 3.3 V class up to ~200 mA write
    # bursts (SD phys spec) + 5x 100k card pulls (SD-2) + 1x 10k card-detect +
    # TXS VCCB; the TXS02612 VCCA side is uA-class but budgeted
    c.draws("+VDD_CARD", DRAWS_CARD_A, draws_card_note)
    c.draws("+VDD_HOST", DRAWS_HOST_A, draws_host_note)
    return meta.finish(c)            # applies meta["bind"] (if any), returns c
