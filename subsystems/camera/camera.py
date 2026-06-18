"""camera — Raspberry-Pi 15-pin FFC, 2-lane MIPI CSI-2 port (LIBRARY).

PROJECT-AGNOSTIC, REUSABLE subsystem (the ``subsystems/<name>/`` library layout;
exemplar: ``subsystems/usb_pd/``). A self-contained package — netlist + README +
SPICE subckt + local test — that declares its interface as ABSTRACT port + rail
names and knows NOTHING about any consuming board (no carrier net names, no
``carrier/nets.py`` / ``som_interface.json`` reads). A project consumes it by
calling :func:`circuit` with the STANDARD ``meta`` dict (see
:mod:`schgen.core.subsystem`): ``bind`` rebinds every externally-visible net to
its real board name, ``expects`` adds per-port linker deferrals, ``buses``
renames the camera-control I2C bus group, ``notes`` restores house-style prose.
Standalone (``meta=None``) it keeps the abstract names so this package's
``test_camera.py`` runs offline.

The reference design is the Amphenol SFW15R-1STE1LF 1.0 mm 15P bottom-contact
FFC (LCSC C3168538, contact orientation verified vs Amphenol drawing 10172241 —
see README "Connector"). FFC pin n = RPi camera FFC pin n. The HS RX side uses
the Xilinx XAPP894 "7-series + external passives" topology: a fixed external
100R differential termination per D-PHY pair, placed at the FPGA/SoM-connector
END of each trace (NOT at the FFC).

ABSTRACT INTERFACE (see README.md for the full table) — the names a project
binds:

  rails (POWER/GROUND):
    +VDD_CAM   the gated camera module rail (3.3 V class). A project supplies a
               GATED rail here so a powered-down camera is not back-fed through
               its own I2C bus pull-ups (the pull-ups land on this rail). 100n +
               10u local bypass at the connector live in this subsystem.
    GND        ground (FFC grounds + mounting-plate tabs).
  ports (PORT):
    CSI_D0_P/N, CSI_D1_P/N, CSI_CLK_P/N   the MIPI CSI-2 D-PHY differential
               lanes to the host receiver, each typed diff_pair @100R with its
               external 100R termination (R1-R3) carried here. D-PHY pairs are
               NOT polarity-swappable (P->P, N->N).
    CAM_SCL/CAM_SDA   the camera-control I2C bus (MIPI CCI class; FFC 13/14),
               with 4k7 pull-ups to +VDD_CAM in this subsystem.
    CAM_EN     module power-enable / shutdown (FFC 11; RPi CAM_GPIO0).
    CAM_LED    LED indicator (FFC 12; RPi CAM_GPIO1, v1-module only — kept
               routed).

DESIGN NOTES (datasheet + reference-design contract): see README.md
"Design notes" — incl. CAM-1 (static 100R vs D-PHY Low-Power signalling) and the
XAPP894 LP resistor-divider DNP stuffing option, both off this FFC sheet.

Stock FFC symbol/footprint + MPN/LCSC come from the global parts library entry
``SFW15R-1STE1LF`` (LCSC C3168538); the connector's bare-number FFC pins stay
numeric. The netlist gate proves KiCad sees every FFC pad.
"""

from __future__ import annotations

from schgen.core.model import Circuit
from schgen.core.subsystem import Meta

R0603 = "Resistor_SMD:R_0603_1608Metric"
C0603 = "Capacitor_SMD:C_0603_1608Metric"
C0805 = "Capacitor_SMD:C_0805_2012Metric"

# ---- the abstract interface (the REUSE contract) ------------------------------
# Externally-visible net names a consuming project binds. RAILS classify as
# POWER/GROUND by name (the '+' prefix + GND), exactly as the bound carrier rails
# do, so a standalone build and a bound build share net classes.
RAILS = ("+VDD_CAM", "GND")
PORTS = (
    "CSI_D0_P", "CSI_D0_N",
    "CSI_D1_P", "CSI_D1_N",
    "CSI_CLK_P", "CSI_CLK_N",
    "CAM_SCL", "CAM_SDA",
    "CAM_EN", "CAM_LED",
)
INTERFACE = RAILS + PORTS

# The camera-control I2C bus this port sits on (MIPI CCI class, 400 kHz). The bus
# NAME is a project-level grouping (the linker groups SCL/SDA by it) and may be
# overridden via meta["buses"]["i2c"] so a consuming board can place this camera
# on one of its named buses; the default is the abstract name for standalone use.
I2C_BUS = "CAM_CCI"
I2C_SPEED_HZ = 400_000

# Default expect-deferral hints for the abstract ports when a project does NOT
# supply its own via meta["expects"]. These are GENERIC (the destination is a
# host connector/receiver) — a board overrides them with its own sheet wording.
EXPECT_CSI = "host MIPI CSI-2 receiver (diff_pair @100R, LVDS-class lanes)"
EXPECT_CTRL = "host camera-control bank (3.3 V logic)"

# Default power-tree draw note (RPi V2/IMX219 module typ ~250 mA incl. the I2C
# pull-ups). A project may override the prose via meta["notes"]["draws"] to cite
# its own dossier wording.
DRAWS_NOTE = "RPi camera module budget (V2/IMX219 typ ~250 mA incl. I2C pull-ups)"
DRAWS_A = 0.300

# (pair, P-side FFC pin, N-side FFC pin, termination ref, ESD array ref, P-IO,
# N-IO) — FFC pin n = RPi pin n (note: N before P on the FFC). The ESD columns
# map each CSI line to a low-cap TI TPD4E02B04DQAR channel (4-ch arrays): U1
# covers D0+D1 (4 ch), U2 covers CLK (IO1/IO2; IO3/IO4 spare). Abstract CSI lane
# names; the termination refs + pin numbers + termination value are the faithful
# reference design.
PAIRS = (
    ("CSI_D0", "3", "2", "R1", "U1", "IO1", "IO2"),
    ("CSI_D1", "6", "5", "R2", "U1", "IO3", "IO4"),
    ("CSI_CLK", "9", "8", "R3", "U2", "IO1", "IO2"),
)


def circuit(meta: "Meta | dict | None" = None) -> Circuit:
    """Build the camera subsystem netlist with ABSTRACT port/rail names.

    ``meta`` is the STANDARD subsystem adapter contract (see
    :mod:`schgen.core.subsystem`) — a single dict a consuming project's adapter
    declares. Keys this subsystem reads (all optional; ``meta=None`` ->
    standalone abstract names for the local test):

      ``bind``    ``{abstract_name: project_net}`` rebinds the externally-visible
                  nets (the :data:`INTERFACE` names) to a project's real board
                  names. Applied last (order-preserving => byte-identical sheet).
      ``expects`` ``{abstract_port: deferral}`` attaches an EXPLICIT linker
                  deferral to a port — a project declares which of its sheets
                  will bind a deferred port (e.g. the generated SoM-connector
                  sheet for the CSI lanes / control lines).
      ``buses``   ``{"i2c": name}`` the camera-control I2C bus-group NAME for
                  SCL/SDA (a project-level grouping; defaults to the abstract
                  :data:`I2C_BUS`).
      ``notes``   ``{"draws": prose}`` the power-tree draw-note prose (a project
                  may cite its own dossier wording; defaults to
                  :data:`DRAWS_NOTE`).

    ``buses`` / ``notes`` let a project reproduce its own house-style metadata
    (bus name, dossier prose) WITHOUT the library knowing any board specifics —
    keeping the library project-agnostic while a consumer's derived artifacts
    (constraints CSV, power-tree note) stay byte-stable.
    """
    meta = Meta(meta)
    i2c_bus = meta.bus("i2c", I2C_BUS)
    draws_note = meta.note("draws", DRAWS_NOTE)
    c = Circuit("camera", "RPi camera port: 2-lane MIPI CSI-2 (15P FFC)")
    c.use_part("SFW15R-1STE1LF", ref="J1")   # bare-number FFC pins stay numeric

    # ---- CSI lanes: FFC -> 100R host-side terminations -> diff pairs -------
    # R1-R3 stay POPULATED: HS D-PHY needs the 100R diff term and a 7-series HR-
    # bank RX cannot gate DIFF_TERM (CAM-1, README). LP observability is the
    # XAPP894 LP-divider DNP stuffing option, off this FFC sheet (README).
    # The CSI lanes' linker deferral lives on the diff_pair port_type (NOT on
    # the bare port), so it is sourced from meta["expects"] for the P-side and
    # applied reciprocally to N by port_type(); a project supplies the real
    # destination (else the generic EXPECT_CSI default for standalone use).
    # low-cap MIPI CSI ESD (user-requested, 2026-06-18): two TI TPD4E02B04DQAR
    # 4-ch arrays (LCSC C106794, 0.2 pF/line typ << the D-PHY budget, 8 kV
    # contact / IEC 61000-4-2 — the SAME part hdmi_rx uses on TMDS) shunt-clamp
    # the 6 CSI D-PHY lines jack -> host. DC-coupled shunt TAPS, not series: each
    # ESD IOn is just added to the existing CSI port net, so the netlist proves
    # {J1.pin, term, U.IOn} per line. GND-referenced (no VCC) -> the clamp is
    # valid even when the gated +VDD_CAM is off and cannot back-power it (LAW 0).
    c.use_part("TPD4E02B04DQAR", ref="U1")
    c.use_part("TPD4E02B04DQAR", ref="U2")
    for name, p_pin, n_pin, term, esd, io_p, io_n in PAIRS:
        c.part(term, "Device:R", "100R", R0603, LCSC="C22775")
        c.port(f"{name}_P", f"J1.{p_pin}", f"{term}.1", f"{esd}.{io_p}")
        c.port(f"{name}_N", f"J1.{n_pin}", f"{term}.2", f"{esd}.{io_n}")
        c.port_type(f"{name}_P", kind="diff_pair", pair_with=f"{name}_N",
                    impedance=100,
                    expect=meta.expects.get(f"{name}_P", EXPECT_CSI))
    c.net("GND", "U1.GND", "U2.GND")     # both GND pads (3, 8) per array
    # spare pads by NUMBER (the 'NC' name spans 4 USON-10 pads 6/7/9/10): U1's
    # four NC pads; U2 also leaves IO3 (pad 4) + IO4 (pad 5) unused (CLK uses
    # only IO1/IO2) plus its four NC pads.
    c.nc("U1.6", "U1.7", "U1.9", "U1.10")
    c.nc("U2.4", "U2.5", "U2.6", "U2.7", "U2.9", "U2.10")

    # ---- control: camera I2C + enable/LED (3.3 V logic) --------------------
    c.part("R4", "Device:R", "4k7", R0603, LCSC="C23162")
    c.part("R5", "Device:R", "4k7", R0603, LCSC="C23162")
    c.port("CAM_SCL", "J1.13", "R4.2", kind="i2c", role="scl",
           bus=i2c_bus, speed_hz=I2C_SPEED_HZ, **meta.expect_kw("CAM_SCL"))
    c.port("CAM_SDA", "J1.14", "R5.2", kind="i2c", role="sda",
           bus=i2c_bus, speed_hz=I2C_SPEED_HZ, **meta.expect_kw("CAM_SDA"))
    c.net("+VDD_CAM", "R4.1", "R5.1")
    c.port("CAM_EN", "J1.11", **meta.expect_kw("CAM_EN"))
    c.port("CAM_LED", "J1.12", **meta.expect_kw("CAM_LED"))

    # ---- power: gated +VDD_CAM at the connector + grounds ------------------
    c.part("C1", "Device:C", "100n", C0603, LCSC="C14663")
    c.part("C2", "Device:C", "10u", C0805, LCSC="C15850")
    c.net("+VDD_CAM", "J1.15", "C1.1", "C2.1")
    c.net("GND", "J1.1", "J1.4", "J1.7", "J1.10", "C1.2", "C2.2",
          "J1.16", "J1.17")

    # round-4 coverage gate: the camera I2C bus + the module enable line (every
    # EN is probeable, bring-up philosophy)
    c.testpoint("CAM_SCL")
    c.testpoint("CAM_SDA")
    c.testpoint("CAM_EN")

    # power-tree budget: RPi V2 module ~250 mA typ, budget 300 mA incl. the I2C
    # pull-ups.
    c.draws("+VDD_CAM", DRAWS_A, draws_note)

    # CSI lanes are typed in abstract names above; Circuit.bind (via meta.finish)
    # rebinds each diff_pair's pair_with complement through the rename map, so the
    # bound pairs reference their real complement and the derived board artifacts
    # (layout_constraints.csv pair_with / length-match group, the XDC pair) stay
    # byte-stable. The library is a pure rename-equivalent — no pair fixup here.
    return meta.finish(c)
