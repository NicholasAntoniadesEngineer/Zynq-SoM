from __future__ import annotations

import enum
import re
from dataclasses import dataclass, field, replace

CIRCUIT_SCHEMA = "schgen.circuit/1"
CIRCUIT_IR_KEYS = (
    "schema",
    "name",
    "title",
    "parts",
    "nets",
    "nc",
    "port_types",
    "hints",
    "loads",
    "tp_waivers",
    "decap_waivers",
    "pull_waivers",
    "reset_waivers",
    "strap_waivers",
    "ep_waivers",
    "thermal_waivers",
    "part_rule_waivers",
)
PART_IR_KEYS = (
    "ref",
    "lib_id",
    "value",
    "footprint",
    "fields",
    "pin_names",
    "pin_numbers",
)
NET_IR_KEYS = ("name", "net_class", "pins")
PORT_TYPE_IR_KEYS = (
    "kind",
    "pair_with",
    "impedance",
    "role",
    "bus",
    "speed_hz",
    "level_v",
    "expect",
)
WAIVER_IR_ATTRS = (
    "tp_waivers",
    "decap_waivers",
    "pull_waivers",
    "reset_waivers",
    "strap_waivers",
    "ep_waivers",
    "thermal_waivers",
    "part_rule_waivers",
)


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


def _reject_unknown_keys(payload: dict, allowed: tuple[str, ...],
                         where: str) -> None:
    extra = set(payload) - set(allowed)
    if extra:
        raise CircuitError(
            f"{where}: unknown key(s) {sorted(extra)}")
    missing = [key for key in allowed if key not in payload]
    if missing:
        raise CircuitError(
            f"{where}: missing key(s) {missing}")


def _require_str(payload: dict, key: str, where: str,
                 allow_empty: bool) -> str:
    value = payload[key]
    if not isinstance(value, str):
        raise CircuitError(f"{where}: {key!r} must be a string")
    if not allow_empty and not value:
        raise CircuitError(f"{where}: {key!r} must not be empty")
    return value


def _require_str_dict(payload: dict, key: str, where: str) -> dict[str, str]:
    value = payload[key]
    if not isinstance(value, dict):
        raise CircuitError(f"{where}: {key!r} must be an object")
    out: dict[str, str] = {}
    for item_key, item_val in value.items():
        if not isinstance(item_key, str) or not item_key:
            raise CircuitError(f"{where}: {key!r} keys must be non-empty strings")
        if not isinstance(item_val, str):
            raise CircuitError(
                f"{where}: {key!r}[{item_key!r}] must be a string")
        out[item_key] = item_val
    return out


def _require_str_list(value: object, where: str) -> list[str]:
    if not isinstance(value, list):
        raise CircuitError(f"{where} must be an array of strings")
    out: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item:
            raise CircuitError(f"{where} entries must be non-empty strings")
        out.append(item)
    return out


def _opt_str(value: object, where: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise CircuitError(f"{where} must be a string or null")
    return value


def _opt_int(value: object, where: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise CircuitError(f"{where} must be an integer or null")
    if isinstance(value, float) and not value.is_integer():
        raise CircuitError(f"{where} must be an integer or null")
    return int(value)


def _opt_float(value: object, where: str) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise CircuitError(f"{where} must be a number or null")
    return float(value)


def _pin_spec(ref: str, pin: str) -> str:
    return f"{ref}.{pin}"


def _split_pin_spec(spec: str, where: str) -> PinRef:
    ref, sep, pin = spec.partition(".")
    if not sep or not ref or not pin:
        raise CircuitError(f"{where}: bad pin spec {spec!r} (want 'REF.PIN')")
    return PinRef(ref, pin)


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
        from pathlib import Path as _P
        from schgen.core import native as _nat
        safe = re.sub(r"[^A-Za-z0-9._-]+", "_", mpn).strip("_")
        parts_dir = _P(__file__).resolve().parents[2] / "parts"
        meta = parts_dir / safe / "part.json"
        if not meta.exists():
            raise CircuitError(
                f"use_part({mpn!r}): parts/{safe}/part.json is missing — "
                f"generate it with:  schgen part add "
                f"{lcsc or 'C<LCSC-id>'} --name {safe}")
        try:
            rec = _nat.catalog_part(safe)
        except Exception as exc:
            raise CircuitError(
                f"use_part({mpn!r}): catalog lookup failed — {exc}") from exc
        if rec["safe_name"] != safe:
            raise CircuitError(
                f"use_part({mpn!r}): catalog safe_name {rec['safe_name']!r} "
                f"does not match folder {safe!r}")
        if ref is None:
            prefix = rec["prefix"]
            if not prefix:
                raise CircuitError(f"use_part({mpn!r}): catalog prefix is empty")
            ref = self.auto_ref(prefix)
        fields = {"LCSC": rec["lcsc"] or (lcsc or "")}
        if lib_id is not None:
            fields["MPN"] = rec["mpn"]
            if rec["datasheet"]:
                fields["Datasheet"] = rec["datasheet"]
        p = self.part(ref, lib_id or rec["lib_id"], value or rec["mpn"],
                      footprint or rec["footprint"], **fields)
        if lib_id is None:
            names: dict[str, list[str]] = {}
            nums: set[str] = set()
            for num, name, _et in rec["pins"]:
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

    def to_ir(self) -> dict:
        parts = []
        for part in self.parts.values():
            pin_names = {name: [str(num) for num in nums]
                         for name, nums in part.pin_names.items()}
            pin_numbers = [str(num) for num in sorted(part.pin_numbers)]
            parts.append({
                "ref": part.ref,
                "lib_id": part.lib_id,
                "value": part.value,
                "footprint": part.footprint,
                "fields": dict(part.fields),
                "pin_names": pin_names,
                "pin_numbers": pin_numbers,
            })
        nets = []
        for net in self.nets.values():
            nets.append({
                "name": net.name,
                "net_class": net.net_class.value,
                "pins": [_pin_spec(pr.ref, pr.pin) for pr in net.pins],
            })
        nc = [_pin_spec(pr.ref, pr.pin)
              for pr in sorted(self.nc_pins, key=lambda p: (p.ref, p.pin))]
        port_types = {}
        for name, pt in self.port_types.items():
            port_types[name] = {
                "kind": pt.kind,
                "pair_with": pt.pair_with,
                "impedance": pt.impedance,
                "role": pt.role,
                "bus": pt.bus,
                "speed_hz": pt.speed_hz,
                "level_v": pt.level_v,
                "expect": pt.expect,
            }
        loads = {}
        for rail, budget in self.loads.items():
            loads[rail] = [[float(amps), note] for amps, note in budget]
        ir = {
            "schema": CIRCUIT_SCHEMA,
            "name": self.name,
            "title": self.title,
            "parts": parts,
            "nets": nets,
            "nc": nc,
            "port_types": port_types,
            "hints": dict(self.hints),
            "loads": loads,
        }
        for attr in WAIVER_IR_ATTRS:
            ir[attr] = dict(getattr(self, attr))
        return ir

    def _restore_ref_counters(self) -> None:
        counters: dict[str, int] = {}
        for ref in self.parts:
            match = re.match(r"^([A-Za-z]+[_A-Za-z]*)(\d+)$", ref)
            if match is None:
                continue
            prefix, number = match.group(1), int(match.group(2))
            if number > counters.get(prefix, 0):
                counters[prefix] = number
        self._ref_counters = counters

    @classmethod
    def from_ir(cls, payload: dict) -> Circuit:
        if not isinstance(payload, dict):
            raise CircuitError("circuit IR must be an object")
        _reject_unknown_keys(payload, CIRCUIT_IR_KEYS, "circuit")
        schema = _require_str(payload, "schema", "circuit", False)
        if schema != CIRCUIT_SCHEMA:
            raise CircuitError(
                f"circuit schema must be {CIRCUIT_SCHEMA!r}, got {schema!r}")
        name = _require_str(payload, "name", "circuit", False)
        title = _require_str(payload, "title", "circuit", True)
        circuit = cls(name, title)
        parts = payload["parts"]
        if not isinstance(parts, list):
            raise CircuitError("circuit parts must be an array")
        for index, prec in enumerate(parts):
            where = f"circuit {name!r} parts[{index}]"
            if not isinstance(prec, dict):
                raise CircuitError(f"{where} must be an object")
            _reject_unknown_keys(prec, PART_IR_KEYS, where)
            ref = _require_str(prec, "ref", where, False)
            if ref in circuit.parts:
                raise CircuitError(f"{where}: duplicate reference {ref!r}")
            lib_id = _require_str(prec, "lib_id", where, False)
            value = _require_str(prec, "value", where, False)
            footprint = _require_str(prec, "footprint", where, True)
            fields = _require_str_dict(prec, "fields", where)
            pin_names_raw = prec["pin_names"]
            if not isinstance(pin_names_raw, dict):
                raise CircuitError(f"{where}: pin_names must be an object")
            pin_names: dict[str, list[str]] = {}
            for pin_name, nums in pin_names_raw.items():
                if not isinstance(pin_name, str) or not pin_name:
                    raise CircuitError(
                        f"{where}: pin_names keys must be non-empty strings")
                pin_names[pin_name] = _require_str_list(
                    nums, f"{where}: pin_names[{pin_name!r}]")
            pin_numbers = frozenset(
                _require_str_list(prec["pin_numbers"], f"{where}: pin_numbers"))
            circuit.parts[ref] = Part(
                ref=ref, lib_id=lib_id, value=value, footprint=footprint,
                fields=fields, pin_names=pin_names, pin_numbers=pin_numbers)
        nets = payload["nets"]
        if not isinstance(nets, list):
            raise CircuitError("circuit nets must be an array")
        for index, nrec in enumerate(nets):
            where = f"circuit {name!r} nets[{index}]"
            if not isinstance(nrec, dict):
                raise CircuitError(f"{where} must be an object")
            _reject_unknown_keys(nrec, NET_IR_KEYS, where)
            net_name = _require_str(nrec, "name", where, False)
            if net_name in circuit.nets:
                raise CircuitError(f"{where}: duplicate net {net_name!r}")
            class_name = _require_str(nrec, "net_class", where, False)
            try:
                net_class = NetClass(class_name)
            except ValueError as exc:
                raise CircuitError(
                    f"{where}: unknown net_class {class_name!r}") from exc
            pin_specs = _require_str_list(nrec["pins"], f"{where}: pins")
            pins = [_split_pin_spec(spec, where) for spec in pin_specs]
            circuit.nets[net_name] = Net(
                name=net_name, net_class=net_class, pins=pins)
        nc_specs = _require_str_list(payload["nc"], f"circuit {name!r} nc")
        for spec in nc_specs:
            circuit.nc_pins.add(_split_pin_spec(spec, f"circuit {name!r} nc"))
        port_types = payload["port_types"]
        if not isinstance(port_types, dict):
            raise CircuitError("circuit port_types must be an object")
        for port_name, prec in port_types.items():
            where = f"circuit {name!r} port_types[{port_name!r}]"
            if not isinstance(port_name, str) or not port_name:
                raise CircuitError("circuit port_types keys must be non-empty strings")
            if not isinstance(prec, dict):
                raise CircuitError(f"{where} must be an object")
            _reject_unknown_keys(prec, PORT_TYPE_IR_KEYS, where)
            kind = _require_str(prec, "kind", where, False)
            if kind not in PORT_KINDS:
                raise CircuitError(f"{where}: unknown kind {kind!r}")
            circuit.port_types[port_name] = PortType(
                kind=kind,
                pair_with=_opt_str(prec["pair_with"], f"{where}: pair_with"),
                impedance=_opt_int(prec["impedance"], f"{where}: impedance"),
                role=_opt_str(prec["role"], f"{where}: role"),
                bus=_opt_str(prec["bus"], f"{where}: bus"),
                speed_hz=_opt_int(prec["speed_hz"], f"{where}: speed_hz"),
                level_v=_opt_float(prec["level_v"], f"{where}: level_v"),
                expect=_opt_str(prec["expect"], f"{where}: expect"),
            )
        circuit.hints = _require_str_dict(payload, "hints", f"circuit {name!r}")
        loads_raw = payload["loads"]
        if not isinstance(loads_raw, dict):
            raise CircuitError("circuit loads must be an object")
        for rail, budget in loads_raw.items():
            where = f"circuit {name!r} loads[{rail!r}]"
            if not isinstance(rail, str) or not rail:
                raise CircuitError("circuit loads keys must be non-empty strings")
            if not isinstance(budget, list) or not budget:
                raise CircuitError(f"{where} must be a non-empty array")
            rows: list[tuple[float, str]] = []
            for row in budget:
                if (not isinstance(row, list) or len(row) != 2
                        or isinstance(row[0], bool)
                        or not isinstance(row[0], (int, float))
                        or not isinstance(row[1], str)):
                    raise CircuitError(
                        f"{where} entries must be [amps, note]")
                rows.append((float(row[0]), row[1]))
            circuit.loads[rail] = rows
        for attr in WAIVER_IR_ATTRS:
            setattr(circuit, attr, _require_str_dict(
                payload, attr, f"circuit {name!r}"))
        circuit._restore_ref_counters()
        return circuit
