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

from schgen import sexpr
from schgen.model import Circuit, NetClass, PinRef
from schgen.symbols import Pin, pin_page_position


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
    """KiCad's own view of the emitted sheet: net name -> pins.

    The kicad-cli output goes into a :func:`tempfile.TemporaryDirectory` that
    is removed on exit — the old ``NamedTemporaryFile(delete=False)`` was never
    unlinked and leaked one stale ``.net`` per build (2600+ observed in the
    audit), growing without bound.
    """
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
    # POSITIONAL check (the original count-based check had slack whenever
    # placement legally emits fewer NC markers than declared NC pins, e.g.
    # stacked pads — `schgen selftest` proved a stray-NC mutant survived it):
    # every (no_connect) must land EXACTLY on a pin, and that pin must be
    # net-free. An NC on a netted pin, or floating in space, FAILS.
    text = Path(sch_path).read_text(errors="ignore")
    if "(no_connect" in text:
        cheats = _emitted_nc_cheats(circuit, text)
        if cheats:
            res.ok = False
            res.nc_cheats += cheats

    # ---- NAME discipline: POWER/GROUND/PORT nets must keep their names ------
    # A declared rail/port that extracts as KiCad's auto-name 'Net-(Ref-Pin)'
    # is a LOST-NAME rail: the power symbol / hier label did not attach, so the
    # net survives unnamed. The old check exempted 'Net-(' (and `not in e`),
    # which masked exactly that failure — a POWER/GROUND/PORT net ALWAYS carries
    # an explicit name/symbol, so an auto-name extraction is never legitimate
    # here (DEF-I gate hardening; LAW 4 — never exempt, flag it).
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


def _emitted_nc_cheats(circuit: Circuit, sch_text: str) -> list[str]:
    """Positional no_connect audit, self-contained from the emitted file.

    Pin positions are recomputed from the file's own embedded ``lib_symbols``
    + each instance's ``(at x y rot)`` through :func:`pin_page_position` — the
    ONE coordinate transform in the program — so the check needs no library
    search path and cannot drift from what KiCad sees. Flags:
    - an NC marker sitting on a pin that carries a DECLARED net (the cheat:
      NC is an authoring decision, never a layout fallback), and
    - an NC marker that lands on no pin at all (a stray marker is emit junk).
    An NC on an author-declared nc() pin is the only legal case.
    """
    doc = sexpr.loads(sch_text)
    nc_pts = []
    for n in sexpr.find_all(doc, "no_connect"):
        at = sexpr.find(n, "at")
        nc_pts.append((round(float(at[1]), 2), round(float(at[2]), 2)))
    if not nc_pts:
        return []

    # pin offsets per embedded lib_id (units are nested (symbol ...) blocks)
    lib_pins: dict[str, list[Pin]] = {}
    for block in sexpr.find_all(sexpr.find(doc, "lib_symbols") or [], "symbol"):
        pins: list[Pin] = []

        def walk(node: list) -> None:
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

    # page position of every emitted instance pin
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
