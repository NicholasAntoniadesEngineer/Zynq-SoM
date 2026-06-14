"""bringup_facts — NETLIST-derived facts shared by the generated system
artifacts (``schgen firmware`` -> SC contract header, ``schgen manual`` ->
bring-up procedure).

EVERYTHING in this module is read programmatically from the authored
subsystem netlists (via :func:`schgen.link.load_subsystem`), the committed
SoM contract (``carrier/som_interface.json``) and a live ``kicad-cli``
extraction of the SoM STM32 (U9) pin map — never hand-typed. The only
non-netlist constants are datasheet formulas/values, each tagged with its
source:

- SN74LVC1G08 gate pinout 1=A 2=B 3=GND 4=Y 5=VCC (TI DS; bringup dossier 1)
- SY6280AAC  ILIM(A) = 6800 / RSET(ohm)           (Silergy DS; dossier 2)
- TPS54302   VREF = 0.596 V (FB setpoint math)    (TI DS; power.py)
- TCA9535 7-bit base address 0b0100_A2A1A0 = 0x20 + straps  (TI SCPS201E)
- INA3221 A0 strap decode GND/VS/SDA/SCL -> 0x40..0x43      (TI SBOS576)
- FUSB302B fixed 7-bit address 0x22                          (onsemi DS)
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from schgen.link import load_som_contract, load_subsystem
from schgen.model import Circuit, NetClass, PinRef

REPO_ROOT = Path(__file__).resolve().parents[1]
SOM_SCH = REPO_ROOT / "som" / "Zynq_SoM.kicad_sch"

# datasheet constants (sources in the module docstring)
GATE_PIN_A, GATE_PIN_B, GATE_PIN_Y = "1", "2", "4"   # SN74LVC1G08
SY6280_ILIM_NUMERATOR = 6800.0                       # ILIM(A) = 6800/RSET
FB_VREF = {"TPS54302": 0.596}                        # buck FB reference [V]
TCA9535_BASE_ADDR = 0x20                             # 0b0100_A2A1A0
INA3221_BASE_ADDR = 0x40                             # + A0 strap decode
FUSB302B_ADDR = 0x22                                 # fixed (onsemi DS)


def parse_value_ohms(value: str) -> float | None:
    """'73.2k' -> 73200.0, '4k7' -> 4700.0, '100R' -> 100.0, '10mR' -> 0.01."""
    v = value.strip()
    m = re.fullmatch(r"(\d+(?:\.\d+)?)\s*(m|k|M)?(?:R|ohm)?", v)
    if m:
        mult = {"m": 1e-3, "k": 1e3, "M": 1e6, None: 1.0}[m.group(2)]
        return float(m.group(1)) * mult
    m = re.fullmatch(r"(\d+)(k|M)(\d+)", v)            # '4k7' style
    if m:
        mult = {"k": 1e3, "M": 1e6}[m.group(2)]
        return float(f"{m.group(1)}.{m.group(3)}") * mult
    return None


def c_ident(net: str) -> str:
    """Net name -> C identifier fragment ('+3V3_SC' -> 'P3V3_SC')."""
    ident = net.replace("+", "P").replace("-", "_")
    ident = "".join(ch if ch.isalnum() or ch == "_" else "_" for ch in ident)
    if ident and ident[0].isdigit():
        ident = "_" + ident
    return ident


def _net_at(c: Circuit, ref: str, pin: str) -> str | None:
    n = c.net_of(PinRef(ref, pin))
    return n.name if n is not None else None


def _pin_name_of(c: Circuit, ref: str, num: str) -> str:
    """Reverse lookup pin NUMBER -> NAME via the use_part pin table."""
    for name, nums in c.parts[ref].pin_names.items():
        if num in nums:
            return name
    return num


def _parts_by_value(c: Circuit, substr: str) -> list[str]:
    return sorted(r for r, p in c.parts.items()
                  if substr in p.value or substr in p.lib_id)


# ---- STM32 (SoM U9) pin map -----------------------------------------------------

@dataclass(frozen=True)
class Stm32Net:
    net: str                  # SoM net name, e.g. "STM32_GPIO6"
    port: str                 # GPIO port letter, e.g. "A"
    pin: int                  # GPIO pin number, e.g. 13
    j_pins: tuple[str, ...]   # ("J1.45",) — empty for SoM-internal nets


def stm32_pin_map(som_sch: Path = SOM_SCH, ref: str = "U9") -> dict:
    """Live ``kicad-cli`` extraction of the SoM system controller (U9):
    net -> STM32 GPIO port/pin, joined with the J-connector contract.

    Returns {"value": "STM32G431CBUx", "nets": {net: Stm32Net},
    "internal": {net: Stm32Net}} where "nets" are J-contract nets and
    "internal" are STM32-driven SoM-internal nets (BMODE, PS_POR, ...).
    """
    from schgen.som_interface import extract_zynq
    data = extract_zynq(som_sch, zynq_ref=ref)
    contract = load_som_contract()
    on_j: dict[str, Stm32Net] = {}
    internal: dict[str, Stm32Net] = {}
    for num, net in data["ball_net"].items():
        if net.startswith("unconnected-"):
            continue
        m = re.fullmatch(r"P([A-G])(\d+)", data["pin_names"].get(num, ""))
        if not m:
            continue                       # VDD/VSS/NRST-as-PG10 handled below
        entry = Stm32Net(net=net, port=m.group(1), pin=int(m.group(2)),
                         j_pins=tuple(contract.get(net, [])))
        if entry.j_pins:
            on_j[net] = entry
        else:
            internal[net] = entry
    return {"value": data["value"], "nets": on_j, "internal": internal}


# ---- DIP switches ----------------------------------------------------------------

@dataclass(frozen=True)
class DipPosition:
    switch: str        # part ref on its sheet, e.g. "SW1"
    position: int      # silkscreen position 1..N
    net: str           # the strap net on the position's even pin


def dip_switch_refs(c: Circuit) -> list[str]:
    """Every DSHP-style DIP switch on the sheet (sorted refs) — so the
    generated manual/header follow when a new bring-up DIP is added
    (round-5 SW6) instead of hard-coding SW1/SW2."""
    return _parts_by_value(c, "DSHP")


def dip_positions(c: Circuit, ref: str,
                  common: tuple[str, ...] = ("+3V3_SC", "GND")) \
        -> list[DipPosition]:
    """Silkscreen position -> strap net for a DSHP-style DIP: position n
    pairs pins (n, 2N+1-n) (Kangshen DSHP footprint, bringup_rails.py).
    Per position the SIGNAL side is reported: bus/common nets are dropped
    and PORT-class nets win over sheet-internal nets."""
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


# ---- EN cells (SN74LVC1G08 AND gates) --------------------------------------------

@dataclass(frozen=True)
class EnCell:
    sheet: str
    gate: str          # gate ref, e.g. "U1"
    dip_net: str       # A input (BU_DIP_*)
    override_net: str  # B input (STM32_RAIL_EN_* / BU_OVR_*)
    enable: str        # Y output (EN_*)


def en_cells(c: Circuit) -> list[EnCell]:
    cells = []
    for ref in _parts_by_value(c, "74LVC1G08"):
        cells.append(EnCell(
            sheet=c.name, gate=ref,
            dip_net=_net_at(c, ref, GATE_PIN_A) or "?",
            override_net=_net_at(c, ref, GATE_PIN_B) or "?",
            enable=_net_at(c, ref, GATE_PIN_Y) or "?"))
    return cells


# ---- TCA9535 expander ------------------------------------------------------------

@dataclass(frozen=True)
class Expander:
    ref: str
    addr: int                      # 7-bit, derived from the A2/A1/A0 straps
    ports: dict[str, str] = field(default_factory=dict)   # "P00" -> net


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


# ---- INA3221 monitors ------------------------------------------------------------

@dataclass(frozen=True)
class Monitor:
    ref: str
    addr: int
    channels: dict[int, tuple[str, str]] = field(default_factory=dict)
    # channel -> (IN+ net, IN- net)


def ina3221_monitors(c: Circuit) -> list[Monitor]:
    out = []
    for ref in _parts_by_value(c, "INA3221"):
        part = c.parts[ref]
        vs_net = _net_at(c, ref, part.pin_names["VS"][0])
        a0 = _net_at(c, ref, part.pin_names["A0"][0])
        sda = _net_at(c, ref, part.pin_names["SDA"][0])
        scl = _net_at(c, ref, part.pin_names["SCL"][0])
        strap = {  # TI SBOS576 table: A0 = GND/VS/SDA/SCL -> +0..+3
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


# ---- power-tree regulator chain --------------------------------------------------

@dataclass
class RegulatorStage:
    ref: str
    value: str         # "TPS54302DDCR" / "AP2112K-1.8"
    enable: str        # EN_* port net on its EN pin
    rail_in: str
    rail_out: str
    vout: float | None         # FB-divider / fixed-LDO setpoint [V]
    pg_led: str | None = None  # PG indicator LED ref (power sheet)


def _rails_of(c: Circuit, ref: str) -> set[str]:
    """POWER-class nets on the part's own pins (always-on SC rail excluded)."""
    rails = set()
    for net in c.nets.values():
        if net.net_class != NetClass.POWER or net.name == "+3V3_SC":
            continue
        if any(pr.ref == ref for pr in net.pins):
            rails.add(net.name)
    return rails


def _canonical_rail(a: str, b: str) -> tuple[str, str]:
    """(board_rail, measurement_rail) for a shunt-bridged pair: the measurement
    rail is the one whose name is the board rail plus a _REG/_SYS suffix
    (+VIN_SYS -> +VIN, +5V_REG -> +5V); fall back to the longer name as the
    measurement side."""
    for suf in ("_REG", "_SYS"):
        if a.endswith(suf) and a[:-len(suf)] == b:
            return b, a
        if b.endswith(suf) and b[:-len(suf)] == a:
            return a, b
    return (a, b) if len(a) <= len(b) else (b, a)


def _shunt_aliases(monitor: Circuit | None) -> dict[str, str]:
    """Rail aliases from the series sense shunts (e.g. power_mon RS1..RS4): a
    2-pin passive bridging two POWER rails is a dead short for bring-up
    sequencing, so its reg-side measurement rail aliases to its board rail.
    Netlist-driven (same idiom as powertree._detect_bridges)."""
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
    """Follow the alias map to the canonical board rail (cycle-guarded)."""
    seen: set[str] = set()
    while rail in alias and rail not in seen:
        seen.add(rail)
        rail = alias[rail]
    return rail


def regulator_chain(power: Circuit, root: str = "+VIN",
                    monitor: Circuit | None = None) -> list[RegulatorStage]:
    """The rail-sequencing order, derived from the power netlist topology:
    each regulator = the part carrying an EN_* PORT pin; its candidate rails
    are the POWER nets on its own pins plus those one inductor hop away
    (buck SW node -> L -> output). Starting from the inlet rail, every stage
    must consume exactly one already-known rail and produce exactly one new
    one — anything else is a build error, never a guess.

    ``monitor`` (power_mon) supplies the series sense-shunt bridges: each
    shunt is a wire for sequencing, so its reg-side rail (+5V_REG) collapses
    to its board rail (+5V) and the walk crosses the shunt transparently."""
    # regulator refs = parts carrying an EN_* PORT pin
    regs: dict[str, str] = {}
    for net in power.nets.values():
        if net.net_class == NetClass.PORT and net.name.startswith("EN_"):
            for pr in net.pins:
                regs[pr.ref] = net.name
    # candidate rails per regulator (direct + one inductor hop)
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
    # series shunts are wires for sequencing: collapse each reg-side rail to
    # its board rail so the walk crosses +VIN ->(RS1) +VIN_SYS, +5V_REG ->(RS2)
    # +5V, ... transparently (else the rail split opens the chain).
    alias = _shunt_aliases(monitor)
    cands = {ref: {_resolve_alias(r, alias) for r in rails}
             for ref, rails in cands.items()}
    # walk the chain from the inlet rail
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
    """Setpoint: fixed-LDO suffix ('AP2112K-1.8' -> 1.8 V) or the buck FB
    divider Vout = VREF * (1 + Rtop/Rbot) computed from the netlist. The top
    (output-sense) arm is the divider resistor that does NOT return to GND, so
    the setpoint is correct regardless of the output rail's name (a series-
    shunt split renames it, e.g. +5V -> +5V_REG)."""
    m = re.search(r"-(\d+(?:\.\d+)?)$", value)
    if m:
        return float(m.group(1))
    vref = next((v for k, v in FB_VREF.items() if k in value), None)
    if vref is None:
        return None
    # FB net = SIGNAL net shared by the regulator and exactly 2 resistors
    for net in power.nets.values():
        if net.net_class != NetClass.SIGNAL \
                or not any(pr.ref == ref for pr in net.pins):
            continue
        rs = [pr.ref for pr in net.pins if pr.ref.startswith("R")]
        if len(rs) != 2:
            continue
        top = bot = None
        for r in rs:
            other = {n.name for n in power.nets.values()
                     if n.name != net.name
                     and any(pr.ref == r for pr in n.pins)}
            if "GND" in other:
                bot = parse_value_ohms(power.parts[r].value)
            else:
                top = parse_value_ohms(power.parts[r].value)
        if top and bot:
            return round(vref * (1 + top / bot), 2)
    return None


def _attach_pg_leds(power: Circuit, stages: list[RegulatorStage]) -> None:
    """PG LED per stage: the LED whose net follows the sheet's PG_<token>
    convention, token taken from the stage's EN_<token> port name."""
    for st in stages:
        token = st.enable.removeprefix("EN_")
        for net in power.nets.values():
            if not net.name.startswith(f"PG_{token}"):
                continue
            for pr in net.pins:
                if pr.ref.startswith("D"):
                    st.pg_led = pr.ref
        # fall back: LED directly on the output rail
        if st.pg_led is None:
            for net in power.nets.values():
                if net.name == st.rail_out:
                    for pr in net.pins:
                        if pr.ref.startswith("D"):
                            st.pg_led = pr.ref


# ---- module load switches --------------------------------------------------------

@dataclass(frozen=True)
class ModuleGate:
    ref: str           # SY6280 ref on bringup_modules
    module: str        # "HDMI_TX" (from its EN_<module> port)
    rail_in: str
    rail_out: str
    enable: str        # EN_<module>
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
