"""schgen netlist model — the single source of electrical truth.

A subsystem ``.py`` builds a :class:`Circuit`: every part and every pin→net
assignment is EXPLICIT. The generator's only job is to draw this netlist;
the netlist gate proves (via kicad-cli's own export) that it did, exactly.

Design rules encoded here (lessons from the failed generator):
- No geometry in this module. Electrical truth never depends on coordinates.
- Every pin of every part must be assigned: to a Net or to NC (an explicit,
  author-declared no-connect). An unassigned pin is a BUILD ERROR — silence
  is how pins were lost before.
- NC is an authoring decision, never a layout fallback. The netlist gate
  fails any emitted No-Connect whose pin has a declared net.
"""

from __future__ import annotations

import enum
import re
from dataclasses import dataclass, field, replace


class NetClass(enum.Enum):
    POWER = "power"      # +3V3, +VIN, … → power symbol at each pin
    GROUND = "ground"    # GND family → GND symbol at each pin
    SIGNAL = "signal"    # internal wired net
    PORT = "port"        # external interface → hier label at sheet edge


_GROUND_RE = re.compile(r"^(GND|GNDA|GNDD|GNDPWR|AGND|DGND|PGND|VSS|CHASSIS_GND)")
_POWER_RE = re.compile(r"^\+|^VBUS$|^VDD|^VCC")

# ---- typed ports --------------------------------------------------------------
# A PORT net may optionally carry a PortType: layout-relevant electrical intent
# (impedance class, pairing, bus grouping, signaling level). The linker
# (schgen/link.py) and the constraints exporter (schgen/constraints.py) consume
# these; untyped ports default to kind "single" and keep working unchanged.

PORT_KINDS = frozenset({
    "single",        # plain signal (default)
    "diff_pair",     # generic differential pair (explicit impedance)
    "usb_hs_pair",   # USB 2.0 high-speed D+/D- (90R differential)
    "tmds_pair",     # HDMI/DVI TMDS lane (100R differential)
    "i2c",           # i2c bus member (role scl/sda, bus group, speed)
    "sd_bus",        # SD/SDIO bus member (signaling level_v, bus group)
})
_PAIR_KINDS = frozenset({"diff_pair", "usb_hs_pair", "tmds_pair"})
_DEFAULT_IMPEDANCE = {"usb_hs_pair": 90, "tmds_pair": 100}

# polarity inference for pair nets, by UPPERCASE name suffix (longest first).
_POLARITY_SUFFIXES: tuple[tuple[str, str], ...] = (
    ("_DP", "P"), ("_DM", "N"), ("_DN", "N"),
    ("DP", "P"), ("DM", "N"), ("DN", "N"),
    ("_P", "P"), ("_N", "N"),
    ("D+", "P"), ("D-", "N"),
    ("+", "P"), ("-", "N"),
    ("P", "P"), ("N", "N"),
)


def pair_polarity(name: str) -> str | None:
    """Infer 'P'/'N' from a net name's suffix; None if not inferable."""
    up = name.upper()
    for suffix, pol in _POLARITY_SUFFIXES:
        if up.endswith(suffix):
            return pol
    return None


@dataclass(frozen=True)
class PortType:
    kind: str = "single"
    pair_with: str | None = None     # complement net (pair kinds)
    impedance: int | None = None     # differential impedance, ohms (pair kinds)
    role: str | None = None          # i2c: "scl" | "sda"
    bus: str | None = None           # bus/group name (i2c, sd_bus)
    speed_hz: int | None = None      # i2c bus speed
    level_v: float | None = None     # sd_bus signaling level (volts)
    expect: str | None = None        # EXPLICIT deferral: name of the future
    #                                  subsystem expected to bind this port.
    #                                  The linker downgrades "resolves nowhere"
    #                                  to a WARNING for expect-marked ports —
    #                                  never silently, always author-declared.


@dataclass(frozen=True)
class PinRef:
    """One pin of one part: the atom of connectivity."""
    ref: str          # part reference, e.g. "U1"
    pin: str          # pin NUMBER as string, e.g. "4" / "A5" / "EP"

    def __str__(self) -> str:
        return f"{self.ref}.{self.pin}"


@dataclass
class Part:
    ref: str                       # "U1", "C3", "R7", "J2"
    lib_id: str                    # "schgen_local:FUSB302B" etc.
    value: str                     # "FUSB302BMPX", "100n", "4k7"
    footprint: str = ""
    fields: dict[str, str] = field(default_factory=dict)
    # authoring v2 (use_part): pin NAME -> [pin numbers] from the part's
    # generated pin table; "U1.SDA" resolves through this. Empty for parts
    # declared with inline lib ids.
    pin_names: dict[str, list[str]] = field(default_factory=dict)
    pin_numbers: frozenset[str] = frozenset()


@dataclass
class Net:
    name: str
    net_class: NetClass
    pins: list[PinRef] = field(default_factory=list)


class CircuitError(ValueError):
    pass


class PartitionError(CircuitError):
    """A page partition would CUT a SIGNAL net across pages (a LAW-0 OPEN).

    Raised by Circuit.subset() — the single, non-suppressible chokepoint that
    proves the auto-paginator (place.partition_pages) only ever cuts merging
    nets (POWER/GROUND/PORT). Distinct from a routine 'won't fit' so the board
    flow can tell an internal partitioner bug from an honest infeasible page."""


# Standard SMD passive footprints, used to default an inline Device:C /
# Device:R that omits a footprint (DEF-3). A bare footprint='' is un-orderable
# — JLC cannot place it — yet several inline decouple()/part() passives relied
# on that empty default. Bulk caps (>= 1 uF) land on 0805, everything else on
# 0603; this matches the JLC Basic packages of every inline passive in the
# board (100n/200p 0603, 10u 0805, 1k/22k1/47k5 0603). Non-passive libs keep ''
# (use_part always supplies the library footprint).
_R_FP_0603 = "Resistor_SMD:R_0603_1608Metric"
_C_FP_0603 = "Capacitor_SMD:C_0603_1608Metric"
_C_FP_0805 = "Capacitor_SMD:C_0805_2012Metric"


def _passive_uF(value: str) -> float | None:
    """Capacitance in microfarads from a value like '100n', '10u', '200p'."""
    m = re.fullmatch(r"\s*([0-9.]+)\s*([pnu]?)F?\s*", value or "")
    if not m:
        return None
    return float(m.group(1)) * {"p": 1e-6, "n": 1e-3, "u": 1.0, "": 1.0}[m.group(2)]


def _default_footprint(lib_id: str, value: str) -> str:
    if lib_id == "Device:R":
        return _R_FP_0603
    if lib_id == "Device:C":
        uF = _passive_uF(value)
        return _C_FP_0805 if (uF is not None and uF >= 1.0) else _C_FP_0603
    return ""


class Circuit:
    """Builder + container for one subsystem's complete netlist."""

    def __init__(self, name: str, title: str = "") -> None:
        self.name = name
        self.title = title or name
        self.parts: dict[str, Part] = {}
        self.nets: dict[str, Net] = {}
        self.nc_pins: set[PinRef] = set()      # author-declared no-connects
        self.port_types: dict[str, PortType] = {}   # PORT net -> PortType
        self.hints: dict[str, str] = {}        # net -> declarative style hint
        # power-tree budget declarations: rail -> [(amps, note), ...]
        self.loads: dict[str, list[tuple[float, str]]] = {}
        # test-point coverage waivers: net -> reason (gate lists them)
        self.tp_waivers: dict[str, str] = {}
        # design-rule completeness waivers (schgen/verify/design_rules.py)
        self.decap_waivers: dict[str, str] = {}   # ref | "ref.pin" | rail -> reason
        self.pull_waivers: dict[str, str] = {}    # i2c net -> reason
        self.reset_waivers: dict[str, str] = {}   # reset net -> reason
        self.strap_waivers: dict[str, str] = {}   # ref | "ref.pin" | net -> reason
        self.ep_waivers: dict[str, str] = {}      # ref | "ref.pin" | net -> reason
        # per-device thermal (Tj) gate waivers (schgen/thermal.py): ref -> reason
        self.thermal_waivers: dict[str, str] = {}
        # per-part rule-engine waivers (schgen/verify/part_rules.py): ref -> reason
        self.part_rule_waivers: dict[str, str] = {}
        self._ref_counters: dict[str, int] = {}
        # Lazy symbol library + per-lib_id pin-number cache, used ONLY to
        # validate inline-part (``part()``) pin references eagerly in
        # _expand_pin (F9), matching use_part's eager check. Import is
        # deferred so the model module stays pure at import time; symbols
        # does not import model, so there is no cycle.
        self._lib = None
        self._inline_pins: dict[str, frozenset[str]] = {}

    # ---- parts -------------------------------------------------------------
    def part(self, ref: str, lib_id: str, value: str, footprint: str = "",
             **fields: str) -> Part:
        if ref in self.parts:
            raise CircuitError(f"duplicate reference {ref!r}")
        if not footprint:
            footprint = _default_footprint(lib_id, value)   # DEF-3
        p = Part(ref=ref, lib_id=lib_id, value=value, footprint=footprint,
                 fields=dict(fields))
        self.parts[ref] = p
        return p

    def use_part(self, mpn: str, ref: str | None = None, *,
                 value: str | None = None, lcsc: str | None = None,
                 lib_id: str | None = None,
                 footprint: str | None = None) -> Part:
        """Library-first part (authoring v2): lib_id, footprint, LCSC,
        reference prefix and the NAMED pin table all come from
        ``parts/<MPN>/<MPN>.py`` — inline metadata is illegal for generated
        parts. A missing folder is a build error carrying the exact fix.

        EXPLICIT OVERRIDE form (``lib_id=`` / ``footprint=``): a sheet that
        deliberately draws a DIFFERENT symbol than the generated one (a
        stock KiCad drawing, a re-pinned local copy) keeps that exact
        drawing while still sourcing its orderable identity from parts/ —
        the part carries hidden MPN + Datasheet fields (LCSC as always) so
        MPN/LCSC/datasheet can never drift from the library folder. Because
        an override symbol's pin numbering owes nothing to the generated
        pin table, pin-by-NAME is disabled when ``lib_id`` is overridden:
        pins are authored by NUMBER and validated against the actual symbol
        by the build's completeness check."""
        import importlib.util as _ilu
        from pathlib import Path as _P
        safe = re.sub(r"[^A-Za-z0-9._-]+", "_", mpn).strip("_")
        parts_dir = _P(__file__).resolve().parents[2] / "parts"
        meta = parts_dir / safe / f"{safe}.py"
        if not meta.exists():
            raise CircuitError(
                f"use_part({mpn!r}): parts/{safe}/ is missing — generate it "
                f"with:  schgen part add {lcsc or 'C<LCSC-id>'} --name {safe}")
        spec = _ilu.spec_from_file_location(f"_part_{safe}", meta)
        mod = _ilu.module_from_spec(spec)
        spec.loader.exec_module(mod)          # type: ignore[union-attr]
        if ref is None:
            ref = self.auto_ref((getattr(mod, "PREFIX", "U") or "U"))
        fields = {"LCSC": getattr(mod, "LCSC", "") or (lcsc or "")}
        if lib_id is not None:
            fields["MPN"] = mod.MPN
            if getattr(mod, "DATASHEET", ""):
                fields["Datasheet"] = mod.DATASHEET
        p = self.part(ref, lib_id or mod.LIB_ID, value or mod.MPN,
                      footprint or mod.FOOTPRINT, **fields)
        if lib_id is None:
            names: dict[str, list[str]] = {}
            nums: set[str] = set()
            for num, name, _et in mod.PINS:
                nums.add(str(num))
                names.setdefault(str(name), []).append(str(num))
            p.pin_names = names
            p.pin_numbers = frozenset(nums)
        return p

    def auto_ref(self, prefix: str) -> str:
        """Next free reference for ``prefix`` ('C' → 'C1', 'C2', …)."""
        n = self._ref_counters.get(prefix, 0) + 1
        while f"{prefix}{n}" in self.parts:
            n += 1
        self._ref_counters[prefix] = n
        return f"{prefix}{n}"

    # ---- nets ---------------------------------------------------------------
    @staticmethod
    def classify(name: str) -> NetClass:
        if _GROUND_RE.match(name):
            return NetClass.GROUND
        if _POWER_RE.match(name):
            return NetClass.POWER
        return NetClass.SIGNAL

    def net(self, name: str, *pins: PinRef | str,
            net_class: NetClass | None = None) -> Net:
        """Declare/extend a net. Pins as PinRef or 'U1.4' strings."""
        nc = net_class or self.classify(name)
        n = self.nets.get(name)
        if n is None:
            n = Net(name=name, net_class=nc)
            self.nets[name] = n
        elif net_class is not None and n.net_class != net_class:
            raise CircuitError(
                f"net {name!r} reclassified {n.net_class}->{net_class}")
        for p in pins:
            for pr in self._expand_pin(p):
                if pr in self.nc_pins:
                    raise CircuitError(
                        f"{pr} is declared NC but assigned to {name!r}")
                existing = self.net_of(pr)
                if existing is not None and existing.name != name:
                    raise CircuitError(
                        f"{pr} already on net {existing.name!r}, "
                        f"cannot also join {name!r}")
                if pr not in n.pins:
                    n.pins.append(pr)
        return n

    def port(self, name: str, *pins: PinRef | str,
             kind: str | None = None, **type_kwargs) -> Net:
        """An external-interface net (hier label at the sheet edge).

        Optional typing: ``kind=`` plus :class:`PortType` kwargs (``pair_with``,
        ``impedance``, ``role``, ``bus``, ``speed_hz``, ``level_v``,
        ``expect``) forward to :meth:`port_type`. Untyped ports stay exactly
        as before (default kind "single").
        """
        n = self.net(name, *pins, net_class=NetClass.PORT)
        if kind is not None or type_kwargs:
            self.port_type(name, kind=kind or "single", **type_kwargs)
        return n

    def port_type(self, net: str, kind: str = "single", *,
                  pair_with: str | None = None,
                  impedance: int | None = None,
                  role: str | None = None,
                  bus: str | None = None,
                  speed_hz: int | None = None,
                  level_v: float | None = None,
                  expect: str | None = None) -> PortType:
        """Attach layout/electrical intent to an already-declared PORT net.

        Pair kinds (diff_pair / usb_hs_pair / tmds_pair) require ``pair_with``
        (the complement net, which must already be a PORT); the reciprocal
        type is registered on the complement automatically. ``diff_pair``
        requires an explicit ``impedance``; usb_hs_pair defaults to 90R and
        tmds_pair to 100R. i2c requires ``role`` ("scl"/"sda"); sd_bus
        requires ``level_v``.
        """
        if kind not in PORT_KINDS:
            raise CircuitError(f"port_type({net!r}): unknown kind {kind!r} "
                               f"(known: {sorted(PORT_KINDS)})")
        n = self.nets.get(net)
        if n is None or n.net_class != NetClass.PORT:
            raise CircuitError(f"port_type({net!r}): not a declared PORT net")
        if kind in _PAIR_KINDS:
            if pair_with is None:
                raise CircuitError(f"port_type({net!r}): {kind} needs pair_with=")
            comp = self.nets.get(pair_with)
            if comp is None or comp.net_class != NetClass.PORT:
                raise CircuitError(
                    f"port_type({net!r}): pair_with {pair_with!r} is not a "
                    f"declared PORT net")
            if impedance is None:
                impedance = _DEFAULT_IMPEDANCE.get(kind)
            if impedance is None:
                raise CircuitError(
                    f"port_type({net!r}): diff_pair needs explicit impedance=")
        elif pair_with is not None:
            raise CircuitError(f"port_type({net!r}): pair_with only valid for "
                               f"pair kinds, not {kind!r}")
        if kind == "i2c":
            if role not in ("scl", "sda"):
                raise CircuitError(
                    f"port_type({net!r}): i2c needs role='scl' or 'sda'")
        elif role is not None:
            raise CircuitError(f"port_type({net!r}): role only valid for i2c")
        if kind == "sd_bus" and level_v is None:
            raise CircuitError(f"port_type({net!r}): sd_bus needs level_v=")
        pt = PortType(kind=kind, pair_with=pair_with, impedance=impedance,
                      role=role, bus=bus, speed_hz=speed_hz, level_v=level_v,
                      expect=expect)
        prev = self.port_types.get(net)
        if prev is not None and prev != pt:
            raise CircuitError(
                f"port_type({net!r}): retyped {prev} -> {pt} (conflict)")
        self.port_types[net] = pt
        if kind in _PAIR_KINDS and pair_with is not None:
            recip = PortType(kind=kind, pair_with=net, impedance=impedance,
                             bus=bus, expect=expect)
            comp_prev = self.port_types.get(pair_with)
            if comp_prev is None:
                self.port_types[pair_with] = recip
            elif comp_prev != recip:
                raise CircuitError(
                    f"port_type({net!r}): complement {pair_with!r} already "
                    f"typed {comp_prev}, conflicts with {recip}")
        return pt

    def port_type_of(self, net: str) -> PortType:
        """The PortType for a PORT net; untyped ports read as 'single'."""
        return self.port_types.get(net, PortType())

    # ---- abstract-port binding (reusable-subsystem contract) ----------------
    def bind(self, mapping: dict[str, str]) -> "Circuit":
        """Rename this circuit's externally-visible net names IN PLACE.

        This is the binding half of the reusable-subsystem contract: a
        project-agnostic ``subsystems/<name>/`` library declares its interface
        with ABSTRACT net names (no carrier net names, no nets.py reads), and a
        consuming project supplies ``{abstract_name: project_net}`` to rebind
        every externally-visible net (POWER / GROUND / PORT — rails + ports) to
        its real board names. Standalone (no bind) the circuit keeps its
        abstract names, so the package's own ``test_<name>.py`` runs offline.

        ONLY externally-visible nets are bindable: POWER, GROUND and PORT nets
        are the subsystem's edge (rails it consumes + ports it exposes). A
        SIGNAL net is the subsystem's PRIVATE wiring and is NEVER renamed —
        binding one would be a meaningless (and dangerous) reach into internals,
        so a SIGNAL key in ``mapping`` is a hard error. An abstract name not
        present on this circuit is also a hard error (a typo'd binding must not
        pass silently). A binding is allowed to be the identity (abstract ==
        real) and a project may bind a subset (unbound externals keep their
        abstract name).

        BYTE-IDENTICAL guarantee: the rename is in place and order-preserving —
        the ``nets`` dict is rebuilt with the new keys in the SAME insertion
        order, and ``port_types`` / ``loads`` keys follow. Parts, refs, NCs,
        pins, port-type payloads and draw budgets are untouched. So if a
        project binds the abstract names to the exact net names the old hand-
        written subsystem used, the emitted sheet is byte-for-byte the same.

        Renames must not COLLIDE: two abstract names may not bind to one real
        name unless they were already the same net (that would silently merge
        two distinct nets — a LAW-0 short). Returns ``self`` for chaining.
        """
        for abstract, real in mapping.items():
            net = self.nets.get(abstract)
            if net is None:
                raise CircuitError(
                    f"bind: {abstract!r} is not a net on circuit "
                    f"{self.name!r} (externals: "
                    f"{sorted(self._bindable_names())})")
            if net.net_class is NetClass.SIGNAL:
                raise CircuitError(
                    f"bind: {abstract!r} is a private SIGNAL net — only "
                    f"POWER/GROUND/PORT (rail/port) externals are bindable; a "
                    f"subsystem's internal wiring is never rebound")
        # collision check: distinct source nets must not land on one target.
        for target in set(mapping.values()):
            srcs = [a for a, r in mapping.items() if r == target]
            if len(srcs) > 1:
                raise CircuitError(
                    f"bind: {sorted(srcs)} all bind to {target!r} — distinct "
                    f"externals cannot merge onto one net (LAW-0 short)")
            # also reject binding ONTO an existing un-renamed net of a
            # different name (would merge with that net at link time)
            if target in self.nets and target not in mapping and \
                    target != srcs[0]:
                raise CircuitError(
                    f"bind: {srcs[0]!r} -> {target!r} collides with the "
                    f"existing net {target!r} on this circuit")
        rename = {a: r for a, r in mapping.items() if a != r}
        if not rename:
            return self
        # rebuild nets in the SAME order with renamed keys (byte-identical emit)
        new_nets: dict[str, Net] = {}
        for name, net in self.nets.items():
            nn = rename.get(name, name)
            net.name = nn
            new_nets[nn] = net
        self.nets = new_nets
        # port_types: rename the keys AND the pair_with PAYLOAD — a diff/usb_hs/
        # tmds pair stores its complement as a net NAME, so binding one half of a
        # pair must follow the complement too, else the pair's two ends disagree
        # (the sheet stays byte-identical but the SI/XDC/constraints artifacts
        # key pairs on pair_with and would drift / report a half-bound pair).
        self.port_types = {
            rename.get(k, k): (replace(v, pair_with=rename[v.pair_with])
                               if v.pair_with in rename else v)
            for k, v in self.port_types.items()}
        self.loads = {rename.get(k, k): v for k, v in self.loads.items()}
        self.hints = {rename.get(k, k): v for k, v in self.hints.items()}
        # waiver dicts may key on a net name (decap/pull/reset/strap/ep/tp)
        for attr in ("tp_waivers", "decap_waivers", "pull_waivers",
                     "reset_waivers", "strap_waivers", "ep_waivers"):
            d = getattr(self, attr)
            setattr(self, attr, {rename.get(k, k): v for k, v in d.items()})
        # TestPoint / MountingHole parts carry the probed net NAME as their
        # value (a display convention) — rebind it too, else a probe/hole on a
        # renamed external would keep the abstract name in the render and break
        # byte-identicality (LAW 0: the value text is on the sheet).
        for p in self.parts.values():
            if p.lib_id in (self.TP_LIB_ID, self.MH_LIB_ID) \
                    and p.value in rename:
                p.value = rename[p.value]
        return self

    def _bindable_names(self) -> list[str]:
        """The externally-visible net names a project may bind (POWER/GROUND/
        PORT) — the subsystem's declared abstract interface."""
        return [n.name for n in self.nets.values()
                if n.net_class is not NetClass.SIGNAL]

    HINT_STYLES = frozenset({"trunk"})

    def hint(self, net: str, style: str) -> None:
        """Declarative layout hint: a net NAME and a STYLE keyword, nothing
        else — never coordinates, never wire plans, never text positions.
        The placement engine derives all geometry; a hint may only select
        among the engine's own topology patterns (e.g. force ``trunk``)."""
        if style not in self.HINT_STYLES:
            raise CircuitError(f"hint({net!r}): unknown style {style!r} "
                               f"(known: {sorted(self.HINT_STYLES)})")
        if net not in self.nets:
            raise CircuitError(f"hint({net!r}): not a declared net")
        self.hints[net] = style

    # ---- power-tree budget declarations (consumed by schgen/powertree.py) ----
    def draws(self, rail: str, amps: float, note: str = "") -> None:
        """Declare this subsystem's WORST-CASE current draw on a POWER rail.

        Declarative electrical intent, never geometry: the power-tree budget
        gate (round 4) sums every sheet's declarations through the regulator
        tree extracted from the netlists and FAILS the build on any
        regulator/source overrun. ``note`` should cite the dossier/datasheet
        figure the number comes from."""
        n = self.nets.get(rail)
        if n is None:
            raise CircuitError(f"draws({rail!r}): not a declared net")
        if n.net_class is not NetClass.POWER:
            raise CircuitError(f"draws({rail!r}): not a POWER rail "
                               f"({n.net_class.value})")
        if not (amps > 0):
            raise CircuitError(f"draws({rail!r}): amps must be > 0")
        self.loads.setdefault(rail, []).append((float(amps), note))

    # ---- test points (consumed by schgen/testpoints.py) ----------------------
    TP_LIB_ID = "Connector:TestPoint"
    TP_FOOTPRINT = "TestPoint:TestPoint_Pad_D1.5mm"

    def testpoint(self, net: str, ref: str | None = None) -> Part:
        """A probe point on ``net``: KiCad TestPoint symbol on a pad-only
        footprint — copper, no component, NO BOM line (the BOM/preflight
        exporters skip ``BOM=exclude`` parts). The placement ENGINE owns its
        geometry (a dedicated probe row); authoring stays netlist-only.

        Only POWER/GROUND/PORT nets are probeable (the coverage gate's
        domain); the net must already carry at least one real pin."""
        n = self.nets.get(net)
        if n is None:
            raise CircuitError(f"testpoint({net!r}): not a declared net")
        if n.net_class is NetClass.SIGNAL:
            raise CircuitError(
                f"testpoint({net!r}): internal SIGNAL net — probe points "
                f"cover rails and PORT buses (make it a port or waive)")
        if not n.pins:
            raise CircuitError(f"testpoint({net!r}): net has no pins yet — "
                               f"declare the circuit first")
        if ref is None:
            ref = self.auto_ref("TP")
        p = self.part(ref, self.TP_LIB_ID, net, self.TP_FOOTPRINT,
                      BOM="exclude")
        self.net(net, f"{ref}.1")
        return p

    # ---- mounting / tooling holes (chassis-bond fab-art, netlist-verifiable) --
    MH_LIB_ID = "Mechanical:MountingHole_Pad"
    MH_FOOTPRINT = "MountingHole:MountingHole_3.2mm_M3_Pad"

    def mounting_hole(self, net: str = "CHASSIS_GND",
                      ref: str | None = None) -> Part:
        """A plated M3 tooling/mounting hole bonded to ``net`` (default
        CHASSIS_GND): KiCad Mechanical:MountingHole_Pad on the 3.2 mm-M3
        plated footprint — real copper + a netlisted pin so the chassis bond
        is ERC/netlist-gate verifiable and the placement ENGINE can place it
        (a one-pin GROUND part, drawn natively like the testpoint() GROUND
        branch). NO BOM line (BOM=exclude, like testpoint()).

        Only GROUND nets are valid: a mounting hole is a chassis/earth bond,
        NEVER a signal or rail — bonding it to anything else would be a
        LAW-0 short (e.g. tying chassis to +3V3)."""
        n = self.nets.get(net)
        if n is None:
            raise CircuitError(f"mounting_hole({net!r}): not a declared net")
        if n.net_class is not NetClass.GROUND:
            raise CircuitError(
                f"mounting_hole({net!r}): only GROUND nets — a mounting hole "
                f"is a chassis/earth bond, never a signal/rail "
                f"({n.net_class.value})")
        if ref is None:
            ref = self.auto_ref("H")
        p = self.part(ref, self.MH_LIB_ID, "MountingHole_M3",
                      self.MH_FOOTPRINT, BOM="exclude")
        self.net(net, f"{ref}.1")
        return p

    def waive_tp(self, net: str, reason: str) -> None:
        """EXPLICIT test-point waiver: this net deliberately has no probe
        point. The coverage gate lists every waiver verbatim in its report —
        a waiver is documentation, never silence."""
        if net not in self.nets:
            raise CircuitError(f"waive_tp({net!r}): not a declared net")
        if not reason.strip():
            raise CircuitError(f"waive_tp({net!r}): a reason is required")
        self.tp_waivers[net] = reason.strip()

    # ---- design-rule completeness waivers (schgen/verify/design_rules.py) ----
    def waive_decap(self, ref_or_pin: str, reason: str) -> None:
        """EXPLICIT decoupling waiver: this IC supply pin/rail deliberately has
        no local cap-to-GND on its sheet. Key on a part ref ('U1'), a pin
        ('U1.3'), or the rail net ('+3V3'). The gate lists it verbatim."""
        if not reason.strip():
            raise CircuitError(f"waive_decap({ref_or_pin!r}): a reason is required")
        ref = ref_or_pin.split(".")[0]
        if ref not in self.parts and ref_or_pin not in self.nets:
            raise CircuitError(f"waive_decap({ref_or_pin!r}): not a part ref, "
                               f"'ref.pin', or declared net")
        self.decap_waivers[ref_or_pin] = reason.strip()

    def waive_pull(self, net: str, reason: str) -> None:
        """EXPLICIT i2c pull-up waiver: this bus's pull-ups live off-board /
        integrated in a transceiver (e.g. TPD12S016 DDC)."""
        if net not in self.nets:
            raise CircuitError(f"waive_pull({net!r}): not a declared net")
        if not reason.strip():
            raise CircuitError(f"waive_pull({net!r}): a reason is required")
        self.pull_waivers[net] = reason.strip()

    def waive_reset(self, net: str, reason: str) -> None:
        """EXPLICIT reset-RC waiver: this reset net deliberately omits the
        cap-to-GND and/or the pull (open-drain pull-only, held pull-down,
        internal POR, GPIO-driven, ...)."""
        if net not in self.nets:
            raise CircuitError(f"waive_reset({net!r}): not a declared net")
        if not reason.strip():
            raise CircuitError(f"waive_reset({net!r}): a reason is required")
        self.reset_waivers[net] = reason.strip()

    def waive_strap(self, ref_or_pin: str, reason: str) -> None:
        """EXPLICIT floating-strap waiver: this config input is intentionally
        on a passive-only net (documented float / external strap)."""
        if not reason.strip():
            raise CircuitError(f"waive_strap({ref_or_pin!r}): a reason is required")
        ref = ref_or_pin.split(".")[0]
        if ref not in self.parts and ref_or_pin not in self.nets:
            raise CircuitError(f"waive_strap({ref_or_pin!r}): not a part ref, "
                               f"'ref.pin', 'ref.NAME', or declared net")
        self.strap_waivers[ref_or_pin] = reason.strip()

    def waive_ep(self, ref_or_pin: str, reason: str) -> None:
        """EXPLICIT exposed-pad waiver: this thermal/exposed pad is intentionally
        NOT on a GROUND net (a documented non-GND heat-spreader island) or
        intentionally left unconnected. The EP gate lists every waiver verbatim
        and demotes the finding to a note — documentation, never silence
        (LAW 4: an EP is a real pad+pin+net, never a prose layout note)."""
        if not reason.strip():
            raise CircuitError(f"waive_ep({ref_or_pin!r}): a reason is required")
        ref = ref_or_pin.split(".")[0]
        if ref not in self.parts and ref_or_pin not in self.nets:
            raise CircuitError(f"waive_ep({ref_or_pin!r}): not a part ref, "
                               f"'ref.pin', or declared net")
        self.ep_waivers[ref_or_pin] = reason.strip()

    def waive_thermal(self, ref: str, reason: str) -> None:
        """EXPLICIT thermal waiver: this device may run past the Tj guard band
        on purpose (e.g. a copper-pour / thermal-via layout the single-number
        RthJA does not capture). The thermal gate lists every waiver verbatim
        and demotes the over-Tj ERROR to a note — documentation, never silence.
        ``ref`` is the part reference on this sheet (e.g. 'U1')."""
        if ref not in self.parts:
            raise CircuitError(f"waive_thermal({ref!r}): not a declared part")
        if not reason.strip():
            raise CircuitError(f"waive_thermal({ref!r}): a reason is required")
        self.thermal_waivers[ref] = reason.strip()

    def waive_part_rule(self, ref: str, reason: str) -> None:
        """EXPLICIT per-part rule-engine waiver (schgen/verify/part_rules.py):
        this part runs a rating margin tighter than the gate's derate on
        purpose (documented layout/lifetime justification). The gate lists every
        waiver verbatim and demotes the finding to a note — never silence."""
        if ref not in self.parts:
            raise CircuitError(f"waive_part_rule({ref!r}): not a declared part")
        if not reason.strip():
            raise CircuitError(f"waive_part_rule({ref!r}): a reason is required")
        self.part_rule_waivers[ref] = reason.strip()

    def nc(self, *pins: PinRef | str) -> None:
        """Author-declared no-connect — pin is INTENTIONALLY unused."""
        for p in pins:
            for pr in self._expand_pin(p):
                if self.net_of(pr) is not None:
                    raise CircuitError(f"{pr} carries a net, cannot be NC")
                self.nc_pins.add(pr)

    def _expand_pin(self, p: PinRef | str) -> list[PinRef]:
        """'U1.SDA' -> every pin NUMBER named SDA (stacked duplicate pads
        net together, exactly like the KiCad symbol). Bare numbers stay
        first-class; an unknown name on a use_part part is an error."""
        if isinstance(p, PinRef):
            return [self._pinref(p)]
        ref, _, pin = p.partition(".")
        if not pin:
            raise CircuitError(f"bad pin spec {p!r} (want 'REF.PIN')")
        part = self.parts.get(ref)
        if part is None:
            raise CircuitError(f"{p}: unknown part {ref!r}")
        if part.pin_numbers:
            if pin in part.pin_numbers:
                return [PinRef(ref, pin)]
            if pin in part.pin_names:
                return [PinRef(ref, n) for n in part.pin_names[pin]]
            raise CircuitError(
                f"{p}: {part.value} has no pin number or name {pin!r} "
                f"(names: {sorted(part.pin_names)[:12]}…)")
        # inline part(): validate the pin NUMBER eagerly against the symbol
        # library — same eager discipline use_part gets above (F9). The old
        # code deferred this to validate(), so a typo'd inline pin survived
        # until the late completeness check with a terser message.
        nums = self._inline_pin_numbers(part.lib_id)
        if nums is not None and pin not in nums:
            raise CircuitError(
                f"{p}: {part.value} ({part.lib_id}) has no pin number {pin!r} "
                f"(valid numbers: {sorted(nums)[:12]}…)")
        return [PinRef(ref, pin)]

    def _inline_pin_numbers(self, lib_id: str) -> frozenset[str] | None:
        """Pin numbers of an inline part's symbol, cached. ``None`` if the
        symbol can't be resolved (synthesized rails, missing lib at authoring
        time) — eager validation is then SKIPPED, never relaxed: the late
        :meth:`validate` still proves every pin against the real library."""
        if lib_id in self._inline_pins:
            return self._inline_pins[lib_id]
        try:
            if self._lib is None:
                from schgen.core.symbols import Library  # deferred: keeps model pure
                self._lib = Library()
            nums = frozenset(self._lib.pin_numbers(lib_id))
        except Exception:                      # noqa: BLE001 — unresolved sym
            nums = None
        self._inline_pins[lib_id] = nums
        return nums

    def _pinref(self, p: PinRef | str) -> PinRef:
        if isinstance(p, PinRef):
            if p.ref not in self.parts:
                raise CircuitError(f"{p}: unknown part {p.ref!r}")
            return p
        prs = self._expand_pin(p)
        if len(prs) != 1:
            raise CircuitError(f"{p}: names {len(prs)} stacked pins — this "
                               f"context needs exactly one")
        return prs[0]

    def net_of(self, pr: PinRef) -> Net | None:
        for n in self.nets.values():
            if pr in n.pins:
                return n
        return None

    # ---- macros (expand to explicit parts + nets) ---------------------------
    def decouple(self, power_pin: PinRef | str, *values: str,
                 rail: str | None = None, gnd: str = "GND",
                 lib_id: str = "Device:C", footprint: str = "") -> list[Part]:
        """N decoupling caps from ``power_pin``'s rail to ``gnd``.

        ``rail`` defaults to the net already on ``power_pin`` (declare it first).
        """
        pr = self._pinref(power_pin)
        rail_net = rail or (self.net_of(pr).name if self.net_of(pr) else None)
        if rail_net is None:
            raise CircuitError(f"decouple({pr}): rail unknown — net the pin first")
        out = []
        for v in values:
            ref = self.auto_ref("C")
            c = self.part(ref, lib_id, v, footprint)
            self.net(rail_net, f"{ref}.1")
            self.net(gnd, f"{ref}.2")
            out.append(c)
        return out

    def pullup(self, signal_pin: PinRef | str, value: str, rail: str,
               lib_id: str = "Device:R", footprint: str = "") -> Part:
        pr = self._pinref(signal_pin)
        sig = self.net_of(pr)
        if sig is None:
            raise CircuitError(f"pullup({pr}): net the signal pin first")
        ref = self.auto_ref("R")
        r = self.part(ref, lib_id, value, footprint)
        self.net(sig.name, f"{ref}.2")
        self.net(rail, f"{ref}.1")
        return r

    def series(self, net_in: str, net_out: str, value: str, prefix: str = "R",
               lib_id: str = "Device:R", footprint: str = "") -> Part:
        """A series element splitting net_in -> [R] -> net_out."""
        ref = self.auto_ref(prefix)
        r = self.part(ref, lib_id, value, footprint)
        self.net(net_in, f"{ref}.1")
        self.net(net_out, f"{ref}.2")
        return r

    # ---- pagination support (DEF-J: auto-split a congested sheet) -----------
    def subset(self, refs: set[str], *, page: int) -> "Circuit":
        """A child Circuit holding exactly ``refs`` plus every net among them.

        The placer's auto-paginator (place.partition_pages) calls this to split
        a sheet that overflows A3 across pages. A net touching parts on OTHER
        pages is copied with only its LOCAL pins; the same-named POWER/GROUND
        net reappears on every page as a power symbol and a PORT net as a label,
        so the board merges them back BY NAME — the merged kicad netlist equals
        the un-paginated one.

        LAW 0 (hard, non-suppressible): a SIGNAL net may NOT be cut across pages
        (both pins on this page, or neither). partition_pages groups SIGNAL-
        connected parts onto one page precisely so this never trips; if a bug
        ever splits a SIGNAL net this raises PartitionError BEFORE any emit — a
        cut SIGNAL net would otherwise be a silent OPEN. This is the ONLY place
        the cut is validated, so it is airtight: no flag, no waiver, no try."""
        import copy
        sub = Circuit(name=f"{self.name}.{page}", title=self.title)
        for r in sorted(refs):
            sub.parts[r] = copy.deepcopy(self.parts[r])
        for pr in self.nc_pins:                 # author NCs first (net() rejects
            if pr.ref in refs:                  # a netted NC pin)
                sub.nc_pins.add(pr)
        sub._inline_pins.update(self._inline_pins)   # lib_id->pins cache (shared)
        for nm, net in self.nets.items():
            kept = [pr for pr in net.pins if pr.ref in refs]
            if not kept:
                continue
            if len(kept) != len(net.pins) and net.net_class is NetClass.SIGNAL:
                raise PartitionError(
                    f"SIGNAL net {nm!r} would be CUT across pages — OPEN. "
                    f"pins {sorted(str(p) for p in net.pins)} split by page "
                    f"refs {sorted(refs)}; partition_pages must keep SIGNAL-"
                    f"connected parts on one page.")
            sub.net(nm, *kept, net_class=net.net_class)
            if net.net_class is NetClass.PORT and nm in self.port_types:
                sub.port_types[nm] = self.port_types[nm]
            if nm in self.hints:
                sub.hints[nm] = self.hints[nm]
        for rail, budget in self.loads.items():      # rail budgets present here
            if rail in sub.nets:
                sub.loads[rail] = list(budget)

        def _kept_key(key: str) -> bool:             # ref | "ref.pin" | net
            return key.split(".")[0] in refs or key in sub.nets
        for attr in ("tp_waivers", "decap_waivers", "pull_waivers",
                     "reset_waivers", "strap_waivers", "ep_waivers",
                     "thermal_waivers", "part_rule_waivers"):
            dst = getattr(sub, attr)
            for k, v in getattr(self, attr).items():
                if _kept_key(k):
                    dst[k] = v
        return sub

    # ---- completeness check (build-time, hard) ------------------------------
    def validate(self, pin_numbers_by_ref: dict[str, set[str]]) -> None:
        """Every physical pin is netted or NC; every netted pin exists.

        ``pin_numbers_by_ref`` comes from the symbol library (geometry layer) —
        the ONLY thing geometry feeds back into the model, and it's a set of
        names, not coordinates.
        """
        errors: list[str] = []
        assigned: dict[PinRef, str] = {}
        for n in self.nets.values():
            if n.net_class == NetClass.SIGNAL and len(n.pins) < 2:
                # SIGNAL implies not PORT/POWER/GROUND, so the old
                # `net_class != PORT` conjunct was dead (F6).
                errors.append(f"net {n.name!r}: single-pin internal signal net")
            for pr in n.pins:
                assigned[pr] = n.name
                have = pin_numbers_by_ref.get(pr.ref)
                if have is not None and pr.pin not in have:
                    errors.append(f"{pr}: pin does not exist on {pr.ref}")
        for ref, pins in pin_numbers_by_ref.items():
            for pin in pins:
                pr = PinRef(ref, pin)
                if pr not in assigned and pr not in self.nc_pins:
                    errors.append(f"{pr}: UNASSIGNED (net it or declare nc())")
        if errors:
            raise CircuitError(
                f"circuit {self.name!r} incomplete:\n  " + "\n  ".join(errors))
