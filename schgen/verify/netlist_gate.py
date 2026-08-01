from __future__ import annotations

import subprocess
import tempfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

from schgen.core import sexpr
from schgen.core.model import Circuit, NetClass, PinRef
from schgen.core.symbols import Pin, pin_page_position


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
    with tempfile.TemporaryDirectory(prefix="schgen_netlist_") as td:
        out = Path(td) / "extracted.net"
        proc = subprocess.run(
            ["kicad-cli", "sch", "export", "netlist", "--format", "kicadxml",
             "-o", str(out), str(sch_path)],
            capture_output=True, text=True,
        )
        if proc.returncode != 0:
            raise RuntimeError(
                f"kicad-cli netlist export failed: {proc.stderr[-500:]}")
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
    return name.lstrip("/")


def _dead_two_terminal(circuit: Circuit) -> list[str]:
    ppins: dict[str, set[str]] = {}
    pnets: dict[str, set[str]] = {}
    for net in circuit.nets.values():
        for pr in net.pins:
            ppins.setdefault(pr.ref, set()).add(pr.pin)
            pnets.setdefault(pr.ref, set()).add(net.name)
    out: list[str] = []
    for ref, p in circuit.parts.items():
        if not any(p.lib_id.startswith(k)
                   for k in ("Device:C", "Device:R", "Device:L")):
            continue
        if len(ppins.get(ref, set())) >= 2 and len(pnets.get(ref, set())) == 1:
            out.append(f"{ref} ({p.lib_id}): both terminals on one net "
                       f"{next(iter(pnets[ref]))!r} — electrically dead (capshort)")
    return out


def check(circuit: Circuit, sch_path: Path) -> GateResult:
    res = GateResult(ok=True)
    extracted = extract_netlist(sch_path)

    declared_of: dict[PinRef, str] = {}
    for net in circuit.nets.values():
        for pr in net.pins:
            declared_of[pr] = net.name

    extracted_of: dict[PinRef, str] = {}
    for name, pins in extracted.items():
        for pr in pins:
            if pr.ref.startswith("#"):
                continue
            extracted_of[pr] = name

    for name, pins in extracted.items():
        decl = {declared_of[pr] for pr in pins if pr in declared_of}
        if len(decl) >= 2:
            res.ok = False
            members = ", ".join(f"{pr}={declared_of.get(pr,'?')}"
                                for pr in pins if pr in declared_of)
            res.shorts.append(f"extracted {name!r} merges {sorted(decl)} [{members}]")

    dead = _dead_two_terminal(circuit)
    if dead:
        res.ok = False
        res.shorts += dead

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
        if net.net_class in (NetClass.PORT, NetClass.POWER, NetClass.GROUND):
            for pr in net.pins:
                e = extracted_of.get(pr) or ""
                if e.startswith("unconnected-") or not e:
                    res.ok = False
                    res.opens.append(
                        f"{net.net_class.name} {net.name!r}: {pr} emitted bare "
                        f"({e!r})")

    text = Path(sch_path).read_text(errors="ignore")
    if "(no_connect" in text:
        cheats = _emitted_nc_cheats(circuit, text)
        if cheats:
            res.ok = False
            res.nc_cheats += cheats

    for net in circuit.nets.values():
        if net.net_class in (NetClass.POWER, NetClass.GROUND, NetClass.PORT):
            for pr in net.pins:
                e = extracted_of.get(pr)
                if e is not None and not e.startswith("unconnected-") \
                        and _norm(e) != net.name:
                    lost = "Net-(" in e
                    res.ok = False
                    res.name_mismatches.append(
                        f"{pr}: declared {net.name!r} but extracted {e!r}"
                        + (" [LOST-NAME rail: power symbol/label did not attach]"
                           if lost else ""))

    extracted_refs = {pr.ref for pins in extracted.values() for pr in pins
                      if not pr.ref.startswith("#")}
    for ref in circuit.parts:
        if ref not in extracted_refs:
            all_nc = all(PinRef(ref, pr.pin) in circuit.nc_pins
                         for pr in circuit.nc_pins if pr.ref == ref) and any(
                         pr.ref == ref for pr in circuit.nc_pins)
            if not all_nc:
                res.ok = False
                res.part_mismatches.append(f"{ref}: missing from extracted netlist")
    return res


def _emitted_nc_cheats(circuit: Circuit, sch_text: str) -> list[str]:
    doc = sexpr.loads(sch_text)
    nc_pts = []
    for n in sexpr.find_all(doc, "no_connect"):
        at = sexpr.find(n, "at")
        nc_pts.append((round(float(at[1]), 2), round(float(at[2]), 2)))
    if not nc_pts:
        return []

    lib_pins: dict[str, list[Pin]] = {}
    for block in sexpr.find_all(sexpr.find(doc, "lib_symbols") or [], "symbol"):
        pins: list[Pin] = []

        def walk(node: list, pins: list[Pin] = pins) -> None:
            for sub in sexpr.find_all(node, "symbol"):
                walk(sub)
            for p in sexpr.find_all(node, "pin"):
                at = sexpr.find(p, "at") or [None, 0, 0, 0]
                num = sexpr.find(p, "number")
                pins.append(Pin(
                    number=str(num[1]) if num and len(num) > 1 else "",
                    name="", etype="passive",
                    x=float(at[1]), y=float(at[2]),
                    rotation=int(float(at[3])) % 360 if len(at) > 3 else 0,
                    length=0.0))

        walk(block)
        lib_pins[str(block[1])] = pins

    pin_at: dict[tuple[float, float], list[PinRef]] = {}
    for inst in sexpr.find_all(doc, "symbol"):
        lid = sexpr.find(inst, "lib_id")
        at = sexpr.find(inst, "at")
        if lid is None or at is None:
            continue
        ax, ay = float(at[1]), float(at[2])
        rot = int(float(at[3])) % 360 if len(at) > 3 else 0
        ref = ""
        for prop in sexpr.find_all(inst, "property"):
            if len(prop) > 2 and prop[1] == "Reference":
                ref = str(prop[2])
                break
        for pin in lib_pins.get(str(lid[1]), []):
            px, py = pin_page_position(pin, ax, ay, rot)
            pin_at.setdefault((round(px, 2), round(py, 2)),
                              []).append(PinRef(ref, pin.number))

    declared_of = {pr: net.name for net in circuit.nets.values()
                   for pr in net.pins}
    out: list[str] = []
    for pos in nc_pts:
        prs = pin_at.get(pos, [])
        netted = [(pr, declared_of[pr]) for pr in prs if pr in declared_of]
        if netted:
            pr, nname = netted[0]
            out.append(f"no_connect at {pos} sits on {pr} which carries "
                       f"declared net {nname!r} — NC is never a layout "
                       f"fallback (forbidden)")
        elif not prs:
            out.append(f"no_connect at {pos} lands on no pin — stray marker")
    return out
