"""Layout constraints from typed ports — JLCPCB JLC04161H-7628 stackup.

Emits, from the PORT types declared in the subsystem models:
  - ``layout_constraints.kicad_dru``  — KiCad custom design rules (conditions
    keyed on net-class names; import the classes from the CSV);
  - ``layout_constraints.csv``        — the human/import table: one row per
    typed port with class, geometry, pairing and length-match group.

Stackup geometry — JLC04161H-7628 (4 layer, 1.6 mm; locked in
carrier/PLAN.md round 2). Outer-layer microstrip referenced to the L2/L3
plane through one sheet of 7628 prepreg (0.2104 mm, er~4.6). The width/gap
numbers below are JLCPCB's own impedance-calculator output for THIS stackup
(community-verified: eevblog thread "JLCPCB Impedance Calculator can't get
100R or 90R"; jlcpcb.com/impedance lists the stackup, the calculator gives
the geometry):

  90R  differential (USB 2.0 HS):   width 10.28 mil = 0.2611 mm, gap 8 mil = 0.2032 mm
  100R differential (TMDS/LVDS/MIPI/MDI): width 8.08 mil = 0.2052 mm, gap 8 mil = 0.2032 mm

NOTE: the often-quoted "90R at 0.127/0.127 mm" geometry belongs to the
THINNER JLC04161H-3313 prepreg (0.0994 mm), not the 7628 stackup this
project locked. Re-run jlcpcb.com/pcb-impedance-calculator before tape-out
if the stackup changes.

Length-match policy (documented defaults, override per-design later):
  usb_hs_pair: intra-pair skew <= 1.27 mm (USB 2.0 HS budget)
  diff_pair:   intra-pair skew <= 1.27 mm (1000BASE-T MDI class)
  tmds_pair:   intra-pair skew <= 0.15 mm; inter-pair <= 5 mm (HDMI class)
  sd_bus:      bus length match <= 2.5 mm to CLK
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

from schgen.model import NetClass

MM_PER_MIL = 0.0254


@dataclass(frozen=True)
class DiffGeometry:
    impedance: int
    width_mm: float
    gap_mm: float
    source: str


# JLC04161H-7628, outer layer vs L2/L3 plane (see module docstring)
GEOMETRY: dict[int, DiffGeometry] = {
    90: DiffGeometry(90, round(10.28 * MM_PER_MIL, 4), round(8 * MM_PER_MIL, 4),
                     "JLCPCB calculator, JLC04161H-7628 outer/L2"),
    100: DiffGeometry(100, round(8.08 * MM_PER_MIL, 4), round(8 * MM_PER_MIL, 4),
                      "JLCPCB calculator, JLC04161H-7628 outer/L2"),
}

INTRA_PAIR_SKEW_MM = {
    "usb_hs_pair": 1.27,
    "diff_pair": 1.27,
    "tmds_pair": 0.15,
}
SD_BUS_MATCH_MM = 2.5


def _net_class(kind: str, impedance: int | None, level_v: float | None) -> str:
    if kind == "usb_hs_pair":
        return "DP90_USB"
    if kind == "tmds_pair":
        return "DP100_TMDS"
    if kind == "diff_pair":
        return f"DP{impedance}_DIFF"
    if kind == "i2c":
        return "I2C"
    if kind == "sd_bus":
        lv = f"{level_v:g}".replace(".", "V")
        return f"SD_{lv}"
    return "Default"


def export(sheets, outdir: Path) -> tuple[Path, Path]:
    """``sheets``: list of schgen.link.SheetCircuit. Writes the .kicad_dru
    and .csv into ``outdir``; returns both paths."""
    outdir.mkdir(parents=True, exist_ok=True)

    rows: list[dict] = []
    classes: dict[str, DiffGeometry | None] = {}
    pair_groups_seen: set[frozenset[str]] = set()

    for sc in sheets:
        c = sc.circuit
        for net in c.nets.values():
            if net.net_class != NetClass.PORT:
                continue
            pt = c.port_type_of(net.name)
            ncls = _net_class(pt.kind, pt.impedance, pt.level_v)
            geo = GEOMETRY.get(pt.impedance) if pt.impedance else None
            classes.setdefault(ncls, geo)
            group, tol = "", ""
            if pt.pair_with:
                key = frozenset((net.name, pt.pair_with))
                pair_groups_seen.add(key)
                group = "PAIR:" + "/".join(sorted(key))
                tol = f"{INTRA_PAIR_SKEW_MM[pt.kind]:g}"
            elif pt.kind == "sd_bus":
                group = f"BUS:{pt.bus or 'SD'}"
                tol = f"{SD_BUS_MATCH_MM:g}"
            rows.append({
                "net": net.name,
                "sheet": sc.name,
                "kind": pt.kind,
                "net_class": ncls,
                "impedance_ohm": pt.impedance or "",
                "track_width_mm": f"{geo.width_mm:g}" if geo else "",
                "pair_gap_mm": f"{geo.gap_mm:g}" if geo else "",
                "pair_with": pt.pair_with or "",
                "length_match_group": group,
                "match_tolerance_mm": tol,
                "notes": "; ".join(filter(None, (
                    f"bus={pt.bus}" if pt.bus else "",
                    f"speed={pt.speed_hz}Hz" if pt.speed_hz else "",
                    f"level={pt.level_v:g}V" if pt.level_v is not None else "",
                    f"deferred: {pt.expect}" if pt.expect else "",
                    geo.source if geo else ""))),
            })

    # ---- .kicad_dru -----------------------------------------------------------
    dru_lines = [
        "(version 1)",
        "",
        "# Generated by schgen/constraints.py from typed ports.",
        "# Stackup: JLCPCB JLC04161H-7628 (4L 1.6mm, 7628 prepreg 0.2104mm).",
        "# Geometry source: JLCPCB impedance calculator for this stackup",
        "# (90R diff: 0.2611/0.2032mm; 100R diff: 0.2052/0.2032mm, outer vs L2).",
        "# Assign nets to the classes listed in layout_constraints.csv first.",
        "",
    ]
    for ncls, geo in sorted(classes.items()):
        if geo is None:
            continue
        dru_lines += [
            f'(rule "{ncls}_geometry"',
            f'  (condition "A.NetClass == \'{ncls}\'")',
            f"  (constraint track_width (min {geo.width_mm}mm) "
            f"(opt {geo.width_mm}mm) (max {geo.width_mm}mm))",
            f"  (constraint diff_pair_gap (min {geo.gap_mm}mm) "
            f"(opt {geo.gap_mm}mm))",
            ")",
            "",
        ]
    dru_path = outdir / "layout_constraints.kicad_dru"
    dru_path.write_text("\n".join(dru_lines))

    # ---- CSV ------------------------------------------------------------------
    csv_path = outdir / "layout_constraints.csv"
    fieldnames = ["net", "sheet", "kind", "net_class", "impedance_ohm",
                  "track_width_mm", "pair_gap_mm", "pair_with",
                  "length_match_group", "match_tolerance_mm", "notes"]
    with open(csv_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for row in sorted(rows, key=lambda r: (r["net_class"], r["sheet"],
                                               r["net"])):
            w.writerow(row)
    return dru_path, csv_path
