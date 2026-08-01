from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from schgen.core.model import Circuit
from schgen.core.symbols import Library, pin_page_position
from schgen.output.emit import (
    HierLabel,
    Junction,
    PlacedDesign,
    PlacedPart,
    PlacedPower,
    Wire,
    emit,
)
from schgen.verify import netlist_gate

OUT = Path("/tmp/schgen_m1/rc.kicad_sch")


def build() -> tuple[Circuit, PlacedDesign, Library]:
    c = Circuit("m1_rc", "M1 RC divider")
    c.part("R1", "Device:R", "10k")
    c.part("R2", "Device:R", "10k")
    c.part("C1", "Device:C", "100n")
    c.net("+3V3", "R1.1")
    c.port("MID", "R1.2", "R2.1", "C1.1")
    c.net("GND", "R2.2", "C1.2")

    lib = Library()
    c.validate({r: lib.pin_numbers(p.lib_id) for r, p in c.parts.items()})

    d = PlacedDesign(circuit=c)
    d.parts += [
        PlacedPart("R1", "Device:R", "10k", 101.6, 81.28,
                   ref_pos=(104.14, 80.01, 0), val_pos=(104.14, 82.55, 0)),
        PlacedPart("R2", "Device:R", "10k", 101.6, 101.6,
                   ref_pos=(104.14, 100.33, 0), val_pos=(104.14, 102.87, 0)),
        PlacedPart("C1", "Device:C", "100n", 111.76, 95.25,
                   ref_pos=(114.3, 93.98, 0), val_pos=(114.3, 96.52, 0)),
    ]
    pins = {}
    for p in d.parts:
        for pin in lib.get(p.lib_id).pins:
            pins[f"{p.ref}.{pin.number}"] = pin_page_position(pin, p.x, p.y, p.rotation)
    assert pins["R1.1"] == (101.6, 77.47), pins["R1.1"]
    assert pins["R1.2"] == (101.6, 85.09)
    assert pins["R2.1"] == (101.6, 97.79)
    assert pins["R2.2"] == (101.6, 105.41)
    assert pins["C1.1"] == (111.76, 91.44)
    assert pins["C1.2"] == (111.76, 99.06)

    d.powers += [
        PlacedPower("power:+3V3", "+3V3", "#PWR01", 101.6, 77.47),
        PlacedPower("power:GND", "GND", "#PWR02", 101.6, 105.41),
        PlacedPower("power:GND", "GND", "#PWR03", 111.76, 99.06),
        PlacedPower("power:PWR_FLAG", "PWR_FLAG", "#FLG01", 96.52, 77.47, 180),
        PlacedPower("power:PWR_FLAG", "PWR_FLAG", "#FLG02", 106.68, 105.41, 180),
    ]
    d.wires += [
        Wire(96.52, 77.47, 101.6, 77.47),
        Wire(101.6, 85.09, 101.6, 91.44),
        Wire(101.6, 91.44, 101.6, 97.79),
        Wire(101.6, 91.44, 111.76, 91.44),
        Wire(111.76, 91.44, 116.84, 91.44),
        Wire(101.6, 105.41, 106.68, 105.41),
    ]
    d.junctions += [Junction(101.6, 91.44), Junction(111.76, 91.44)]
    d.hlabels += [HierLabel("MID", 116.84, 91.44, 0)]
    return c, d, lib


def main() -> int:
    c, d, lib = build()
    emit(d, OUT, lib)
    print(f"emitted {OUT}")

    res = netlist_gate.check(c, OUT)
    print(res.summary())

    erc = subprocess.run(
        ["kicad-cli", "sch", "erc", "--severity-error", "--exit-code-violations",
         "-o", "/tmp/schgen_m1/erc.rpt", str(OUT)],
        capture_output=True, text=True)
    erc_ok = erc.returncode == 0
    print(f"ERC GATE: {'PASS' if erc_ok else 'FAIL'}")
    if not erc_ok:
        print(Path("/tmp/schgen_m1/erc.rpt").read_text()[-1500:])

    ok = res.ok and erc_ok
    print(f"M1: {'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
