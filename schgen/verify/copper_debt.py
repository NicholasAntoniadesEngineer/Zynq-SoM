from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path

from schgen.core import sexpr
from schgen.core.project import PROJECT_ROOT
from schgen.core.sexpr import Sym

REPO_ROOT = Path(__file__).resolve().parents[2]

_PAD_PREFIXES = ("LM61460", "TLV75725", "TPS26631")


@dataclass(frozen=True)
class ZoneInfo:
    name: str
    net_name: str
    layers: tuple[str, ...]
    keepout: bool
    filled: bool
    bbox: tuple[float, float, float, float]


@dataclass(frozen=True)
class ViaInfo:
    x: float
    y: float
    net_name: str


@dataclass(frozen=True)
class PadInfo:
    name: str
    dx: float
    dy: float
    drill: float
    net_name: str


@dataclass(frozen=True)
class FpInfo:
    ref: str
    value: str
    x: float
    y: float
    layer: str
    pads: tuple[PadInfo, ...]


@dataclass
class BoardCopper:
    path: Path
    zones: list[ZoneInfo] = field(default_factory=list)
    vias: list[ViaInfo] = field(default_factory=list)
    segments: int = 0
    footprints: list[FpInfo] = field(default_factory=list)
    net_names: set[str] = field(default_factory=set)

    def fill_zones(self, net: str, layer: str) -> list[ZoneInfo]:
        return [z for z in self.zones
                if not z.keepout and z.filled and z.net_name == net
                and layer in z.layers]

    def gnd_plane(self, layer: str = "In1.Cu") -> bool:
        return bool(self.fill_zones("GND", layer))

    def instances(self, value_prefix: str) -> list[FpInfo]:
        return sorted((f for f in self.footprints
                       if f.value.startswith(value_prefix)),
                      key=lambda f: f.ref)

    def gnd_vias_within(self, x: float, y: float, r: float) -> int:
        return sum(1 for v in self.vias if v.net_name == "GND"
                   and math.hypot(v.x - x, v.y - y) <= r)

    def pour_at(self, x: float, y: float, layer: str,
                net: str = "GND") -> bool:
        return any(z.bbox[0] <= x <= z.bbox[2] and z.bbox[1] <= y <= z.bbox[3]
                   for z in self.fill_zones(net, layer))

    def zone_named(self, prefix: str) -> list[ZoneInfo]:
        return sorted((z for z in self.zones if z.name.startswith(prefix)),
                      key=lambda z: z.name)

    def net_copper(self, net_substr: str) -> tuple[int, int]:
        zs = sum(1 for z in self.zones
                 if not z.keepout and net_substr in z.net_name)
        vs = sum(1 for v in self.vias if net_substr in v.net_name)
        return zs, vs


def _zone_info(node: list) -> ZoneInfo:
    name_n = sexpr.find(node, "name")
    net_n = sexpr.find(node, "net_name")
    lay1 = sexpr.find(node, "layer")
    layn = sexpr.find(node, "layers")
    layers: tuple[str, ...] = ()
    if lay1 and len(lay1) > 1:
        layers = (str(lay1[1]),)
    elif layn:
        layers = tuple(str(x) for x in layn[1:])
    fill = sexpr.find(node, "fill")
    filled = bool(fill and len(fill) > 1 and fill[1] == Sym("yes"))
    poly = sexpr.find(node, "polygon")
    xs: list[float] = []
    ys: list[float] = []
    if poly:
        pts = sexpr.find(poly, "pts")
        for xy in (pts or [])[1:]:
            if isinstance(xy, list) and len(xy) >= 3:
                xs.append(float(xy[1]))
                ys.append(float(xy[2]))
    bbox = (min(xs), min(ys), max(xs), max(ys)) if xs else (0.0, 0.0, 0.0, 0.0)
    return ZoneInfo(
        name=str(name_n[1]) if name_n and len(name_n) > 1 else "",
        net_name=str(net_n[1]) if net_n and len(net_n) > 1 else "",
        layers=layers,
        keepout=sexpr.find(node, "keepout") is not None,
        filled=filled,
        bbox=bbox)


def _fp_info(node: list) -> FpInfo:
    at = sexpr.find(node, "at")
    ref = value = ""
    for prop in sexpr.find_all(node, "property"):
        if len(prop) > 2 and prop[1] == "Reference":
            ref = str(prop[2])
        elif len(prop) > 2 and prop[1] == "Value":
            value = str(prop[2])
    lay = sexpr.find(node, "layer")
    pads: list[PadInfo] = []
    if value.startswith(_PAD_PREFIXES):
        for pad in sexpr.find_all(node, "pad"):
            pat = sexpr.find(pad, "at")
            dr = sexpr.find(pad, "drill")
            net = sexpr.find(pad, "net")
            pads.append(PadInfo(
                name=str(pad[1]) if len(pad) > 1 else "",
                dx=float(pat[1]) if pat and len(pat) > 1 else 0.0,
                dy=float(pat[2]) if pat and len(pat) > 2 else 0.0,
                drill=float(dr[1]) if dr and len(dr) > 1
                and isinstance(dr[1], (int, float)) else 0.0,
                net_name=str(net[2]) if net and len(net) > 2 else ""))
    return FpInfo(
        ref=ref, value=value,
        x=float(at[1]) if at and len(at) > 1 else 0.0,
        y=float(at[2]) if at and len(at) > 2 else 0.0,
        layer=str(lay[1]) if lay and len(lay) > 1 else "",
        pads=tuple(pads))


def scan_board(pcb_path: Path) -> BoardCopper:
    doc = sexpr.loads(Path(pcb_path).read_text())
    bc = BoardCopper(path=Path(pcb_path))
    for node in doc:
        if not (isinstance(node, list) and node):
            continue
        head = node[0]
        if head == Sym("zone"):
            bc.zones.append(_zone_info(node))
        elif head == Sym("via"):
            at = sexpr.find(node, "at")
            net = sexpr.find(node, "net")
            num = int(net[1]) if net and len(net) > 1 else 0
            bc.vias.append(ViaInfo(float(at[1]), float(at[2]), str(num)))
        elif head == Sym("segment"):
            bc.segments += 1
        elif head == Sym("footprint"):
            bc.footprints.append(_fp_info(node))
        elif head == Sym("net") and len(node) > 2:
            bc.net_names.add(str(node[2]))
    num2name: dict[str, str] = {}
    for node in doc:
        if isinstance(node, list) and node and node[0] == Sym("net") \
                and len(node) > 2:
            num2name[str(int(node[1]))] = str(node[2])
    bc.vias = [ViaInfo(v.x, v.y, num2name.get(v.net_name, v.net_name))
               for v in bc.vias]
    return bc


def _where(rel_path: str, anchor: str) -> str:
    p = REPO_ROOT / rel_path
    if not p.exists():
        return f"{rel_path}:FILE-MISSING"
    for n, line in enumerate(p.read_text().splitlines(), 1):
        if anchor in line:
            return f"{rel_path}:{n}"
    return f"{rel_path}:ANCHOR-NOT-FOUND({anchor!r})"


@dataclass
class Entry:
    eid: str
    title: str
    assumes: str
    where: list[str]
    emits: str
    status: str
    risk: str


@dataclass
class Result:
    entries: list[Entry] = field(default_factory=list)
    inventory: str = ""

    @property
    def n_entries(self) -> int:
        return len(self.entries)

    def n_status(self, s: str) -> int:
        return sum(1 for e in self.entries if e.status == s)


def _lm61460_entry(bc: BoardCopper | None) -> Entry:
    where = [
        _where("schgen/verify/thermal.py", '"LM61460": ThermalSpec('),
        _where("carrier/subsystems/power.py",
               "thermal gate now credits a CONSERVATIVE"),
    ]
    if bc is None:
        return Entry(
            "CD-01", "LM61460 pour-aware effective RthJA (58.7 -> 35 C/W)",
            _LM_ASSUMES, where, "UNMEASURED — no emitted board scanned",
            "UNMEASURED", _LM_RISK)
    insts = bc.instances("LM61460")
    plane = bc.gnd_plane()
    rows = []
    all_ok = bool(insts) and plane
    for f in insts:
        nv = bc.gnd_vias_within(f.x, f.y, 5.2)
        fp = bc.pour_at(f.x, f.y, "F.Cu")
        bp = bc.pour_at(f.x, f.y, "B.Cu")
        ok = nv >= 6 and fp and bp
        all_ok = all_ok and ok
        rows.append(f"{f.ref}: {nv} GND vias<=5.2mm, F.Cu pour "
                    f"{'YES' if fp else 'NO'}, B.Cu pour "
                    f"{'YES' if bp else 'NO'}")
    emits = (f"In1.Cu GND plane: {'YES' if plane else 'NO'}; "
             + "; ".join(rows))
    partial = plane or any(bc.gnd_vias_within(f.x, f.y, 5.2) for f in insts)
    status = "EMITTED" if all_ok else ("PARTIAL" if partial else "NOTHING")
    return Entry("CD-01",
                 "LM61460 pour-aware effective RthJA (58.7 -> 35 C/W)",
                 _LM_ASSUMES, where, emits, status, _LM_RISK)


_LM_ASSUMES = ("full-board In1.Cu GND plane + per-buck thermal-via field "
               "(>=6 x 0.6/0.3) at PGND1/PGND2 + local F.Cu/B.Cu GND pours "
               "(TI SNVSBD5D 7.3 bare 58.7 C/W vs 25 C/W on a 4-layer board; "
               "11.1.1 layout)")
_LM_RISK = ("without this copper Tj(power:U1, 2.42 W) backs out to ~192 C at "
            "the bare 58.7 C/W against the 140 C guard — a board-dead thermal "
            "PASS-on-fiction (the GAP1 CRITICAL). The thermal gate now "
            "HARD-verifies this copper per build.")


def _dyd_entry(bc: BoardCopper | None) -> Entry:
    where = [_where("schgen/verify/thermal.py", '("TLV75725", "DYD")')]
    assumes = ("DYD thermal pad soldered to GND copper + JESD51-5 "
               "pad-adjacent thermal vias into the buried plane (the DS DYD "
               "RthJA ~92.5 C/W is DEFINED on that stackup; without it the "
               "gate falls back to the DBV bare 231 C/W)")
    risk = ("at the no-copper fallback 231 C/W the VADJ LDO (fmc:U1, 320 mW) "
            "lands Tj ~124 C over its 115 C guard — the PWR-3 package swap's "
            "entire benefit rides on this copper")
    if bc is None:
        return Entry("CD-02", "TLV75725 DYD EP thermal-pad RthJA (92.5 C/W)",
                     assumes, where, "UNMEASURED — no emitted board scanned",
                     "UNMEASURED", risk)
    insts = bc.instances("TLV75725")
    plane = bc.gnd_plane()
    rows = []
    all_ok = bool(insts) and plane
    for f in insts:
        nv = bc.gnd_vias_within(f.x, f.y, 3.0)
        fp = bc.pour_at(f.x, f.y, "F.Cu")
        ok = nv >= 2 and fp
        all_ok = all_ok and ok
        rows.append(f"{f.ref}: {nv} GND vias<=3.0mm, F.Cu pour "
                    f"{'YES' if fp else 'NO'}")
    emits = (f"In1.Cu GND plane: {'YES' if plane else 'NO'}; "
             + "; ".join(rows))
    partial = plane or any(bc.gnd_vias_within(f.x, f.y, 3.0) for f in insts)
    status = "EMITTED" if all_ok else ("PARTIAL" if partial else "NOTHING")
    return Entry("CD-02", "TLV75725 DYD EP thermal-pad RthJA (92.5 C/W)",
                 assumes, where, emits, status, risk)


def _tps26631_entry(bc: BoardCopper | None) -> Entry:
    where = [_where("schgen/verify/thermal.py", '"TPS26631": ThermalSpec(')]
    assumes = ("HTSSOP-20 PowerPAD EP soldered to copper with thermal vias "
               "into a buried plane (TI SLVSE94 RthJA ~33.6 C/W is the JEDEC "
               "2s2p figure — it presumes internal planes)")
    risk = ("low today (Pd ~54 mW -> huge margin even at several times the "
            "2s2p figure), but the basis string was still plane-predicated "
            "while no plane existed")
    if bc is None:
        return Entry("CD-03", "TPS26631 PWP 2s2p RthJA (33.6 C/W)", assumes,
                     where, "UNMEASURED — no emitted board scanned",
                     "UNMEASURED", risk)
    insts = bc.instances("TPS26631")
    plane = bc.gnd_plane()
    rows = []
    all_ok = bool(insts) and plane
    for f in insts:
        nev = sum(1 for p in f.pads
                  if p.drill > 0 and p.net_name == "GND"
                  and math.hypot(p.dx, p.dy) <= 1.5)
        ok = nev >= 4
        all_ok = all_ok and ok
        rows.append(f"{f.ref}: {nev} in-footprint EP via-pads (GND, PTH)")
    emits = (f"In1.Cu GND plane: {'YES' if plane else 'NO'}; "
             + "; ".join(rows))
    status = "EMITTED" if all_ok else ("PARTIAL" if plane or rows else
                                       "NOTHING")
    return Entry("CD-03", "TPS26631 PWP 2s2p RthJA (33.6 C/W)", assumes,
                 where, emits, status, risk)


def _chassis_entry(bc: BoardCopper | None) -> Entry:
    where = [_where("carrier/subsystems/mechanical/mechanical.py",
                    "SINGLE-POINT STAR STITCH")]
    assumes = ("a CHASSIS_GND copper island (connector shells + mounting "
               "ring) joined to signal GND at EXACTLY ONE point (bonding pad "
               "/ 0R / via stitch near power entry)")
    risk = ("fab'd as-is the shields/mounting ring have NO DC reference "
            "(ESD return path open) — ERC/DRC cannot see it because the "
            "single-point bond is deliberately not netlisted")
    if bc is None:
        return Entry("CD-04", "CHASSIS_GND island + single-point GND bond",
                     assumes, where, "UNMEASURED — no emitted board scanned",
                     "UNMEASURED", risk)
    zs, vs = bc.net_copper("CHASSIS_GND")
    emits = (f"CHASSIS_GND board-level copper: {zs} zones, {vs} vias "
             "(pads only otherwise); no bond stitch emitted")
    status = "EMITTED" if (zs and vs) else ("PARTIAL" if (zs or vs)
                                            else "NOTHING")
    return Entry("CD-04", "CHASSIS_GND island + single-point GND bond",
                 assumes, where, emits, status, risk)


def _bobsmith_entry(bc: BoardCopper | None) -> Entry:
    where = [_where("subsystems/ethernet/ethernet.py",
                    "Bob-Smith: each MEDIA centre tap")]
    assumes = ("a Bob-Smith common trunk (4 x 75R || 1n/2kV into BS_COMMON) "
               "laid in copper on the chassis-side island, spaced for the "
               "2kV surge rating (IEEE 802.3 40.7.1)")
    risk = ("without trunk copper + spacing the 2kV HF termination exists "
            "only as parts; surge creepage and return-path behaviour are "
            "unproven until the routing wave draws the island")
    if bc is None:
        return Entry("CD-05", "Bob-Smith trunk copper (BS_COMMON island)",
                     assumes, where, "UNMEASURED — no emitted board scanned",
                     "UNMEASURED", risk)
    zs, vs = bc.net_copper("BS_COMMON")
    emits = f"BS_COMMON board-level copper: {zs} zones, {vs} vias (pads only)"
    status = "EMITTED" if (zs and vs) else ("PARTIAL" if (zs or vs)
                                            else "NOTHING")
    return Entry("CD-05", "Bob-Smith trunk copper (BS_COMMON island)",
                 assumes, where, emits, status, risk)


def _moat_entry(bc: BoardCopper | None) -> Entry:
    where = [_where("subsystems/ethernet/ethernet.py",
                    "chassis-ground island"),
             _where("schgen/generate/pcb/constants.py", "ISO_VOID_VALUES")]
    assumes = ("NO GND plane under the ethernet magnetics line side / RJ45 "
               "media pins (Pulse HX5008 layout guidance; the 2kV isolation "
               "moat) — the full-board In1 plane must be VOIDED there")
    risk = ("a continuous plane under the magnetics bridges the isolation "
            "barrier capacitively and violates the 2kV creepage intent; the "
            "RJ45<->magnetics media CORRIDOR void remains routing-wave debt")
    if bc is None:
        return Entry("CD-06", "Ethernet isolation moat (In1 plane voids)",
                     assumes, where, "UNMEASURED — no emitted board scanned",
                     "UNMEASURED", risk)
    voids = bc.zone_named("ethernet_isolation_void")
    names = ", ".join(z.name for z in voids) or "none"
    plane = bc.gnd_plane()
    emits = (f"In1 rule-area voids: {names}; corridor between them: "
             "NOT voided (debt)")
    if not plane:
        status = "NOTHING" if not voids else "PARTIAL"
    else:
        status = "PARTIAL" if len(voids) >= 2 else "NOTHING"
    return Entry("CD-06", "Ethernet isolation moat (In1 plane voids)",
                 assumes, where, emits, status, risk)


def _dp_ref_entry(bc: BoardCopper | None) -> Entry:
    where = [_where("schgen/generate/constraints.py",
                    "Outer-layer microstrip referenced to the L2/L3")]
    assumes = ("the DP90_USB / DP100_TMDS trace geometry (widths/gaps in the "
               ".kicad_dru + net classes) is an OUTER-layer microstrip "
               "referenced to a CONTINUOUS L2 GND plane through one 7628 "
               "prepreg sheet")
    risk = ("without the L2 plane every impedance number in the dru is "
            "unmoored (return path undefined, impedance wrong by design); "
            "with the plane emitted the residual risk is fill VOIDS/splits "
            "under a future route path (checked at the routing wave)")
    if bc is None:
        return Entry("CD-07", "DP90/DP100 L2 reference plane", assumes,
                     where, "UNMEASURED — no emitted board scanned",
                     "UNMEASURED", risk)
    plane = bc.fill_zones("GND", "In1.Cu")
    if plane:
        z = plane[0]
        emits = (f"In1.Cu GND plane zone {z.bbox[0]:g},{z.bbox[1]:g} -> "
                 f"{z.bbox[2]:g},{z.bbox[3]:g} mm (unfilled-on-disk, "
                 "DRC-refilled); ethernet voids punch it locally (CD-06)")
        status = "EMITTED"
    else:
        emits = "no GND fill zone on In1.Cu"
        status = "NOTHING"
    return Entry("CD-07", "DP90/DP100 L2 reference plane", assumes, where,
                 emits, status, risk)


def _som_fanout_entry(bc: BoardCopper | None) -> Entry:
    where = [_where("schgen/generate/pcb/embed.py",
                    "fanout vias right beneath the connector")]
    assumes = ("the under-SoM bottom-side rail-entry decoupling "
               "(som_decoupling) reaches the rails/planes through fanout "
               "vias directly beneath the DF40 mezzanine")
    risk = ("until those vias land the 18 bottom caps decouple nothing "
            "(no path from B.Cu pads to the rails) — a routing-wave item, "
            "but the prose reads as if the path exists")
    if bc is None:
        return Entry("CD-08", "Under-SoM decoupling fanout vias", assumes,
                     where, "UNMEASURED — no emitted board scanned",
                     "UNMEASURED", risk)
    som = bc.zone_named("SoM_body_keepout")
    n = 0
    if som:
        x0, y0, x1, y1 = som[0].bbox
        n = sum(1 for v in bc.vias if v.net_name == "GND"
                and x0 <= v.x <= x1 and y0 <= v.y <= y1)
    emits = (f"GND vias inside the SoM body zone: {n} "
             f"(SoM zone {'found' if som else 'NOT found'}); "
             "rail fanout vias: none emitted")
    status = "PARTIAL" if n else "NOTHING"
    return Entry("CD-08", "Under-SoM decoupling fanout vias", assumes, where,
                 emits, status, risk)


def analyze(pcb_path: Path | None) -> Result:
    bc = scan_board(pcb_path) if pcb_path and Path(pcb_path).exists() else None
    res = Result()
    if bc is not None:
        n_fill = sum(1 for z in bc.zones if not z.keepout and z.filled)
        n_rule = sum(1 for z in bc.zones if z.keepout)
        n_gnd_vias = sum(1 for v in bc.vias if v.net_name == "GND")
        res.inventory = (
            f"{n_fill} fill zones ({'with' if bc.gnd_plane() else 'NO'} "
            f"In1.Cu GND plane), {n_rule} rule areas, "
            f"{len(bc.vias)} vias ({n_gnd_vias} GND), "
            f"{bc.segments} segments")
    else:
        res.inventory = "NO BOARD SCANNED (statuses UNMEASURED)"
    res.entries = [
        _lm61460_entry(bc),
        _dyd_entry(bc),
        _tps26631_entry(bc),
        _chassis_entry(bc),
        _bobsmith_entry(bc),
        _moat_entry(bc),
        _dp_ref_entry(bc),
        _som_fanout_entry(bc),
    ]
    return res


def report(res: Result) -> str:
    L = ["schgen copper-debt ledger — copper-predicated claims vs the "
         "EMITTED board",
         "=" * 78, "",
         "Every gate basis string / design-prose note that PRESUMES board "
         "copper,",
         "measured against what the emitter actually wrote into the "
         ".kicad_pcb this",
         "build. REPORT-ONLY (not a hard gate) — but the thermal gate "
         "HARD-verifies",
         "its pour credits against the same scan, so CD-01/CD-02 cannot "
         "pass on",
         "fiction regardless of this file. 'where' lines are anchor-resolved "
         "at",
         "report time (a vanished anchor reads ANCHOR-NOT-FOUND, never a "
         "stale line).",
         "",
         f"emitted copper inventory: {res.inventory}",
         ""]
    for e in res.entries:
        L.append(f"{e.eid}  {e.title}   [{e.status}]")
        L.append(f"  assumes: {e.assumes}")
        for i, w in enumerate(e.where):
            L.append(f"  where:   {w}" if i == 0 else f"           {w}")
        L.append(f"  emits:   {e.emits}")
        L.append(f"  risk:    {e.risk}")
        L.append("")
    L.append(f"COPPER DEBT: {res.n_entries} entries — "
             f"{res.n_status('EMITTED')} emitted, "
             f"{res.n_status('PARTIAL')} partial, "
             f"{res.n_status('NOTHING')} unemitted, "
             f"{res.n_status('UNMEASURED')} unmeasured (report-only)")
    return "\n".join(L)


def run(reports_dir: Path, pcb_path: Path | None) -> Result:
    res = analyze(pcb_path)
    reports_dir.mkdir(parents=True, exist_ok=True)
    (reports_dir / "copper_debt.txt").write_text(report(res) + "\n")
    return res


if __name__ == "__main__":
    _pcb = PROJECT_ROOT / "Zynq_Carrier.kicad_pcb"
    _res = run(PROJECT_ROOT / "reports", _pcb)
    print(report(_res))
