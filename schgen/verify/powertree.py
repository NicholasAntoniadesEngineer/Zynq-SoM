"""Power-tree BUDGET GATE (PLAN round 4): prove regulator headroom from the
netlists + the subsystems' declarative ``c.draws(rail, amps, note)`` budget
declarations.

The TREE is extracted from the netlists themselves, never hand-drawn:
- a part whose ``value`` matches REG_SPECS is a regulator/load switch; its
  input rail is the POWER net on its IN pin, its output rail the POWER net
  on its OUT pin (bucks hop SW-net -> inductor -> rail, exactly like the
  placement engine's stage detection);
- a SY6280's current limit is COMPUTED from its ISET resistor in the
  netlist (ILIM = 6800 / RSET) — change the resistor, the budget follows;
- a series resistor bridging two POWER rails is a shunt bridge (the
  power_mon INA3221 shunts);
- board power SOURCES are the enumerated electrical contract (USB-C PD
  20 V/3 A into +VIN; the SoM's always-on TPS7A20 LDO behind +3V3_SC).

Loads flow bottom-up: a rail's total = its declared draws + every child
regulator's input current (LDO/switch: I_in = I_out; buck:
I_in = V_out*I_out / (V_in*eta), eta = 0.90 conservative).

ERRORS (gate FAILS, non-zero exit): any regulator or source loaded past its
limit. FINDINGS/WARNINGS (reported loudly, build continues): unsourced
rails (annotated with their PLAN deferral where one exists), the VBUS
pre-contract capacitance audit (computed from the netlists), and the
SoM-exported +3V3/+1V8 parallel-source question.

Outputs: carrier/reports/power_tree.txt (verdict) +
carrier/docs/power_tree.svg (numbered tree diagram, diagram.py style).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from schgen.core.model import NetClass

# ---- SI value parsing (shared with schgen/spice.py) ----------------------------

_SI = {"p": 1e-12, "n": 1e-9, "u": 1e-6, "µ": 1e-6, "m": 1e-3,
       "k": 1e3, "K": 1e3, "M": 1e6, "G": 1e9, "R": 1.0, "": 1.0}

_VAL_RE = re.compile(
    r"^(\d+(?:\.\d+)?)\s*([pnuµmkKMGR]?)(\d*)\s*(?:[RFHΩ]|mR)?$")


def parse_si(text: str) -> float | None:
    """'6.8k'->6800, '4k7'->4700, '22k1'->22100, '100n'->1e-7, '10mR'->0.01,
    '1.5R'->1.5, '10uH'->1e-5. None if unparseable."""
    t = text.strip()
    if t.endswith("mR"):                       # milliohm shunts: 10mR / 20mR
        head = t[:-2]
        try:
            return float(head) * 1e-3
        except ValueError:
            return None
    m = _VAL_RE.match(t)
    if not m:
        return None
    whole, prefix, frac = m.groups()
    if frac:                                    # 4k7 / 22k1 style
        num = float(f"{whole}.{frac}")
    else:
        num = float(whole)
    return num * _SI.get(prefix, 1.0)


# ---- rail voltages (by name pattern) -------------------------------------------

_VOLT_PATTERNS: tuple[tuple[str, float], ...] = (
    (r"^\+VBUS_IN$", 20.0),     # raw receptacle VBUS (contract rail)
    # DEF-D shunt-split rails: the reg-side _REG/_SYS clusters are the SAME
    # voltage as the post-shunt board rail (the 10/20 mR shunt drop is mV).
    # The generic prefixes below already resolve these, but the explicit
    # anchored entries (placed BEFORE their generic counterparts) harden
    # against any future narrower-value anchored pattern shadowing them.
    (r"^\+VIN_SYS$", 20.0),     # DEF-D: post-RS1 buck-input rail (= +VIN - IR)
    (r"^\+VIN", 20.0),          # fused board input (behind the TPS26631)
    # +5V_SOM is DELIBERATELY re-centred BELOW 5 V (PWR-5): the SoM is a
    # 4.2-5.0 V-input module, so the old 4.96 V nom / 5.17 V worst-case-high
    # setpoint poked above its 5.0 V rec-max. R14/R15 = 68.1k/10k now target
    # 4.65 V nom (WC-hi ~4.81 V) so the whole band stays inside 4.2-5.0 V.
    # MUST precede the generic +5V pattern so the FB +/-3% gate judges this
    # buck against its real intended 4.65 V, not a stale 5.0 V.
    (r"^\+5V_SOM$", 4.65),
    (r"^\+5V_REG$", 5.0),       # DEF-D: buck-1 output, pre-RS2
    (r"^\+5V", 5.0),
    # DEF-I: ~5 V rails that are NOT +5V-prefixed (so the generic +5V pattern
    # misses them) — EXACT-anchored so they resolve for the CAP_VOLTAGE derate
    # without shadowing any FB/SW/BOOT/CC trap node. Each carries a bypass cap
    # that was previously voltage-unchecked (CAP_VOLTAGE-blind).
    (r"^USB_VBUS$", 5.0),          # usbc_otg downstream VBUS (5 V)
    (r"^USB_UART_VBUS$", 5.0),     # usb_uart_connector host VBUS (5 V)
    (r"^HDMI_RX_5V$", 5.0),        # HDMI-RX cable +5 V (HDMI 1.4 pin 18)
    (r"^HDMI_TX_CON_5V0$", 5.0),   # HDMI-TX connector +5 V
    # AUD: the SY7201 LCD-backlight boost OUTPUT node (open-LED OVP clamp ~30 V,
    # the single highest-voltage node on the board). SIGNAL-class + SY7201 not
    # in REG_SPECS, so it was CAP_VOLTAGE-blind — resolve it so the boost output
    # cap (lcd C2) is derated against the 30 V clamp, not silently UNSPEC.
    (r"^LCD_VLED_P$", 30.0),       # lcd SY7201 boost out @ open-LED OVP clamp
    (r"^\+3V3_REG$", 3.3),      # DEF-D: buck-2 output, pre-RS3
    (r"^\+3V3", 3.3),
    (r"^\+1V8_REG$", 1.8),      # DEF-D: LDO output, pre-RS4
    (r"^\+1V8", 1.8),
    (r"^\+2V5", 2.5),
    (r"^\+VCCO_35$", 2.5),      # bank 35 = 2.5 V (camera/FMC dossiers)
    (r"^\+VCCO_", 3.3),         # banks 13/33/34 = 3.3 V (rail map)
    (r"^VBUS$", 5.0),
)


def rail_volts(name: str) -> float | None:
    for pat, v in _VOLT_PATTERNS:
        if re.match(pat, name):
            return v
    return None


# ---- regulator registry (datasheet limits; topology comes from netlists) -------

@dataclass(frozen=True)
class RegSpec:
    kind: str                  # "buck" | "ldo" | "load_switch" | "efuse"
    limit_a: float | None      # None => limit computed from ISET resistor
    eff: float = 1.0           # input-power transfer (bucks only)
    in_pin: str = ""           # pin number or NAME (resolved via pin_names)
    out_pin: str = ""          # ldo/switch: OUT pin; buck: SW pin (-> L -> rail)
    iset_pin: str = ""         # switch/efuse: ILIM = ilim_num / R(ISET->GND)
    ilim_num: float = 6800.0   # ILIM numerator [A*ohm] (SY6280 DS: 6800;
                               # TPS2663 DS Eq 5: 18/R_kohm = 18000/R_ohm)
    note: str = ""


# keyed by part-value PREFIX (power.py writes 'LM61460AANRJRR', fmc 'TLV75725PDBVR')
REG_SPECS: dict[str, RegSpec] = {
    # TPS54302: NO emitted part uses it any more (the +5V/+3V3 bucks were re-spec'd
    # to the LM61460, BOM-verified), but the key is RETAINED as the thermal-gate
    # mutant-test fixture (test_tps54302_over_2A_fails_at_datasheet_rthja proves the
    # gate WOULD have caught the original over-2A TPS54302 defect that drove the
    # LM61460 re-spec). Do NOT remove it without updating that test (audit 2026-06-20
    # flagged removal as "not proven safe" — and it broke the test).
    "TPS54302": RegSpec("buck", 3.0, eff=0.90, in_pin="3", out_pin="2",
                        note="TI 3 A synchronous buck (SW->L->rail); thermal-gate test fixture"),
    # power.py +5V buck U1 — RE-SPEC'd (wt/buck) from the LMR33630 (3 A) to the
    # LM61460 (6 A): the +5V chain is the board's heaviest converter (2.95 A),
    # which ran the old 3 A part at 98% with no headroom. 6 A -> ~2x margin.
    # U1 draws the faithful parts/LM61460AANRJRR/ dossier symbol (the
    # "0 hand-built symbols" migration); EasyEDA types every dossier pin
    # 'passive' so a name-keyed lookup is unreliable -> address pins BY NUMBER:
    # VIN1=8 (in), SW=10 (out, ->L->rail).
    "LM61460": RegSpec("buck", 6.0, eff=0.90, in_pin="8", out_pin="10",
                       note="TI 6 A 3-36V synchronous buck (VIN1=8 ->L<-SW=10 ->rail)"),
    # DEF-I: U1 (power.py) +5V buck — was the LMR33630 (3 A) before the wt/buck
    # re-spec above; row kept for provenance (no part matches it now).
    "LMR33630": RegSpec("buck", 3.0, eff=0.90, in_pin="2", out_pin="8",
                        note="TI 3 A 36V synchronous buck (VIN=2, SW=8 ->L->rail)"),
    "AP2112K": RegSpec("ldo", 0.6, in_pin="1", out_pin="5",
                       note="600 mA LDO"),
    "TLV75725": RegSpec("ldo", 0.4, in_pin="1", out_pin="5",
                        note="1 A LDO held to 0.4 A continuous (PWR-3: DYD "
                             "thermal-pad, RthJA ~92.5 C/W EP-to-GND, Tj ~80 C "
                             "at 0.32 W/Ta=50 C — fmc.md section 3)"),
    "SY6280": RegSpec("load_switch", None, in_pin="IN", out_pin="OUT",
                      iset_pin="ISET", note="ILIM = 6800/RSET from netlist"),
    # PLAN round-5 inlet eFuse: dVdT-soft-started, OVP-cutoff, auto-retry
    "TPS26631": RegSpec("efuse", None, in_pin="IN", out_pin="OUT",
                        iset_pin="ILIM", ilim_num=18000.0,
                        note="ILIM = 18/R_kohm from netlist (TPS2663 Eq 5)"),
}

# Board power sources: the electrical contract (rail -> (volts, amps, who)).
SOURCES: dict[str, tuple[float, float, str]] = {
    "+VBUS_IN": (20.0, 3.0, "USB-C PD sink contract 20 V / 3 A at the "
                            "receptacle (pd_input J1; +VIN sits behind "
                            "the TPS26631 eFuse, round 5)"),
    # P0 corollary (wave3_function_map.md): +3V3_SC is the SoM TPS7A20 LDO
    # U13 (300 mA class — the SoM power_architecture sheet annotates "3V3
    # (300mA)"), NOT the MPM3822 (that is the +1V35 DDR3L rail). The 300 mA
    # envelope is SHARED with the SoM-side SC loads (the STM32G431 SC ~50 mA
    # + its on-module peripherals); the carrier tally (~23 mA: FUSB302 +
    # TCA9535 + 2x INA3221 + 12x SN74LVC1G08 gates + pull-ups) leaves ample
    # room. The gate now guards the REAL 300 mA envelope, not a 2 A phantom.
    "+3V3_SC": (3.3, 0.3, "SoM TPS7A20 always-on SC LDO U13 (J1.37); 300 mA "
                          "class — the SoM power_architecture sheet says "
                          "'3V3 (300mA)'. Envelope shared with the SoM-side "
                          "SC (STM32G431 ~50 mA); carrier tally only here"),
    # debug-USB inlet: the JTAG/UART debug USB-C receptacle's 5 V VBUS
    # (usb_jtag_connector J1) feeds the self-powered debug island (usb_jtag
    # AP2112K-3.3 LDO U4). Host-supplied, present only when the debug cable is
    # connected; modelled like +VBUS_IN so it is not flagged UNSOURCED. It stays
    # electrically ISOLATED from the carrier +5V (audit 2026-06-19).
    "+5V_DBG": (5.0, 0.5, "debug USB-C VBUS (usb_jtag_connector J1) — host-"
                          "supplied 5 V / 0.5 A USB2 default; feeds the usb_jtag "
                          "AP2112K-3.3 debug-island LDO; isolated from carrier +5V"),
}

# Rails known to be deferred by PLAN flags (unsourced today, by decision).
# The four +VCCO_* bank rails are NO LONGER here (SYS-1, 2026-06-13): the
# J-sheet generator now MERGES each +VCCO_* contact pin onto its carrier rail
# (som_conn_gen.VCCO_RAIL_MAP -> +3V3 / +2V5_VADJ), so the banks appear as real
# SOURCED loads on those rails — not unsourced orphans. Re-adding a +VCCO_* key
# here would be dead (no sheet emits that net anymore).
# DEF-D (2026-06-14): the four +VIN_SYS / +5V_REG / +3V3_REG / +1V8_REG shunt
# rails left this table — power.py/power_som.py now put each regulator's OUTPUT
# (or buck INPUT, for +VIN_SYS) on the _REG/_SYS net, so the RS1..RS4 shunts sit
# IN SERIES. The shunt-bridge endpoints land in `sourced` automatically (see the
# `sourced` union in analyze()), so the plain board rails are sourced and the
# _REG/_SYS rails carry real load. The dict + machinery stay wired for any future
# deferral; it is empty today.
KNOWN_DEFERRED: dict[str, str] = {}


@dataclass
class Reg:
    n: int                    # diagram number
    sheet: str
    ref: str
    value: str
    kind: str
    vin: str
    vout: str
    limit_a: float
    eff: float
    note: str
    i_out: float = 0.0
    i_in: float = 0.0


@dataclass
class Result:
    regs: list[Reg] = field(default_factory=list)
    rails: dict[str, float] = field(default_factory=dict)        # total amps
    draws: dict[str, list[tuple[str, float, str]]] = field(default_factory=dict)
    bridges: list[tuple[str, str, str, str]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    findings: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)      # resolved audits
    source_load: dict[str, float] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return not self.errors


def _pin_no(part, pin_spec: str) -> str | None:
    """Resolve a RegSpec pin (NAME via use_part pin table, else number)."""
    if part.pin_names and pin_spec in part.pin_names:
        nums = part.pin_names[pin_spec]
        return nums[0] if nums else None
    return pin_spec


def _net_on(c, ref: str, pin_no: str | None):
    from schgen.core.model import PinRef
    if pin_no is None:
        return None
    return c.net_of(PinRef(ref, pin_no))


def _detect_regs(sheets) -> tuple[list[Reg], list[str]]:
    regs: list[Reg] = []
    errors: list[str] = []
    n = 0
    for sc in sheets:
        c = sc.circuit
        for ref, part in sorted(c.parts.items()):
            spec = next((s for k, s in REG_SPECS.items()
                         if part.value.startswith(k)), None)
            if spec is None:
                continue
            vin_net = _net_on(c, ref, _pin_no(part, spec.in_pin))
            out_net = _net_on(c, ref, _pin_no(part, spec.out_pin))
            if vin_net is None or out_net is None:
                errors.append(f"{sc.name}:{ref} ({part.value}): cannot "
                              f"resolve IN/OUT pins for the power tree")
                continue
            vout_name = out_net.name
            if spec.kind == "buck":
                # SW net -> inductor -> output rail
                vout_name = ""
                for pr in out_net.pins:
                    other = c.parts.get(pr.ref)
                    if other is None or pr.ref == ref:
                        continue
                    if other.lib_id.endswith(":L") or \
                            other.value.upper().endswith("H"):
                        for p2 in ("1", "2"):
                            nn = _net_on(c, pr.ref, p2)
                            if nn is not None and nn.name != out_net.name \
                                    and nn.net_class is NetClass.POWER:
                                vout_name = nn.name
                if not vout_name:
                    errors.append(f"{sc.name}:{ref} ({part.value}): no "
                                  f"SW->inductor->rail hop found")
                    continue
            limit = spec.limit_a
            note = spec.note
            if spec.kind in ("load_switch", "efuse"):
                iset_net = _net_on(c, ref, _pin_no(part, spec.iset_pin))
                rset = None
                if iset_net is not None:
                    for pr in iset_net.pins:
                        rp = c.parts.get(pr.ref)
                        if rp is not None and rp.lib_id.endswith(":R"):
                            rset = parse_si(rp.value)
                if rset:
                    limit = round(spec.ilim_num / rset, 3)
                    note = (f"ILIM = {spec.ilim_num:.0f}/{rset:.0f}R = "
                            f"{limit*1000:.0f} mA")
                else:
                    errors.append(f"{sc.name}:{ref} ({part.value}): ISET "
                                  f"resistor not found — cannot prove ILIM")
                    continue
            n += 1
            regs.append(Reg(n=n, sheet=sc.name, ref=ref, value=part.value,
                            kind=spec.kind, vin=vin_net.name, vout=vout_name,
                            limit_a=float(limit), eff=spec.eff, note=note))
    return regs, errors


def _detect_bridges(sheets) -> list[tuple[str, str, str, str]]:
    """Series 2-pin element bridging two POWER rails (the power_mon INA3221
    shunts): (sheet, ref, rail_a, rail_b). Netlist-driven: a part with
    EXACTLY two netted pins, both on different POWER rails."""
    out = []
    for sc in sheets:
        c = sc.circuit
        netted: dict[str, list] = {}
        for net in c.nets.values():
            for pr in net.pins:
                netted.setdefault(pr.ref, []).append(net)
        for ref in sorted(netted):
            nets = netted[ref]
            if len(nets) != 2:
                continue
            if all(n.net_class is NetClass.POWER for n in nets) \
                    and nets[0].name != nets[1].name:
                out.append((sc.name, ref, nets[0].name, nets[1].name))
    return out


def analyze(sheets) -> Result:
    res = Result()
    res.regs, det_errors = _detect_regs(sheets)
    res.errors += det_errors
    res.bridges = _detect_bridges(sheets)

    # declared draws per rail
    all_rails: set[str] = set()
    for sc in sheets:
        for net in sc.circuit.nets.values():
            if net.net_class is NetClass.POWER:
                all_rails.add(net.name)
        for rail, entries in sc.circuit.loads.items():
            for amps, note in entries:
                res.draws.setdefault(rail, []).append((sc.name, amps, note))

    regs_by_vin: dict[str, list[Reg]] = {}
    regs_by_vout: dict[str, list[Reg]] = {}
    for r in res.regs:
        regs_by_vin.setdefault(r.vin, []).append(r)
        regs_by_vout.setdefault(r.vout, []).append(r)

    # DEF-D: a series shunt passes current 1:1, so the UPSTREAM (reg/source)
    # side of each bridge must inherit the DOWNSTREAM (board/load) side's total
    # — otherwise the regulator feeding the upstream rail sees zero load and the
    # overrun gate goes blind. Orient each bridge by where the load sits: an
    # endpoint is downstream if it actually bears load (declared draws or a
    # child regulator), and the bare reg/source endpoint is upstream. (power_mon
    # authors RSn.1 = reg-side, RSn.2 = board-side, but _detect_bridges is
    # net-iteration-ordered, so we infer direction from the load topology, not
    # pin order.) bridge_down maps upstream -> [downstream].
    has_load = set(res.draws) | set(regs_by_vin)

    bridge_down: dict[str, list[str]] = {}
    for _s, _r, a, b in res.bridges:
        a_down, b_down = a in has_load, b in has_load
        # the load-bearing endpoint is downstream; the bare one is upstream.
        if b_down and not a_down:
            up, down = a, b
        elif a_down and not b_down:
            up, down = b, a
        else:
            # ambiguous (both or neither bear load) — do not fold into the
            # budget; the `sourced` set still keeps both endpoints sourced.
            continue
        bridge_down.setdefault(up, []).append(down)

    # bottom-up totals (cycle-guarded; the tree is a DAG by construction)
    visiting: set[str] = set()

    def rail_total(rail: str) -> float:
        if rail in res.rails:
            return res.rails[rail]
        if rail in visiting:
            res.errors.append(f"power-tree CYCLE through rail {rail!r}")
            return 0.0
        visiting.add(rail)
        total = sum(a for _s, a, _n in res.draws.get(rail, []))
        for reg in regs_by_vin.get(rail, []):
            i_out = rail_total(reg.vout)
            reg.i_out = i_out
            if reg.kind == "buck":
                v_in = rail_volts(reg.vin) or 0.0
                v_out = rail_volts(reg.vout) or 0.0
                reg.i_in = (v_out * i_out / (v_in * reg.eff)) if v_in else 0.0
            else:
                reg.i_in = i_out
            total += reg.i_in
        # fold each downstream shunt rail's total through the series shunt (1:1)
        for down in bridge_down.get(rail, []):
            total += rail_total(down)
        visiting.discard(rail)
        res.rails[rail] = round(total, 4)
        return res.rails[rail]

    for rail in sorted(all_rails):
        rail_total(rail)

    # ---- gate: regulator overrun ------------------------------------------
    for reg in res.regs:
        if reg.i_out > reg.limit_a + 1e-9:
            res.errors.append(
                f"OVERRUN: {reg.sheet}:{reg.ref} ({reg.value}) "
                f"{reg.vin} -> {reg.vout}: load {reg.i_out:.3f} A > limit "
                f"{reg.limit_a:.3f} A ({reg.note})")

    # ---- gate: source overrun ----------------------------------------------
    for rail, (_v, amps, who) in SOURCES.items():
        load = res.rails.get(rail, 0.0)
        res.source_load[rail] = load
        if load > amps + 1e-9:
            res.errors.append(
                f"OVERRUN: source {rail} ({who}): load {load:.3f} A > "
                f"{amps:.3f} A")

    # ---- findings: unsourced rails ------------------------------------------
    # BOTH endpoints of every shunt bridge are sourced: the shunt passes the
    # rail through (DEF-D — the RS1..RS4 INA3221 shunts now sit IN SERIES, so a
    # reg-side _REG/_SYS net and its post-shunt board rail are each sourced).
    sourced = set(SOURCES) | {r.vout for r in res.regs} \
        | {b for _s, _r, _a, b in res.bridges} \
        | {a for _s, _r, a, _b in res.bridges}
    for rail in sorted(all_rails):
        if rail in sourced:
            continue
        load = res.rails.get(rail, 0.0)
        if rail in KNOWN_DEFERRED:
            res.warnings.append(
                f"unsourced rail {rail} (load {load:.3f} A) — KNOWN "
                f"deferral: {KNOWN_DEFERRED[rail]}")
        else:
            res.findings.append(
                f"UNSOURCED RAIL {rail} (declared load {load:.3f} A): no "
                f"regulator output, no source contract — needs a gate/tie "
                f"decision before layout")

    # bridge stubs feeding nothing = the pending power_mon split
    bridge_children = {b for _s, _r, _a, b in res.bridges}
    for rail in sorted(bridge_children):
        if not res.draws.get(rail) and not regs_by_vin.get(rail) \
                and rail in KNOWN_DEFERRED:
            res.warnings.append(
                f"shunt-bridge rail {rail} feeds nothing — "
                f"{KNOWN_DEFERRED[rail]}")

    _vbus_precontract_finding(sheets, res)
    _som_parallel_rail_finding(sheets, res)
    return res


def _cap_farads_on(sheets, rail: str) -> list[tuple[str, str, str, float]]:
    """All caps rail->GND across sheets: (sheet, ref, value, farads)."""
    out = []
    for sc in sheets:
        c = sc.circuit
        for ref, part in sorted(c.parts.items()):
            if not part.lib_id.endswith(":C"):
                continue
            nets = {(_net_on(c, ref, p) or type("N", (), {"name": ""})).name
                    for p in ("1", "2")}
            if rail in nets and any(n.startswith("GND") for n in nets):
                f = parse_si(part.value)
                if f:
                    out.append((sc.name, ref, part.value, f))
    return out


def _vbus_precontract_finding(sheets, res: Result) -> None:
    """The PLAN round-4 flag, RESOLVED round 5 by the pd_input TPS26631
    eFuse — and kept armed, computed from the netlists on every run:

    - the PD source sees ONLY the capacitance on the receptacle rail
      (+VBUS_IN) pre-contract; it must stay under the ~10 uF cSnkBulk
      guidance or the finding re-fires;
    - the dVdT-soft-started eFuse must actually bridge the inlet rail to
      the board bulk (+VIN); if it ever disappears from the netlist while
      un-switched bulk remains, the original decision-needed finding
      re-fires with the measured numbers;
    - when compliant, the computed audit (inlet uF, behind-eFuse uF,
      slew from the netlist dVdT cap via TPS2663 DS Eq 2, the resulting
      inrush) is reported as a NOTE in the warnings-free report body.
    """
    inlet = "+VBUS_IN"
    inlet_caps = _cap_farads_on(sheets, inlet)
    inlet_uf = sum(f for *_x, f in inlet_caps) * 1e6
    bulk_caps = _cap_farads_on(sheets, "+VIN")
    bulk_uf = sum(f for *_x, f in bulk_caps) * 1e6
    efuses = [r for r in res.regs if r.kind == "efuse" and r.vin == inlet]
    if not efuses:
        detail = " + ".join(f"{s}:{r}={v}" for s, r, v, _f in
                            inlet_caps + bulk_caps)
        res.findings.append(
            f"VBUS PRE-CONTRACT CAPACITANCE (decision needed — the round-5 "
            f"inlet eFuse is GONE from the netlist): the PD source sees "
            f"{inlet_uf + bulk_uf:.1f} uF un-switched ({detail}) vs the "
            f"~10 uF cSnkBulk guidance; restore an inrush-limited path "
            f"(TPS2663-class eFuse with dVdT control) between the "
            f"receptacle and the board bulk.")
        return
    if inlet_uf > 10.0:
        detail = " + ".join(f"{s}:{r}={v}" for s, r, v, _f in inlet_caps)
        res.findings.append(
            f"VBUS PRE-CONTRACT CAPACITANCE: {inlet} (ahead of the eFuse) "
            f"carries {inlet_uf:.1f} uF nominal ({detail}) — above the "
            f"~10 uF cSnkBulk guidance; keep the receptacle side lean and "
            f"let the dVdT eFuse charge the bulk.")
        return
    # compliant: compute the audit numbers from the netlist for the note
    slew_note = ""
    for sc in sheets:
        c = sc.circuit
        for r in efuses:
            if r.sheet != sc.name:
                continue
            part = c.parts[r.ref]
            dvdt_net = _net_on(c, r.ref, _pin_no(part, "dVdT"))
            if dvdt_net is None:
                continue
            for pr in dvdt_net.pins:
                cp = c.parts.get(pr.ref)
                if cp is not None and cp.lib_id.endswith(":C"):
                    cdvdt = parse_si(cp.value)
                    if cdvdt:
                        # TPS2663 DS Eq 2: t = 20.8e3 * V * C -> slew is
                        # V/t = 1/(20.8e3 * C) [V/s], independent of V
                        slew = 1.0 / (20.8e3 * cdvdt)
                        inrush_ma = bulk_uf * 1e-6 * slew * 1e3
                        slew_note = (f"; dVdT {cp.value} -> slew "
                                     f"{slew / 1e3:.2f} V/ms, inrush into "
                                     f"the bulk ~{inrush_ma:.0f} mA")
    res.notes.append(
        f"VBUS pre-contract audit (round-4 flag, RESOLVED round 5): source "
        f"sees {inlet_uf:.2f} uF at the receptacle ({inlet}) — within the "
        f"~10 uF cSnkBulk guidance; {bulk_uf:.1f} uF board bulk sits "
        f"behind the {', '.join(f'{r.sheet}:{r.ref} {r.value}' for r in efuses)} "
        f"eFuse{slew_note}.")


def _som_parallel_rail_finding(sheets, res: Result) -> None:
    """+3V3 / +1V8 appear on SoM J1 (pins 24-27 / 56-60) AND the SoM's own
    Power sheet regulates +3V3/+1V8 on-module (MPM3834 stages with
    3V3_EN/3V3_PG, 1V8_EN/1V8_PG — som/schematic/Power.kicad_sch), while
    carrier power.py ALSO generates +3V3/+1V8 (LM61460 U2 / AP2112K U3).
    Same net name across the connector = electrically ONE net = two
    regulators in parallel.

    RESOLVED (PLAN round 5, 2026-06-12): carrier bucks win — those J1 pins
    are explicit author no-connects (som_conn_gen.ISOLATED_SOM_RAILS,
    policy twin schgen.link.ISOLATED_SOM_RAILS). This detector STAYS as the
    netlist-driven guard: it reads the connector sheets' actual nets, so it
    is silent while the isolation holds and the finding returns the moment
    a J sheet re-binds either rail."""
    j1_rails = set()
    for sc in sheets:
        if not sc.name.startswith("som_j"):
            continue
        for net in sc.circuit.nets.values():
            if net.net_class is NetClass.POWER and net.name in ("+3V3",
                                                                "+1V8"):
                j1_rails.add(net.name)
    carrier_outs = {r.vout for r in res.regs}
    clash = sorted(j1_rails & carrier_outs)
    if clash:
        res.findings.append(
            f"PARALLEL-SOURCE QUESTION on {', '.join(clash)}: these rails "
            f"are OUTPUTS of carrier regulators (power.py LM61460/AP2112K) "
            f"AND appear on SoM J1 contract pins "
            f"(+3V3: J1.24-27, +1V8: J1.56/58/60) while the SoM's own Power "
            f"sheet regulates same-named rails on-module (MPM3834 stages "
            f"with 3V3_EN/PG + 1V8_EN/PG). If the SoM exports its rails on "
            f"those pins, linking them to the carrier's bucks puts two "
            f"regulators in parallel on one net — needs an explicit "
            f"decision (rename one side, sense-only pins, or drop one "
            f"source) before layout. Facts from som_interface.json + "
            f"som/schematic/Power.kicad_sch; nothing changed here.")


# ---- report ---------------------------------------------------------------------

def report(res: Result) -> str:
    lines = ["schgen power-tree budget gate", "=" * 64, ""]
    lines.append("sources:")
    for rail, (v, amps, who) in SOURCES.items():
        load = res.source_load.get(rail, 0.0)
        pct = 100.0 * load / amps if amps else 0.0
        lines.append(f"  {rail:<10} {v:>5.1f} V  limit {amps:.2f} A  "
                     f"load {load:.3f} A  ({pct:.0f}%)  — {who}")
    lines.append("")
    lines.append(f"regulators ({len(res.regs)}) — numbered as in "
                 f"carrier/docs/power_tree.svg:")
    for r in res.regs:
        pct = 100.0 * r.i_out / r.limit_a if r.limit_a else 0.0
        lines.append(
            f"  ({r.n:>2}) {r.sheet}:{r.ref:<4} {r.value:<14} "
            f"{r.vin:>9} -> {r.vout:<14} load {r.i_out:.3f} A / "
            f"limit {r.limit_a:.3f} A ({pct:.0f}%)  in {r.i_in:.3f} A "
            f"[{r.kind}] {r.note}")
    lines.append("")
    lines.append("shunt bridges (series R rail->rail, power_mon):")
    for s, ref, a, b in res.bridges:
        lines.append(f"  {s}:{ref} {a} -> {b}")
    lines.append("")
    lines.append("declared draws (c.draws — every number cites its source):")
    for rail in sorted(res.draws):
        for sheet, amps, note in res.draws[rail]:
            lines.append(f"  {rail:<16} {amps*1000:>8.1f} mA  {sheet:<18} "
                         f"{note}")
    lines.append("")
    lines.append("rail totals (declared + child regulator inputs):")
    for rail in sorted(res.rails):
        v = rail_volts(rail)
        lines.append(f"  {rail:<16} {res.rails[rail]:>7.3f} A"
                     + (f"  @ {v:.1f} V" if v else ""))
    if res.notes:
        lines += ["", f"notes — resolved audits, recomputed every run "
                      f"({len(res.notes)}):"]
        for n_ in res.notes:
            lines.append(f"  + {n_}")
    if res.findings:
        lines += ["", f"FINDINGS — decisions needed ({len(res.findings)}):"]
        for f_ in res.findings:
            lines.append(f"  * {f_}")
    if res.warnings:
        lines += ["", f"warnings ({len(res.warnings)}):"]
        for w in res.warnings:
            lines.append(f"  WARNING: {w}")
    lines.append("")
    if res.errors:
        lines.append(f"ERRORS ({len(res.errors)}):")
        for e in res.errors:
            lines.append(f"  ERROR: {e}")
    else:
        lines.append("errors: none")
    lines.append("")
    lines.append(f"POWER TREE: {'PASS' if res.ok else 'FAIL'} "
                 f"({len(res.errors)} errors, "
                 f"{len(res.findings)} findings, "
                 f"{len(res.warnings)} warnings)")
    return "\n".join(lines)


# ---- diagram (SVG, diagram.py style) --------------------------------------------

_FONT = "ui-monospace, SFMono-Regular, Menlo, monospace"


def _esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def render_svg(res: Result, out: Path) -> Path:
    """Numbered power-tree diagram: source/rail boxes in depth columns,
    regulator edges labeled with their number + computed load/limit."""
    # depth via BFS from sources
    depth: dict[str, int] = {r: 0 for r in SOURCES}
    changed = True
    while changed:
        changed = False
        for reg in res.regs:
            if reg.vin in depth:
                d = depth[reg.vin] + 1
                if depth.get(reg.vout, -1) < d:
                    depth[reg.vout] = d
                    changed = True
    for s, _r, a, b in res.bridges:
        if a in depth and b not in depth:
            depth[b] = depth[a] + 1
    orphans = [r for r in sorted(res.rails) if r not in depth]

    cols: dict[int, list[str]] = {}
    for rail, d in depth.items():
        cols.setdefault(d, []).append(rail)
    maxd = max(cols) if cols else 0
    BOX_W, ROW_H, COL_W = 190, 40, 330      # 140 px label gap between columns
    pos: dict[str, tuple[int, int]] = {}
    height = 60
    for d in sorted(cols):
        y = 50
        for rail in sorted(cols[d]):
            pos[rail] = (30 + d * COL_W, y)
            y += ROW_H + 26
        height = max(height, y)
    oy = height + 30
    legend_h = 22 + 16 * (len(res.regs) + 1)
    total_h = oy + 90 + 18 * (len(orphans) // 4 + 1) + legend_h
    width = 30 + maxd * COL_W + BOX_W + 60

    e = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} '
         f'{total_h}" font-family="{_FONT}" font-size="11">']
    e.append(f'<rect width="{width}" height="{total_h}" fill="white"/>')
    e.append(f'<text x="30" y="28" font-size="15" font-weight="bold">'
             f'carrier power tree — budget gate '
             f'({"PASS" if res.ok else "FAIL"})</text>')

    # edges first; the short numbered label sits in the inter-column gap,
    # one row per DESTINATION rail, so labels can never collide
    for reg in res.regs:
        if reg.vin not in pos or reg.vout not in pos:
            continue
        x0, y0 = pos[reg.vin]
        x1, y1 = pos[reg.vout]
        ax, ay = x0 + BOX_W, y0 + ROW_H // 2
        bx, by = x1, y1 + ROW_H // 2
        color = "#dc2626" if reg.i_out > reg.limit_a else "#2563eb"
        e.append(f'<path d="M{ax},{ay} C{ax + 60},{ay} {bx - 110},{by} '
                 f'{bx},{by}" fill="none" stroke="{color}" '
                 f'stroke-width="2"/>')
        label = f"({reg.n}) {reg.i_out:.2f}/{reg.limit_a:.2f}A"
        lw = len(label) * 7
        e.append(f'<rect x="{bx - 106}" y="{by - 16}" width="{lw}" '
                 f'height="14" fill="white" fill-opacity="0.85"/>')
        e.append(f'<text x="{bx - 104}" y="{by - 5}" '
                 f'fill="{color}">{_esc(label)}</text>')
    for s, _r, a, b in res.bridges:
        if a not in pos or b not in pos:
            continue
        x0, y0 = pos[a]
        x1, y1 = pos[b]
        e.append(f'<line x1="{x0 + BOX_W}" y1="{y0 + ROW_H // 2}" '
                 f'x2="{x1}" y2="{y1 + ROW_H // 2}" stroke="#9ca3af" '
                 f'stroke-width="1.5" stroke-dasharray="5,4"/>')

    # rail boxes
    for rail, (x, y) in pos.items():
        src = rail in SOURCES
        fill = "#fef3c7" if src else "#eff6ff"
        stroke = "#92400e" if src else "#1e3a8a"
        e.append(f'<rect x="{x}" y="{y}" width="{BOX_W}" height="{ROW_H}" '
                 f'rx="8" fill="{fill}" stroke="{stroke}" '
                 f'stroke-width="1.5"/>')
        v = rail_volts(rail)
        e.append(f'<text x="{x + 10}" y="{y + 16}" font-weight="bold" '
                 f'font-size="12">{_esc(rail)}'
                 + (f' ({v:g} V)' if v else "") + "</text>")
        load = res.rails.get(rail, 0.0)
        cap = ""
        if src:
            cap = f" / {SOURCES[rail][1]:g} A"
        e.append(f'<text x="{x + 10}" y="{y + 32}" fill="#374151">'
                 f'load {load:.3f} A{cap}</text>')

    # orphan rails (unsourced — PLAN deferrals + findings)
    e.append(f'<text x="30" y="{oy}" font-weight="bold" fill="#6b7280">'
             f'unsourced rails (PLAN deferrals / findings):</text>')
    for i, rail in enumerate(orphans):
        e.append(f'<text x="{30 + (i % 4) * 200}" '
                 f'y="{oy + 18 + 18 * (i // 4)}" fill="#6b7280">'
                 f'{_esc(rail)} ({res.rails.get(rail, 0.0):.3f} A)</text>')

    # numbered legend (the same numbers as the verdict report)
    ly = oy + 60 + 18 * (len(orphans) // 4 + 1)
    e.append(f'<text x="30" y="{ly}" font-weight="bold">regulators:</text>')
    for i, reg in enumerate(res.regs):
        e.append(f'<text x="30" y="{ly + 18 + 16 * i}" fill="#374151">'
                 f'({reg.n}) {_esc(reg.sheet)}:{_esc(reg.ref)} '
                 f'{_esc(reg.value)} {_esc(reg.vin)} -&gt; {_esc(reg.vout)} '
                 f'— load {reg.i_out:.3f} A / limit {reg.limit_a:.3f} A '
                 f'[{reg.kind}]</text>')
    e.append("</svg>")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(e) + "\n")
    return out


# ---- entry points ----------------------------------------------------------------

def run(sheets, reports_dir: Path, docs_dir: Path) -> Result:
    res = analyze(sheets)
    txt = report(res)
    reports_dir.mkdir(parents=True, exist_ok=True)
    (reports_dir / "power_tree.txt").write_text(txt + "\n")
    render_svg(res, docs_dir / "power_tree.svg")
    return res


def cmd_powertree(args) -> int:
    from schgen.core.link import all_subsystem_paths, load_subsystem
    names = args.subsystems or [p.stem for p in all_subsystem_paths()]
    sheets = [load_subsystem(n) for n in names]
    repo = Path(__file__).resolve().parents[2]
    res = run(sheets, repo / "carrier" / "reports", repo / "carrier" / "docs")
    print(report(res))
    print(f"\nreport: {repo / 'carrier' / 'reports' / 'power_tree.txt'}")
    print(f"diagram: {repo / 'carrier' / 'docs' / 'power_tree.svg'}")
    return 0 if res.ok else 1
