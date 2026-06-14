"""DESIGN-RULE COMPLETENESS gate (verification P1): is the declared netlist
electrically COMPLETE, not merely self-consistent?

The netlist gate (schgen/verify/netlist_gate.py) proves the *drawing* matches
the declared :class:`~schgen.model.Circuit`, pin for pin. NOTHING proves the
netlist itself is electrically complete: a chip whose VDD has no bypass cap, an
I2C bus with no pull-ups, a reset with no RC, a strap left floating all pass
the netlist gate, ERC, and the zero-overlap visual gate untouched — and because
every emitted pin etype on this board is the flat EasyEDA default ``passive``,
KiCad's ERC cannot even SEE a power pin to complain. This gate closes that
silent-pass blind spot.

It reads ONLY the model (parts, nets, port types, library pin tables) — never
geometry — and infers each pin's FUNCTION from its NAME (the etype is
unreliable), via regex on the library's own pin table (``lib.get(lib_id).pins``
gives ``(number, name, etype)`` for every part, inline or use_part alike). It is
deterministic: same model in, same report out, no timestamps, sheets and pins
sorted.

Four rules, every one with an EXPLICIT author waiver (a waiver is documentation,
never silence — the report lists every waiver verbatim):

  DECAP   every multi-pin IC (>2 distinct pin numbers, not a bare R/C/L) must
          carry, for each POWER-NAMED pin's net, at least one capacitor
          (``lib_id`` ending ``:C``) from that net to a GROUND-class net,
          declared on the SAME sheet.  Waiver: ``c.waive_decap(ref_or_pin, reason)``.

  I2C     every I2C-typed bus net (a PORT whose ``PortType.kind == 'i2c'``) must
          have a pull-up resistor to a POWER rail somewhere ACROSS the board.
          Waiver: ``c.waive_pull(net, reason)``.

  RESET   every net whose name matches reset/NRST/RST/SRST (minus an
          internal-pull whitelist) must carry BOTH a cap-to-GROUND and a pull
          resistor (the classic RC reset); a net missing either is flagged.
          Waiver: ``c.waive_reset(net, reason)``.

  STRAP   a config-input-named pin (nOE/OE/MODE/ADDR/Ax/SEL/CFG/STRAP/...) that
          is NOT a typed PORT and sits on a passive-only, undriven net is
          flagged as a floating control input (P7).  Waiver:
          ``c.waive_strap(ref_or_pin, reason)``.

LAW 4: the gate stays strict. A real exception is WAIVED (the author signs it
with a reason the report prints), never relaxed. Run standalone with
``python -m schgen design-rules`` (see ``cmd_design_rules``) or hook
``run(sheets)`` into ``cmd_board``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from schgen.model import NetClass, PinRef

# ---- pin-function inference (by NAME — etype on this board is flat 'passive') --

# GROUND-class pin/net names. VSS family included so a 'VSS' power-named pin is
# never mistaken for a supply that needs its own decap.
_GROUND_RE = re.compile(
    r"^(GND|GNDA|GNDD|GNDPWR|AGND|DGND|PGND|VSS|VSSA|VSSIO|CHASSIS_GND)",
    re.IGNORECASE)

# POWER-supply pin names (longest-prefix set). VOUT* is EXCLUDED (it is an
# output rail the part SOURCES, not a supply input that needs local bypass);
# VSS* is excluded as ground. Matched as: exact, or prefix followed by a digit
# or '_' (so VDD1 / VCC_3V3 / VDDIO2 all match, but 'VLAN' never matches via the
# VL prefix because a bare trailing letter does not extend the match).
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
    """True if a pin NAME denotes a supply INPUT that needs local decoupling.

    Ground names and output rails (VOUT*) are excluded. A power prefix only
    matches when it is the whole name or is followed by a digit/underscore, so
    'VS' matches VS / VS1 / VS_3V3 but a hypothetical 'VSENSE' matches via the
    VS prefix too (conservative: better to require a decap and let the author
    waive a true sense pin than to silently miss a supply)."""
    if not name:
        return False
    up = name.upper()
    if _is_ground_name(up):
        return False
    if up.startswith("VOUT") or up.startswith("VO_"):
        return False
    for pre in _POWER_PIN_PREFIXES:
        # whole name, or prefix followed by a digit / '_' continuation. The
        # full family spellings (VDDA, VDDD, VDDIO, VCCB, VCC5V, ...) are
        # already explicit prefixes, so a bare trailing LETTER must NOT extend
        # a match (that wrongly caught e.g. 'VLAN' via the VL prefix).
        if up == pre or (up.startswith(pre)
                         and (up[len(pre):][:1].isdigit()
                              or up[len(pre):][:1] == "_")):
            return True
    return False


# config / strap INPUT pin names (P7 floating-control audit). NOT a switching
# 'BOOT' bootstrap pin (that is a buck bootstrap cap node, not a config strap),
# and NOT 'EN'/enable (enables are gated/driven control, audited elsewhere).
_CONFIG_PIN_RE = re.compile(
    r"^(nOE|OE|nCS|CS|nCE|CE|MODE\d*|ADDR\d*|A\d{1,2}|SEL\d*|CFG\d*|"
    r"STRAP\d*|CONFIG\d*|SET|S\d|POL)$",
    re.IGNORECASE)

# RESET net names. Matches NRST / RST_N / SRST / nRESET / *_RESET etc. The bare
# token must stand alone or be bounded by a separator/polarity letter so a net
# like 'WRST_BURST' or 'FIRST' never matches.
_RESET_NET_RE = re.compile(
    r"(^|_)(N?RST|N?RESET|SRST|POR)(_?N|_?B|_|$)",
    re.IGNORECASE)

# Reset nets with a part-internal pull (no external RC required by design).
# The author still gets a per-net waiver; this whitelist suppresses the noise
# for the well-known internal-pull silicon families.
_RESET_INTERNAL_PULL = (
    re.compile(r"STM32.*NRST", re.IGNORECASE),    # STM32 NRST: internal ~40k pull-up
)

# Exposed/thermal-pad pin NAMES (the part's heat-spreader pad). An EP must be a
# real netted pad on a GROUND net — never floating (nc) and never on a non-GND
# net — or explicitly waived. validate() already forbids a floating pin; this
# rule additionally forbids an EP that is nc'd or netted to a non-GND net (the
# silent LAW-0 holes neither validate() nor KiCad ERC can see). Anchored to the
# whole pin name so a signal like 'PADDR'/'EPHY' never trips it.
_EP_PIN_RE = re.compile(
    r"^(EP\d*|E?PAD\d*|PPAD|THERMAL.*|GND_?PAD|DAP)$",
    re.IGNORECASE)

# KiCad etypes that DRIVE a net (so a config input on such a net is not floating).
_DRIVER_ETYPES = frozenset({
    "output", "bidirectional", "tri_state",
    "power_out", "open_collector", "open_emitter",
})

# library lib_id suffixes that are bare passives (never an "IC")
_BARE_PASSIVE_SUFFIX = (":R", ":C", ":L")
_CAP_SUFFIX = ":C"
_RES_SUFFIX = ":R"


# ---- result -------------------------------------------------------------------

@dataclass
class DesignRuleResult:
    decap: list[str] = field(default_factory=list)        # missing-bypass findings
    i2c: list[str] = field(default_factory=list)          # I2C-no-pullup findings
    reset: list[str] = field(default_factory=list)        # reset-RC findings
    strap: list[str] = field(default_factory=list)        # floating-strap findings
    ep: list[str] = field(default_factory=list)           # exposed-pad-not-GND findings
    waived: list[str] = field(default_factory=list)       # verbatim waivers honoured
    checked: dict[str, int] = field(default_factory=dict)  # rule -> # of subjects

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


# ---- waiver access (model-side dicts; tolerated absent) ------------------------
# The author-facing waiver API lives on Circuit (model.py) — see this module's
# waiver_mechanism note. Each is a dict the gate reads; getattr keeps the gate
# importable BEFORE model.py grows the methods (it simply finds zero waivers).

def _waivers(c, attr: str) -> dict:
    d = getattr(c, attr, None)
    return d if isinstance(d, dict) else {}


def _decap_waived(c, ref: str, pin_num: str, net: str) -> str | None:
    """A DECAP waiver may key on the part ref ('U1'), a specific pin
    ('U1.3'), or the rail net ('+3V3'). Returns the reason if any match."""
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
    """An EP waiver may key on 'ref.pin', 'ref.NAME', the part ref, or the net
    the pad sits on. Returns the reason if any match."""
    w = _waivers(c, "ep_waivers")
    for key in (f"{ref}.{pin_num}", f"{ref}.{pin_name}", ref, net):
        if key and key in w:
            return w[key]
    return None


# ---- library helpers ----------------------------------------------------------

def _pins(lib, part):
    """The (number, name, etype) pin table for a part via the symbol library;
    [] if the symbol cannot be resolved (the part is then skipped, never
    silently passed — an unresolved symbol fails the build's own gates)."""
    try:
        return lib.get(part.lib_id).pins
    except Exception:        # noqa: BLE001 — unresolved symbol: skip cleanly
        return []


def _is_multipin_ic(lib, part) -> bool:
    if part.lib_id.endswith(_BARE_PASSIVE_SUFFIX):
        return False
    nums = {p.number for p in _pins(lib, part)}
    return len(nums) > 2


# ---- the engine ---------------------------------------------------------------

def check(sheets, lib) -> DesignRuleResult:
    """Run all four rules over the loaded board sheets.

    ``sheets`` is the linker's list of SheetCircuit (each ``.name`` /
    ``.circuit``); ``lib`` is a ``schgen.symbols.Library``."""
    res = DesignRuleResult()

    # board-wide index: net name -> list of (sheet, circuit, Net)
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
    """rail-net-name -> [(cap_ref, value), ...] for every 2-terminal cap on this
    sheet bridging that rail to a GROUND-class net. A cap counts as decoupling
    ONLY when one side is the rail and the OTHER side is a ground net."""
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
            # group supply pins by NAME so stacked VDD pads report once. A pin
            # is a supply if its NAME is a power-rail name OR the symbol itself
            # types it power_in (the name table misses families like CP2102N
            # VIO/VREGIN — the etype on this board is NOT uniformly 'passive').
            # GROUND-named power_in pins (VSS family) are excluded below.
            supply: dict[str, list[str]] = {}
            for p in _pins(lib, part):
                if is_power_pin_name(p.name) or (
                        p.etype == "power_in" and not _is_ground_name(p.name)):
                    supply.setdefault(p.name, []).append(p.number)
            for pin_name in sorted(supply):
                pnums = sorted(supply[pin_name])
                # the rail(s) actually on these pins
                rails: dict[str, list[str]] = {}
                for pn in pnums:
                    rn = _net_name_of(c, ref, pn)
                    rails.setdefault(rn or "<unconnected>", []).append(pn)
                for rail in sorted(rails):
                    if rail == "<unconnected>" or _is_ground_name(rail):
                        # an NC/ground-tied supply pin needs no bypass
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
    """Board-wide: [(sheet:ref -> rail)] for every resistor with one pin on
    ``net_name`` and the OTHER pin on a POWER rail. A pull-up (to a supply) and
    a pull-down (to ground) are both resistor ties; for I2C we want a PULL-UP,
    i.e. the other end is a POWER net specifically."""
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
    """Board-wide [sheet:ref] for any resistor with a pin on ``net_name``
    (pull-up OR pull-down — used by the RESET rule, where a pull-down to GND is
    a legitimate held-reset)."""
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
    """Board-wide [sheet:ref] for any cap bridging ``net_name`` to a GROUND net."""
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
    # collect i2c-typed PORT nets (board-wide, by name)
    i2c_nets: dict[str, str] = {}        # net -> first sheet that typed it
    for sc in sheets:
        c = sc.circuit
        for name, pt in c.port_types.items():
            if pt.kind == "i2c":
                i2c_nets.setdefault(name, sc.name)
    res.checked["i2c"] = len(i2c_nets)
    for net in sorted(i2c_nets):
        # waiver may sit on ANY sheet that declares the net
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
    reset_nets: dict[str, str] = {}      # net -> first sheet it appears on
    for sc in sheets:
        for net in sc.circuit.nets.values():
            if _RESET_NET_RE.search(net.name):
                reset_nets.setdefault(net.name, sc.name)
    res.checked["reset"] = len(reset_nets)
    for net in sorted(reset_nets):
        # internal-pull whitelist
        if any(rx.search(net) for rx in _RESET_INTERNAL_PULL):
            # whitelisted parts self-pull; suppress the finding but log it as a
            # waiver so the suppression is visible, never silent.
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
                    continue        # NC or unassigned (model gate owns that)
                # a typed PORT, a POWER rail or a GROUND tie is, by definition,
                # NOT floating — it is strapped / externally bound
                if n.net_class in (NetClass.PORT, NetClass.POWER,
                                   NetClass.GROUND):
                    continue
                n_checked += 1
                # other pins on the net: any driver-class etype?
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
    """Every exposed/thermal pad (EP/PAD/...) must be a real netted pad on a
    GROUND net — the LAW-0 'an EP is a pad+pin+GND net, never a prose layout
    note' rule. validate() already forbids a floating pin; this additionally
    forbids an EP that is nc'd (net is None here) or netted to a NON-GROUND net.
    A pad deliberately on a non-GND heat-spreader island, or left unconnected,
    is waived (waive_ep), never relaxed (LAW 4)."""
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
                    continue                          # netted to GND — correct
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


# ---- entry points -------------------------------------------------------------

def run(sheets, reports_dir: Path | None = None,
        lib=None) -> DesignRuleResult:
    """Gate entry point: run the four rules, optionally write the verdict
    report to ``reports_dir/design_rules.txt`` (deterministic, no timestamp)."""
    if lib is None:
        from schgen.symbols import Library
        lib = Library()
    res = check(sheets, lib)
    if reports_dir is not None:
        reports_dir.mkdir(parents=True, exist_ok=True)
        (reports_dir / "design_rules.txt").write_text(res.report() + "\n")
    return res


def cmd_design_rules(args) -> int:
    """Standalone CLI: ``python -m schgen design-rules [subsystems...]``."""
    from schgen.link import all_subsystem_paths, load_subsystem
    from schgen.symbols import Library
    names = args.subsystems or [p.stem for p in all_subsystem_paths()]
    sheets = [load_subsystem(n) for n in names]
    lib = Library()
    repo = Path(__file__).resolve().parents[2]
    res = run(sheets, repo / "carrier" / "reports", lib=lib)
    print(res.report())
    print(f"\nreport: {repo / 'carrier' / 'reports' / 'design_rules.txt'}")
    return 0 if res.ok else 1