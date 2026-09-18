from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from schgen.core import si_spec
from schgen.core.model import NetClass

MM_PER_MIL = 0.0254

# Outer-layer microstrip referenced to the L2/L3 plane, one 7628 prepreg sheet.


@dataclass(frozen=True)
class DiffGeometry:
    impedance: int
    width_mm: float
    gap_mm: float
    source: str


GEOMETRY: dict[int, DiffGeometry] = {
    90: DiffGeometry(90, round(10.28 * MM_PER_MIL, 4), round(8 * MM_PER_MIL, 4),
                     "JLCPCB calculator, JLC04161H-7628 outer/L2"),
    100: DiffGeometry(100, round(8.08 * MM_PER_MIL, 4), round(8 * MM_PER_MIL, 4),
                      "JLCPCB calculator, JLC04161H-7628 outer/L2"),
}

SD_BUS_MATCH_MM_UNCITED_POLICY = 2.5


def researched_skews(sheets) -> dict[str, si_spec.PairSpec]:
    for sc in sheets:
        c = sc.circuit
        for net in c.nets.values():
            if (net.net_class == NetClass.PORT
                    and c.port_type_of(net.name).pair_with):
                return si_spec.spec_by_net()
    return {}


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
    from dataclasses import asdict
    from schgen.core import native
    sheets = list(sheets)
    skews = researched_skews(sheets)
    dru, csv_text = native.module().layout_constraints(
        [{"name": sc.name, "circuit": sc.circuit.to_ir()} for sc in sheets],
        {"pairs": [asdict(spec) for spec in skews.values()]},
        str(si_spec.SI_SPEC_PATH))
    outdir.mkdir(parents=True, exist_ok=True)
    dru_path = outdir / "layout_constraints.kicad_dru"
    csv_path = outdir / "layout_constraints.csv"
    dru_path.write_bytes(dru.encode("utf-8"))
    csv_path.write_bytes(csv_text.encode("utf-8"))
    return dru_path, csv_path
