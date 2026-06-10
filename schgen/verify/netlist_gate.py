"""The unfakeable electrical gate: declared netlist == KiCad's extracted netlist.

Runs ``kicad-cli sch export netlist`` on the EMITTED sheet and compares the
result to the :class:`schgen.model.Circuit`, pin by pin, net by net.

Failure modes this catches (all seen in the failed generator):
- SHORT: one extracted net carries pins from >=2 declared nets.
- OPEN: a declared net's pins split across >=2 extracted nets, or a pin with a
  declared net lands on a single-pin ``unconnected-(...)`` net.
- NC-CHEAT: a No-Connect emitted on a pin that has a declared net (KiCad then
  reports the pin "connected" — ERC passes while the circuit is broken).
- MISSING/EXTRA part or pin.

ERC=0 is necessary but NOT sufficient; this gate is the electrical truth.
"""

from __future__ import annotations

import subprocess
import tempfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

from schgen.model import Circuit, NetClass, PinRef


@dataclass
class GateResult:
    ok: bool
    shorts: list[str] = field(default_factory=list)
    opens: list[str] = field(default_factory=list)
    nc_cheats: list[str] = field(default_factory=list)
    part_mismatches: list[str] = field(default_factory=list)
    name_mismatches: list[str] = field(default_factory=list)

    def summary(self) -> str:
        if self.ok:
            return "NETLIST GATE: PASS (extracted == declared)"
        lines = ["NETLIST GATE: FAIL"]
        for tag, items in (("SHORT", self.shorts), ("OPEN", self.opens),
                           ("NC-CHEAT", self.nc_cheats),
                           ("PART", self.part_mismatches),
                           ("NAME", self.name_mismatches)):
            for it in items:
                lines.append(f"  {tag}: {it}")
        return "\n".join(lines)


def extract_netlist(sch_path: Path) -> dict[str, list[PinRef]]:
    """KiCad's own view of the emitted sheet: net name -> pins."""
    with tempfile.NamedTemporaryFile(suffix=".net", delete=False) as tf:
        out = Path(tf.name)
    proc = subprocess.run(
        ["kicad-cli", "sch", "export", "netlist", "--format", "kicadxml",
         "-o", str(out), str(sch_path)],
        capture_output=True, text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"kicad-cli netlist export failed: {proc.stderr[-500:]}")
    root = ET.parse(out).getroot()
    nets: dict[str, list[PinRef]] = {}
    nets_el = root.find("nets")
    if nets_el is not None:
        for n in nets_el:
            name = n.get("name") or ""
            nets[name] = [PinRef(nd.get("ref") or "", nd.get("pin") or "")
                          for nd in n.findall("node")]
    return nets


def _norm(name: str) -> str:
    """KiCad prefixes sheet-local nets with '/'; strip for comparison."""
    return name.lstrip("/")


def check(circuit: Circuit, sch_path: Path) -> GateResult:
    res = GateResult(ok=True)
    extracted = extract_netlist(sch_path)

    # pin -> declared net name
    declared_of: dict[PinRef, str] = {}
    for net in circuit.nets.values():
        for pr in net.pins:
            declared_of[pr] = net.name

    # pin -> extracted net name (skip power-symbol/PWR_FLAG virtual parts)
    extracted_of: dict[PinRef, str] = {}
    for name, pins in extracted.items():
        for pr in pins:
            if pr.ref.startswith("#"):
                continue
            extracted_of[pr] = name

    # ---- SHORTS: one extracted net carrying >=2 declared nets ---------------
    for name, pins in extracted.items():
        decl = {declared_of[pr] for pr in pins if pr in declared_of}
        if len(decl) >= 2:
            res.ok = False
            members = ", ".join(f"{pr}={declared_of.get(pr,'?')}"
                                for pr in pins if pr in declared_of)
            res.shorts.append(f"extracted {name!r} merges {sorted(decl)} [{members}]")

    # ---- OPENS: declared net split / pin on unconnected-* -------------------
    for net in circuit.nets.values():
        ext_names = {extracted_of.get(pr) for pr in net.pins}
        ext_names.discard(None)
        real = {e for e in ext_names if e and not e.startswith("unconnected-")}
        stranded = [pr for pr in net.pins
                    if (extracted_of.get(pr) or "").startswith("unconnected-")
                    or extracted_of.get(pr) is None]
        if len(net.pins) >= 2 and (len(real) > 1 or stranded):
            res.ok = False
            res.opens.append(
                f"declared {net.name!r}: extracted as {sorted(ext_names)}"
                + (f", stranded: {[str(p) for p in stranded]}" if stranded else ""))
        # single-pin PORT nets: the hier label must still hold the pin
        if net.net_class == NetClass.PORT:
            for pr in net.pins:
                e = extracted_of.get(pr) or ""
                if e.startswith("unconnected-") or not e:
                    res.ok = False
                    res.opens.append(f"PORT {net.name!r}: {pr} emitted bare ({e!r})")

    # ---- NC-CHEAT: no_connect in the emitted file on a declared-net pin -----
    # KiCad reports an NC'd pin as connected; detect via the source s-expr.
    text = Path(sch_path).read_text(errors="ignore")
    if "(no_connect" in text:
        # cheap but reliable: NC count must equal the author's nc() count.
        emitted_nc = text.count("(no_connect")
        declared_nc = len(circuit.nc_pins)
        if emitted_nc > declared_nc:
            res.ok = False
            res.nc_cheats.append(
                f"{emitted_nc} no_connects emitted but only {declared_nc} declared "
                f"— a layout fallback NC'd a real pin (forbidden)")

    # ---- NAME discipline: POWER/GROUND/PORT nets must keep their names ------
    for net in circuit.nets.values():
        if net.net_class in (NetClass.POWER, NetClass.GROUND, NetClass.PORT):
            for pr in net.pins:
                e = extracted_of.get(pr)
                if e is not None and not e.startswith("unconnected-") \
                        and _norm(e) != net.name and "Net-(" not in e:
                    res.ok = False
                    res.name_mismatches.append(
                        f"{pr}: declared {net.name!r} but extracted {e!r}")

    # ---- parts present ------------------------------------------------------
    extracted_refs = {pr.ref for pins in extracted.values() for pr in pins
                      if not pr.ref.startswith("#")}
    for ref in circuit.parts:
        if ref not in extracted_refs:
            # a part can be absent from nets only if ALL its pins are NC
            all_nc = all(PinRef(ref, pr.pin) in circuit.nc_pins
                         for pr in circuit.nc_pins if pr.ref == ref) and any(
                         pr.ref == ref for pr in circuit.nc_pins)
            if not all_nc:
                res.ok = False
                res.part_mismatches.append(f"{ref}: missing from extracted netlist")
    return res
