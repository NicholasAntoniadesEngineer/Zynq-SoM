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
from dataclasses import dataclass, field


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


@dataclass
class Net:
    name: str
    net_class: NetClass
    pins: list[PinRef] = field(default_factory=list)


class CircuitError(ValueError):
    pass


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
        self._ref_counters: dict[str, int] = {}

    # ---- parts -------------------------------------------------------------
    def part(self, ref: str, lib_id: str, value: str, footprint: str = "",
             **fields: str) -> Part:
        if ref in self.parts:
            raise CircuitError(f"duplicate reference {ref!r}")
        p = Part(ref=ref, lib_id=lib_id, value=value, footprint=footprint,
                 fields=dict(fields))
        self.parts[ref] = p
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
            pr = self._pinref(p)
            if pr in self.nc_pins:
                raise CircuitError(f"{pr} is declared NC but assigned to {name!r}")
            existing = self.net_of(pr)
            if existing is not None and existing.name != name:
                raise CircuitError(
                    f"{pr} already on net {existing.name!r}, cannot also join {name!r}")
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

    def nc(self, *pins: PinRef | str) -> None:
        """Author-declared no-connect — pin is INTENTIONALLY unused."""
        for p in pins:
            pr = self._pinref(p)
            if self.net_of(pr) is not None:
                raise CircuitError(f"{pr} carries a net, cannot be NC")
            self.nc_pins.add(pr)

    def _pinref(self, p: PinRef | str) -> PinRef:
        if isinstance(p, PinRef):
            pr = p
        else:
            ref, _, pin = p.partition(".")
            if not pin:
                raise CircuitError(f"bad pin spec {p!r} (want 'REF.PIN')")
            pr = PinRef(ref, pin)
        if pr.ref not in self.parts:
            raise CircuitError(f"{pr}: unknown part {pr.ref!r}")
        return pr

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
            if n.net_class != NetClass.PORT and len(n.pins) < 2 and n.net_class == NetClass.SIGNAL:
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
