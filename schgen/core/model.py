from __future__ import annotations

import enum
import re
from dataclasses import dataclass, field, replace


class NetClass(enum.Enum):
    POWER = "power"
    GROUND = "ground"
    SIGNAL = "signal"
    PORT = "port"


_GROUND_RE = re.compile(r"^(GND|GNDA|GNDD|GNDPWR|AGND|DGND|PGND|VSS|CHASSIS_GND)")
_POWER_RE = re.compile(r"^\+|^VBUS$|^VDD|^VCC")


PORT_KINDS = frozenset({
    "single",
    "diff_pair",
    "usb_hs_pair",
    "tmds_pair",
    "i2c",
    "sd_bus",
})
PAIR_KINDS = frozenset({"diff_pair", "usb_hs_pair", "tmds_pair"})
_DEFAULT_IMPEDANCE = {"usb_hs_pair": 90, "tmds_pair": 100}

_POLARITY_SUFFIXES: tuple[tuple[str, str], ...] = (
    ("_DP", "P"), ("_DM", "N"), ("_DN", "N"),
    ("DP", "P"), ("DM", "N"), ("DN", "N"),
    ("_P", "P"), ("_N", "N"),
    ("D+", "P"), ("D-", "N"),
    ("+", "P"), ("-", "N"),
    ("P", "P"), ("N", "N"),
)


def pair_polarity(name: str) -> str | None:
    up = name.upper()
    for suffix, pol in _POLARITY_SUFFIXES:
        if up.endswith(suffix):
            return pol
    return None


@dataclass(frozen=True)
class PortType:
    kind: str = "single"
    pair_with: str | None = None
    impedance: int | None = None
    role: str | None = None
    bus: str | None = None
    speed_hz: int | None = None
    level_v: float | None = None
    expect: str | None = None


@dataclass(frozen=True)
class PinRef:
    ref: str
    pin: str

    def __str__(self) -> str:
        return f"{self.ref}.{self.pin}"


@dataclass
class Part:
    ref: str
    lib_id: str
    value: str
    footprint: str = ""
    fields: dict[str, str] = field(default_factory=dict)
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
    pass


_R_FP_0603 = "Resistor_SMD:R_0603_1608Metric"
_C_FP_0603 = "Capacitor_SMD:C_0603_1608Metric"
_C_FP_0805 = "Capacitor_SMD:C_0805_2012Metric"


def _passive_uF(value: str) -> float | None:
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
    def __init__(self, name: str, title: str = "") -> None:
        self.name = name
        self.title = title or name
        self.parts: dict[str, Part] = {}
        self.nets: dict[str, Net] = {}
        self.nc_pins: set[PinRef] = set()
        self.port_types: dict[str, PortType] = {}
        self.hints: dict[str, str] = {}
        self.loads: dict[str, list[tuple[float, str]]] = {}
        self.tp_waivers: dict[str, str] = {}
        self.decap_waivers: dict[str, str] = {}
        self.pull_waivers: dict[str, str] = {}
        self.reset_waivers: dict[str, str] = {}
        self.strap_waivers: dict[str, str] = {}
        self.ep_waivers: dict[str, str] = {}
        self.thermal_waivers: dict[str, str] = {}
        self.part_rule_waivers: dict[str, str] = {}
        self._ref_counters: dict[str, int] = {}
        self._lib = None
        self._inline_pins: dict[str, frozenset[str]] = {}

    def part(self, ref: str, lib_id: str, value: str, footprint: str = "",
             **fields: str) -> Part:
        if ref in self.parts:
            raise CircuitError(f"duplicate reference {ref!r}")
        if not footprint:
            footprint = _default_footprint(lib_id, value)
        p = Part(ref=ref, lib_id=lib_id, value=value, footprint=footprint,
                 fields=dict(fields))
        self.parts[ref] = p
        return p

    def use_part(self, mpn: str, ref: str | None = None, *,
                 value: str | None = None, lcsc: str | None = None,
                 lib_id: str | None = None,
                 footprint: str | None = None) -> Part:
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
            ref = self.auto_ref(getattr(mod, "PREFIX", "U") or "U")
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
        n = self._ref_counters.get(prefix, 0) + 1
        while f"{prefix}{n}" in self.parts:
            n += 1
        self._ref_counters[prefix] = n
        return f"{prefix}{n}"

    @staticmethod
    def classify(name: str) -> NetClass:
        if _GROUND_RE.match(name):
            return NetClass.GROUND
        if _POWER_RE.match(name):
            return NetClass.POWER
        return NetClass.SIGNAL

    def net(self, name: str, *pins: PinRef | str,
            net_class: NetClass | None = None) -> Net:
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
        if kind not in PORT_KINDS:
            raise CircuitError(f"port_type({net!r}): unknown kind {kind!r} "
                               f"(known: {sorted(PORT_KINDS)})")
        n = self.nets.get(net)
        if n is None or n.net_class != NetClass.PORT:
            raise CircuitError(f"port_type({net!r}): not a declared PORT net")
        if kind in PAIR_KINDS:
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
        if kind in PAIR_KINDS and pair_with is not None:
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
        return self.port_types.get(net, PortType())

    def bind(self, mapping: dict[str, str]) -> Circuit:
        """Rename external POWER/GROUND/PORT nets in place, order-preserving."""
        for abstract, _real in mapping.items():
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
        for target in set(mapping.values()):
            srcs = [a for a, r in mapping.items() if r == target]
            if len(srcs) > 1:
                raise CircuitError(
                    f"bind: {sorted(srcs)} all bind to {target!r} — distinct "
                    f"externals cannot merge onto one net (LAW-0 short)")
            if target in self.nets and target not in mapping and \
                    target != srcs[0]:
                raise CircuitError(
                    f"bind: {srcs[0]!r} -> {target!r} collides with the "
                    f"existing net {target!r} on this circuit")
        rename = {a: r for a, r in mapping.items() if a != r}
        if not rename:
            return self
        new_nets: dict[str, Net] = {}
        for name, net in self.nets.items():
            nn = rename.get(name, name)
            net.name = nn
            new_nets[nn] = net
        self.nets = new_nets
        self.port_types = {
            rename.get(k, k): (replace(v, pair_with=rename[v.pair_with])
                               if v.pair_with in rename else v)
            for k, v in self.port_types.items()}
        self.loads = {rename.get(k, k): v for k, v in self.loads.items()}
        self.hints = {rename.get(k, k): v for k, v in self.hints.items()}
        for attr in ("tp_waivers", "decap_waivers", "pull_waivers",
                     "reset_waivers", "strap_waivers", "ep_waivers"):
            d = getattr(self, attr)
            setattr(self, attr, {rename.get(k, k): v for k, v in d.items()})
        for p in self.parts.values():
            if p.lib_id in (self.TP_LIB_ID, self.MH_LIB_ID) \
                    and p.value in rename:
                p.value = rename[p.value]
        return self

    def _bindable_names(self) -> list[str]:
        return [n.name for n in self.nets.values()
                if n.net_class is not NetClass.SIGNAL]

    HINT_STYLES = frozenset({"trunk"})

    def hint(self, net: str, style: str) -> None:
        if style not in self.HINT_STYLES:
            raise CircuitError(f"hint({net!r}): unknown style {style!r} "
                               f"(known: {sorted(self.HINT_STYLES)})")
        if net not in self.nets:
            raise CircuitError(f"hint({net!r}): not a declared net")
        self.hints[net] = style

    def draws(self, rail: str, amps: float, note: str = "") -> None:
        n = self.nets.get(rail)
        if n is None:
            raise CircuitError(f"draws({rail!r}): not a declared net")
        if n.net_class is not NetClass.POWER:
            raise CircuitError(f"draws({rail!r}): not a POWER rail "
                               f"({n.net_class.value})")
        if not (amps > 0):
            raise CircuitError(f"draws({rail!r}): amps must be > 0")
        self.loads.setdefault(rail, []).append((float(amps), note))

    TP_LIB_ID = "Connector:TestPoint"
    TP_FOOTPRINT = "TestPoint:TestPoint_Pad_D1.5mm"

    def testpoint(self, net: str, ref: str | None = None) -> Part:
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

    MH_LIB_ID = "Mechanical:MountingHole_Pad"
    MH_FOOTPRINT = "MountingHole:MountingHole_3.2mm_M3_Pad"

    def mounting_hole(self, net: str = "CHASSIS_GND",
                      ref: str | None = None) -> Part:
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
        if net not in self.nets:
            raise CircuitError(f"waive_tp({net!r}): not a declared net")
        if not reason.strip():
            raise CircuitError(f"waive_tp({net!r}): a reason is required")
        self.tp_waivers[net] = reason.strip()

    def waive_decap(self, ref_or_pin: str, reason: str) -> None:
        if not reason.strip():
            raise CircuitError(f"waive_decap({ref_or_pin!r}): a reason is required")
        ref = ref_or_pin.split(".")[0]
        if ref not in self.parts and ref_or_pin not in self.nets:
            raise CircuitError(f"waive_decap({ref_or_pin!r}): not a part ref, "
                               f"'ref.pin', or declared net")
        self.decap_waivers[ref_or_pin] = reason.strip()

    def waive_pull(self, net: str, reason: str) -> None:
        if net not in self.nets:
            raise CircuitError(f"waive_pull({net!r}): not a declared net")
        if not reason.strip():
            raise CircuitError(f"waive_pull({net!r}): a reason is required")
        self.pull_waivers[net] = reason.strip()

    def waive_reset(self, net: str, reason: str) -> None:
        if net not in self.nets:
            raise CircuitError(f"waive_reset({net!r}): not a declared net")
        if not reason.strip():
            raise CircuitError(f"waive_reset({net!r}): a reason is required")
        self.reset_waivers[net] = reason.strip()

    def waive_strap(self, ref_or_pin: str, reason: str) -> None:
        if not reason.strip():
            raise CircuitError(f"waive_strap({ref_or_pin!r}): a reason is required")
        ref = ref_or_pin.split(".")[0]
        if ref not in self.parts and ref_or_pin not in self.nets:
            raise CircuitError(f"waive_strap({ref_or_pin!r}): not a part ref, "
                               f"'ref.pin', 'ref.NAME', or declared net")
        self.strap_waivers[ref_or_pin] = reason.strip()

    def waive_ep(self, ref_or_pin: str, reason: str) -> None:
        if not reason.strip():
            raise CircuitError(f"waive_ep({ref_or_pin!r}): a reason is required")
        ref = ref_or_pin.split(".")[0]
        if ref not in self.parts and ref_or_pin not in self.nets:
            raise CircuitError(f"waive_ep({ref_or_pin!r}): not a part ref, "
                               f"'ref.pin', or declared net")
        self.ep_waivers[ref_or_pin] = reason.strip()

    def waive_thermal(self, ref: str, reason: str) -> None:
        if ref not in self.parts:
            raise CircuitError(f"waive_thermal({ref!r}): not a declared part")
        if not reason.strip():
            raise CircuitError(f"waive_thermal({ref!r}): a reason is required")
        self.thermal_waivers[ref] = reason.strip()

    def waive_part_rule(self, ref: str, reason: str) -> None:
        if ref not in self.parts:
            raise CircuitError(f"waive_part_rule({ref!r}): not a declared part")
        if not reason.strip():
            raise CircuitError(f"waive_part_rule({ref!r}): a reason is required")
        self.part_rule_waivers[ref] = reason.strip()

    def nc(self, *pins: PinRef | str) -> None:
        for p in pins:
            for pr in self._expand_pin(p):
                if self.net_of(pr) is not None:
                    raise CircuitError(f"{pr} carries a net, cannot be NC")
                self.nc_pins.add(pr)

    def _expand_pin(self, p: PinRef | str) -> list[PinRef]:
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
        nums = self._inline_pin_numbers(part.lib_id)
        if nums is not None and pin not in nums:
            raise CircuitError(
                f"{p}: {part.value} ({part.lib_id}) has no pin number {pin!r} "
                f"(valid numbers: {sorted(nums)[:12]}…)")
        return [PinRef(ref, pin)]

    def _inline_pin_numbers(self, lib_id: str) -> frozenset[str] | None:
        if lib_id in self._inline_pins:
            return self._inline_pins[lib_id]
        try:
            if self._lib is None:
                from schgen.core.symbols import Library
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

    def decouple(self, power_pin: PinRef | str, *values: str,
                 rail: str | None = None, gnd: str = "GND",
                 lib_id: str = "Device:C", footprint: str = "") -> list[Part]:
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
        ref = self.auto_ref(prefix)
        r = self.part(ref, lib_id, value, footprint)
        self.net(net_in, f"{ref}.1")
        self.net(net_out, f"{ref}.2")
        return r

    def subset(self, refs: set[str], *, page: int) -> Circuit:
        """Child Circuit over ``refs``; cutting a SIGNAL net raises PartitionError."""
        import copy
        sub = Circuit(name=f"{self.name}.{page}", title=self.title)
        for r in sorted(refs):
            sub.parts[r] = copy.deepcopy(self.parts[r])
        for pr in self.nc_pins:
            if pr.ref in refs:
                sub.nc_pins.add(pr)
        sub._inline_pins.update(self._inline_pins)
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
        for rail, budget in self.loads.items():
            if rail in sub.nets:
                sub.loads[rail] = list(budget)

        def _kept_key(key: str) -> bool:
            return key.split(".")[0] in refs or key in sub.nets
        for attr in ("tp_waivers", "decap_waivers", "pull_waivers",
                     "reset_waivers", "strap_waivers", "ep_waivers",
                     "thermal_waivers", "part_rule_waivers"):
            dst = getattr(sub, attr)
            for k, v in getattr(self, attr).items():
                if _kept_key(k):
                    dst[k] = v
        return sub

    def validate(self, pin_numbers_by_ref: dict[str, set[str]]) -> None:
        errors: list[str] = []
        assigned: dict[PinRef, str] = {}
        for n in self.nets.values():
            if n.net_class == NetClass.SIGNAL and len(n.pins) < 2:
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
