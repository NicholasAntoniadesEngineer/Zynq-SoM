from __future__ import annotations

import argparse
import json
import math
import re
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

from schgen.core import sexpr
from schgen.core.sexpr import Sym
from schgen.layout import textmetrics

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PARTS_DIR = REPO_ROOT / "parts"

EASYEDA_API = "https://easyeda.com/api/products/{lcsc}/components?version=6.4.19.5"
MODEL_STEP_URL = "https://modules.easyeda.com/qAxj6KHrDKw4blvCG8QJPs7Y/{uuid}"
MODEL_OBJ_URL = "https://modules.easyeda.com/3dmodel/{uuid}"

USER_AGENT = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
              "AppleWebKit/537.36 (KHTML, like Gecko) "
              "Chrome/120.0.0.0 Safari/537.36")

MM = 0.254
GRID = 1.27
PITCH = 2.54
PIN_LEN = 2.54


class PartGenError(RuntimeError):
    pass


def _http_get(url: str, binary: bool = False, timeout: int = 30) -> bytes | str | None:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
            data = resp.read()
    except (urllib.error.URLError, urllib.error.HTTPError, OSError):
        return None
    if data[:2] == b"\x1f\x8b":
        import gzip
        data = gzip.decompress(data)
    return data if binary else data.decode("utf-8", errors="replace")


def fetch_cad(lcsc_id: str) -> dict:
    txt = _http_get(EASYEDA_API.format(lcsc=lcsc_id))
    if txt is None:
        raise PartGenError(
            f"EasyEDA API unreachable for {lcsc_id} "
            f"({EASYEDA_API.format(lcsc=lcsc_id)}) — retry or use --from-json")
    try:
        payload = json.loads(txt)
    except json.JSONDecodeError as exc:
        raise PartGenError(f"EasyEDA API returned non-JSON for {lcsc_id}: "
                           f"{txt[:120]!r}") from exc
    if not payload.get("success") or "result" not in payload:
        raise PartGenError(f"EasyEDA has no CAD data for {lcsc_id}: "
                           f"{str(payload)[:200]}")
    return payload


_ETYPE = {0: "passive", 1: "input", 2: "output", 3: "bidirectional", 4: "power_in"}

_GND_RE = re.compile(r"^(GND|GNDA|GNDD|PGND|AGND|DGND|VSS|EP$|EPAD|PAD$|EXPOSED)",
                     re.IGNORECASE)
_PWR_RE = re.compile(r"^(VDD|VCC|VBUS|VBAT|VIN|V\+|AVDD|DVDD|VDDA|VDDIO|\+\d)",
                     re.IGNORECASE)
_NC_RE = re.compile(r"^(NC|N\.C\.?|DNC)$", re.IGNORECASE)


@dataclass(frozen=True)
class PinInfo:
    number: str
    name: str
    etype: str


def parse_pins(result: dict) -> list[PinInfo]:
    pins: list[PinInfo] = []
    for line in result["dataStr"]["shape"]:
        if not line.startswith("P~"):
            continue
        seg = [s.split("~") for s in line.split("^^")]
        try:
            ee_type = int(float(seg[0][2])) if seg[0][2] else 0
        except (ValueError, IndexError):
            ee_type = 0
        number = seg[4][4] if len(seg) > 4 and len(seg[4]) > 4 and seg[4][4] \
            else (seg[0][3] if len(seg[0]) > 3 else "")
        name = seg[3][4] if len(seg) > 3 and len(seg[3]) > 4 else ""
        name = name or number
        pins.append(PinInfo(number=str(number), name=str(name),
                            etype=_ETYPE.get(ee_type, "passive")))
    if not pins:
        raise PartGenError("EasyEDA symbol has no pins")
    return pins


def normalize_etypes(pins: list[PinInfo], prefix: str) -> list[PinInfo]:
    if len(pins) <= 2 or prefix in ("R", "C", "L", "FB", "F"):
        return [PinInfo(p.number, p.name, "passive") for p in pins]
    if all(p.etype == "input" for p in pins):
        return [PinInfo(p.number, p.name, "passive") for p in pins]
    return pins


def part_info(result: dict) -> dict:
    c_para = result["dataStr"]["head"]["c_para"]
    lcsc = (result.get("lcsc") or {}).get("number", "") or \
           (result.get("szlcsc") or {}).get("number", "")
    mpn = c_para.get("Manufacturer Part") or c_para.get("name") or lcsc
    desc = result.get("description", "") or \
        f"{result.get('title', mpn)} ({c_para.get('package', '')})"
    return {
        "mpn": mpn,
        "lcsc": lcsc,
        "prefix": (c_para.get("pre") or "U?").rstrip("?") or "U",
        "package": c_para.get("package", ""),
        "manufacturer": c_para.get("Manufacturer", ""),
        "jlc_class": c_para.get("JLCPCB Part Class", ""),
        "description": desc,
        "product_url": (result.get("lcsc") or {}).get("url", ""),
        "datasheet": f"https://www.lcsc.com/datasheet/{lcsc}.pdf" if lcsc else "",
        "tags": result.get("tags") or [],
    }


def safe_name(mpn: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", mpn).strip("_")


@dataclass
class _Groups:
    left: list[PinInfo] = field(default_factory=list)
    right: list[PinInfo] = field(default_factory=list)
    top: list[PinInfo] = field(default_factory=list)
    bottom: list[PinInfo] = field(default_factory=list)


def group_pins(pins: list[PinInfo]) -> _Groups:
    g = _Groups()
    named_power = any(_GND_RE.match(p.name) or _PWR_RE.match(p.name)
                      or p.etype == "power_in" for p in pins)
    all_signal = all(p.etype in ("passive", "bidirectional") for p in pins)

    if all_signal and not named_power:
        numeric = [p for p in pins if p.number.isdigit()]
        if len(numeric) == len(pins) and len(pins) > 6:
            g.left = [p for p in pins if int(p.number) % 2 == 1]
            g.right = [p for p in pins if int(p.number) % 2 == 0]
        elif len(pins) == 2:
            ordered = sorted(pins, key=lambda p: (not p.number.isdigit(),
                                                  int(p.number)
                                                  if p.number.isdigit() else 0,
                                                  p.number))
            g.left, g.right = [ordered[0]], [ordered[1]]
        else:
            half = (len(pins) + 1) // 2
            g.left, g.right = list(pins[:half]), list(pins[half:])
        return g

    for p in pins:
        if _NC_RE.match(p.name):
            g.bottom.append(p)
        elif _GND_RE.match(p.name):
            g.bottom.append(p)
        elif _PWR_RE.match(p.name) or p.etype == "power_in":
            g.top.append(p)
        elif p.etype == "input":
            g.left.append(p)
        else:
            g.right.append(p)

    if not g.left and len(g.right) > 4:
        names_in_order: list[str] = []
        for p in g.right:
            if p.name not in names_in_order:
                names_in_order.append(p.name)
        half_names = set(names_in_order[:(len(names_in_order) + 1) // 2])
        g.left = [p for p in g.right if p.name in half_names]
        g.right = [p for p in g.right if p.name not in half_names]
    return g


def _ceil_grid(v: float, step: float = PITCH) -> float:
    return round(math.ceil(v / step - 1e-9) * step, 4)


def _name_w(p: PinInfo) -> float:
    return textmetrics.text_wh(p.name)[0]


def _num_overhang(pins_on_edge: list[PinInfo]) -> float:
    w = max((textmetrics.text_wh(p.number)[0] for p in pins_on_edge),
            default=0.0)
    return max(0.0, w - PIN_LEN)


def _effects(size: float = 1.27) -> list:
    return [Sym("effects"), [Sym("font"), [Sym("size"), size, size]]]


def _hidden_effects() -> list:
    return [Sym("effects"), [Sym("font"), [Sym("size"), 1.27, 1.27]],
            [Sym("hide"), Sym("yes")]]


def _pin_sx(p: PinInfo, x: float, y: float, rot: int,
            length: float = PIN_LEN) -> list:
    return [Sym("pin"), Sym(p.etype), Sym("line"),
            [Sym("at"), x, y, rot],
            [Sym("length"), length],
            [Sym("name"), p.name, _effects()],
            [Sym("number"), p.number, _effects()]]


def _edge_pin_len(pins_on_edge: list[PinInfo]) -> float:
    w = max((textmetrics.text_wh(p.number)[0] for p in pins_on_edge),
            default=0.0)
    return max(PIN_LEN, _ceil_grid(w + 0.6, step=GRID))


def gen_symbol(name: str, pins: list[PinInfo], info: dict) -> list:
    g = group_pins(pins)
    hide_names = all(p.name == p.number for p in pins)

    name_off = 0.508
    max_l = max((_name_w(p) for p in g.left), default=0.0)
    max_r = max((_name_w(p) for p in g.right), default=0.0)
    max_t = max((_name_w(p) for p in g.top), default=0.0)
    max_b = max((_name_w(p) for p in g.bottom), default=0.0)
    if hide_names:
        max_l = max_r = max_t = max_b = 0.0

    w_names = max_l + max_r + 2 * name_off + PITCH
    w_row = (max(len(g.top), len(g.bottom)) + 1) * PITCH
    width = max(_ceil_grid(w_names), _ceil_grid(w_row), 2 * PITCH)
    pad_t = _ceil_grid(max_t + name_off + 1.27) if (g.top and max_t) else 0.0
    pad_b = _ceil_grid(max_b + name_off + 1.27) if (g.bottom and max_b) else 0.0
    h_rows = (max(len(g.left), len(g.right)) + 1) * PITCH
    h_names = max_t + max_b + 2 * name_off + PITCH
    height = max(_ceil_grid(h_rows) + pad_t + pad_b, _ceil_grid(h_names),
                 2 * PITCH)

    hw, hh = width / 2, height / 2
    len_l, len_r = _edge_pin_len(g.left), _edge_pin_len(g.right)
    len_t, len_b = _edge_pin_len(g.top), _edge_pin_len(g.bottom)
    pin_nodes: list[list] = []
    for i, p in enumerate(g.left):
        y = hh - pad_t - PITCH * (i + 1)
        pin_nodes.append(_pin_sx(p, -hw - len_l, y, 0, len_l))
    for i, p in enumerate(g.right):
        y = hh - pad_t - PITCH * (i + 1)
        pin_nodes.append(_pin_sx(p, hw + len_r, y, 180, len_r))
    for j, p in enumerate(g.top):
        x = -PITCH * (len(g.top) - 1) / 2 + PITCH * j
        pin_nodes.append(_pin_sx(p, x, hh + len_t, 270, len_t))
    for j, p in enumerate(g.bottom):
        x = -PITCH * (len(g.bottom) - 1) / 2 + PITCH * j
        pin_nodes.append(_pin_sx(p, x, -hh - len_b, 90, len_b))

    body = [Sym("rectangle"),
            [Sym("start"), -hw, hh], [Sym("end"), hw, -hh],
            [Sym("stroke"), [Sym("width"), 0.254], [Sym("type"), Sym("default")]],
            [Sym("fill"), [Sym("type"), Sym("background")]]]

    def prop(pname: str, value: str, x: float, y: float, hide: bool) -> list:
        return [Sym("property"), pname, value, [Sym("at"), x, y, 0],
                _hidden_effects() if hide else _effects()]

    pin_names_blk: list = [Sym("pin_names"), [Sym("offset"), name_off]]
    if hide_names:
        pin_names_blk.append([Sym("hide"), Sym("yes")])

    sym = [Sym("symbol"), name,
           pin_names_blk,
           [Sym("exclude_from_sim"), Sym("no")],
           [Sym("in_bom"), Sym("yes")],
           [Sym("on_board"), Sym("yes")],
           prop("Reference", info.get("prefix", "U"), 0,
                hh + len_t + 1.27, False),
           prop("Value", info.get("mpn", name), 0,
                -hh - len_b - 1.27, False),
           prop("Footprint", f"{name}:{name}", 0, 0, True),
           prop("Datasheet", info.get("datasheet", ""), 0, 0, True),
           prop("Description", info.get("description", ""), 0, 0, True),
           prop("LCSC", info.get("lcsc", ""), 0, 0, True),
           [Sym("symbol"), f"{name}_0_1", body],
           [Sym("symbol"), f"{name}_1_1", *pin_nodes]]

    return [Sym("kicad_symbol_lib"),
            [Sym("version"), 20241209],
            [Sym("generator"), "schgen_part_gen"],
            [Sym("generator_version"), "1.0"],
            sym]


_PAD_SHAPE = {"ELLIPSE": "circle", "RECT": "rect", "OVAL": "oval",
              "POLYGON": "custom"}
_LAYERS = {1: "F.Cu", 2: "B.Cu", 3: "F.SilkS", 4: "B.SilkS", 5: "F.Paste",
           6: "B.Paste", 7: "F.Mask", 8: "B.Mask", 10: "Edge.Cuts",
           12: "Cmts.User", 13: "F.Fab", 14: "B.Fab", 15: "Dwgs.User",
           99: "F.CrtYd", 100: "F.Fab", 101: "F.SilkS"}
_PAD_LAYERS_SMD = {1: ["F.Cu", "F.Paste", "F.Mask"],
                   2: ["B.Cu", "B.Paste", "B.Mask"],
                   11: ["*.Cu", "*.Paste", "*.Mask"]}
_PAD_LAYERS_THT = {1: ["F.Cu", "F.Mask"], 2: ["B.Cu", "B.Mask"],
                   11: ["*.Cu", "*.Mask"]}
_REGION_LAYERS = {3, 4, 13, 14, 99}


def _f(v: str | float, default: float = 0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _mm(v: str | float) -> float:
    return round(_f(v) * MM, 6)


class _FpCtx:
    def __init__(self, ox: float, oy: float) -> None:
        self.ox, self.oy = ox, oy

    def pt(self, x: str | float, y: str | float) -> tuple[float, float]:
        return (round((_f(x) - self.ox) * MM, 4), round((_f(y) - self.oy) * MM, 4))


def _stroke(width: float) -> list:
    return [Sym("stroke"), [Sym("width"), round(max(width, 0.01), 4)],
            [Sym("type"), Sym("solid")]]


def _svg_tokens(path: str) -> list[tuple[str, list[float]]]:
    out = []
    for tok in re.split(r"(?=[MLHVAZmlhvaz])", path.strip()):
        tok = tok.strip()
        if not tok:
            continue
        args = [float(a) for a in re.split(r"[,\s]+", tok[1:].strip()) if a]
        out.append((tok[0].upper(), args))
    return out


def _path_points(path: str, ctx: _FpCtx) -> list[tuple[float, float]]:
    pts: list[tuple[float, float]] = []
    cx = cy = 0.0
    for cmd, args in _svg_tokens(path):
        if cmd in ("M", "L") and len(args) >= 2:
            for i in range(0, len(args) - 1, 2):
                cx, cy = args[i], args[i + 1]
                pts.append(ctx.pt(cx, cy))
        elif cmd == "H" and args:
            cx = args[-1]
            pts.append(ctx.pt(cx, cy))
        elif cmd == "V" and args:
            cy = args[-1]
            pts.append(ctx.pt(cx, cy))
        elif cmd == "A" and len(args) >= 7:
            cx, cy = args[5], args[6]
            pts.append(ctx.pt(cx, cy))
        elif cmd == "Z" and pts and pts[0] != pts[-1]:
            pts.append(pts[0])
    return pts


def _arc_center(x0: float, y0: float, rx: float, ry: float, phi_deg: float,
                large: bool, sweep: bool, x1: float, y1: float
                ) -> tuple[float, float] | None:
    rx, ry = abs(rx), abs(ry)
    if rx < 1e-9 or ry < 1e-9:
        return None
    phi = math.radians(phi_deg % 360)
    c, s = math.cos(phi), math.sin(phi)
    dx, dy = (x0 - x1) / 2, (y0 - y1) / 2
    x1p = c * dx + s * dy
    y1p = -s * dx + c * dy
    lam = x1p ** 2 / rx ** 2 + y1p ** 2 / ry ** 2
    if lam > 1:
        rx *= math.sqrt(lam)
        ry *= math.sqrt(lam)
    num = rx ** 2 * ry ** 2 - rx ** 2 * y1p ** 2 - ry ** 2 * x1p ** 2
    den = rx ** 2 * y1p ** 2 + ry ** 2 * x1p ** 2
    coef = math.sqrt(max(num / den, 0)) if den else 0.0
    if large == sweep:
        coef = -coef
    cxp = coef * rx * y1p / ry
    cyp = -coef * ry * x1p / rx
    return (c * cxp - s * cyp + (x0 + x1) / 2,
            s * cxp + c * cyp + (y0 + y1) / 2)


def _arc_three_points(path: str, ctx: _FpCtx
                      ) -> list[tuple[tuple[float, float], ...]]:
    arcs = []
    cur: tuple[float, float] | None = None
    for cmd, args in _svg_tokens(path):
        if cmd == "M" and len(args) >= 2:
            cur = (args[0], args[1])
        elif cmd == "A" and len(args) >= 7 and cur is not None:
            rx, ry, rot, large, sweep, ex, ey = args[:7]
            ctr = _arc_center(cur[0], cur[1], rx, ry, rot,
                              bool(large), bool(sweep), ex, ey)
            if ctr is None:
                cur = (ex, ey)
                continue
            a0 = math.atan2(cur[1] - ctr[1], cur[0] - ctr[0])
            a1 = math.atan2(ey - ctr[1], ex - ctr[0])
            delta = (a1 - a0) % (2 * math.pi)
            if not sweep:
                delta -= 2 * math.pi
            amid = a0 + delta / 2
            r = math.hypot(cur[0] - ctr[0], cur[1] - ctr[1])
            mid = (ctr[0] + r * math.cos(amid), ctr[1] + r * math.sin(amid))
            arcs.append((ctx.pt(*cur), ctx.pt(*mid), ctx.pt(ex, ey)))
            cur = (ex, ey)
    return arcs


PASTE_RELIEF_MIN = 2.0
PASTE_COVER = 0.6
PASTE_PITCH_MAX = 1.5
MODEL_BODY_OVERHANG_MM = 5.0


def _paste_grid(number: str, cx: float, cy: float, w: float, h: float,
                rot: float) -> list:
    import math
    nx = max(2, math.ceil(w / PASTE_PITCH_MAX))
    ny = max(2, math.ceil(h / PASTE_PITCH_MAX))
    px, py = w / nx, h / ny
    aw = round(px * math.sqrt(PASTE_COVER), 4)
    ah = round(py * math.sqrt(PASTE_COVER), 4)
    th = math.radians(rot)
    cos, sin = math.cos(th), math.sin(th)
    out: list = []
    for i in range(nx):
        for j in range(ny):
            ox = -w / 2 + px * (i + 0.5)
            oy = -h / 2 + py * (j + 0.5)
            ax = round(cx + ox * cos - oy * sin, 4)
            ay = round(cy + ox * sin + oy * cos, 4)
            at = [Sym("at"), ax, ay]
            if rot:
                at.append(round(rot, 2))
            out.append([Sym("pad"), str(number), Sym("smd"), Sym("rect"),
                        at, [Sym("size"), aw, ah],
                        [Sym("layers"), "F.Paste"]])
    return out


@dataclass(frozen=True)
class _EpSpec:
    w: float
    h: float
    cite: str


PACKAGE_EP: dict[str, _EpSpec] = {
    "C3192119": _EpSpec(1.0, 1.1, "MPS MPQ4423H Rev1.11 QFN-8 BOTTOM VIEW "
                        "D2xE2 = 0.95-1.05 x 1.05-1.15 mm -> 1.0x1.1 nominal"),
}


@dataclass(frozen=True)
class _PolaritySpec:
    x: float
    y: float
    size: float
    cite: str


PACKAGE_SILK_PLUS: dict[str, _PolaritySpec] = {
    "C5365933": _PolaritySpec(-5.6, 0.0, 0.6,
        "EasyEDA dataStr layer-12 SOLIDREGION '+' cross at pad-1 (V_RTC_BAT) "
        "side; board_services BT1.1=V_RTC_BAT, BT1.2=GND -> pad 1 is '+'"),
}


def _ep_number(pins: list[PinInfo]) -> str:
    nums = [int(p.number) for p in pins if p.number.isdigit()]
    return str(max(nums) + 1) if nums else "EP"


def synth_ep_pin(info: dict, pins: list[PinInfo]) -> PinInfo | None:
    if PACKAGE_EP.get(info.get("lcsc", "")) is None:
        return None
    if any((p.name or "").upper() in ("EP", "PAD", "EPAD") for p in pins):
        return None
    return PinInfo(_ep_number(pins), "EP", "passive")


def synth_ep_pad_nodes(number: str, lcsc: str) -> list:
    spec = PACKAGE_EP[lcsc]
    w, h = spec.w, spec.h
    if min(w, h) >= PASTE_RELIEF_MIN:
        main = [Sym("pad"), number, Sym("smd"), Sym("rect"),
                [Sym("at"), 0.0, 0.0], [Sym("size"), w, h],
                [Sym("layers"), "F.Cu", "F.Mask"]]
        return [main, *_paste_grid(number, 0.0, 0.0, w, h, 0.0)]
    return [[Sym("pad"), number, Sym("smd"), Sym("rect"),
             [Sym("at"), 0.0, 0.0], [Sym("size"), w, h],
             [Sym("layers"), "F.Cu", "F.Paste", "F.Mask"]]]


def synth_silk_plus_nodes(lcsc: str) -> list:
    s = PACKAGE_SILK_PLUS.get(lcsc)
    if s is None:
        return []
    return [
        [Sym("fp_line"), [Sym("start"), round(s.x - s.size, 4), s.y],
         [Sym("end"), round(s.x + s.size, 4), s.y],
         _stroke(0.15), [Sym("layer"), "F.SilkS"]],
        [Sym("fp_line"), [Sym("start"), s.x, round(s.y - s.size, 4)],
         [Sym("end"), s.x, round(s.y + s.size, 4)],
         _stroke(0.15), [Sym("layer"), "F.SilkS"]],
    ]


def _pad_sx(fields: list[str], ctx: _FpCtx) -> list | None:
    (shape, cx, cy, w, h, layer, _net, number, hole_r, points, rot
     ) = fields[:11]
    if "(" in number and ")" in number:
        number = number.split("(")[1].split(")")[0]
    hole_len = _mm(fields[12]) if len(fields) > 12 else 0.0
    plated = (fields[14].upper() == "Y") if len(fields) > 14 and fields[14] else True
    x, y = ctx.pt(cx, cy)
    w_mm, h_mm = max(_mm(w), 0.01), max(_mm(h), 0.01)
    hole_d = 2 * _mm(hole_r)
    layer_id = int(_f(layer, 1))
    rot_deg = _f(rot) % 360

    ki_shape = _PAD_SHAPE.get(shape, "custom")
    through = hole_d > 0
    if through and not plated:
        ptype = "np_thru_hole"
    elif through:
        ptype = "thru_hole"
    else:
        ptype = "smd"
    layers = (_PAD_LAYERS_THT if through else _PAD_LAYERS_SMD).get(
        layer_id, _PAD_LAYERS_THT.get(11) if through else _PAD_LAYERS_SMD.get(1))
    if shape == "ELLIPSE" and abs(w_mm - h_mm) > 1e-6:
        ki_shape = "oval"

    pad: list = [Sym("pad"), str(number), Sym(ptype), Sym(ki_shape)]
    at: list = [Sym("at"), x, y]
    if ki_shape != "custom" and rot_deg:
        at.append(round(rot_deg, 2))
    pad.append(at)

    if ki_shape == "custom":
        pts = [p for p in points.split() if p]
        prim_pts: list = [Sym("pts")]
        for i in range(0, len(pts) - 1, 2):
            px, py = ctx.pt(pts[i], pts[i + 1])
            prim_pts.append([Sym("xy"), round(px - x, 4), round(py - y, 4)])
        if len(prim_pts) < 4:
            return None
        pad.append([Sym("size"), 0.1, 0.1])
        pad.append([Sym("layers"), *layers])
        pad.append([Sym("options"), [Sym("clearance"), Sym("outline")],
                    [Sym("anchor"), Sym("rect")]])
        pad.append([Sym("primitives"),
                    [Sym("gr_poly"), prim_pts, [Sym("width"), 0],
                     [Sym("fill"), Sym("yes")]]])
    else:
        pad.append([Sym("size"), w_mm, h_mm])
        if through:
            if hole_len > 0:
                long_axis = max(hole_d, hole_len)
                if (h_mm - long_axis) >= (w_mm - long_axis):
                    pad.append([Sym("drill"), Sym("oval"), hole_d, hole_len])
                else:
                    pad.append([Sym("drill"), Sym("oval"), hole_len, hole_d])
            else:
                pad.append([Sym("drill"), hole_d])
        if (not through and ki_shape in ("rect", "roundrect")
                and "F.Paste" in layers
                and min(w_mm, h_mm) >= PASTE_RELIEF_MIN):
            pad.append([Sym("layers"), *[ly for ly in layers if ly != "F.Paste"]])
            return [pad, *_paste_grid(number, x, y, w_mm, h_mm, rot_deg)]
        pad.append([Sym("layers"), *layers])
    return [pad]


def convert_footprint(result: dict, name: str, info: dict,
                      model_files: list[str],
                      ep_pin: PinInfo | None = None) -> tuple[list, dict | None]:
    pkg = result.get("packageDetail") or {}
    data = pkg.get("dataStr") or {}
    if not data.get("shape"):
        raise PartGenError("EasyEDA payload has no footprint (packageDetail)")
    head = data.get("head", {})
    ctx = _FpCtx(_f(head.get("x")), _f(head.get("y")))
    c_para = head.get("c_para", {})

    smd = bool(result.get("SMT")) and "-TH_" not in (pkg.get("title") or "")

    fp: list = [Sym("footprint"), name,
                [Sym("version"), 20260206],
                [Sym("generator"), "schgen_part_gen"],
                [Sym("generator_version"), "1.0"],
                [Sym("layer"), "F.Cu"],
                [Sym("descr"),
                 f"{c_para.get('package', '')} — {info.get('description', '')} "
                 f"(EasyEDA/LCSC {info.get('lcsc', '')}, faithful conversion)"],
                [Sym("tags"), " ".join(info.get("tags", []))]]

    pads: list[list] = []
    graphics: list[list] = []
    model_3d: dict | None = None

    for line in data["shape"]:
        kind, _, rest = line.partition("~")
        fields = rest.split("~")
        if kind == "PAD":
            p = _pad_sx(fields, ctx)
            if p is not None:
                pads.extend(p)
        elif kind == "TRACK":
            width = _mm(fields[0])
            layer = _LAYERS.get(int(_f(fields[1], 3)), "F.Fab")
            pts = [p for p in fields[3].split() if p]
            for i in range(0, len(pts) - 3, 2):
                x0, y0 = ctx.pt(pts[i], pts[i + 1])
                x1, y1 = ctx.pt(pts[i + 2], pts[i + 3])
                graphics.append([Sym("fp_line"),
                                 [Sym("start"), x0, y0], [Sym("end"), x1, y1],
                                 _stroke(width), [Sym("layer"), layer]])
        elif kind == "CIRCLE":
            x, y = ctx.pt(fields[0], fields[1])
            r = _mm(fields[2])
            layer = _LAYERS.get(int(_f(fields[4], 3)), "F.Fab")
            graphics.append([Sym("fp_circle"),
                             [Sym("center"), x, y],
                             [Sym("end"), round(x + r, 4), y],
                             _stroke(_mm(fields[3])),
                             [Sym("fill"), Sym("none")], [Sym("layer"), layer]])
        elif kind == "RECT":
            x, y = ctx.pt(fields[0], fields[1])
            w, h = _mm(fields[2]), _mm(fields[3])
            layer = _LAYERS.get(int(_f(fields[4], 3)), "F.Fab")
            sw = _mm(fields[7]) if len(fields) > 7 else 0.1
            graphics.append([Sym("fp_rect"),
                             [Sym("start"), x, y],
                             [Sym("end"), round(x + w, 4), round(y + h, 4)],
                             _stroke(sw), [Sym("fill"), Sym("none")],
                             [Sym("layer"), layer]])
        elif kind == "ARC":
            layer = _LAYERS.get(int(_f(fields[1], 3)), "F.Fab")
            for start, mid, end in _arc_three_points(fields[3], ctx):
                graphics.append([Sym("fp_arc"),
                                 [Sym("start"), *start], [Sym("mid"), *mid],
                                 [Sym("end"), *end],
                                 _stroke(_mm(fields[0])), [Sym("layer"), layer]])
        elif kind == "HOLE":
            x, y = ctx.pt(fields[0], fields[1])
            d = 2 * _mm(fields[2])
            pads.append([Sym("pad"), "", Sym("np_thru_hole"), Sym("circle"),
                         [Sym("at"), x, y], [Sym("size"), d, d],
                         [Sym("drill"), d], [Sym("layers"), "*.Cu", "*.Mask"]])
        elif kind == "VIA":
            x, y = ctx.pt(fields[0], fields[1])
            dia, drill = _mm(fields[2]), 2 * _mm(fields[4])
            pads.append([Sym("pad"), "", Sym("thru_hole"), Sym("circle"),
                         [Sym("at"), x, y], [Sym("size"), dia, dia],
                         [Sym("drill"), drill], [Sym("layers"), "*.Cu", "*.Mask"]])
        elif kind == "TEXT":
            if len(fields) < 10 or not fields[9]:
                continue
            x, y = ctx.pt(fields[1], fields[2])
            layer = _LAYERS.get(int(_f(fields[6], 3)), "F.Fab")
            if fields[0] == "N":
                layer = layer.replace(".SilkS", ".Fab")
            size = max(_mm(fields[8]), 0.5)
            graphics.append([Sym("fp_text"), Sym("user"), fields[9],
                             [Sym("at"), x, y, round(_f(fields[4]) % 360, 2)],
                             [Sym("layer"), layer],
                             [Sym("effects"),
                              [Sym("font"), [Sym("size"), size, size],
                               [Sym("thickness"), max(_mm(fields[3]), 0.1)]]]])
        elif kind == "SOLIDREGION":
            layer_id = int(_f(fields[0], 3))
            rtype = fields[3] if len(fields) > 3 else "solid"
            if layer_id not in _REGION_LAYERS or rtype not in ("solid", "npth"):
                continue
            pts = _path_points(fields[2], ctx)
            if len(pts) < 3:
                continue
            if layer_id == 99:
                for i in range(len(pts) - 1):
                    graphics.append([Sym("fp_line"),
                                     [Sym("start"), *pts[i]],
                                     [Sym("end"), *pts[i + 1]],
                                     _stroke(0.05), [Sym("layer"), "F.CrtYd"]])
            else:
                poly_pts: list = [Sym("pts")]
                poly_pts += [[Sym("xy"), x, y] for x, y in pts]
                graphics.append([Sym("fp_poly"), poly_pts,
                                 [Sym("stroke"), [Sym("width"), 0],
                                  [Sym("type"), Sym("solid")]],
                                 [Sym("fill"), Sym("yes")],
                                 [Sym("layer"), _LAYERS[layer_id]]])
        elif kind == "SVGNODE":
            try:
                node = json.loads(fields[0])
            except json.JSONDecodeError:
                continue
            attrs = node.get("attrs", {})
            canvas = (data.get("canvas") or "").split("~")
            cox = _f(canvas[16]) if len(canvas) > 17 else ctx.ox
            coy = _f(canvas[17]) if len(canvas) > 17 else ctx.oy
            co = (attrs.get("c_origin") or "0,0").split(",")
            rot = (attrs.get("c_rotation") or "0,0,0").split(",")
            model_3d = {
                "uuid": attrs.get("uuid", ""),
                "title": attrs.get("title", ""),
                "tx": round((_f(co[0]) - cox) * MM, 4),
                "ty": round(-(_f(co[1] if len(co) > 1 else 0) - coy) * MM, 4),
                "tz": round(_f(attrs.get("z", 0)) * MM, 4),
                "rx": (360 - _f(rot[0])) % 360,
                "ry": (360 - _f(rot[1] if len(rot) > 1 else 0)) % 360,
                "rz": (360 - _f(rot[2] if len(rot) > 2 else 0)) % 360,
            }

    if ep_pin is not None:
        pads.extend(synth_ep_pad_nodes(ep_pin.number, info.get("lcsc", "")))

    graphics.extend(synth_silk_plus_nodes(info.get("lcsc", "")))

    fp.append([Sym("attr"), Sym("smd") if smd else Sym("through_hole")])

    ys = [n[4][2] for n in pads if len(n) > 4 and n[4][0] == "at"]
    y_lo = min(ys, default=0.0)
    y_hi = max(ys, default=0.0)

    def fp_prop(pname: str, value: str, y: float, layer: str, hide: bool) -> list:
        node = [Sym("property"), pname, value,
                [Sym("at"), 0, y, 0], [Sym("layer"), layer]]
        if hide:
            node.append([Sym("hide"), Sym("yes")])
        node.append([Sym("effects"),
                     [Sym("font"), [Sym("size"), 1, 1],
                      [Sym("thickness"), 0.15]]])
        return node

    fp.append(fp_prop("Reference", "REF**", round(y_lo - 2, 2), "F.SilkS", False))
    fp.append(fp_prop("Value", name, round(y_hi + 2, 2), "F.Fab", False))
    fp.append(fp_prop("Datasheet", info.get("datasheet", ""), 0, "F.Fab", True))
    fp.append(fp_prop("Description", info.get("description", ""), 0, "F.Fab", True))
    fp.append(fp_prop("LCSC", info.get("lcsc", ""), 0, "F.Fab", True))
    fp.append([Sym("fp_text"), Sym("user"), "${REFERENCE}",
               [Sym("at"), 0, 0, 0], [Sym("layer"), "F.Fab"],
               [Sym("effects"), [Sym("font"), [Sym("size"), 1, 1],
                                 [Sym("thickness"), 0.15]]]])

    fp.extend(graphics)
    fp.extend(pads)

    if model_3d and model_files:
        hx = hy = 0.0
        for _pad in pads:
            ax = ay = pw = ph = 0.0
            for _el in _pad:
                if isinstance(_el, list) and _el and _el[0] == Sym("at"):
                    ax, ay = float(_el[1]), float(_el[2])
                elif isinstance(_el, list) and _el and _el[0] == Sym("size"):
                    pw, ph = float(_el[1]), float(_el[2])
            hx, hy = max(hx, abs(ax) + pw / 2), max(hy, abs(ay) + ph / 2)
        bx, by = hx + MODEL_BODY_OVERHANG_MM, hy + MODEL_BODY_OVERHANG_MM
        # trap: catches only the GROSS unit mismatch; model3d_gate is authoritative
        if abs(model_3d["tx"]) > bx or abs(model_3d["ty"]) > by:
            print(f"  3d: implausible model offset "
                  f"({model_3d['tx']:.1f},{model_3d['ty']:.1f} mm vs bbox "
                  f"+/-{bx:.1f},{by:.1f}) -> reset to 0 "
                  f"(EasyEDA c_origin unit mismatch)")
            model_3d["tx"] = model_3d["ty"] = 0.0
        fp.append([Sym("model"), model_files[0],
                   [Sym("offset"), [Sym("xyz"), model_3d["tx"], model_3d["ty"],
                                    model_3d["tz"]]],
                   [Sym("scale"), [Sym("xyz"), 1, 1, 1]],
                   [Sym("rotate"), [Sym("xyz"), model_3d["rx"], model_3d["ry"],
                                    model_3d["rz"]]]])
    return fp, model_3d


def fetch_3d_models(uuid: str, outdir: Path, base: str) -> list[str]:
    files: list[str] = []
    if not uuid:
        return files
    step = _http_get(MODEL_STEP_URL.format(uuid=uuid), binary=True)
    if isinstance(step, bytes) and len(step) > 200 and b"ISO-10303" in step[:100]:
        (outdir / f"{base}.step").write_bytes(step)
        files.append(f"{base}.step")
    obj = _http_get(MODEL_OBJ_URL.format(uuid=uuid))
    if isinstance(obj, str) and "\nv " in obj:
        wrl = _obj_to_wrl(obj)
        if wrl:
            (outdir / f"{base}.wrl").write_text(wrl)
            files.append(f"{base}.wrl")
    files.sort(key=lambda f: 0 if f.endswith(".wrl") else 1)
    return files


def _obj_to_wrl(obj_data: str) -> str | None:
    mats: dict[str, dict] = {}
    for m in re.findall(r"newmtl .*?endmtl", obj_data, flags=re.DOTALL):
        mid = m.splitlines()[0].split()[1]
        mat: dict = {}
        for ln in m.splitlines():
            if ln.startswith("Kd"):
                mat["kd"] = ln.split()[1:4]
            elif ln.startswith("d "):
                mat["tr"] = ln.split()[1]
        mats[mid] = mat

    verts: list[tuple[float, float, float]] = []
    for ln in obj_data.splitlines():
        p = ln.split()
        if len(p) >= 4 and p[0] == "v":
            verts.append((float(p[1]), float(p[2]), float(p[3])))
    if not verts:
        return None
    cx = (min(v[0] for v in verts) + max(v[0] for v in verts)) / 2
    cy = (min(v[1] for v in verts) + max(v[1] for v in verts)) / 2
    z0 = min(v[2] for v in verts)
    sv = [(round((x - cx) / 2.54, 4), round((y - cy) / 2.54, 4),
           round((z - z0) / 2.54, 4)) for x, y, z in verts]

    out = ["#VRML V2.0 utf8", "# generated by schgen part add"]
    for shape in obj_data.split("usemtl")[1:]:
        lines = shape.splitlines()
        mat = mats.get(lines[0].strip(), {})
        kd = " ".join(mat.get("kd", ["0.6", "0.6", "0.6"]))
        tr = mat.get("tr", "0")
        idx_map: dict[int, int] = {}
        coords: list[str] = []
        faces: list[str] = []
        for ln in lines[1:]:
            p = ln.split()
            if not p or p[0] != "f":
                continue
            face = []
            for tok in p[1:]:
                vi = int(tok.split("/")[0])
                if vi not in idx_map:
                    idx_map[vi] = len(coords)
                    coords.append(" ".join(str(c) for c in sv[vi - 1]))
                face.append(str(idx_map[vi]))
            faces.append(",".join(face) + ",-1")
        if not faces:
            continue
        out.append(
            "Shape{appearance Appearance{material Material{"
            f"diffuseColor {kd} transparency {tr}}}}}"
            "geometry IndexedFaceSet{ccw TRUE solid FALSE "
            "coord Coordinate{point [" + ", ".join(coords) + "]} "
            "coordIndex [" + ",".join(faces) + "]}}")
    return "\n".join(out) if len(out) > 2 else None


def gen_part_json(name: str, info: dict, pins: list[PinInfo],
                  model_files: list[str]) -> str:
    payload = {
        "schema": "schgen.part/1",
        "mpn": info["mpn"],
        "safe_name": name,
        "lcsc": info["lcsc"],
        "description": info["description"],
        "manufacturer": info["manufacturer"],
        "package": info["package"],
        "jlc_class": info["jlc_class"],
        "prefix": info["prefix"],
        "datasheet": info["datasheet"],
        "product_url": info["product_url"],
        "lib_id": f"{name}:{name}",
        "footprint": f"{name}:{name}",
        "models_3d": list(model_files),
        "pins": [{"num": p.number, "name": p.name, "etype": p.etype}
                 for p in pins],
    }
    required = ("mpn", "safe_name", "lcsc", "description", "manufacturer",
                "package", "prefix", "datasheet", "lib_id", "footprint")
    for key in required:
        if not payload[key]:
            raise PartGenError(f"part.json field {key!r} must not be empty")
    if not payload["pins"]:
        raise PartGenError("part.json pins must not be empty")
    return json.dumps(payload, indent=2, ensure_ascii=False) + "\n"


def add_part(lcsc_id: str, name: str | None = None,
             parts_dir: Path = DEFAULT_PARTS_DIR,
             from_json: Path | None = None) -> Path:
    if from_json:
        payload = json.loads(Path(from_json).read_text())
    else:
        payload = fetch_cad(lcsc_id)
    result = payload["result"] if "result" in payload else payload

    info = part_info(result)
    if lcsc_id and not info["lcsc"]:
        info["lcsc"] = lcsc_id
    pins = normalize_etypes(parse_pins(result), info["prefix"])
    ep_pin = synth_ep_pin(info, pins)
    if ep_pin is not None:
        pins = [*pins, ep_pin]
    base = safe_name(name or info["mpn"])
    if not base:
        raise PartGenError(f"cannot derive a folder name for {lcsc_id}")

    outdir = parts_dir / base
    outdir.mkdir(parents=True, exist_ok=True)

    uuid_3d = ""
    for line in (result.get("packageDetail", {}).get("dataStr", {})
                 .get("shape", [])):
        if line.startswith("SVGNODE~"):
            try:
                uuid_3d = json.loads(line.split("~", 1)[1]).get(
                    "attrs", {}).get("uuid", "")
            except json.JSONDecodeError:
                pass
            break
    model_files = [] if from_json else fetch_3d_models(uuid_3d, outdir, base)
    if not model_files:
        model_files = [f.name for f in (outdir / f"{base}.wrl",
                                        outdir / f"{base}.step") if f.exists()]

    sym = gen_symbol(base, pins, info)
    (outdir / f"{base}.kicad_sym").write_text(sexpr.dumps(sym) + "\n")

    fp, _ = convert_footprint(result, base, info, model_files, ep_pin=ep_pin)
    (outdir / f"{base}.kicad_mod").write_text(sexpr.dumps(fp) + "\n")

    (outdir / "part.json").write_text(gen_part_json(base, info, pins, model_files))
    (outdir / f"{base}.easyeda.json").write_text(
        json.dumps(payload, indent=1, ensure_ascii=False) + "\n")
    if parts_dir.resolve() == DEFAULT_PARTS_DIR.resolve():
        from schgen.core import native as _nat
        if not _nat.catalog_recompile(parts_dir):
            raise PartGenError("catalog recompile returned false")

    from schgen.core.symbols import Library
    d = Library(extra_paths=[outdir]).get(f"{base}:{base}")
    sexpr.loads((outdir / f"{base}.kicad_mod").read_text())

    print(f"part: {info['mpn']} ({info['lcsc']}) -> {outdir}")
    print(f"  symbol:    {base}.kicad_sym ({len(d.pins)} pins, all on "
          f"{GRID} mm grid)")
    pad_count = sum(1 for n in fp if isinstance(n, list) and n
                    and n[0] == Sym("pad"))
    print(f"  footprint: {base}.kicad_mod ({pad_count} pads, faithful)")
    print(f"  3d:        {', '.join(model_files) if model_files else 'none'}")
    return outdir


def cmd_part_add(args: argparse.Namespace) -> int:
    try:
        add_part(args.lcsc_id, name=args.name,
                 parts_dir=args.parts_dir or DEFAULT_PARTS_DIR,
                 from_json=args.from_json)
        return 0
    except PartGenError as exc:
        print(f"part add FAILED: {exc}")
        return 1
