"""hdmi_rx — HDMI-A sink: connector + TMDS-RX ESD + 24C02-class EDID EEPROM (LIBRARY).

PROJECT-AGNOSTIC, REUSABLE subsystem (the ``subsystems/<name>/`` library layout;
see ``subsystems/hdmi_tx/`` for the source-side sibling and ``subsystems/usb_pd/``
for the worked exemplar). It declares its interface as ABSTRACT port + rail names
and knows NOTHING about any consuming board — no carrier net names. A project
consumes it by calling :func:`circuit` with the STANDARD ``meta`` dict (see
:mod:`schgen.core.subsystem`): ``bind`` rebinds every externally-visible net to
its real board name, ``expects`` adds per-port linker deferrals, ``notes``
restores house-style prose. Standalone (``meta=None``) it keeps the abstract
names so this package's ``test_hdmi_rx.py`` runs offline.

Sink-side reference circuit (mirrors hdmi_tx's connector front end, RX
orientation). The four TMDS lanes run DC-coupled connector -> the receiver's
FPGA/SoC HR-bank inputs (a 3.3 V class TMDS_33 bank in the reference build); the
SoM-facing TMDS lanes (TMDS_RX_*) are the externals, and they reach the receiver
via two low-cap GND-referenced ESD arrays at the jack.

SI-HDMIRX-TERM (electrical) — TMDS SINK TERMINATION: an HDMI/DVI sink MUST
present a 50 ohm-to-AVCC source-termination per single-ended line (the standard
2x 49.9 ohm/pair to a 3.3 V AVCC node + decoupling, 8 R for the 4 pairs). A
7-series HR (high-range) bank CANNOT supply it on-die (only HP banks implement
DIFF_TERM; TMDS_33 is HR-only and UNTERMINATED, UG471 SelectIO), so external sink
termination is REQUIRED — but it must sit at the RECEIVER end of the line (next
to the bank pins, on the consuming project's connector sheet), NOT at this HDMI
connector. Resistors here would stub the far end of the line and reflect, and the
8 termination R's all converging on one AVCC node while the TMDS lines exit as
ports trips the zero-crossing visual gate. So the populated 2x49.9 ohm/pair-to-
AVCC network is a DOCUMENTED, MANDATORY layout requirement carried at the
receiver, not auto-placed on THIS sheet. LAYOUT NOTE (PCB): per TMDS pair, fit
2x 49.9 ohm 0603 1% (e.g. YAGEO RC0603FR-0749R9L, LCSC C114625) from each single-
ended line to a local AVCC = 3.3 V plane island, AVCC bypassed with 100 nF + 1 uF
near the bank; 8 R total for D2/D1/D0/CLK, at the FPGA bank balls.

HDMIRX-1 — RX TMDS ESD: the RX receptacle is user-facing and the four TMDS pairs
reach the receiver with no ESD of their own. The part is the TI TPD4E02B04DQAR
(LCSC C106794; 0.2 pF I/O capacitance typ << the 0.5 pF/line TMDS budget, 8 kV
contact / IEC 61000-4-2): a 4-channel GND-referenced shunt array, so TWO devices
cover the eight TMDS lines (D2+D1 on U2, D0+CLK on U3), placed at the jack between
the receptacle and the bank. IO1..IO4 tap the four single-ended lines of two
adjacent pairs each, both GND pads to GND, the lanes staying DC-coupled jack ->
receiver (shunt TAPS, not series — the netlist gate proves each TMDS net is
{J1.pin, U2/U3.IOn}). The placer recognizes a pure GND-referenced clamp (all-
passive signal pins + a ground pin) as a shunt even with a single connector peer
and draws each array as a detached shunt cell with a labeled stub per line
(place.py shunt detector + _shunt_cells) — no in-line array, no crossed TMDS
lanes, so the zero-crossing visual gate holds.

EDID: the sink must present EDID even when the consuming board is off (HDMI 1.4
sec 8.5), so a 2-Kbit I2C EEPROM (ST M24C02, LCSC C7562) sits on the DDC bus
powered from the CABLE's +5V (pin 18): a source can always read the EDID. WC# is
write-PROTECTED — it is HARDWIRED to the EEPROM's own cable-5 V VCC node
(HDMI_RX_5V = U1.8, the pin adjacent to WC#=U1.7), so a runtime DDC write can
never corrupt the fixed EDID (COMP-1: WC# MUST reference the EEPROM's own cable-
5 V VCC domain, NOT a gated 3.3 V rail — on a gated rail the protection is
defeated in the board-off EDID-read case and 3.3 V is below the 5 V-VCC EEPROM's
VIH(min)=0.7*VCC~3.5 V). This is a permanently write-protected, fixed EDID with no
field-(re)program path by design. DDC pull-ups live on the SOURCE side per spec,
so none are duplicated here. E0/E1/E2 are grounded (EDID address 0xA0/0x50).

Hot-plug detect is asserted passively: 1k from the cable's own +5V to HPD
(pin 19) — a plugged source sees its 5V returned on HPD and starts reading EDID
with zero involvement from the consuming board (HPD is 5-V-domain, so it is NOT
routed to a 3V3 receiver bank — it stays internal SIGNAL on this sheet). Source
presence IS observable off-sheet: a 10k/15k divider on the cable 5V gives the
HDMI_5V_DET port (3.15 V max at 5.25 V — LVCMOS33-safe). CEC is 3V3-domain
signalling, routed to the receiver with the spec 27k pull-up to the consuming
board's gated module rail (+VDD_LOGIC).

HDMIRX-3 — SLOW-LINE CONNECTOR ESD: the four SLOW cable lines (DDC SCL/SDA, CEC,
HPD) get one GND-referenced low-cap ESD array as DETACHED SHUNT TAPS — the TI
TPD4E05U06DQAR (LCSC C138714, USON-10): 4-channel, GND-referenced (two GND pads,
NO VCC pin -> a pure passive+GND clamp), VRWM = 5.5 V, CL = 0.5 pF/line typ,
+-12 kV IEC 61000-4-2. The uniform 5.5 V standoff is ABOVE the 5.25 V max cable
rail, so the SAME part safely serves BOTH the 3.3 V DDC pair AND the +5 V-domain
CEC/HPD lines (idle 5 V < 5.5 V VRWM -> no false clamp; a 3.6 V-standoff part
would CONDUCT at 5 V, which is why the TMDS array is NOT reused here):
  D1+ = SCL, D1- = SDA (DDC, 3.3 V) ; D2+ = CEC (3.3 V), D2- = HPD (5 V).

Connector: SOFNG HDMI-019S (LCSC C111617). Symbol schgen:HDMI_A_RX is a LOCAL
re-pin (DDC rows match the EEPROM's SDA-over-SCL order for straight runs; TMDS
rows at 5.08 mm label pitch; HPD/CEC/shields on the bottom edge); its pads 20-23
are the shell tabs of the faithful generated footprint (parts/HDMI-019S/),
stacked on pin 20 and tied to CHASSIS_GND like a magjack shield (chassis star-
bonds to GND elsewhere). Pin 14 (UTILITY/HEAC+) is reserved -> author no-connect.

PENDING_MIGRATION (symbol_law allowlist): the ``lib_id="schgen:HDMI_A_RX"``
override on J1 is a hand-built symbol whose deep-engine migration is tracked and
DELIBERATELY PRESERVED here verbatim — a separate engine task replaces it later.
"""

from __future__ import annotations

from schgen.core.model import Circuit
from schgen.core.subsystem import Meta

# DELIBERATE symbol overrides (use_part lib_id=): the RX-direction schgen
# receptacle drawing + the stock EEPROM drawing stay; MPN/LCSC/datasheet + the
# faithful footprints come from parts/HDMI-019S/ + parts/M24C02-WMN6TP/. The
# J_LIB override is a TRACKED PENDING_MIGRATION (symbol_law) and is kept VERBATIM.
J_LIB = "schgen:HDMI_A_RX"
U_LIB = "Memory_EEPROM:M24C02-WMN"
R_FP = "Resistor_SMD:R_0603_1608Metric"
C_FP = "Capacitor_SMD:C_0603_1608Metric"

# ---- the abstract interface (the REUSE contract) ------------------------------
# Externally-visible net names a consuming project binds. RAILS classify as
# POWER/GROUND by name (a leading '+' = POWER; GND/CHASSIS_GND = GROUND), exactly
# as the bound carrier rails do, so a standalone build and a bound build share
# net classes. PORTS are the SoM/receiver-facing lines that cross the sheet
# boundary: the four TMDS RX pairs + the cable-5V presence detect + CEC. The
# DDC I2C, HPD assert and cable-5V quasi-rail are PRIVATE SIGNAL wiring (they run
# entirely connector<->ESD<->EEPROM on this sheet) and are NEVER part of the
# contract (HDMI_RX_SDA/SCL/HPD/5V — see below).
RAILS = ("+VDD_LOGIC", "GND", "CHASSIS_GND")
# receiver-side TMDS RX pairs (the differential lines INTO the FPGA/SoC bank)
TMDS_PORTS = (
    "TMDS_RX_D2_P", "TMDS_RX_D2_N",
    "TMDS_RX_D1_P", "TMDS_RX_D1_N",
    "TMDS_RX_D0_P", "TMDS_RX_D0_N",
    "TMDS_RX_CLK_P", "TMDS_RX_CLK_N",
)
# slow control ports that cross the boundary to the receiver
CTRL_PORTS = ("HDMI_5V_DET", "CEC")
PORTS = TMDS_PORTS + CTRL_PORTS
INTERFACE = RAILS + PORTS

# connector pin -> abstract TMDS RX port (RX direction: lanes IN from the source)
# -> (ESD array ref, ESD IO pin). The receptacle pin numbers are the HDMI 1.4
# Sec 4.2.2 pinout (re-checked against parts/HDMI-019S/ + the schgen:HDMI_A_RX
# re-pin); the ESD IO mapping is the TI TPD4E02B04 4-ch layout (two arrays).
TMDS_LANES = (
    ("TMDS_RX_D2_P", 1, "U2", "IO1"), ("TMDS_RX_D2_N", 3, "U2", "IO2"),
    ("TMDS_RX_D1_P", 4, "U2", "IO3"), ("TMDS_RX_D1_N", 6, "U2", "IO4"),
    ("TMDS_RX_D0_P", 7, "U3", "IO1"), ("TMDS_RX_D0_N", 9, "U3", "IO2"),
    ("TMDS_RX_CLK_P", 10, "U3", "IO3"), ("TMDS_RX_CLK_N", 12, "U3", "IO4"),
)
# the four differential pairs (P/N) of the above, for c.port_type pairing
TMDS_PAIRS = (
    ("TMDS_RX_D2_P", "TMDS_RX_D2_N"),
    ("TMDS_RX_D1_P", "TMDS_RX_D1_N"),
    ("TMDS_RX_D0_P", "TMDS_RX_D0_N"),
    ("TMDS_RX_CLK_P", "TMDS_RX_CLK_N"),
)

# Default power-tree draw note: only the CEC 27k pull-up sits on the gated module
# rail (+VDD_LOGIC). A project may override the prose via meta["notes"]["draws"]
# to cite its own dossier wording.
DRAWS_NOTE = ("CEC 27k pull-up (EEPROM + EDID WC# are cable-5V-fed)")
DRAWS_A = 0.001


def circuit(meta: "Meta | dict | None" = None) -> Circuit:
    """Build the hdmi_rx subsystem netlist with ABSTRACT port/rail names.

    ``meta`` is the STANDARD subsystem adapter contract (see
    :mod:`schgen.core.subsystem`) — a single dict a consuming project's adapter
    declares. Keys this subsystem reads (all optional; ``meta=None`` ->
    standalone abstract names for the local test):

      ``bind``    ``{abstract_name: project_net}`` rebinds the externally-visible
                  nets (the :data:`INTERFACE` names) to a project's real board
                  names. Applied last (order-preserving => byte-identical sheet).
      ``expects`` ``{abstract_port: deferral}`` attaches an EXPLICIT linker
                  deferral to a port — a project declares which of its sheets
                  will bind a deferred port (the TMDS/5V-DET/CEC lines that bind
                  on a generated connector sheet). For a TMDS pair, naming the P
                  line carries the pair's deferral.
      ``notes``   ``{"draws": prose}`` the power-tree draw-note prose (a project
                  may cite its own dossier wording; defaults to :data:`DRAWS_NOTE`).
    """
    meta = Meta(meta)
    draws_note = meta.note("draws", DRAWS_NOTE)

    c = Circuit("hdmi_rx", "HDMI RX: HDMI-A sink + EDID EEPROM")
    c.use_part("HDMI-019S", ref="J1", lib_id=J_LIB)
    c.use_part("M24C02-WMN6TP", ref="U1", lib_id=U_LIB)
    c.part("R1", "Device:R", "1k", R_FP, LCSC="C21190")     # HPD assert
    c.part("R2", "Device:R", "27k", R_FP, LCSC="C22967")    # CEC pull-up
    c.part("R3", "Device:R", "10k", R_FP, LCSC="C25804")    # 5V-det divider top
    c.part("R4", "Device:R", "15k", R_FP, LCSC="C22809")    # 5V-det divider bottom
    c.part("C1", "Device:C", "100n", C_FP, LCSC="C14663")   # EEPROM VCC bypass

    # TMDS lanes: DC-coupled connector -> receiver HR bank. The 2x49.9R/pair sink
    # termination to AVCC lives at the receiver-bank end, NOT here — SI-HDMIRX-TERM
    # (docstring): an HR bank does not self-terminate TMDS_33, so external sink
    # termination is REQUIRED, placed at the receiver.
    #
    # HDMIRX-1: real low-cap TMDS RX ESD. Two TI TPD4E02B04DQAR 4-ch arrays
    # (LCSC C106794, 0.2 pF/line typ << the 0.5 pF/line TMDS budget, 8 kV contact /
    # IEC 61000-4-2) shunt the 8 single-ended lines jack -> bank: D2+D1 on U2,
    # D0+CLK on U3. The lines stay DC-coupled (shunt TAPS, not series) — each ESD
    # IOn pin is just added to the existing connector port net, so the netlist
    # proves {J1.pin, U.IOn} per line. Both arrays' GND -> GND. The placer sees
    # these as pure GND-referenced clamps and draws each as a detached shunt cell
    # (place.py shunt detector + _shunt_cells).
    c.use_part("TPD4E02B04DQAR", ref="U2")
    c.use_part("TPD4E02B04DQAR", ref="U3")
    for net, jpin, esd_ref, esd_io in TMDS_LANES:
        c.port(net, f"J1.{jpin}", f"{esd_ref}.{esd_io}")
    c.net("GND", "U2.GND", "U3.GND")
    c.nc("U2.NC", "U3.NC")               # spare USON-10 pads (6/7/9/10)
    for p_pos, p_neg in TMDS_PAIRS:
        c.port_type(p_pos, kind="tmds_pair", pair_with=p_neg,
                    **meta.expect_kw(p_pos))

    # DDC: source-mastered I2C, EEPROM is the only sink-side device. PRIVATE
    # SIGNAL wiring (connector<->EEPROM<->ESD only — the DDC bus is mastered over
    # the cable, so it does NOT route off-sheet to the receiver).
    c.net("HDMI_RX_SDA", "J1.16", "U1.5")
    c.net("HDMI_RX_SCL", "J1.15", "U1.6")

    # HDMIRX-3: SLOW-LINE CONNECTOR ESD. One GND-referenced low-cap ESD array as
    # DETACHED SHUNT TAPS (not series — each protected line stays {J1.pin,
    # ...existing..., U.IOn}), drawn as a shunt cell exactly like U2/U3. The TI
    # TPD4E05U06DQAR (LCSC C138714, USON-10): 4-channel, GND-referenced (two GND
    # pads, NO VCC pin -> pure passive+GND clamp), VRWM = 5.5 V > 5.25 V max cable
    # rail, so the ONE part safely serves both the 3.3 V DDC pair and the +5 V
    # CEC/HPD lines (a TPD4E02B04-class 3.6 V-standoff part would CONDUCT at 5 V).
    #   D1+ = SCL, D1- = SDA (DDC, 3.3 V) ; D2+ = CEC (3.3 V), D2- = HPD (5 V).
    c.use_part("TPD4E05U06DQAR", ref="U4")
    c.net("HDMI_RX_SCL", "U4.D1+")
    c.net("HDMI_RX_SDA", "U4.D1-")
    c.net("GND", "U4.GND")
    c.nc("U4.NC")                              # USON-10 pads 6/7/9/10 (datasheet: float/GND OK)

    # cable +5V domain (PRIVATE SIGNAL quasi-rail): EEPROM supply + bypass, HPD
    # assert, presence divider top, and the EDID WC# write-protect (COMP-1) —
    # WC# (U1.7) is HARDWIRED to the EEPROM's OWN 5 V VCC node (U1.8, the adjacent
    # pin), so write-protect tracks VCC whenever a source is plugged.
    c.net("HDMI_RX_5V", "J1.18", "U1.8", "U1.7", "C1.1", "R1.1", "R3.1")
    c.net("GND", "C1.2")
    c.net("HDMI_RX_HPD", "J1.19", "R1.2", "U4.D2-")   # HDMIRX-3: HPD ESD tap (5 V)
    c.port("HDMI_5V_DET", "R3.2", "R4.1", **meta.expect_kw("HDMI_5V_DET"))
    c.net("GND", "R4.2")

    # CEC to the receiver, spec 27k pull-up to the gated module rail
    c.port("CEC", "J1.13", "R2.2", "U4.D2+", **meta.expect_kw("CEC"))  # HDMIRX-3: CEC ESD tap
    c.net("+VDD_LOGIC", "R2.1")

    # HDMIRX-2 / COMP-1: EDID write-protect. WC# (U1.7) is HARDWIRED to the
    # EEPROM's own cable-5 V VCC node HDMI_RX_5V (the adjacent U1.8 pin) above — a
    # NETLIST FIX, not a strap/jumper. This is a fixed, permanently write-protected
    # EDID: a runtime DDC write cannot corrupt it, and there is no field-(re)program
    # path by design. WC# tied to a gated 3.3 V rail would be WRONG twice — DOMAIN
    # (the gated rail is dead in the board-off EDID-read case, HDMI 1.4 sec 8.5 ->
    # WC# floats to 0 V -> write-ENABLED) and LEVEL (the 5 V-VCC EEPROM's
    # VIH(min)=0.7*VCC~3.5 V > 3.3 V). E0/E1/E2 address straps stay grounded
    # (0xA0/0x50).

    # grounds: TMDS shields + DDC/CEC ground on signal GND; shell on chassis
    c.net("GND", "J1.2", "J1.5", "J1.8", "J1.11", "J1.17",
          "U1.1", "U1.2", "U1.3", "U1.4")
    c.net("CHASSIS_GND", "J1.20", "J1.21", "J1.22", "J1.23")

    # pin 14 UTILITY/HEAC+: reserved, HEAC unused by design
    c.nc("J1.14")

    # power-tree budget: only the CEC 27k pull-up sits on the gated module rail
    # (~0.12 mA when CEC is driven low). EDID WC# is hardwired to cable 5 V (COMP-1)
    # so it draws nothing from +VDD_LOGIC; the EEPROM runs from cable 5 V.
    c.draws("+VDD_LOGIC", DRAWS_A, draws_note)
    return meta.finish(c)
