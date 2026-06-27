"""Module tunables, lookup tables and the PCB dataclasses (pure data — no
function cross-dependencies). Split out of the old monolithic
``schgen/generate/pcb.py`` (PURE MOVE, no behaviour change). Every other pcb
submodule imports its constants from here, so this is the dependency leaf.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from schgen.generate import constraints as cst

REPO_ROOT = Path(__file__).resolve().parents[3]
PARTS_DIR = REPO_ROOT / "parts"
CARRIER = REPO_ROOT / "carrier"

# KiCad-installed standard footprint libraries (the non-parts/ footprints —
# Resistor_SMD, Capacitor_SMD, Package_*, Diode_SMD, LED_SMD, TestPoint,
# MountingHole). Probed at the standard macOS/Linux locations.
_KICAD_FP_DIRS = [
    Path("/Applications/KiCad/KiCad.app/Contents/SharedSupport/footprints"),
    Path("/usr/share/kicad/footprints"),
    Path("/usr/local/share/kicad/footprints"),
]

# A few footprint names this project authored that a given KiCad install may
# ship under a near-identical dimensional name. Same body, same pads — the
# substitution is dimensionally faithful and reported. (3225 vs 3216 is the
# 1206 metric body; some KiCad lib versions ship one, some the other.)
_FOOTPRINT_ALIASES = {
    "Capacitor_SMD:C_1206_3225Metric": "Capacitor_SMD:C_1206_3216Metric",
}


def _kicad_fp_root() -> Path | None:
    for d in _KICAD_FP_DIRS:
        if d.is_dir():
            return d
    return None


# ---- board geometry --------------------------------------------------------------
# The outline is DERIVED from the ACTUAL packed-zone extents (build_model): the
# board grows until the centered SoM region + every per-subsystem zone + the 4
# corner mounting holes + a perimeter keepout all fit, so EVERY footprint sits
# inside Edge.Cuts (LAW 5 — no off-board parts). The coordinate frame is shifted
# by ORIGIN_X/Y so the board sits in positive KiCad page space (KiCad's drawing
# sheet origin is top-left, +y down).
ORIGIN_X = 25.0          # board top-left in KiCad page mm
ORIGIN_Y = 25.0
MH_INSET = 5.0          # M3 hole center inset from each board corner
GRID = 1.27             # placement snap grid (mm)

# --- subsystem-zone outline derivation (LAW 5) -------------------------------
PERIM = 3.0              # perimeter keepout ring (no zone touches the edge)
MH_KEEPOUT = 5.0         # extra inset reserving the corner mounting-hole pads
SOM_HALO_PCB = 7.0       # routing/escape halo reserved around the SoM body
SOM_CORE_CLEARANCE = 0.03  # grow the SoM-body silk outline + keepout 3% (1.5% per
#                            side) past the bare DF40 span for mating clearance
EDGE_BAND_PCB = 10.0     # nominal connector band each side (board-aspect seed)
ZONE_FILL = 0.58         # zone-area packing efficiency for the seed board size
ZONE_STEP = 2.54         # zone-placement raster scan step (mm)
OUTLINE_GROW = 5.0       # board grow increment per fit attempt (mm)
OUTLINE_SNAP_PCB = 5.0   # round the final W/H UP to this grid (mm)


def _snap_up(v: float) -> float:
    n = int((v + OUTLINE_SNAP_PCB - 1e-6) / OUTLINE_SNAP_PCB)
    return round(n * OUTLINE_SNAP_PCB, 1)


@dataclass
class FootprintInst:
    ref: str
    value: str
    footprint: str        # lib:name
    x: float              # KiCad page mm (center)
    y: float
    rotation: float
    pad_nets: dict[str, tuple[int, str]]   # pad name -> (net number, net name)
    mod_path: Path
    sheet: str
    side: str = "top"     # "top" (F.Cu) | "bottom" (B.Cu) — 2-side assembly


@dataclass
class PcbModel:
    board_w: float
    board_h: float
    insts: list[FootprintInst]
    net_numbers: dict[str, int]            # net name -> number (0 = no-net)
    netclass_of: dict[str, str]            # net name -> net class
    classes: dict[str, cst.DiffGeometry | None]
    placed: int
    deferred: list[str]
    som_keepout: tuple[float, float, float, float] | None = None  # x0,y0,x1,y1
    n_top: int = 0
    n_bottom: int = 0
    two_side: bool = True
    # SoM module-body CORE rectangle in the board page frame (NO halo) — the
    # footprint of the plugged-in SoM. Under it ONLY low-profile passives may
    # sit (LAW 6); the placement_mech gate enforces it.
    som_core: tuple[float, float, float, float] | None = None  # x0,y0,x1,y1


# ---- footprint resolution + parsing ----------------------------------------------

_PAD_RE = re.compile(r'\(pad\s+"([^"]+)"')
# a pad that occupies EVERY copper layer (through-hole / NPTH) — its copper is
# on both F.Cu and B.Cu, so a bottom-side SMD part placed at the same XY would
# short to it. The 2-side packer reserves such top-side footprints on the
# bottom too.
_THRU_PAD_RE = re.compile(r'\(pad\s+"[^"]*"\s+(?:thru_hole|np_thru_hole)\b')


# ---- net classes -----------------------------------------------------------------
# Reuse the constraints exporter's class names + geometry: the high-speed diff
# classes (DP90_USB / DP100_TMDS / DP<imp>_DIFF) plus a POWER class for rails.

POWER_CLASS = "POWER"
POWER_TRACK_MM = 0.4            # rail trace minimum (sensible default; user widens)
POWER_CLEARANCE_MM = 0.2
DEFAULT_TRACK_MM = 0.2032       # 8 mil — JLCPCB default minimum trace width
# Board-wide copper clearance: 0.15 mm (6 mil) — a standard JLCPCB process
# minimum. The 8-mil figure is the trace WIDTH target, not the pad-to-pad
# clearance; several faithful fine-pitch QFN/SOT footprints in the BOM have an
# intrinsic pad-to-EP gap of ~0.198 mm, so an 8-mil clearance rule would flag
# the footprints' OWN geometry (350+ intra-footprint false positives) before a
# single track is routed. 6 mil clears those and stays manufacturable.
DEFAULT_CLEARANCE_MM = 0.15


# ---- placement -------------------------------------------------------------------

# Mandatory clearance between any two footprint courtyards AND between a
# footprint and the board edge — so the emitted PCB has NO courtyard-overlap /
# pad-clearance / copper-edge DRC errors (only the expected unrouted-net items).
PLACE_CLEAR = 0.5
EDGE_CLEAR = 2.0
ZONE_GAP = 0.8             # gap between two adjacent subsystem zones
ZONE_PAD = 0.3            # padding inside a subsystem zone around its parts
# N/S EDGE-connector subsystems pack WIDE + SHALLOW (their shelf target width is
# multiplied by this) so the zone spreads ALONG the horizontal top/bottom edge
# instead of eating deep into the interior behind the connector (a deep edge
# block forces the board to grow). ~halves the depth of the deepest connector
# blocks (microSD 30->20, pd_input 33->17, hdmi 29->20). W/E edges are left
# squarish (a wide pack there would be DEEP into the board) — the floorplan
# spreads them down the vertical edge as-is.
EDGE_ZONE_ASPECT = 2.2

# LEVER L1: INTERIOR subsystems that pack TALLER than the SoM side-band (the
# interior strip beside the centered SoM keepout, ~39.5 mm deep) force the board
# WIDE because the interior packer (_Occupancy.place_near) does NOT rotate a
# zone — each over-tall column eats a full board-height slot and the free area
# fragments below ~165 mm width (PACK_NOFIT). Two complementary fixes make these
# zones lie FLAT in the band so the board can narrow:
#   (1) a wide-shallow aspect (like EDGE_ZONE_ASPECT) for any interior zone whose
#       SHELF-packable parts are all short enough that re-flowing them wider drops
#       the zone height under the band — this re-flows bringup_rails (50.6->~28)
#       and user_io (41.8->~22) without touching any part; and
#   (2) a 90-deg BLOCK rotation for a zone whose SINGLE TALLEST part is itself
#       taller than the band (fmc: a rigid 2x40 header J11001 is 51.8 mm, so no
#       re-flow can shrink the zone height) — rotating the whole packed zone lays
#       that header flat (zone 15.5x52.9 -> 52.9x15.5). The part is NOT redrawn;
#       only the BLOCK is turned, exactly as a hand layout would orient the header
#       along the band (NEVER-redraw-parts memo honoured).
INTERIOR_ZONE_ASPECT = 2.0       # wide-shallow target for over-tall interior zones
SOM_SIDE_BAND_MM = 39.5          # depth of the interior strip beside the SoM keepout
INTERIOR_ZONE_BAND_TARGET = 32.0 # re-flow/rotate an interior zone to <= this height

# ---- LAW 6: off-board connector ORIENTATION ---------------------------------------
# Every connector that mates with an external cable/plug/card MUST sit on a board
# EDGE with its mating face (the slot/mouth/cable-exit) pointing OFF-BOARD, so the
# mate physically inserts. The placer ROTATES each such connector to its assigned
# edge — never axis-aligned — and seats it flush at the edge; the rest of its
# subsystem packs behind it, inward. DRC=0 + the ratsnest gate are blind to this
# (an interior or inward-facing connector is not a DRC/airwire error), so this is
# encoded here AND enforced by the placement_mech gate.
#
# MATING_FACE: the direction the connector's mouth points in its footprint LOCAL
# frame at rotation 0 (researched from the parts/<MPN>/<MPN>.kicad_mod pad/post
# asymmetry + datasheet). KiCad's page frame is +y DOWN, so -Y is toward the
# board top (N edge) and +Y toward the bottom (S edge).
CONN_MATING_FACE: dict[str, str] = {
    "TYPE-C-31-M-12":  "+Y",   # USB-C receptacle: mouth is OPPOSITE the 12 SMT
                               # signal-tail row (tails at local -Y; the hollow
                               # shell mouth +Y) — same rule as HDMI/RJ45. Was "-Y"
                               # which placed all 4 USB-C at rot 0 with the mouth
                               # facing INBOARD on the N edge (user caught it; render
                               # + .wrl end-cavity test (+Y 582 vs -Y 48) confirm).
    "HDMI-019S":       "+Y",   # HDMI receptacle mouth (plug enters OPPOSITE the
                               # SMT contact row at -Y; verified from footprint
                               # geometry — was -Y, faced inward in the render)
    "AFC07-S40FCA-00": "-Y",   # LCD FPC slot
    "KH-5224-8P8C-D":  "-Y",   # RJ45 jack mouth (plug enters at the pin-1..8
                               # CONTACT end at -Y; shield tails/posts at +Y are
                               # the board-attach back — was +Y, faced inward)
    "TF-01A":          "+Y",   # microSD card slot
    "SFW15R-1STE1LF":  "-Y",   # camera FFC slot opens away from the solder tabs
                               # (posts at +Y -> cable entry at -Y), same as the
                               # geometrically-identical AFC07 LCD FPC
    "ZX-SH1.0-4PWT":   "-Y",   # QWIIC SH connector: mouth at the CONTACT-row side
                               # (-Y, pads 1-4); the 2 big posts (pads 5,6) at +Y
                               # are the BACK. Was +Y (faced the mouth INBOARD on
                               # the E edge — user caught it); -Y seats the legs
                               # inboard + opening toward the edge like the RJ45.
                               # Render-verified (the .wrl open-face heuristic is
                               # unreliable for these housings; the render decides).
    "DS1024-2x6R2":    "+Y",   # PMOD 2x6 socket
    "XT60PW-M":        "+X",   # ESC power XT60 (motor_sense): side-entry, the
                               # plug mates onto the bullet contacts at local +X
                               # (signal pads 1/2 at x=+3; mounting tabs at -3).
                               # In-plane HORIZONTAL mouth -> the +X table. Render-
                               # verified the mouth seats toward the board edge.
}
# EDGE -> placement rotation (deg, KiCad CCW) that turns the mating face OFF-BOARD.
# Derived in the CODE's actual page frame (+y DOWN: N/top edge = MIN y, off-board
# from N is toward -Y; S/bottom = MAX y, off-board +Y; E/right off-board +X;
# W/left off-board -X) using the SAME rotation matrix _inst_pad_geom applies:
# (x,y) -> (x cos r - y sin r, x sin r + y cos r). NOTE this differs from the
# research spec's table by swapping N<->S: the research derived in a +y-UP frame
# (it called +Y "North/away"), but this codebase places on a +y-DOWN page, so the
# off-board direction of the top/bottom edges is the opposite sign. The
# _mating_face_out_dir oracle (and the placement_mech gate that uses it) is the
# ground truth that proves each mouth points off-board after rotation.
_ROT_FACE_NEG_Y = {"N": 0.0, "S": 180.0, "E": 90.0, "W": 270.0}
_ROT_FACE_POS_Y = {"N": 180.0, "S": 0.0, "E": 270.0, "W": 90.0}
# +X/-X: an in-plane HORIZONTAL mouth along the footprint X axis (e.g. a side-
# entry XT60 whose plug enters along +X). Derived the same way as +Y/-Y from
# _mating_face_out_dir's rotation matrix (mouth (1,0) -> off-board edge).
_ROT_FACE_POS_X = {"N": 270.0, "S": 90.0, "E": 0.0, "W": 180.0}
_ROT_FACE_NEG_X = {"N": 90.0, "S": 270.0, "E": 180.0, "W": 0.0}
_ROT_TABLES = {"-Y": _ROT_FACE_NEG_Y, "+Y": _ROT_FACE_POS_Y,
               "+X": _ROT_FACE_POS_X, "-X": _ROT_FACE_NEG_X}
_FACE_VEC = {"-Y": (0, -1), "+Y": (0, 1), "+X": (1, 0), "-X": (-1, 0)}

# off-board connector seating: the outermost PAD sits this far (mm) from the
# board edge — just clears the 0.3 mm copper_edge_clearance with grid-snap margin;
# the connector's mouth/shell (ahead of the pads) then reaches/overhangs the edge
# so a cable actually mates (LAW 6 — user: "connectors at the absolute edge").
EDGE_PAD_CLEAR = 0.4

# inter-button air gap (mm) inside the tactile-button grid — wider than the
# generic PLACE_CLEAR so the buttons read as a spaced, finger-friendly array.
BUTTON_GAP = 2.0

# ---- 2-side assembly: layer-assignment policy ------------------------------------
# JLCPCB assembles BOTH sides. The policy keeps the mechanically-/cable-/heat-
# critical parts on TOP and pushes the small decoupling/bypass passives to the
# BOTTOM (placed directly under their cluster), which roughly halves the
# top-side area pressure. Default ON; a forced single-side build keeps all on
# top (every classification then returns "top").

# Footprint families that MUST stay on the top (component) side regardless of
# size: the SoM mezzanine, every off-board edge connector, the mounting holes,
# test points (probe from the top), and through-hole headers.
_TOP_ALWAYS_LIBS = (
    "DF40C", "MountingHole", "Mechanical:", "TestPoint",
    "PinHeader", "PinSocket", "Connector", "Conn_",
)
# Active/large IC area floor (mm^2 of the footprint bbox): a part this big or
# bigger is an IC/connector/magnetic and stays on top.
TOP_AREA_MM2 = 12.0

# how close (mm) a connector courtyard outer face must sit to the board edge to
# count as "flush" (LAW 6 / placement_mech gate). The post-placement edge-snap
# seats every off-board connector with its outer PAD at EDGE_PAD_CLEAR and its
# mouth/shell reaching or overhanging the edge, so the courtyard outer face lands
# at ~EDGE_PAD_CLEAR or NEGATIVE (overhang). The flush gate fails any connector
# whose body courtyard is recessed more than EDGE_FLUSH_MM inboard of the edge.
# TIGHTENED 9.0 -> 1.5 -> EDGE_PAD_CLEAR+0.2 (=0.6): a connector MUST reach the
# very edge (user law). A pad-limited connector (its outer pad IS the mating face,
# e.g. USB-C/QWIIC) can only reach EDGE_PAD_CLEAR (0.4 mm, the copper-edge-clearance
# floor) — so the threshold is that floor + a hair, NOT the old slack 1.5/9.0 that
# let a connector sit ~2.4 mm inboard and not mate. Overhang (negative flush)
# passes; any recess beyond the pad-clearance floor FAILS the board.
EDGE_FLUSH_MM = round(EDGE_PAD_CLEAR + 0.2, 3)   # 0.6 mm — "at the very edge" law


# ---- SHARED subsystem zone packing (ONE source of truth) -------------------------
# Both the floorplan (block SIZING) and the PCB (block PLACEMENT) must agree on how
# big each subsystem's 2-sided packed cluster is, or the FLOORPLAN.svg and the PCB
# ratsnest diverge (the historical 235x215-vs-165x155 split). This function is the
# single sizing oracle: it shelf-packs every subsystem's TOP + BOTTOM footprints
# (the exact STEP-1 geometry the PCB places with) and returns the per-sheet packed
# (w, h) + per-part offsets. It runs from the subsystem circuits + the stable
# board-unique ref namespace (carrier/sheet_index.json), so it is identical whether
# called standalone (`schgen floorplan`, no emitted root sch) or inside the board
# flow — proven: per-sheet decoupling classification == merged classification, and
# board-unique-ref packing is byte-identical to build_model's old inline packing.

@dataclass
class ZoneGeom:
    zone_box: dict[str, tuple[float, float]]                # sheet -> (w, h)
    top_off: dict[str, dict[str, tuple[float, float]]]      # sheet -> {bref:(x,y)}
    bot_off: dict[str, dict[str, tuple[float, float]]]
    side_of: dict[str, str]                                 # bref -> top|bottom
    bbox_of: dict[str, tuple[float, float, float, float]]   # bref -> local bbox
    resolvable: dict[str, Path]                             # bref -> .kicad_mod
    refs_by_sheet: dict[str, list[str]]                     # sheet -> [bref,...]
    mh_refs: list[str]                                      # mounting-hole brefs
    deferred: list[str]
    conn_rot: dict[str, float] = field(default_factory=dict)  # bref -> LAW-6 rot
    conn_edge: dict[str, str] = field(default_factory=dict)   # bref -> edge N/E/S/W
    zone_extra_rot: dict[str, float] = field(default_factory=dict)  # bref -> +rot
    #                                          from a LEVER-L1 90-deg zone rotation


# 4-layer controlled-impedance stackup: Sig / GND / PWR / Sig, JLC04161H-7628
# 1.6 mm (the build schgen/generate/constraints.py already targets).
_FOUR_LAYER = [
    (0, "F.Cu", "signal", "L1 (Sig)"),
    (1, "In1.Cu", "power", "L2 (GND)"),
    (2, "In2.Cu", "power", "L3 (PWR)"),
    (31, "B.Cu", "signal", "L4 (Sig)"),
    (32, "B.Adhes", "user", "B.Adhesive"),
    (33, "F.Adhes", "user", "F.Adhesive"),
    (34, "B.Paste", "user", None),
    (35, "F.Paste", "user", None),
    (36, "B.SilkS", "user", "B.Silkscreen"),
    (37, "F.SilkS", "user", "F.Silkscreen"),
    (38, "B.Mask", "user", None),
    (39, "F.Mask", "user", None),
    (40, "Dwgs.User", "user", "User.Drawings"),
    (41, "Cmts.User", "user", "User.Comments"),
    (42, "Eco1.User", "user", "User.Eco1"),
    (43, "Eco2.User", "user", "User.Eco2"),
    (44, "Edge.Cuts", "user", None),
    (45, "Margin", "user", None),
    (46, "B.CrtYd", "user", "B.Courtyard"),
    (47, "F.CrtYd", "user", "F.Courtyard"),
    (48, "B.Fab", "user", None),
    (49, "F.Fab", "user", None),
]


# Short, human silk descriptor per off-board connector SHEET — so the bare board
# is self-documenting ("which connector is which"). Keyed on the subsystem sheet
# (1:1 with each connector's function); the 3 PMOD ports are numbered below.
_CONN_DESC: dict[str, str] = {
    "pd_input":            "PWR",        # USB-C PD power inlet (the only power-in)
    "usbc_otg":            "USB OTG",    # USB 2.0 OTG data port
    "usb_jtag_connector":  "JTAG",       # USB->JTAG debug/program bridge (CH347T)
    "usb_uart_connector":  "UART",       # USB->UART serial console (CP2102N)
    "microsd":             "microSD",    # microSD card slot
    "hdmi_tx":             "HDMI TX",    # HDMI source
    "hdmi_rx":             "HDMI RX",    # HDMI sink
    "rj45_connector":      "ETH",        # 10/100 Ethernet
    "board_qwiic":         "QWIIC",      # QWIIC/Stemma I2C
    "camera":              "CAM",        # CSI camera FFC
    "lcd":                 "LCD",        # display FFC
    "pmod":                "PMOD",       # PMOD GPIO (numbered)
    "pmod_expansion":      "PMOD",       # PMOD GPIO (numbered)
}

# Interior (non-edge) user/developer headers — labelled by REF (their sheets carry
# >1 connector). The SoM DF40 mezzanines are intentionally NOT here: the "Zynq SoM"
# body-silk already labels that region (the SoM mounts on them).
_INT_DESC: dict[str, str] = {
    "J11001": "GPIO",   # FMC-site 2x20 2.54mm breakout
    "J9001":  "JTAG",   # Zynq 2x7 2.00mm JTAG header
    "J9002":  "SWD",    # system-controller ARM Cortex 10-pin SWD header
    # motor interface (drone demo): the 8-ch ESC PWM header + the in-line ESC
    # power XT60s. Per-ref so IN vs OUT is on the silk (J37002=J2=ESC_VRAIL_IN
    # in, J37003=J3=ESC_VRAIL out — local-ref order in motor_sense.py).
    "J36001": "ESC PWM",      # motor_pwm: 3x8 servo/ESC signal header
    "J37002": "ESC PWR IN",   # motor_sense: XT60 battery/bench-supply input
    "J37003": "ESC PWR OUT",  # motor_sense: XT60 out to off-board ESCs
}

# Switches — a short FUNCTION label beside every DIP enable + tactile button, the
# same way connectors/headers are labelled. Keyed by the board-unique ref (the
# per-sheet renumbering is deterministic); test_switch_descriptors asserts EVERY
# switch on the board gets a label so a ref shift can't silently drop one.
# The multi-position config DIPs carry an INLINE position legend (words in
# silkscreen-position order 1..N — the DIP footprint already silk-prints the
# numbers), so the bare board tells you what each rocker does. Every legend is
# VERIFIED against the owning subsystem's position map (bringup_rails SW1/SW2/SW6
# docstring + maps; debug_boot boot-DIP) — a wrong legend is worse than none
# (LAW 0). The single-pole enables + tactile buttons get a plain function label.
_SW_DESC: dict[str, str] = {
    "SW1001":  "AUX EN",                         # board_aux:  gates +3V3_AUX (aux)
    "SW7001":  "RAIL: 5V 3V3 1V8 LED",           # bringup:    rail DIP  (pos 1..4)
    "SW7002":  "MOD: HTX HRX LCD CAM SD USB PMD", # bringup:   module DIP (1..7,8=spare)
    "SW7003":  "BTN0",                           # bringup:    PL_BTN0 user button
    "SW7004":  "BTN1",                           # bringup:    PL_BTN1 user button
    "SW7005":  "SC RST",                         # bringup:    sys-ctrlr reset (NRST)
    "SW7006":  "5V: HTX LCD",                    # bringup:    +5V module DIP (pos 1..2)
    "SW9001":  "BOOT: DFU BSEL BSEL",            # debug_boot: boot DIP (1=DFU 2-3=BSEL)
    "SW9002":  "RST",                            # debug_boot: reset button
    "SW19001": "PMOD EN",                        # pmod_expansion: port power enable
    "SW28001": "JTAG EN",                        # usb_jtag:   USB-JTAG bridge OE
    "SW33001": "USR0",                           # user_io:    user button 0
    "SW33002": "USR1",                           # user_io:    user button 1
    "SW33003": "USR2",                           # user_io:    user button 2
    "SW33004": "USR3",                           # user_io:    user button 3
}
