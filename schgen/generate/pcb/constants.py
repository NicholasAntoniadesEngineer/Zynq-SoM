from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path

from schgen.core import quantize as _quantize
from schgen.core.project import PROJECT_ROOT
from schgen.core.project import spec as _project_spec
from schgen.generate import constraints as cst

REPO_ROOT = Path(__file__).resolve().parents[3]
PARTS_DIR = REPO_ROOT / "parts"
CARRIER = PROJECT_ROOT

_KICAD_FP_DIRS = [
    Path("/Applications/KiCad/KiCad.app/Contents/SharedSupport/footprints"),
    Path("/usr/share/kicad/footprints"),
    Path("/usr/local/share/kicad/footprints"),
]

_FOOTPRINT_ALIASES = {
    "Capacitor_SMD:C_1206_3225Metric": "Capacitor_SMD:C_1206_3216Metric",
}


def _kicad_fp_root() -> Path | None:
    for d in _KICAD_FP_DIRS:
        if d.is_dir():
            return d
    return None


ORIGIN_X = 25.0
ORIGIN_Y = 25.0
MH_INSET = 5.0
GRID = _quantize.GRID_MM

FIDUCIAL_FOOTPRINT = "Fiducial:Fiducial_1mm_Mask2mm"
FID_INSET = 9.0

PERIM = 3.0
MH_KEEPOUT = 5.0
SOM_HALO_PCB = 7.0
SOM_CORE_CLEARANCE = 0.03
EDGE_BAND_PCB = 10.0
ZONE_PACK_FILL = 0.62
ZONE_STEP = 2.54
OUTLINE_GROW = 5.0
BOARD_EDGE_MARGIN = 0.6
SOM_ZONE_GROW = 2.0


@dataclass
class FootprintInst:
    ref: str
    value: str
    footprint: str
    x: float
    y: float
    rotation: float
    pad_nets: dict[str, tuple[int, str]]
    mod_path: Path
    sheet: str
    side: str = "top"
    mirror: bool = False


@dataclass
class PcbModel:
    board_w: float
    board_h: float
    insts: list[FootprintInst]
    net_numbers: dict[str, int]
    netclass_of: dict[str, str]
    classes: dict[str, cst.DiffGeometry | None]
    placed: int
    deferred: list[str]
    som_keepout: tuple[float, float, float, float] | None = None
    n_top: int = 0
    n_bottom: int = 0
    two_side: bool = True
    som_core: tuple[float, float, float, float] | None = None
    copper: list = field(default_factory=list)
    escape_meta: dict = field(default_factory=dict)
    escape_plan: dict | None = None
    stage_moves: dict = field(default_factory=dict)


_PAD_RE = re.compile(r'\(pad\s+"([^"]+)"')
_THRU_PAD_RE = re.compile(r'\(pad\s+"[^"]*"\s+(?:thru_hole|np_thru_hole)\b')


POWER_CLASS = "POWER"
POWER_TRACK_MM = 0.4
POWER_CLEARANCE_MM = 0.2
DEFAULT_TRACK_MM = 0.2032
DEFAULT_CLEARANCE_MM = 0.15


try:
    PLACE_CLEAR = float(os.environ.get("SCHGEN_PLACE_CLEAR", "0.5"))
except ValueError as _e:
    raise ValueError(
        f"SCHGEN_PLACE_CLEAR must be a float mm, got "
        f"{os.environ.get('SCHGEN_PLACE_CLEAR')!r}") from _e

PLACE_CLEAR_BASELINE = 0.5

TEMPLATE_CLEAR = PLACE_CLEAR_BASELINE
ZONE_PAD = 0.3
EDGE_ZONE_ASPECT = 2.2

INTERIOR_ZONE_ASPECT = 2.0
SOM_SIDE_BAND_MM = 39.5
INTERIOR_ZONE_BAND_TARGET = 32.0

INTERIOR_SHAPE_ASPECTS = (2.2, 1.0, 0.45)

CONN_MATING_FACE: dict[str, str] = {
    "TYPE-C-31-M-12":  "+Y",
    "HDMI-019S":       "+Y",
    "AFC07-S40FCA-00": "+Y",
    "KH-5224-8P8C-D":  "+Y",
    "TF-01A":          "+Y",
    "SFW15R-1STE1LF":  "+Y",
    "ZX-SH1.0-4PWT":   "+Y",
    "DS1024-2x6R2":    "+Y",
    "XT60PW-M":        "+X",
}
GND_PLANE_LAYER = "In1.Cu"
MICROSTRIP_REFERENCE = {"F.Cu": "In1.Cu", "B.Cu": "In2.Cu"}
GND_PLANE_EDGE_BACK = 0.5
GND_PLANE_CLEARANCE = 0.3
POUR_CLEARANCE = 0.2
ZONE_MIN_THICKNESS = 0.25
THERMAL_VIA_SIZE = 0.6
THERMAL_VIA_DRILL = 0.3
THERMAL_VIA_CLEAR = 0.25
CLR_HOLE_SAMENET_PAD = 0.10
HOLE_TO_HOLE_FAB = 0.15
HOLE_TO_HOLE_DRC_MARGIN = 0.10
HOLE_TO_HOLE_THERMAL_MARGIN = 0.30
MIN_HOLE_TO_HOLE = round(HOLE_TO_HOLE_FAB + HOLE_TO_HOLE_DRC_MARGIN, 4)
THERMAL_VIA_H2H = round(HOLE_TO_HOLE_FAB + HOLE_TO_HOLE_THERMAL_MARGIN, 4)
THERMAL_VIA_EDGE = 1.0
THERMAL_VIA_SPACING = 0.8
THERMAL_VIA_LATTICE_PITCH = 0.25

THERMAL_COPPER: dict[str, dict] = {
    "LM61460": {
        "via_sites": [(1.55, -2.5), (1.55, 2.5),
                      (2.45, -2.5), (2.45, 2.5),
                      (1.55, -4.35), (1.55, 4.35),
                      (2.45, -4.35), (2.45, 4.35),
                      (1.0, -4.35), (1.0, 4.35),
                      (-1.6, -2.7), (-1.6, 2.7),
                      (0.3, -2.6), (0.3, 2.6),
                      (2.85, -1.45), (2.85, 0.0), (2.85, 1.45)],
        "max_vias": 8,
        "pour": (-3.0, -4.75, 4.4, 4.75),
        "pour_layers": ("F.Cu", "B.Cu"),
        "cite": "TI SNVSBD5D 11.1.1 thermal-via field at PGND1/PGND2",
    },
    "TLV75725": {
        "via_sites": [(-1.15, 0.0), (1.15, 0.0),
                      (-1.75, 0.0), (1.75, 0.0),
                      (1.85, -1.0), (1.85, 1.0),
                      (2.35, -0.55), (2.35, 0.55),
                      (-1.85, -1.0), (-1.85, 1.0)],
        "max_vias": 3,
        "pour": (-2.9, -1.6, 2.9, 1.6),
        "pour_layers": ("F.Cu",),
        "cite": "TI TLV757P DYD JESD51-5 pad-adjacent thermal vias",
    },
}

ISO_VOID_VALUES = ("HX5008", "KH-5224")
ISO_VOID_MARGIN = 0.6

_ROT_FACE_NEG_Y = {"N": 0.0, "S": 180.0, "E": 270.0, "W": 90.0}
_ROT_FACE_POS_Y = {"N": 180.0, "S": 0.0, "E": 90.0, "W": 270.0}
_ROT_FACE_POS_X = {"N": 90.0, "S": 270.0, "E": 0.0, "W": 180.0}
_ROT_FACE_NEG_X = {"N": 270.0, "S": 90.0, "E": 180.0, "W": 0.0}
_ROT_TABLES = {"-Y": _ROT_FACE_NEG_Y, "+Y": _ROT_FACE_POS_Y,
               "+X": _ROT_FACE_POS_X, "-X": _ROT_FACE_NEG_X}
_FACE_VEC = {"-Y": (0, -1), "+Y": (0, 1), "+X": (1, 0), "-X": (-1, 0)}

EDGE_PAD_CLEAR = 0.4

BUTTON_GAP = 2.0


_TOP_ALWAYS_LIBS = (
    "DF40C", "MountingHole", "Mechanical:", "TestPoint",
    "PinHeader", "PinSocket", "Connector", "Conn_",
)
TOP_AREA_MM2 = 12.0

EDGE_FLUSH_RELIEF = 0.2
EDGE_FLUSH_MM = round(EDGE_PAD_CLEAR + EDGE_FLUSH_RELIEF, 3)


@dataclass(frozen=True)
class ZoneShape:
    w: float
    h: float
    top_off: dict[str, tuple[float, float]]
    bot_off: dict[str, tuple[float, float]]
    extra_rot: dict[str, float]
    tag: str
    side: str = "top"
    mirror: dict[str, Path] = field(default_factory=dict)


@dataclass
class ZoneGeom:
    zone_box: dict[str, tuple[float, float]]
    top_off: dict[str, dict[str, tuple[float, float]]]
    bot_off: dict[str, dict[str, tuple[float, float]]]
    side_of: dict[str, str]
    bbox_of: dict[str, tuple[float, float, float, float]]
    resolvable: dict[str, Path]
    refs_by_sheet: dict[str, list[str]]
    mh_refs: list[str]
    deferred: list[str]
    conn_rot: dict[str, float] = field(default_factory=dict)
    conn_edge: dict[str, str] = field(default_factory=dict)
    zone_extra_rot: dict[str, float] = field(default_factory=dict)
    shapes: dict[str, tuple[ZoneShape, ...]] = field(default_factory=dict)
    mirror_refs: frozenset = frozenset()


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


_CONN_DESC: dict[str, str] = {
    "pd_input":            "PWR",
    "usbc_otg":            "USB OTG",
    "usb_jtag_connector":  "JTAG",
    "usb_uart_connector":  "UART",
    "microsd":             "microSD",
    "hdmi_tx":             "HDMI TX",
    "hdmi_rx":             "HDMI RX",
    "rj45_connector":      "ETH",
    "board_qwiic":         "QWIIC",
    "camera":              "CAM",
    "lcd":                 "LCD",
    "pmod":                "PMOD",
    "pmod_expansion":      "PMOD",
}

_INT_DESC: dict[str, str] = dict(_project_spec().header_desc)

_SW_DESC: dict[str, str] = dict(_project_spec().switch_desc)
