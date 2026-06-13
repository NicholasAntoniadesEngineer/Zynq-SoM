"""schgen board LINKER — resolves every sheet PORT against the rest of the board.

``python -m schgen link [subsystems...]`` (default: every ``.py`` in
``carrier/subsystems/``) builds each subsystem's :class:`Circuit` and links
the PORT graph:

Every PORT must resolve against
  (a) a same-named PORT on another sheet, or
  (b) a SoM net in ``carrier/som_interface.json``,
with one EXPLICIT, enumerated alias map for rail spellings (RAIL_ALIASES —
the SoM project writes ``VIN`` where the carrier writes ``+VIN``). Signals
are NEVER fuzzy-matched: a near-miss is a name-drift ERROR, not a silent bind.

ERRORS (non-zero exit):
  - undefined port:        resolves nowhere, no deferral declared
  - name drift:            resolves nowhere but a case/separator/token
                           near-miss exists in the pool — report + FAIL
  - diff-pair polarity:    a typed pair whose P/N polarity cannot be read
                           from the two names, or both ends same polarity
  - kind/impedance/level:  the same linked net typed differently on two
                           sheets (e.g. sd_bus level_v mismatch)
WARNINGS (reported, exit 0):
  - deferred ports:        the author declared expect="..." — the binding
                           subsystem arrives in a later wave
  - unbound SoM nets:      contract nets no sheet consumes yet (later waves)
  - i2c bus missing a role on a sheet (scl without sda or vice versa)

Standalone, ``schgen link`` writes into the SAME committed carrier/ homes
``schgen board`` uses, so the two agree: the link report ->
``carrier/reports/``, layout constraints (schgen/constraints.py) ->
``carrier/manufacturing/``, the block diagram (schgen/diagram.py) ->
``docs/block_diagram.svg``. Unless ``--no-board`` it then emits the
hierarchical board root sheet + the board-level netlist gate
(schgen/board.py) into the normal carrier/ taxonomy.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from schgen.model import Circuit, NetClass, PortType, pair_polarity

REPO_ROOT = Path(__file__).resolve().parents[1]
SUBSYSTEMS_DIR = REPO_ROOT / "carrier" / "subsystems"
SOM_INTERFACE = REPO_ROOT / "carrier" / "som_interface.json"

# ---- the alias map -------------------------------------------------------------
# Rail spellings differ between the SoM project and the carrier house style.
# This map is the ONLY pure-name translation the linker performs; it is exact
# and enumerated (carrier spelling -> SoM contract spelling). Anything not
# listed must match verbatim. Identity rails (+3V3, +1V8, GND) need no entry.
# (Pre-P0 this carried "+VIN": "VIN"; the SoM VIN is now a deliberate REBIND,
#  not a spelling alias — see REBOUND_SOM_RAILS below.)
RAIL_ALIASES: dict[str, str] = {}

# PLAN "P0 + wave-3 decisions" REBIND (user-signed-off 2026-06-12): the SoM
# net VIN (J1.1-14) is the module's 4.2-5V input; binding it to the carrier
# 20V PD rail +VIN destroys the SoM at the first PD contract
# (wave3_function_map.md P0). som_conn_gen REBINDS those pins onto the
# carrier always-on +5V_SOM buck (power.py U4, UNIT 1). This map is the
# policy twin of carrier/som_conn_gen.REBOUND_SOM_RAILS (carrier rail -> SoM
# contract net): it lets the rail census account the 14 SoM VIN pins under
# +5V_SOM rather than reporting VIN unbound. The linker ERRORs if a connector
# sheet still carries the OLD pre-rebind rail (+VIN) on those pins, so the two
# maps cannot drift. Carrier-rail -> SoM-net (inverse of som_conn_gen's map).
REBOUND_SOM_RAILS: dict[str, str] = {
    "+5V_SOM": "VIN",   # SoM 4.2-5V input <- carrier always-on +5V_SOM buck
}

# PLAN round-5 RAIL ISOLATION (user decision 2026-06-12): the SoM exports
# its own +3V3/+1V8 on J1 (on-module MPM3834 stages) while carrier power.py
# regulates same-named rails — binding them would parallel two regulators
# on one net. Carrier bucks WIN: carrier/som_conn_gen.ISOLATED_SOM_RAILS
# (this map's authoring twin) emits those J1 pins as explicit author
# no-connects, the per-sheet netlist gate proves every NC, and the rail
# census below reports the isolation instead of a SoM bind. The linker
# ERRORS if a connector sheet ever re-binds an isolated rail, so the two
# maps cannot drift apart silently.
ISOLATED_SOM_RAILS: dict[str, str] = {
    "+3V3": "SoM MPM3834 3V3 output on J1.24-27 — carrier TPS54302 "
            "(power:U2) is the only +3V3 source",
    "+1V8": "SoM MPM3834 1V8 output on J1.56/58/60 — carrier AP2112K "
            "(power:U3) is the only +1V8 source",
}


def canon_to_som(name: str) -> str:
    """Carrier net name -> SoM contract spelling (rails only; else identity).
    Covers both the pure spelling aliases (RAIL_ALIASES) and the P0 rebind
    (REBOUND_SOM_RAILS — a carrier rail standing in for a SoM contract net)."""
    if name in REBOUND_SOM_RAILS:
        return REBOUND_SOM_RAILS[name]
    return RAIL_ALIASES.get(name, name)


# ---- inputs --------------------------------------------------------------------

@dataclass
class SheetCircuit:
    name: str
    circuit: Circuit
    path: Path
    module: object


def load_subsystem(name_or_path: str) -> SheetCircuit:
    path = Path(name_or_path)
    if path.suffix != ".py":
        path = SUBSYSTEMS_DIR / f"{Path(name_or_path).stem}.py"
    if not path.exists():
        raise SystemExit(f"subsystem not found: {path}")
    spec = importlib.util.spec_from_file_location(f"carrier_subsys_{path.stem}", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    c = mod.circuit()
    return SheetCircuit(name=c.name, circuit=c, path=path, module=mod)


def all_subsystem_paths() -> list[Path]:
    return sorted(p for p in SUBSYSTEMS_DIR.glob("*.py")
                  if p.stem != "__init__")


def load_som_contract(path: Path = SOM_INTERFACE) -> dict[str, list[str]]:
    """SoM net name -> ['J1.29', ...] connector pin locations."""
    data = json.loads(path.read_text())
    nets: dict[str, list[str]] = {}
    for jref, conn in data["connectors"].items():
        for pin, net in conn["pins"].items():
            nets.setdefault(net, []).append(f"{jref}.{pin}")
    for locs in nets.values():
        locs.sort(key=lambda s: (s.split(".")[0], int(s.split(".")[1])))
    return nets


# ---- name-drift detection -------------------------------------------------------

def _tokens(name: str) -> list[str]:
    """Uppercase alpha/numeric tokens: 'ETH_PHY_MDI0_P' -> [ETH,PHY,MDI,0,P]."""
    return re.findall(r"[A-Za-z]+|\d+", name.upper())


def _levenshtein(a: str, b: str, cap: int = 3) -> int:
    if abs(len(a) - len(b)) > cap:
        return cap + 1
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1,
                           prev[j - 1] + (ca != cb)))
        if min(cur) > cap:
            return cap + 1
        prev = cur
    return prev[-1]


def drift_candidates(name: str, pool: set[str]) -> list[str]:
    """Near-misses for an unresolved port name. Deterministic, no scoring:
    case-insensitive equality, separator-stripped equality, token multisets
    differing by at most one token, or edit distance <= 2."""
    out: list[str] = []
    ta = _tokens(name)
    flat_a = "".join(ta)
    for cand in sorted(pool):
        if cand == name:
            continue
        tb = _tokens(cand)
        if cand.upper() == name.upper() or "".join(tb) == flat_a:
            out.append(cand)
            continue
        common = 0
        rest = list(tb)
        for t in ta:
            if t in rest:
                rest.remove(t)
                common += 1
        if common >= 3 and common >= max(len(ta), len(tb)) - 1:
            out.append(cand)
            continue
        if _levenshtein(name.upper(), cand.upper()) <= 2:
            out.append(cand)
    return out


# ---- link result ----------------------------------------------------------------

@dataclass
class PortBinding:
    sheet: str
    net: str
    ptype: PortType
    targets: list[str] = field(default_factory=list)   # human descriptions
    status: str = "bound"   # bound | deferred | error


@dataclass
class LinkResult:
    sheets: list[SheetCircuit] = field(default_factory=list)
    bindings: list[PortBinding] = field(default_factory=list)
    rail_bindings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    unbound_som: list[str] = field(default_factory=list)
    deferred: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors

    def report(self) -> str:
        lines = ["schgen link report", "=" * 60]
        lines.append(f"sheets ({len(self.sheets)}): "
                     + ", ".join(s.name for s in self.sheets))
        lines.append("")
        lines.append("alias map (rails only, exact, enumerated):")
        for a, b in sorted(RAIL_ALIASES.items()):
            lines.append(f"  carrier {a!r} <-> SoM {b!r}")
        if not RAIL_ALIASES:
            lines.append("  (no pure spelling aliases)")
        for a, b in sorted(REBOUND_SOM_RAILS.items()):
            lines.append(f"  carrier {a!r} == SoM {b!r}  (P0 REBIND, not a "
                         f"spelling alias — wave3_function_map.md P0)")
        lines.append("  (identity rails +3V3 / +1V8 / GND need no entry; "
                     "signals are never aliased)")
        lines.append("")
        bound = [b for b in self.bindings if b.status == "bound"]
        lines.append(f"bound ports ({len(bound)}):")
        for b in bound:
            t = "; ".join(b.targets)
            kind = b.ptype.kind if b.ptype.kind != "single" else ""
            lines.append(f"  {b.sheet}:{b.net}"
                         + (f" [{kind}]" if kind else "") + f" -> {t}")
        lines.append("")
        lines.append(f"rails ({len(self.rail_bindings)}):")
        for r in self.rail_bindings:
            lines.append(f"  {r}")
        lines.append("")
        lines.append(f"deferred ports — author-declared, awaiting later waves "
                     f"({len(self.deferred)}) [WARNING]:")
        for d in self.deferred:
            lines.append(f"  {d}")
        lines.append("")
        lines.append(f"unbound SoM nets — no consumer yet, later waves "
                     f"({len(self.unbound_som)}) [WARNING]:")
        for chunk_start in range(0, len(self.unbound_som), 6):
            lines.append("  " + ", ".join(
                self.unbound_som[chunk_start:chunk_start + 6]))
        lines.append("")
        if self.warnings:
            lines.append(f"other warnings ({len(self.warnings)}):")
            for w in self.warnings:
                lines.append(f"  WARNING: {w}")
            lines.append("")
        if self.errors:
            lines.append(f"ERRORS ({len(self.errors)}):")
            for e in self.errors:
                lines.append(f"  ERROR: {e}")
        else:
            lines.append("errors: none")
        lines.append("")
        nwarn = len(self.deferred) + (1 if self.unbound_som else 0) \
            + len(self.warnings)
        lines.append(f"LINK: {'PASS' if self.ok else 'FAIL'} "
                     f"({len(self.errors)} errors, {nwarn} warnings)")
        return "\n".join(lines)


# ---- the linker ------------------------------------------------------------------

def link(sheets: list[SheetCircuit],
         som_nets: dict[str, list[str]] | None = None) -> LinkResult:
    if som_nets is None:
        som_nets = load_som_contract()
    res = LinkResult(sheets=sheets)
    som_names = set(som_nets)

    # port name -> [sheet, ...]
    ports_by_name: dict[str, list[SheetCircuit]] = {}
    for sc in sheets:
        for net in sc.circuit.nets.values():
            if net.net_class == NetClass.PORT:
                ports_by_name.setdefault(net.name, []).append(sc)

    bound_som_names: set[str] = set()

    # -- resolve every port --------------------------------------------------
    for sc in sheets:
        c = sc.circuit
        for net in c.nets.values():
            if net.net_class != NetClass.PORT:
                continue
            pt = c.port_type_of(net.name)
            b = PortBinding(sheet=sc.name, net=net.name, ptype=pt)
            peers = [p.name for p in ports_by_name.get(net.name, [])
                     if p is not sc]
            som_name = canon_to_som(net.name)
            if peers:
                b.targets += [f"sheet {p}:{net.name}" for p in peers]
            if som_name in som_names:
                pins = ",".join(som_nets[som_name][:4])
                more = len(som_nets[som_name]) - 4
                b.targets.append(
                    f"SoM {som_name} ({pins}{f',+{more}' if more > 0 else ''})")
                bound_som_names.add(som_name)
            if not b.targets:
                if pt.expect:
                    b.status = "deferred"
                    res.deferred.append(
                        f"{sc.name}:{net.name} — awaiting {pt.expect}")
                else:
                    b.status = "error"
                    pool = (som_names | set(ports_by_name)) - {net.name}
                    cands = drift_candidates(net.name, pool)
                    if cands:
                        res.errors.append(
                            f"name drift: {sc.name}:{net.name} resolves "
                            f"nowhere; near-miss candidates: "
                            + ", ".join(cands))
                    else:
                        res.errors.append(
                            f"undefined port: {sc.name}:{net.name} resolves "
                            f"nowhere (no same-named port on another sheet, "
                            f"not a SoM net, no expect= deferral)")
            res.bindings.append(b)

    # -- rails: POWER/GROUND nets bind to the SoM contract via the alias map --
    rails: dict[str, set[str]] = {}
    for sc in sheets:
        for net in sc.circuit.nets.values():
            if net.net_class in (NetClass.POWER, NetClass.GROUND):
                rails.setdefault(net.name, set()).add(sc.name)
    for rail, users in sorted(rails.items()):
        som_name = canon_to_som(rail)
        if rail in ISOLATED_SOM_RAILS:
            # round-5 isolation: the SoM's OWN +3V3/+1V8 OUTPUT pins (the
            # MPM3834 stages on J1) must be author-NC so the carrier buck does
            # not fight them. VERIFY the isolation actually holds — but the
            # offense is specifically the SoM-output net being re-bound, NOT
            # the carrier rail merely appearing on a connector. Since SYS-1 the
            # carrier +3V3 LEGITIMATELY feeds the Zynq VCCO banks on J2/J3
            # (+VCCO_13/33/34 -> +3V3, carrier-sourced INPUTS to the FPGA, a
            # different SoM contract net than the isolated +3V3 OUTPUT). So an
            # offender is only a connector that carries the rail AND on which
            # the ISOLATED SoM contract net itself appears (i.e. the SoM's own
            # output pins) — that connector would have to author them NC.
            iso_conns = {loc.split(".")[0] for loc in som_nets.get(som_name, [])}
            offenders = sorted(u for u in users if u.startswith("som_j")
                               and u[len("som_"):].upper() in iso_conns)
            if offenders:
                res.errors.append(
                    f"RAIL ISOLATION VIOLATED: {rail} is declared isolated "
                    f"from the SoM ({ISOLATED_SOM_RAILS[rail]}) but the SoM "
                    f"{som_name!r} output pins still bind it on connector "
                    f"sheet(s) {', '.join(offenders)} — som_conn_gen must "
                    f"author those pins NC")
            bound_som_names.add(som_name)   # accounted: isolated by decision
            res.rail_bindings.append(
                f"{rail} — ISOLATED from SoM {som_name!r} pins (round-5 "
                f"decision: {ISOLATED_SOM_RAILS[rail]}; pins author-NC on "
                f"the J1 sheet); carrier-local rail (sheets: "
                f"{', '.join(sorted(users))})")
        elif rail in REBOUND_SOM_RAILS:
            # P0 rebind: this carrier rail stands in for a SoM contract net
            # on the connector. VERIFY the rebind actually landed — the rail
            # MUST appear on a connector sheet (else som_conn_gen and this
            # map drifted and the SoM VIN pins resolve nowhere).
            if not any(u.startswith("som_j") for u in users):
                res.errors.append(
                    f"REBIND BROKEN: {rail} is declared the P0 stand-in for "
                    f"SoM {som_name!r} pins but appears on NO connector sheet "
                    f"(sheets: {', '.join(sorted(users))}) — som_conn_gen "
                    f"REBOUND_SOM_RAILS must map SoM {som_name!r} -> {rail}")
            elif som_name not in som_names:
                res.errors.append(
                    f"REBIND BROKEN: {rail} -> SoM {som_name!r} but "
                    f"{som_name!r} is not a SoM contract net")
            else:
                bound_som_names.add(som_name)
                res.rail_bindings.append(
                    f"{rail} — P0 REBIND of SoM {som_name!r} (the SoM 4.2-5V "
                    f"input; never the 20V +VIN PD rail — "
                    f"wave3_function_map.md P0) <- sheets: "
                    f"{', '.join(sorted(users))} -> SoM "
                    f"{len(som_nets[som_name])} pins")
        elif som_name in som_names:
            bound_som_names.add(som_name)
            alias = f" (alias of SoM {som_name!r})" if som_name != rail else ""
            res.rail_bindings.append(
                f"{rail}{alias} <- sheets: {', '.join(sorted(users))} "
                f"-> SoM {len(som_nets[som_name])} pins")
        else:
            # P0-rebind drift guard: a SoM contract net that is supposed to be
            # rebound (REBOUND_SOM_RAILS values) must NEVER appear under its
            # raw contract name on a connector sheet, and the carrier 20V +VIN
            # must never reach a connector sheet (the SoM is 4.2-5V).
            on_conn = sorted(u for u in users if u.startswith("som_j"))
            if on_conn and rail in REBOUND_SOM_RAILS.values():
                res.errors.append(
                    f"REBIND DRIFT: SoM net {rail!r} appears RAW on connector "
                    f"sheet(s) {', '.join(on_conn)} — som_conn_gen must rebind "
                    f"it (REBOUND_SOM_RAILS) onto its carrier rail")
            if on_conn and rail == "+VIN":
                res.errors.append(
                    f"SoM OVERVOLTAGE: the 20V PD rail +VIN reaches connector "
                    f"sheet(s) {', '.join(on_conn)} — the SoM is a 4.2-5V "
                    f"module; J1 VIN must rebind to +5V_SOM "
                    f"(wave3_function_map.md P0)")
            res.rail_bindings.append(
                f"{rail} — carrier-local rail (sheets: "
                f"{', '.join(sorted(users))})")

    # -- typed-port checks -----------------------------------------------------
    _check_pairs(sheets, res)
    _check_buses(sheets, res)
    _check_net_type_agreement(sheets, res)

    # -- wave-3 FUNCTION map accounting ----------------------------------------
    # The connector sheets emit each mapped pin under its carrier FUNCTION name
    # (som_conn_gen.FUNCTION_MAP), not the raw contract name — so a SoM net like
    # IO_L16_P_13 is CONSUMED (as LCD_CTP_SDA) yet would read "unbound" if we
    # only matched raw names. Account a SoM net as bound when its function-map
    # target is a bound PORT somewhere on the board.
    bound_ports = {b.net for b in res.bindings if b.status == "bound"}
    for som_net, func_net in _function_map().items():
        if som_net in som_names and func_net in bound_ports:
            bound_som_names.add(som_net)

    # -- VCCO bank-rail accounting (SYS-1) -------------------------------------
    # The connector sheets MERGE each +VCCO_* contact pin onto its carrier rail
    # (som_conn_gen.VCCO_RAIL_MAP -> +3V3 / +2V5_VADJ), so a SoM net like
    # +VCCO_13 is CONSUMED (it IS that rail's pins) yet would read "unbound" if
    # we only matched the raw +VCCO_* name. Account each as bound when its
    # target rail is present on the board.
    for som_net, target_rail in _vcco_rail_map().items():
        if som_net in som_names and target_rail in rails:
            bound_som_names.add(som_net)

    # -- unbound SoM nets (later waves) ----------------------------------------
    res.unbound_som = sorted(n for n in som_names if n not in bound_som_names)
    return res


def _load_som_conn_gen():
    import importlib.util
    gen_path = REPO_ROOT / "carrier" / "som_conn_gen.py"
    spec = importlib.util.spec_from_file_location("_link_som_conn_gen", gen_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _function_map() -> dict[str, str]:
    """The wave-3 SoM-contract-net -> carrier-function-net renames the J-sheet
    generator applies (carrier/som_conn_gen.FUNCTION_MAP + PUDC_STRAPS). Loaded
    from the SAME source the J-sheets use so the linker census cannot drift."""
    mod = _load_som_conn_gen()
    m = dict(mod.FUNCTION_MAP)
    m.update(mod.PUDC_STRAPS)
    return m


def _vcco_rail_map() -> dict[str, str]:
    """The SYS-1 VCCO bank-rail source ties (+VCCO_* -> carrier +3V3/+2V5_VADJ)
    the J-sheet generator merges. Loaded from the SAME source so the linker's
    bound-net census cannot drift from carrier/som_conn_gen.VCCO_RAIL_MAP."""
    return dict(_load_som_conn_gen().VCCO_RAIL_MAP)


def _check_pairs(sheets: list[SheetCircuit], res: LinkResult) -> None:
    """Diff-pair polarity: each typed pair must read as one P and one N."""
    for sc in sheets:
        c = sc.circuit
        seen: set[frozenset[str]] = set()
        for name, pt in c.port_types.items():
            if pt.pair_with is None:
                continue
            key = frozenset((name, pt.pair_with))
            if key in seen:
                continue
            seen.add(key)
            pols = {n: pair_polarity(n) for n in key}
            if set(pols.values()) != {"P", "N"}:
                res.errors.append(
                    f"diff-pair polarity: {sc.name}: pair {sorted(key)} "
                    f"reads as {pols} — need exactly one P and one N")
        # untyped P/N hint: both complementary names exist as ports, untyped
        for net in c.nets.values():
            if net.net_class != NetClass.PORT or net.name in c.port_types:
                continue
            pol = pair_polarity(net.name)
            if pol != "P":
                continue
            comp = _complement_name(net.name)
            if comp and comp in c.nets and comp not in c.port_types:
                res.warnings.append(
                    f"{sc.name}: ports {net.name}/{comp} look like a pair "
                    f"but are untyped (no port_type)")


def _complement_name(name: str) -> str | None:
    up = name.upper()
    for p_sfx, n_sfx in (("_P", "_N"), ("_DP", "_DM"), ("DP", "DM"),
                         ("D+", "D-"), ("+", "-"), ("P", "N")):
        if up.endswith(p_sfx):
            return name[: len(name) - len(p_sfx)] + n_sfx
    return None


def _check_buses(sheets: list[SheetCircuit], res: LinkResult) -> None:
    """i2c: a bus on a sheet should carry exactly one scl and one sda."""
    for sc in sheets:
        buses: dict[str, dict[str, list[str]]] = {}
        for name, pt in sc.circuit.port_types.items():
            if pt.kind == "i2c":
                bus = pt.bus or "I2C"
                buses.setdefault(bus, {}).setdefault(pt.role, []).append(name)
        for bus, roles in buses.items():
            for role, nets in roles.items():
                if len(nets) > 1:
                    res.errors.append(
                        f"i2c bus {bus!r} on {sc.name}: duplicate role "
                        f"{role!r}: {sorted(nets)}")
            for missing in {"scl", "sda"} - set(roles):
                res.warnings.append(
                    f"i2c bus {bus!r} on {sc.name}: no {missing} member typed")


def _check_net_type_agreement(sheets: list[SheetCircuit],
                              res: LinkResult) -> None:
    """The same linked net typed on >=2 sheets must agree on kind /
    impedance / sd_bus signaling level (level mismatch = ERROR)."""
    by_net: dict[str, list[tuple[str, PortType]]] = {}
    for sc in sheets:
        for name, pt in sc.circuit.port_types.items():
            by_net.setdefault(name, []).append((sc.name, pt))
    # sd_bus groups also compare ACROSS nets sharing a bus name
    sd_levels: dict[str, dict[float, list[str]]] = {}
    for sc in sheets:
        for name, pt in sc.circuit.port_types.items():
            if pt.kind == "sd_bus" and pt.level_v is not None:
                bus = pt.bus or "SD"
                sd_levels.setdefault(bus, {}).setdefault(
                    pt.level_v, []).append(f"{sc.name}:{name}")
    for bus, levels in sd_levels.items():
        if len(levels) > 1:
            detail = "; ".join(f"{lv}V: {', '.join(ms)}"
                               for lv, ms in sorted(levels.items()))
            res.errors.append(
                f"sd_bus level mismatch on bus {bus!r}: {detail}")
    for net, typed in by_net.items():
        if len(typed) < 2:
            continue
        kinds = {pt.kind for _, pt in typed if pt.kind != "single"}
        if len(kinds) > 1:
            res.errors.append(
                f"type mismatch on linked net {net!r}: "
                + "; ".join(f"{s}={pt.kind}" for s, pt in typed))
        imps = {pt.impedance for _, pt in typed if pt.impedance is not None}
        if len(imps) > 1:
            res.errors.append(
                f"impedance mismatch on linked net {net!r}: "
                + "; ".join(f"{s}={pt.impedance}R" for s, pt in typed))
        levels = {pt.level_v for _, pt in typed if pt.level_v is not None}
        if len(levels) > 1:
            res.errors.append(
                f"level mismatch on linked net {net!r}: "
                + "; ".join(f"{s}={pt.level_v}V" for s, pt in typed))


# ---- CLI -------------------------------------------------------------------------

def cmd_link(args: argparse.Namespace) -> int:
    names = args.subsystems or [p.stem for p in all_subsystem_paths()]
    sheets = [load_subsystem(n) for n in names]

    # model-completeness first (same hard check as `schgen build`)
    from schgen.symbols import Library
    lib = Library()
    for sc in sheets:
        sc.circuit.validate({r: lib.pin_numbers(p.lib_id)
                             for r, p in sc.circuit.parts.items()})

    som_nets = load_som_contract()
    res = link(sheets, som_nets)

    # Standalone link writes into the SAME committed carrier/ homes that
    # `schgen board` uses, so the two agree. `-o OUTDIR` redirects every
    # artifact there instead (an isolated-output escape hatch); it is never
    # carrier/out. The board emission goes to the normal carrier/ taxonomy.
    carrier = REPO_ROOT / "carrier"
    override = args.outdir
    if override is None and args.subsystems:
        # Guard (DEF-4): a PARTIAL link — an explicit subset of sheets — must
        # never overwrite the committed whole-board carrier/ artifacts (reports,
        # constraints, block diagram, root sheet), which are only valid for the
        # full board. Only a no-args full-board link writes carrier/ in place;
        # a subset is redirected to a tempdir unless the user gives an explicit
        # -o. (Mirrors `schgen build`, which persists nothing without -o.)
        import tempfile
        override = Path(tempfile.mkdtemp(prefix="schgen_link_"))
        print(f"(partial link of {len(args.subsystems)} sheet(s) -> {override}; "
              f"pass -o to choose an output dir, or run `schgen link` with no "
              f"sheet args to refresh the committed carrier/ artifacts)")
    rep_dir = override or (carrier / "reports")
    man_dir = override or (carrier / "manufacturing")
    diag_path = (override / "block_diagram.svg" if override
                 else REPO_ROOT / "docs" / "block_diagram.svg")
    rep_dir.mkdir(parents=True, exist_ok=True)
    man_dir.mkdir(parents=True, exist_ok=True)

    report_path = rep_dir / "link_report.txt"
    report_path.write_text(res.report() + "\n")
    print(res.report())
    print(f"\nlink report: {report_path}")

    # layout constraints from typed ports
    from schgen import constraints
    dru, csv_path = constraints.export(sheets, man_dir)
    print(f"constraints: {dru} + {csv_path}")

    # block diagram from the port graph
    from schgen import diagram
    svg = diagram.render(res, som_nets, diag_path)
    print(f"block diagram: {svg}")

    board_ok = True
    if not args.no_board:
        from schgen import board
        if override:
            board_ok = board.build_board(sheets, lib, override / "board")
        else:
            board_ok = board.build_board(
                sheets, lib, carrier, placements=None,
                root_name="Zynq_Carrier", sheet_subdir="schematic",
                reports_dir=rep_dir)

    ok = res.ok and board_ok
    print(f"LINK CMD: {'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1
