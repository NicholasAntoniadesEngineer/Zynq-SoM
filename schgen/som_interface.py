"""Programmatic SoM↔carrier interface extraction.

The carrier's J1/J2/J3 sheets must mate the SoM's DF40 mezzanine connectors
pin-for-pin. The ONLY source of truth is the SoM KiCad project itself: this
module runs ``kicad-cli sch export netlist`` on the SoM and emits the
connector pin→net contract as JSON. Nothing is hand-copied — re-run after any
SoM change and the carrier rebuilds against the fresh contract.

    python -m schgen som-interface som/Zynq_SoM.kicad_sch \
        --refs J1,J2,J3 -o carrier/som_interface.json
"""

from __future__ import annotations

import json
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path


def extract(som_sch: Path, refs: list[str]) -> dict:
    with tempfile.NamedTemporaryFile(suffix=".net", delete=False) as tf:
        net = Path(tf.name)
    proc = subprocess.run(
        ["kicad-cli", "sch", "export", "netlist", "--format", "kicadxml",
         "-o", str(net), str(som_sch)],
        capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"kicad-cli failed on {som_sch}: {proc.stderr[-400:]}")
    root = ET.parse(net).getroot()

    meta: dict[str, dict] = {}
    comps = root.find("components")
    if comps is not None:
        for cmp in comps:
            ref = cmp.get("ref") or ""
            if ref in refs:
                val = cmp.find("value")
                fp = cmp.find("footprint")
                meta[ref] = {
                    "value": val.text if val is not None else "",
                    "footprint": fp.text if fp is not None else "",
                    "pins": {},
                }
    missing = [r for r in refs if r not in meta]
    if missing:
        raise RuntimeError(f"connector refs not found in SoM netlist: {missing}")

    nets_el = root.find("nets")
    if nets_el is not None:
        for n in nets_el:
            name = n.get("name") or ""
            for nd in n.findall("node"):
                ref = nd.get("ref") or ""
                if ref in meta:
                    meta[ref]["pins"][nd.get("pin") or ""] = name
    return {
        "source": str(som_sch),
        "connectors": meta,
    }


def cmd(args) -> int:
    refs = [r.strip() for r in args.refs.split(",") if r.strip()]
    data = extract(Path(args.som_sch), refs)
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, indent=1, sort_keys=True) + "\n")
    total = sum(len(c["pins"]) for c in data["connectors"].values())
    print(f"SoM interface: {len(refs)} connectors, {total} pins -> {out}")
    for ref, c in sorted(data["connectors"].items()):
        named = sum(1 for v in c["pins"].values()
                    if not v.startswith("unconnected-"))
        print(f"  {ref} ({c['value']}): {len(c['pins'])} pins, {named} netted")
    return 0
