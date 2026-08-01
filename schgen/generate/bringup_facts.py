from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from schgen.core.link import load_som_contract
from schgen.core.model import Circuit, NetClass, PinRef

REPO_ROOT = Path(__file__).resolve().parents[2]
SOM_SCH = REPO_ROOT / "som" / "Zynq_SoM.kicad_sch"

LVC1G08_PIN_A, LVC1G08_PIN_B, LVC1G08_PIN_Y = "1", "2", "4"
SY6280_ILIM_NUMERATOR = 6800.0
FB_VREF = {"TPS54302": 0.596, "LMR33630": 1.0,
           "LM61460": 1.0}
TCA9535_BASE_ADDR = 0x20
INA3221_BASE_ADDR = 0x40
FUSB302B_ADDR = 0x22


def parse_value_ohms(value: str) -> float | None:
    v = value.strip()
    m = re.fullmatch(r"(\d+(?:\.\d+)?)\s*(m|k|M)?(?:R|ohm)?", v)
    if m:
        mult = {"m": 1e-3, "k": 1e3, "M": 1e6, None: 1.0}[m.group(2)]
        return float(m.group(1)) * mult
    m = re.fullmatch(r"(\d+)(k|M)(\d+)", v)
    if m:
        mult = {"k": 1e3, "M": 1e6}[m.group(2)]
        return float(f"{m.group(1)}.{m.group(3)}") * mult
    return None


def c_ident(net: str) -> str:
    ident = net.replace("+", "P").replace("-", "_")
    ident = "".join(ch if ch.isalnum() or ch == "_" else "_" for ch in ident)
    if ident and ident[0].isdigit():
        ident = "_" + ident
    return ident


def _net_at(c: Circuit, ref: str, pin: str) -> str | None:
    n = c.net_of(PinRef(ref, pin))
    return n.name if n is not None else None


def _pin_name_of(c: Circuit, ref: str, num: str) -> str:
    for name, nums in c.parts[ref].pin_names.items():
        if num in nums:
            return name
    return num


def _parts_by_value(c: Circuit, substr: str) -> list[str]:
    return sorted(r for r, p in c.parts.items()
                  if substr in p.value or substr in p.lib_id)


@dataclass(frozen=True)
class Stm32Net:
    net: str
    port: str
    pin: int
    j_pins: tuple[str, ...]


def stm32_pin_map(som_sch: Path = SOM_SCH, ref: str = "U9") -> dict:
    from schgen.core.som_interface import extract_zynq
    data = extract_zynq(som_sch, zynq_ref=ref)
    contract = load_som_contract()
    on_j: dict[str, Stm32Net] = {}
    internal: dict[str, Stm32Net] = {}
    for num, net in data["ball_net"].items():
        if net.startswith("unconnected-"):
            continue
        m = re.fullmatch(r"P([A-G])(\d+)", data["pin_names"].get(num, ""))
        if not m:
            continue
        entry = Stm32Net(net=net, port=m.group(1), pin=int(m.group(2)),
                         j_pins=tuple(contract.get(net, [])))
        if entry.j_pins:
            on_j[net] = entry
        else:
            internal[net] = entry
    return {"value": data["value"], "nets": on_j, "internal": internal}


@dataclass(frozen=True)
class DipPosition:
    switch: str
    position: int
    net: str


def dip_switch_refs(c: Circuit) -> list[str]:
    return _parts_by_value(c, "DSHP")


def dip_positions(c: Circuit, ref: str,
                  common: tuple[str, ...] = ("+3V3_SC", "GND")) \
        -> list[DipPosition]:
    part = c.parts[ref]
    total = len(part.pin_numbers)
    cand: dict[int, list] = {}
    for net in c.nets.values():
        for pr in net.pins:
            if pr.ref == ref:
                pin = int(pr.pin)
                cand.setdefault(min(pin, total + 1 - pin), []).append(net)
    out = []
    for pos in sorted(cand):
        nets = [n for n in cand[pos] if n.name not in common]
        if not nets:
            continue
        nets.sort(key=lambda n: (n.net_class != NetClass.PORT, n.name))
        out.append(DipPosition(ref, pos, nets[0].name))
    return out


@dataclass(frozen=True)
class EnCell:
    sheet: str
    gate: str
    dip_net: str
    override_net: str
    enable: str


def en_cells(c: Circuit) -> list[EnCell]:
    cells = []
    for ref in _parts_by_value(c, "74LVC1G08"):
        cells.append(EnCell(
            sheet=c.name, gate=ref,
            dip_net=_net_at(c, ref, LVC1G08_PIN_A) or "?",
            override_net=_net_at(c, ref, LVC1G08_PIN_B) or "?",
            enable=_net_at(c, ref, LVC1G08_PIN_Y) or "?"))
    return cells


@dataclass(frozen=True)
class Expander:
    ref: str
    addr: int
    ports: dict[str, str] = field(default_factory=dict)


def expander(c: Circuit) -> Expander:
    refs = _parts_by_value(c, "TCA9535")
    if len(refs) != 1:
        raise ValueError(f"{c.name}: expected exactly one TCA9535, "
                         f"found {refs}")
    ref = refs[0]
    part = c.parts[ref]
    vcc_net = _net_at(c, ref, part.pin_names["VCC"][0])
    addr = TCA9535_BASE_ADDR
    for bit, strap in enumerate(("A0", "A1", "A2")):
        net = _net_at(c, ref, part.pin_names[strap][0])
        if net == vcc_net:
            addr |= 1 << bit
        elif net != "GND":
            raise ValueError(f"{c.name}: TCA9535 {strap} on {net!r} — "
                             f"not a valid GND/VCC strap")
    ports = {}
    for name, nums in part.pin_names.items():
        if re.fullmatch(r"P[01][0-7]", name):
            ports[name] = _net_at(c, ref, nums[0]) or "?"
    return Expander(ref=ref, addr=addr, ports=ports)


@dataclass(frozen=True)
class Monitor:
    ref: str
    addr: int
    channels: dict[int, tuple[str, str]] = field(default_factory=dict)


def ina3221_monitors(c: Circuit) -> list[Monitor]:
    out = []
    for ref in _parts_by_value(c, "INA3221"):
        part = c.parts[ref]
        vs_net = _net_at(c, ref, part.pin_names["VS"][0])
        a0 = _net_at(c, ref, part.pin_names["A0"][0])
        sda = _net_at(c, ref, part.pin_names["SDA"][0])
        scl = _net_at(c, ref, part.pin_names["SCL"][0])
        strap = {
            "GND": 0, vs_net: 1, sda: 2, scl: 3}.get(a0)
        if strap is None:
            raise ValueError(f"{c.name}: {ref} A0 on {a0!r} — unknown strap")
        chans = {}
        for ch in (1, 2, 3):
            chans[ch] = (_net_at(c, ref, part.pin_names[f"IN+{ch}"][0]) or "?",
                         _net_at(c, ref, part.pin_names[f"IN-{ch}"][0]) or "?")
        out.append(Monitor(ref=ref, addr=INA3221_BASE_ADDR + strap,
                           channels=chans))
    return sorted(out, key=lambda m: m.addr)


@dataclass
class RegulatorStage:
    ref: str
    value: str
    enable: str
    rail_in: str
    rail_out: str
    vout: float | None
    pg_led: str | None = None


def _rails_of(c: Circuit, ref: str) -> set[str]:
    rails = set()
    for net in c.nets.values():
        if net.net_class != NetClass.POWER or net.name == "+3V3_SC":
            continue
        if any(pr.ref == ref for pr in net.pins):
            rails.add(net.name)
    return rails


def _canonical_rail(a: str, b: str) -> tuple[str, str]:
    for suf in ("_REG", "_SYS"):
        if a.endswith(suf) and a[:-len(suf)] == b:
            return b, a
        if b.endswith(suf) and b[:-len(suf)] == a:
            return a, b
    return (a, b) if len(a) <= len(b) else (b, a)


def _shunt_aliases(monitor: Circuit | None) -> dict[str, str]:
    if monitor is None:
        return {}
    netted: dict[str, list] = {}
    for net in monitor.nets.values():
        for pr in net.pins:
            netted.setdefault(pr.ref, []).append(net)
    alias: dict[str, str] = {}
    for ref in sorted(netted):
        nets = netted[ref]
        if len(nets) != 2 \
                or not all(n.net_class is NetClass.POWER for n in nets) \
                or nets[0].name == nets[1].name:
            continue
        canonical, other = _canonical_rail(nets[0].name, nets[1].name)
        alias[other] = canonical
    return alias


def _resolve_alias(rail: str, alias: dict[str, str]) -> str:
    seen: set[str] = set()
    while rail in alias and rail not in seen:
        seen.add(rail)
        rail = alias[rail]
    return rail


def regulator_chain(power: Circuit, root: str = "+VIN",
                    monitor: Circuit | None = None) -> list[RegulatorStage]:
    regs: dict[str, str] = {}
    for net in power.nets.values():
        if net.net_class == NetClass.PORT and net.name.startswith("EN_"):
            for pr in net.pins:
                regs[pr.ref] = net.name
    inductors = [r for r, p in power.parts.items() if p.lib_id == "Device:L"]
    cands: dict[str, set[str]] = {}
    for ref in regs:
        rails = _rails_of(power, ref)
        for lref in inductors:
            shared = any(
                net.net_class == NetClass.SIGNAL
                and any(pr.ref == ref for pr in net.pins)
                and any(pr.ref == lref for pr in net.pins)
                for net in power.nets.values())
            if shared:
                rails |= _rails_of(power, lref)
        cands[ref] = rails
    alias = _shunt_aliases(monitor)
    cands = {ref: {_resolve_alias(r, alias) for r in rails}
             for ref, rails in cands.items()}
    known = {_resolve_alias(root, alias)}
    stages: list[RegulatorStage] = []
    pending = dict(cands)
    while pending:
        ready = [(ref, rails) for ref, rails in sorted(pending.items())
                 if len(rails & known) == 1 and len(rails - known) == 1]
        if not ready:
            raise ValueError(
                f"power-tree walk stuck: known={sorted(known)}, "
                f"pending={ {r: sorted(v) for r, v in pending.items()} }")
        ref, rails = ready[0]
        rail_in = next(iter(rails & known))
        rail_out = next(iter(rails - known))
        part = power.parts[ref]
        stages.append(RegulatorStage(
            ref=ref, value=part.value, enable=regs[ref],
            rail_in=rail_in, rail_out=rail_out,
            vout=_stage_vout(power, ref, part.value)))
        known.add(rail_out)
        del pending[ref]
    _attach_pg_leds(power, stages)
    return stages


def _stage_vout(power: Circuit, ref: str, value: str) -> float | None:
    m = re.search(r"-(\d+(?:\.\d+)?)$", value)
    if m:
        return float(m.group(1))
    vref = next((v for k, v in FB_VREF.items() if k in value), None)
    if vref is None:
        return None
    for net in power.nets.values():
        if net.net_class != NetClass.SIGNAL \
                or not any(pr.ref == ref for pr in net.pins):
            continue
        rs = [pr.ref for pr in net.pins if pr.ref.startswith("R")]
        if len(rs) < 2:
            continue
        top = bot = None
        for r in rs:
            other = {n.name: n.net_class for n in power.nets.values()
                     if n.name != net.name
                     and any(pr.ref == r for pr in n.pins)}
            if "GND" in other:
                bot = parse_value_ohms(power.parts[r].value)
            elif any(cls is NetClass.POWER for cls in other.values()):
                top = parse_value_ohms(power.parts[r].value)
        if top and bot:
            return round(vref * (1 + top / bot), 2)
    return None


def _attach_pg_leds(power: Circuit, stages: list[RegulatorStage]) -> None:
    for st in stages:
        token = st.enable.removeprefix("EN_")
        for net in power.nets.values():
            if not net.name.startswith(f"PG_{token}"):
                continue
            for pr in net.pins:
                if pr.ref.startswith("D"):
                    st.pg_led = pr.ref
        if st.pg_led is None:
            for net in power.nets.values():
                if net.name == st.rail_out:
                    for pr in net.pins:
                        if pr.ref.startswith("D"):
                            st.pg_led = pr.ref


@dataclass(frozen=True)
class ModuleGate:
    ref: str
    module: str
    rail_in: str
    rail_out: str
    enable: str
    ilim_ma: int | None
    status_led: str | None


def module_gates(c: Circuit) -> list[ModuleGate]:
    out = []
    for ref in _parts_by_value(c, "SY6280"):
        part = c.parts[ref]
        en = _net_at(c, ref, part.pin_names["EN"][0]) or "?"
        rail_out = _net_at(c, ref, part.pin_names["OUT"][0]) or "?"
        iset_net = _net_at(c, ref, part.pin_names["ISET"][0])
        ilim = None
        for net in c.nets.values():
            if net.name != iset_net:
                continue
            for pr in net.pins:
                if pr.ref.startswith("R"):
                    ohms = parse_value_ohms(c.parts[pr.ref].value)
                    if ohms:
                        ilim = round(SY6280_ILIM_NUMERATOR / ohms * 1000)
        led = None
        for net in c.nets.values():
            if net.name == rail_out:
                for pr in net.pins:
                    if pr.ref.startswith("D"):
                        led = pr.ref
        out.append(ModuleGate(
            ref=ref, module=en.removeprefix("EN_"),
            rail_in=_net_at(c, ref, part.pin_names["IN"][0]) or "?",
            rail_out=rail_out, enable=en, ilim_ma=ilim, status_led=led))
    return sorted(out, key=lambda g: (g.ref[0], int(g.ref[1:])
                                      if g.ref[1:].isdigit() else 0))
