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
    # TemporaryDirectory (auto-removed) — the old NamedTemporaryFile(delete=
    # False) leaked one .net per call, same root cause as F3 in netlist_gate;
    # this path runs on every board build via the J1/J2/J3 contract.
    with tempfile.TemporaryDirectory(prefix="schgen_som_") as td:
        net = Path(td) / "som.net"
        proc = subprocess.run(
            ["kicad-cli", "sch", "export", "netlist", "--format", "kicadxml",
             "-o", str(net), str(som_sch)],
            capture_output=True, text=True)
        if proc.returncode != 0:
            raise RuntimeError(
                f"kicad-cli failed on {som_sch}: {proc.stderr[-400:]}")
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


def extract_zynq(som_sch: Path, zynq_ref: str = "U2",
                 jrefs: tuple[str, ...] = ("J1", "J2", "J3")) -> dict:
    """Programmatic Zynq ball map from the SoM netlist (NEVER hand-typed).

    Returns, in one ``kicad-cli`` pass over the SoM project:
    - ``pin_names``: ball -> the Zynq pin NAME (which carries the bank
      suffix ``..._35`` and the MRCC/SRCC clock capability — the symbol is
      the vendor pinout, so the bank map rides along for free),
    - ``ball_net``:  ball -> SoM net name (every netted ``zynq_ref`` pin),
    - ``jpin_net``:  "J2.20" -> SoM net name (the LIVE J-connector view,
      cross-checked by the XDC generator against the committed
      carrier/som_interface.json — a stale contract fails the build).
    """
    with tempfile.TemporaryDirectory(prefix="schgen_som_") as td:
        net = Path(td) / "som.net"
        proc = subprocess.run(
            ["kicad-cli", "sch", "export", "netlist", "--format", "kicadxml",
             "-o", str(net), str(som_sch)],
            capture_output=True, text=True)
        if proc.returncode != 0:
            raise RuntimeError(
                f"kicad-cli failed on {som_sch}: {proc.stderr[-400:]}")
        root = ET.parse(net).getroot()

    # component ref -> (lib, part) so the right libpart pin table is used
    libsource: dict[str, tuple[str, str]] = {}
    value = ""
    comps = root.find("components")
    for cmp in comps if comps is not None else []:
        ref = cmp.get("ref") or ""
        ls = cmp.find("libsource")
        if ls is not None:
            libsource[ref] = (ls.get("lib") or "", ls.get("part") or "")
        if ref == zynq_ref:
            v = cmp.find("value")
            value = v.text if v is not None else ""
    if zynq_ref not in libsource:
        raise RuntimeError(f"{zynq_ref} not found in SoM netlist {som_sch}")

    pin_names: dict[str, str] = {}
    libparts = root.find("libparts")
    for lp in libparts if libparts is not None else []:
        if (lp.get("lib") or "", lp.get("part") or "") == libsource[zynq_ref]:
            pins = lp.find("pins")
            for p in pins if pins is not None else []:
                pin_names[p.get("num") or ""] = p.get("name") or ""
    if not pin_names:
        raise RuntimeError(
            f"libpart pin table for {zynq_ref} ({libsource[zynq_ref]}) "
            f"missing from SoM netlist")

    ball_net: dict[str, str] = {}
    jpin_net: dict[str, str] = {}
    nets_el = root.find("nets")
    for n in nets_el if nets_el is not None else []:
        name = n.get("name") or ""
        for nd in n.findall("node"):
            ref = nd.get("ref") or ""
            if ref == zynq_ref:
                ball_net[nd.get("pin") or ""] = name
            elif ref in jrefs:
                jpin_net[f"{ref}.{nd.get('pin')}"] = name
    return {"zynq_ref": zynq_ref, "value": value, "source": str(som_sch),
            "pin_names": pin_names, "ball_net": ball_net,
            "jpin_net": jpin_net}


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
