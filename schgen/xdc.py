"""Generated Vivado pin constraints (PLAN.md round 4) — zero hand-typed pins.

For every carrier PORT net bound through J2/J3 to a Zynq PL ball, emit
``set_property -dict {PACKAGE_PIN <ball> IOSTANDARD <std>} [get_ports …]``
into ``carrier/fpga/Zynq_Carrier_pins.xdc`` so the PL design starts with
zero pin-mapping work and CANNOT drift from the hardware.

Sources (all programmatic — a hand-typed ball map is banned):
- J-pin -> Zynq ball: ``schgen.som_interface.extract_zynq`` runs kicad-cli
  on the SoM project at generation time; the Zynq symbol's vendor pin NAMES
  carry the bank suffix (``..._34``) and clock capability (MRCC/SRCC).
- carrier net -> J-pin: the committed ``carrier/som_interface.json``
  contract, CROSS-CHECKED pin-for-pin against the live SoM netlist — if
  the contract is stale the build FAILS and says to re-extract it.
- electrical type: the carrier subsystems' typed-port registry
  (``pair_with`` pairs the diff lines; LVDS_25/TMDS_33 as typed).

IOSTANDARD comes from the VCCO rail map decided in carrier/PLAN.md
(rounds 2-4 + harvest flags): banks 13/33/34 run +3V3 -> LVCMOS33, bank 35
runs +2V5_VADJ (shared camera/FMC 2.5 V) -> LVCMOS25. A bank with no rail
decision FAILS the build — never a silent default.

MRCC/SRCC-capable P-side balls get a commented ``create_clock`` template.
Contract nets not yet claimed by a function sheet are still constrained
(they ARE bound carrier ports on the som_j2/som_j3 sheets) and marked
unclaimed; the wave-3 function-map regen renames them in place.
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from schgen.link import _vcco_rail_map
from schgen.model import Circuit, NetClass, PortType
from schgen.som_interface import extract_zynq

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOM = REPO_ROOT / "som" / "Zynq_SoM.kicad_sch"
DEFAULT_CONTRACT = REPO_ROOT / "carrier" / "som_interface.json"
DEFAULT_OUT = REPO_ROOT / "carrier" / "fpga" / "Zynq_Carrier_pins.xdc"

# Carrier spelling of SoM rail names (mirror of link.RAIL_ALIASES — the one
# enumerated rail alias; signals are NEVER respelled).
RAIL_SPELLING = {"VIN": "+VIN"}


def _function_map() -> dict[str, str]:
    """The wave-3 SoM-contract-net -> carrier-function-net renames the J-sheet
    generator (carrier/som_conn_gen.FUNCTION_MAP) applies. The XDC walks the
    raw contract to reach each PL ball, then must look up the carrier PORT
    under its FUNCTION name (e.g. IO_L18_N_13 -> ZYNQ_PS_UART0_RTS_N) — exactly
    as som_conn_gen renamed it — or every renamed pin would read as an orphan.
    Loaded from the SAME source the J-sheets use, so the two cannot drift."""
    import importlib.util
    gen_path = REPO_ROOT / "carrier" / "som_conn_gen.py"
    spec = importlib.util.spec_from_file_location("_xdc_som_conn_gen", gen_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    m = dict(mod.FUNCTION_MAP)
    m.update(mod.PUDC_STRAPS)   # PUDC_34: the strap part lives on bringup_rails
    return m

# ---- the VCCO rail map (carrier/PLAN.md decisions, rounds 2-4) -----------------
# bank id -> carrier rail powering +VCCO_<bank> on the SoM. The bank LIST is
# discovered from the Zynq pin names; only the RAIL per bank is design intent.
BANK_RAIL = {
    "13": "+3V3",        # pmod + user_io + LCD touch I2C (round 3/harvest)
    "33": "+3V3",        # spare / camera control
    "34": "+3V3",        # LCD TTL panel (round 3: "LCD -> J3 bank 34")
    "35": "+2V5_VADJ",   # SHARED camera D-PHY / FMC VADJ 2.5 V (harvest flag)
}

_IOSTD_SINGLE = {3.3: "LVCMOS33", 2.5: "LVCMOS25", 1.8: "LVCMOS18"}
_PAIR_KINDS = {"diff_pair", "usb_hs_pair", "tmds_pair"}


class XdcError(ValueError):
    pass


def _rail_volts(rail: str) -> float:
    m = re.match(r"\+(\d+)V(\d*)", rail)
    if not m:
        raise XdcError(f"cannot parse voltage from rail name {rail!r}")
    return float(f"{m.group(1)}.{m.group(2) or '0'}")


@dataclass
class PinEntry:
    net: str            # carrier PORT net name (== get_ports name)
    jpin: str           # "J2.20"
    ball: str           # "W6"
    pin_name: str       # "IO_L2P_T0_13"
    bank: str           # "13"
    iostd: str = ""
    consumers: list[str] = field(default_factory=list)
    ptype: PortType = field(default_factory=PortType)

    @property
    def clock_capable(self) -> str | None:
        for cc in ("MRCC", "SRCC"):
            if cc in self.pin_name:
                return cc
        return None

    @property
    def p_side(self) -> bool:
        return bool(re.search(r"IO_L\d+P", self.pin_name))


@dataclass
class XdcResult:
    path: Path
    entries: list[PinEntry]
    checks: list[str]            # human-readable proof of each cross-check

    @property
    def count(self) -> int:
        return len(self.entries)


def _port_registry(sheets) -> tuple[dict[str, list[str]],
                                    dict[str, PortType]]:
    """PORT net -> consumer sheets, and the merged PortType per net (the
    linker separately proves cross-sheet type agreement)."""
    consumers: dict[str, list[str]] = {}
    ptypes: dict[str, PortType] = {}
    for sc in sheets:
        c = sc.circuit
        for net in c.nets.values():
            if net.net_class != NetClass.PORT:
                continue
            consumers.setdefault(net.name, []).append(sc.name)
            pt = c.port_types.get(net.name)
            if pt is not None and pt.kind != "single":
                ptypes.setdefault(net.name, pt)
    return consumers, ptypes


def generate(sheets, out_path: Path = DEFAULT_OUT, *,
             som_sch: Path = DEFAULT_SOM,
             contract_path: Path = DEFAULT_CONTRACT,
             refs: tuple[str, ...] = ("J1", "J2", "J3")) -> XdcResult:
    """Build + verify + write the XDC. Raises :class:`XdcError` on ANY
    orphan, ambiguity, stale contract or unmapped bank.

    ALL THREE connectors are walked (SYS-2): the PL also fans out on J1 —
    the bank-35 FMC LA08-11 LVDS pairs land on J1 (LA08 J1.74/92, LA09
    J1.80/84, LA10 J1.90/88, LA11 J1.78/76). Their balls reach no constraint
    unless J1 is in the walk. Every PACKAGE_PIN is still cross-checked against
    the live SoM netlist; J1's PS/SC nets (no PL ball) and rails are skipped
    exactly as on J2/J3, and the bank-35 spare singles (IO_0_35 J1.86,
    IO_L2_N_35 J1.100) constrain as unclaimed ports the way J2/J3 spares do."""
    contract = json.loads(contract_path.read_text())["connectors"]
    live = extract_zynq(som_sch, jrefs=tuple(refs))
    consumers, ptypes = _port_registry(sheets)
    func_map = _function_map()

    # SYS-1 consistency gate: xdc's BANK_RAIL (which picks each pin's
    # IOSTANDARD) MUST agree with the rail som_conn_gen actually drives onto
    # +VCCO_<bank> (the real hardware). They are two independent copies; if a
    # future SoM / bank re-rail (C3) edits one and not the other, the XDC would
    # emit the wrong IOSTANDARD on the re-railed bank — a board-bring-up fault
    # no other gate catches. Assert they agree.
    _vcco = {k.removeprefix("+VCCO_"): v for k, v in _vcco_rail_map().items()}
    _drift = {b: {"BANK_RAIL": BANK_RAIL.get(b), "VCCO_RAIL_MAP": _vcco.get(b)}
              for b in set(BANK_RAIL) | set(_vcco)
              if BANK_RAIL.get(b) != _vcco.get(b)}
    if _drift:
        raise XdcError(
            "VCCO bank-rail drift: schgen/xdc.BANK_RAIL and "
            "carrier/som_conn_gen.VCCO_RAIL_MAP disagree — the XDC would emit "
            f"the wrong IOSTANDARD on a re-railed bank: {_drift}")
    checks: list[str] = []

    # net -> PL balls (Zynq side, live netlist; IO_* names are PL I/O)
    net_balls: dict[str, list[str]] = {}
    for ball, net in live["ball_net"].items():
        if live["pin_names"].get(ball, "").startswith("IO_"):
            net_balls.setdefault(net, []).append(ball)

    # -- cross-check 0: committed contract == live SoM netlist, pin for pin --
    for jref in refs:
        if jref not in contract:
            raise XdcError(f"{jref} missing from {contract_path}")
        cpins = contract[jref]["pins"]
        live_pins = {k.split(".")[1]: v for k, v in live["jpin_net"].items()
                     if k.startswith(f"{jref}.")}
        if set(cpins) != set(live_pins):
            raise XdcError(
                f"{jref}: contract pin set != live SoM netlist — "
                f"som_interface.json is STALE; re-run `schgen som-interface`")
        for pin, net in sorted(cpins.items(), key=lambda kv: int(kv[0])):
            if live_pins[pin] != net:
                raise XdcError(
                    f"{jref}.{pin}: contract says {net!r} but the SoM "
                    f"netlist says {live_pins[pin]!r} — som_interface.json "
                    f"is STALE; re-run `schgen som-interface`")
        checks.append(f"{jref}: all {len(cpins)} contract pins match the "
                      f"live SoM netlist verbatim")

    # -- walk the contract: every J2/J3 net that reaches a PL ball ------------
    entries: list[PinEntry] = []
    seen_balls: dict[str, str] = {}
    seen_nets: dict[str, str] = {}
    for jref in refs:
        for pin, som_net in sorted(contract[jref]["pins"].items(),
                                   key=lambda kv: int(kv[0])):
            if som_net.startswith("unconnected-"):
                continue
            # contract net -> carrier net: rail spelling, then the wave-3
            # FUNCTION map (the J-sheet generator's same rename) so a renamed
            # PL pin resolves to its function PORT, not an orphan.
            carrier_net = RAIL_SPELLING.get(som_net, som_net)
            carrier_net = func_map.get(carrier_net, carrier_net)
            if Circuit.classify(carrier_net) in (NetClass.POWER,
                                                 NetClass.GROUND):
                continue                       # rails are not get_ports
            balls = net_balls.get(som_net, [])
            if not balls:
                continue                       # not a PL net (PS/SC side)
            if len(balls) > 1:
                raise XdcError(
                    f"{som_net!r}: reaches {len(balls)} PL balls "
                    f"({sorted(balls)}) — ambiguous LOC, refusing to guess")
            ball = balls[0]
            pin_name = live["pin_names"][ball]
            # ORPHAN check: the net must be a bound carrier PORT
            if carrier_net not in consumers:
                raise XdcError(
                    f"orphan: {jref}.{pin} net {som_net!r} reaches PL ball "
                    f"{ball} but is not a PORT on any carrier sheet")
            if not re.fullmatch(r"[A-Za-z0-9_]+", carrier_net):
                raise XdcError(
                    f"{carrier_net!r}: not a safe Vivado port name "
                    f"(get_ports needs [A-Za-z0-9_]+)")
            m = re.search(r"_(\d+)$", pin_name)
            if not m:
                raise XdcError(f"ball {ball} pin name {pin_name!r} carries "
                               f"no bank suffix")
            if ball in seen_balls:
                raise XdcError(f"ball {ball} claimed twice: "
                               f"{seen_balls[ball]!r} and {carrier_net!r}")
            if carrier_net in seen_nets:
                raise XdcError(f"net {carrier_net!r} mapped twice: "
                               f"{seen_nets[carrier_net]} and {jref}.{pin}")
            seen_balls[ball] = carrier_net
            seen_nets[carrier_net] = f"{jref}.{pin}"
            entries.append(PinEntry(
                net=carrier_net, jpin=f"{jref}.{pin}", ball=ball,
                pin_name=pin_name, bank=m.group(1),
                consumers=[s for s in consumers[carrier_net]
                           if not s.startswith("som_j")],
                ptype=ptypes.get(carrier_net, PortType())))
    if not entries:
        raise XdcError(f"no carrier port reaches a PL ball through "
                       f"{'/'.join(refs)} — wrong refs?")

    # -- IOSTANDARD per entry (rail map + typed ports) ------------------------
    by_net = {e.net: e for e in entries}
    for e in entries:
        rail = BANK_RAIL.get(e.bank)
        if rail is None:
            raise XdcError(f"bank {e.bank} ({e.net} @ {e.ball}): no VCCO "
                           f"rail decision in BANK_RAIL — decide the rail "
                           f"in carrier/PLAN.md first, never default")
        volts = _rail_volts(rail)
        if e.ptype.kind in _PAIR_KINDS:
            comp = e.ptype.pair_with
            if comp not in by_net:
                raise XdcError(
                    f"{e.net}: typed {e.ptype.kind} but its complement "
                    f"{comp!r} is not bound through {'/'.join(refs)} — "
                    f"half a pair cannot be constrained")
            if e.ptype.kind == "tmds_pair":
                if volts != 3.3:
                    raise XdcError(f"{e.net}: TMDS_33 needs a 3.3 V bank, "
                                   f"bank {e.bank} runs {rail}")
                e.iostd = "TMDS_33"
            else:
                if volts != 2.5:
                    raise XdcError(f"{e.net}: LVDS_25 needs a 2.5 V bank, "
                                   f"bank {e.bank} runs {rail} "
                                   f"(bank {e.bank})")
                e.iostd = "LVDS_25"
        else:
            std = _IOSTD_SINGLE.get(volts)
            if std is None:
                raise XdcError(f"bank {e.bank}: no LVCMOS standard for "
                               f"{volts} V rail {rail}")
            e.iostd = std

    # -- sanity: emitted count vs the LIVE netlist's PL population ------------
    # (independent derivation: J pins from the live netlist, not the contract)
    expect = len({nn for jp, nn in live["jpin_net"].items()
                  if jp.split(".")[0] in refs and nn in net_balls})
    if len(entries) != expect:
        raise XdcError(f"emitted {len(entries)} pins but the live netlist "
                       f"shows {expect} {'/'.join(refs)} nets on PL balls "
                       f"— a net was dropped")
    checks.append(f"emitted pin count {len(entries)} == live "
                  f"{'/'.join(refs)}-to-PL net population {expect}")
    checks.append(f"{len(seen_balls)} unique balls, {len(seen_nets)} unique "
                  f"ports (no double-claims)")

    # -- write -----------------------------------------------------------------
    text = _render(entries, live, refs, contract_path, som_sch)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(text)
    n_lines = sum(1 for ln in text.splitlines()
                  if ln.startswith("set_property"))
    if n_lines != len(entries):
        raise XdcError(f"wrote {n_lines} set_property lines for "
                       f"{len(entries)} pins — renderer bug")
    checks.append(f"{n_lines} set_property lines for {len(entries)} pins")
    return XdcResult(path=out_path, entries=entries, checks=checks)


def _render(entries: list[PinEntry], live: dict, refs: tuple[str, ...],
            contract_path: Path, som_sch: Path) -> str:
    def rel(p: Path) -> str:
        try:
            return str(Path(p).resolve().relative_to(REPO_ROOT))
        except ValueError:
            return str(p)

    banks = sorted({e.bank for e in entries})
    n_clk = sum(1 for e in entries if e.clock_capable)
    lines = [
        "#" * 78,
        "# Zynq_Carrier_pins.xdc — GENERATED by `schgen xdc`. DO NOT EDIT.",
        f"# Device: {live['value']} ({live['zynq_ref']} on the SoM)",
        "# Sources (all programmatic, zero hand-typed pins):",
        f"#   ball map : {rel(som_sch)} netlist (kicad-cli, at generation time)",
        f"#   contract : {rel(contract_path)} (cross-checked pin-for-pin, stale = build FAIL)",
        "#   types    : carrier subsystems' typed-port registry",
        "# VCCO rail map (carrier/PLAN.md): "
        + ", ".join(f"bank {b} = {BANK_RAIL[b]}" for b in banks),
        f"# {len(entries)} pins, banks {'/'.join(banks)}, "
        f"{n_clk} clock-capable (MRCC/SRCC)",
        "# Ports named IO_* are the bound SoM contract nets not yet claimed",
        "# by a function sheet; the wave-3 function map renames them here",
        "# automatically on the next `schgen board`.",
        "#" * 78,
    ]
    emitted: set[str] = set()
    for bank in banks:
        bank_entries = sorted((e for e in entries if e.bank == bank),
                              key=lambda e: e.net)
        rail = BANK_RAIL[bank]
        lines += ["",
                  f"# ---- bank {bank} — VCCO = {rail} "
                  f"({len(bank_entries)} pins) " + "-" * 20]
        for e in bank_entries:
            if e.net in emitted:
                continue
            group = [e]
            if e.ptype.kind in _PAIR_KINDS:
                comp = next(x for x in entries if x.net == e.ptype.pair_with)
                group = sorted([e, comp], key=lambda x: not x.p_side)
                lines.append(f"# {e.ptype.kind} ({e.ptype.impedance}R): "
                             f"{group[0].net} / {group[1].net}")
            for g in group:
                used = ", ".join(g.consumers) if g.consumers \
                    else "unclaimed (wave-3 function map)"
                lines.append(
                    f"set_property -dict {{PACKAGE_PIN {g.ball:<4} "
                    f"IOSTANDARD {g.iostd}}} [get_ports {{{g.net}}}]"
                    f"  ;# {g.jpin} {g.pin_name} <- {used}")
                cc = g.clock_capable
                if cc and g.p_side:
                    lines.append(
                        f"#   ^ {cc}-capable: "
                        f"# create_clock -name {g.net} -period <ns> "
                        f"[get_ports {{{g.net}}}]")
                emitted.add(g.net)
    return "\n".join(lines) + "\n"


# ---- CLI --------------------------------------------------------------------------

def cmd_xdc(args: argparse.Namespace) -> int:
    from schgen.link import all_subsystem_paths, load_subsystem
    names = args.subsystems or [p.stem for p in all_subsystem_paths()]
    sheets = [load_subsystem(n) for n in names]
    refs = tuple(r.strip() for r in args.refs.split(",") if r.strip())
    try:
        res = generate(sheets, args.output, som_sch=args.som, refs=refs)
    except XdcError as exc:
        print(f"XDC: FAIL — {exc}")
        return 1
    for c in res.checks:
        print(f"  check: {c}")
    print(f"XDC: {res.path} ({res.count} pins)")
    return 0
