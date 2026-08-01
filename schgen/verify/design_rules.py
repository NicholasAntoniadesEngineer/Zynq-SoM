from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from schgen.core.model import NetClass, PinRef

_GROUND_RE = re.compile(
    r"^(GND|GNDA|GNDD|GNDPWR|AGND|DGND|PGND|VSS|VSSA|VSSIO|CHASSIS_GND)",
    re.IGNORECASE)

_POWER_PIN_PREFIXES = (
    "VDDIO", "VDDA", "VDDD", "VDDQ", "VDD",
    "VCCIO", "VCCA", "VCCB", "VCC5V", "VCC3V3", "VCC",
    "AVDD", "AVCC", "DVDD", "PVDD",
    "VBAT", "VBACKUP", "VSYS", "VIN", "VPP", "VREF", "VPU",
    "VANA", "VCORE", "VDRV", "VAUX", "VL", "VS",
)


def _is_ground_name(name: str) -> bool:
    return bool(_GROUND_RE.match(name or ""))


def is_power_pin_name(name: str) -> bool:
    if not name:
        return False
    up = name.upper()
    if _is_ground_name(up):
        return False
    if up.startswith("VOUT") or up.startswith("VO_"):
        return False
    for pre in _POWER_PIN_PREFIXES:
        if up == pre or (up.startswith(pre)
                         and (up[len(pre):][:1].isdigit()
                              or up[len(pre):][:1] == "_")):
            return True
    return False


_CONFIG_PIN_RE = re.compile(
    r"^(nOE|OE|nCS|CS|nCE|CE|MODE\d*|ADDR\d*|A\d{1,2}|SEL\d*|CFG\d*|"
    r"STRAP\d*|CONFIG\d*|SET|S\d|POL)$",
    re.IGNORECASE)

_RESET_NET_RE = re.compile(
    r"(^|_)(N?RST|N?RESET|SRST|POR)(_?N|_?B|_|$)",
    re.IGNORECASE)

_RESET_INTERNAL_PULL = (
    re.compile(r"STM32.*NRST", re.IGNORECASE),
)

_EP_PIN_RE = re.compile(
    r"^(EP\d*|E?PAD\d*|PPAD|THERMAL.*|GND_?PAD|DAP)$",
    re.IGNORECASE)

_DRIVER_ETYPES = frozenset({
    "output", "bidirectional", "tri_state",
    "power_out", "open_collector", "open_emitter",
})

_BARE_PASSIVE_SUFFIX = (":R", ":C", ":L")
_CAP_SUFFIX = ":C"
_RES_SUFFIX = ":R"


@dataclass
class DesignRuleResult:
    decap: list[str] = field(default_factory=list)
    i2c: list[str] = field(default_factory=list)
    reset: list[str] = field(default_factory=list)
    strap: list[str] = field(default_factory=list)
    ep: list[str] = field(default_factory=list)
    waived: list[str] = field(default_factory=list)
    checked: dict[str, int] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return not (self.decap or self.i2c or self.reset or self.strap
                    or self.ep)

    @property
    def findings(self) -> list[str]:
        return self.decap + self.i2c + self.reset + self.strap + self.ep

    def summary(self) -> str:
        if self.ok:
            return ("DESIGN RULES: PASS (netlist electrically complete — "
                    f"{self.checked.get('decap', 0)} IC supply pins, "
                    f"{self.checked.get('i2c', 0)} I2C nets, "
                    f"{self.checked.get('reset', 0)} reset nets, "
                    f"{self.checked.get('strap', 0)} strap pins, "
                    f"{self.checked.get('ep', 0)} exposed pads checked; "
                    f"{len(self.waived)} waived)")
        lines = ["DESIGN RULES: FAIL"]
        for tag, items in (("DECAP", self.decap), ("I2C", self.i2c),
                           ("RESET", self.reset), ("STRAP", self.strap),
                           ("EP", self.ep)):
            for it in items:
                lines.append(f"  {tag}: {it}")
        return "\n".join(lines)

    def report(self) -> str:
        lines = ["schgen design-rule completeness gate", "=" * 64, ""]
        lines.append("rules (model-only, pin FUNCTION inferred by NAME):")
        lines.append("  DECAP every multi-pin IC supply pin has a cap to GND on "
                     "its sheet")
        lines.append("  I2C   every i2c-typed bus net has a pull-up to a rail "
                     "(board-wide)")
        lines.append("  RESET every reset net carries an RC (cap-to-GND + pull "
                     "resistor)")
        lines.append("  STRAP no config-input pin floats on a passive-only "
                     "undriven net")
        lines.append("  EP    every exposed/thermal pad is netted to a GROUND "
                     "net (never nc/floating, never a non-GND net)")
        lines.append("")
        lines.append(f"checked: {self.checked.get('decap', 0)} IC supply pins, "
                     f"{self.checked.get('i2c', 0)} i2c nets, "
                     f"{self.checked.get('reset', 0)} reset nets, "
                     f"{self.checked.get('strap', 0)} config pins, "
                     f"{self.checked.get('ep', 0)} exposed pads")
        lines.append("")
        for tag, label, items in (
                ("DECAP", "missing decoupling", self.decap),
                ("I2C", "i2c bus with no pull-up", self.i2c),
                ("RESET", "reset without a full RC", self.reset),
                ("STRAP", "floating control input", self.strap),
                ("EP", "exposed pad not on GND", self.ep)):
            lines.append(f"{tag} — {label} ({len(items)}):")
            for it in items:
                lines.append(f"  * {it}")
            if not items:
                lines.append("  (none)")
            lines.append("")
        lines.append(f"waivers — author-declared, verbatim ({len(self.waived)}):")
        for w in self.waived:
            lines.append(f"  {w}")
        if not self.waived:
            lines.append("  (none)")
        lines.append("")
        lines.append(f"DESIGN RULES: {'PASS' if self.ok else 'FAIL'} "
                     f"({len(self.findings)} findings, "
                     f"{len(self.waived)} waived)")
        return "\n".join(lines)


def _waivers(c, attr: str) -> dict:
    d = getattr(c, attr, None)
    return d if isinstance(d, dict) else {}


def _decap_waived(c, ref: str, pin_num: str, net: str) -> str | None:
    w = _waivers(c, "decap_waivers")
    for key in (f"{ref}.{pin_num}", ref, net):
        if key in w:
            return w[key]
    return None


def _strap_waived(c, ref: str, pin_num: str, pin_name: str, net: str) -> str | None:
    w = _waivers(c, "strap_waivers")
    for key in (f"{ref}.{pin_num}", f"{ref}.{pin_name}", ref, net):
        if key in w:
            return w[key]
    return None


def _ep_waived(c, ref: str, pin_num: str, pin_name: str,
               net: str | None) -> str | None:
    w = _waivers(c, "ep_waivers")
    for key in (f"{ref}.{pin_num}", f"{ref}.{pin_name}", ref, net):
        if key and key in w:
            return w[key]
    return None


def _pins(lib, part):
    try:
        return lib.get(part.lib_id).pins
    except Exception:        # noqa: BLE001 — unresolved symbol: skip cleanly
        return []


def _is_multipin_ic(lib, part) -> bool:
    if part.lib_id.endswith(_BARE_PASSIVE_SUFFIX):
        return False
    nums = {p.number for p in _pins(lib, part)}
    return len(nums) > 2


def check(sheets, lib) -> DesignRuleResult:
    res = DesignRuleResult()

    nets_by_name: dict[str, list[tuple[str, object, object]]] = {}
    for sc in sheets:
        for net in sc.circuit.nets.values():
            nets_by_name.setdefault(net.name, []).append(
                (sc.name, sc.circuit, net))

    _check_decap(sheets, lib, res)
    _check_i2c(sheets, lib, nets_by_name, res)
    _check_reset(sheets, lib, nets_by_name, res)
    _check_strap(sheets, lib, res)
    _check_ep(sheets, lib, res)
    return res


def _net_name_of(c, ref: str, pin_num: str) -> str | None:
    n = c.net_of(PinRef(ref, pin_num))
    return n.name if n is not None else None


def _caps_to_ground_on_sheet(c, lib) -> dict[str, list[tuple[str, str]]]:
    out: dict[str, list[tuple[str, str]]] = {}
    for ref, part in c.parts.items():
        if not part.lib_id.endswith(_CAP_SUFFIX):
            continue
        names = [_net_name_of(c, ref, p.number) for p in _pins(lib, part)]
        names = [n for n in names if n]
        grounds = [n for n in names if _is_ground_name(n)]
        if not grounds:
            continue
        for n in names:
            if n not in grounds:
                out.setdefault(n, []).append((ref, part.value))
    return out


def _check_decap(sheets, lib, res: DesignRuleResult) -> None:
    n_checked = 0
    for sc in sheets:
        c = sc.circuit
        caps = _caps_to_ground_on_sheet(c, lib)
        for ref in sorted(c.parts):
            part = c.parts[ref]
            if not _is_multipin_ic(lib, part):
                continue
            supply: dict[str, list[str]] = {}
            for p in _pins(lib, part):
                if is_power_pin_name(p.name) or (
                        p.etype == "power_in" and not _is_ground_name(p.name)):
                    supply.setdefault(p.name, []).append(p.number)
            for pin_name in sorted(supply):
                pnums = sorted(supply[pin_name])
                rails: dict[str, list[str]] = {}
                for pn in pnums:
                    rn = _net_name_of(c, ref, pn)
                    rails.setdefault(rn or "<unconnected>", []).append(pn)
                for rail in sorted(rails):
                    if rail == "<unconnected>" or _is_ground_name(rail):
                        continue
                    n_checked += 1
                    wv = _decap_waived(c, ref, rails[rail][0], rail)
                    if wv is not None:
                        res.waived.append(
                            f"DECAP {sc.name}:{ref}.{pin_name} ({rail}): {wv}")
                        continue
                    if rail not in caps:
                        res.decap.append(
                            f"{sc.name}:{ref}.{pin_name} (pin "
                            f"{','.join(rails[rail])}) on rail {rail!r} has no "
                            f"decoupling cap to GND on this sheet "
                            f"({part.value}) — add a bypass cap or "
                            f"c.waive_decap({ref!r}, reason)")
    res.checked["decap"] = n_checked


def _resistor_pulls_to_rail(sheets, lib, net_name: str) -> list[str]:
    out: list[str] = []
    for sc in sheets:
        c = sc.circuit
        for ref in sorted(c.parts):
            part = c.parts[ref]
            if not part.lib_id.endswith(_RES_SUFFIX):
                continue
            pin_nets = [(p.number, c.net_of(PinRef(ref, p.number)))
                        for p in _pins(lib, part)]
            names = {n.name for _pn, n in pin_nets if n is not None}
            if net_name not in names:
                continue
            for _pn, n in pin_nets:
                if n is not None and n.name != net_name \
                        and n.net_class is NetClass.POWER:
                    out.append(f"{sc.name}:{ref}->{n.name}")
    return sorted(set(out))


def _resistor_on_net(sheets, lib, net_name: str) -> list[str]:
    out: list[str] = []
    for sc in sheets:
        c = sc.circuit
        for ref in sorted(c.parts):
            part = c.parts[ref]
            if not part.lib_id.endswith(_RES_SUFFIX):
                continue
            names = {n.name for n in
                     (c.net_of(PinRef(ref, p.number)) for p in _pins(lib, part))
                     if n is not None}
            if net_name in names:
                out.append(f"{sc.name}:{ref}")
    return sorted(set(out))


def _cap_to_ground_anywhere(sheets, lib, net_name: str) -> list[str]:
    out: list[str] = []
    for sc in sheets:
        c = sc.circuit
        for ref in sorted(c.parts):
            part = c.parts[ref]
            if not part.lib_id.endswith(_CAP_SUFFIX):
                continue
            names = [n.name for n in
                     (c.net_of(PinRef(ref, p.number)) for p in _pins(lib, part))
                     if n is not None]
            if net_name in names and any(_is_ground_name(n) for n in names):
                out.append(f"{sc.name}:{ref}")
    return sorted(set(out))


def _check_i2c(sheets, lib, nets_by_name, res: DesignRuleResult) -> None:
    i2c_nets: dict[str, str] = {}
    for sc in sheets:
        c = sc.circuit
        for name, pt in c.port_types.items():
            if pt.kind == "i2c":
                i2c_nets.setdefault(name, sc.name)
    res.checked["i2c"] = len(i2c_nets)
    for net in sorted(i2c_nets):
        waived = None
        for _s, c, _n in nets_by_name.get(net, []):
            wv = _waivers(c, "pull_waivers").get(net)
            if wv is not None:
                waived = (c, wv)
                break
        if waived is not None:
            res.waived.append(f"I2C {net} (typed on {i2c_nets[net]}): "
                              f"{waived[1]}")
            continue
        pulls = _resistor_pulls_to_rail(sheets, lib, net)
        if not pulls:
            res.i2c.append(
                f"{net} (i2c, typed on {i2c_nets[net]}) has NO pull-up "
                f"resistor to any power rail anywhere on the board — an "
                f"open-drain I2C bus is dead without pull-ups; add a pull-up "
                f"or c.waive_pull({net!r}, reason)")


def _check_reset(sheets, lib, nets_by_name, res: DesignRuleResult) -> None:
    reset_nets: dict[str, str] = {}
    for sc in sheets:
        for net in sc.circuit.nets.values():
            if _RESET_NET_RE.search(net.name):
                reset_nets.setdefault(net.name, sc.name)
    res.checked["reset"] = len(reset_nets)
    for net in sorted(reset_nets):
        if any(rx.search(net) for rx in _RESET_INTERNAL_PULL):
            res.waived.append(
                f"RESET {net} (on {reset_nets[net]}): internal-pull whitelist "
                f"(part provides its own pull; external RC optional)")
            continue
        waived = None
        for _s, c, _n in nets_by_name.get(net, []):
            wv = _waivers(c, "reset_waivers").get(net)
            if wv is not None:
                waived = wv
                break
        if waived is not None:
            res.waived.append(f"RESET {net} (on {reset_nets[net]}): {waived}")
            continue
        cap = _cap_to_ground_anywhere(sheets, lib, net)
        pull = _resistor_on_net(sheets, lib, net)
        if not (cap and pull):
            miss = []
            if not cap:
                miss.append("no cap-to-GND")
            if not pull:
                miss.append("no pull resistor")
            have = []
            if cap:
                have.append(f"cap @ {', '.join(cap)}")
            if pull:
                have.append(f"pull @ {', '.join(pull)}")
            res.reset.append(
                f"{net} (reset, on {reset_nets[net]}) lacks a complete RC: "
                f"{'; '.join(miss)}"
                + (f" (has {'; '.join(have)})" if have else "")
                + f" — add the missing element or c.waive_reset({net!r}, reason)")


def _check_strap(sheets, lib, res: DesignRuleResult) -> None:
    n_checked = 0
    for sc in sheets:
        c = sc.circuit
        for ref in sorted(c.parts):
            part = c.parts[ref]
            if not _is_multipin_ic(lib, part):
                continue
            for p in _pins(lib, part):
                if not _CONFIG_PIN_RE.match(p.name):
                    continue
                n = c.net_of(PinRef(ref, p.number))
                if n is None:
                    continue
                if n.net_class in (NetClass.PORT, NetClass.POWER,
                                   NetClass.GROUND):
                    continue
                n_checked += 1
                driven = False
                for pr in n.pins:
                    if pr.ref == ref and pr.pin == p.number:
                        continue
                    op = c.parts.get(pr.ref)
                    if op is None:
                        continue
                    for q in _pins(lib, op):
                        if q.number == pr.pin and q.etype in _DRIVER_ETYPES:
                            driven = True
                if driven:
                    continue
                wv = _strap_waived(c, ref, p.number, p.name, n.name)
                if wv is not None:
                    res.waived.append(
                        f"STRAP {sc.name}:{ref}.{p.name} ({n.name}): {wv}")
                    continue
                others = sorted(str(pr) for pr in n.pins
                                if not (pr.ref == ref and pr.pin == p.number))
                res.strap.append(
                    f"{sc.name}:{ref}.{p.name} (pin {p.number}, {part.value}) "
                    f"is a config input on passive-only undriven net {n.name!r} "
                    f"(other pins: {others or 'none'}) — strap it to a rail/GND "
                    f"or drive it, or c.waive_strap({ref!r}, reason)")
    res.checked["strap"] = n_checked


def _check_ep(sheets, lib, res: DesignRuleResult) -> None:
    n_checked = 0
    for sc in sheets:
        c = sc.circuit
        for ref in sorted(c.parts):
            part = c.parts[ref]
            for p in _pins(lib, part):
                if not _EP_PIN_RE.match(p.name):
                    continue
                n_checked += 1
                n = c.net_of(PinRef(ref, p.number))
                if n is not None and _is_ground_name(n.name):
                    continue
                wv = _ep_waived(c, ref, p.number, p.name,
                                n.name if n is not None else None)
                if wv is not None:
                    where = n.name if n is not None else "unconnected"
                    res.waived.append(
                        f"EP {sc.name}:{ref}.{p.name} ({where}): {wv}")
                    continue
                if n is None:
                    res.ep.append(
                        f"{sc.name}:{ref}.{p.name} (pin {p.number}, "
                        f"{part.value}) exposed pad is UNCONNECTED (nc/floating) "
                        f"— net it to GND, or c.waive_ep({ref!r}, reason)")
                else:
                    res.ep.append(
                        f"{sc.name}:{ref}.{p.name} (pin {p.number}, "
                        f"{part.value}) exposed pad is on non-GROUND net "
                        f"{n.name!r} — net it to GND, or "
                        f"c.waive_ep({ref!r}, reason)")
    res.checked["ep"] = n_checked


def run(sheets, reports_dir: Path | None = None,
        lib=None) -> DesignRuleResult:
    if lib is None:
        from schgen.core.symbols import Library
        lib = Library()
    res = check(sheets, lib)
    if reports_dir is not None:
        reports_dir.mkdir(parents=True, exist_ok=True)
        (reports_dir / "design_rules.txt").write_text(res.report() + "\n")
    return res


def cmd_design_rules(args) -> int:
    from schgen.core.link import all_subsystem_paths, load_subsystem
    from schgen.core.symbols import Library
    names = args.subsystems or [p.stem for p in all_subsystem_paths()]
    sheets = [load_subsystem(n) for n in names]
    lib = Library()
    repo = Path(__file__).resolve().parents[2]
    res = run(sheets, repo / "carrier" / "reports", lib=lib)
    print(res.report())
    print(f"\nreport: {repo / 'carrier' / 'reports' / 'design_rules.txt'}")
    return 0 if res.ok else 1
