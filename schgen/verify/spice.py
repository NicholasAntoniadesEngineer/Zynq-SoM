from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from schgen.core.model import NetClass, PinRef
from schgen.verify.powertree import parse_si, rail_volts

VREF_TPS54302 = 0.596
STM32_BOOT0_PULLDOWN = 1500.0
STM32_VDD = 3.3
STM32_VIH = 0.7 * STM32_VDD
STM32_NRST_PULLUP = 40_000.0
SY7201_VFB = 0.2
AO3400A_VGS_TH_MAX = 1.45
CP2102N_VBUS_MAX = 5.8
CP2102N_VBUS_DETECT = 3.0
LVCMOS33_VMAX = 3.465
LVCMOS33_VIH = 2.0
TPS2663_OVPR_MIN = 1.176
TPS2663_OVPR_MAX = 1.224
PD_CONTRACT_VMAX = 21.0
SMBJ22A_VBR_MIN = 24.4

TPS54302_EN_RISING = 1.21
TPS54302_EN_ENABLE_FLOOR = 1.5
TPS54302_EN_RECMAX = 5.5
TPS54302_EN_IHYS = 1.55e-6
PD_VIN_CONTRACT_LO = 4.75
ZENER_5V1_IZT = 20e-3
ZENER_5V1_ZZT = 17.0
ZENER_5V1_VZ = {"MMSZ5231B": (4.845, 5.1, 5.355),
                "BZT52C5V1": (4.845, 5.1, 5.355)}


@dataclass
class Check:
    name: str
    sheet: str
    kind: str
    detail: str
    value: float
    unit: str
    lo: float | None
    hi: float | None
    engine: str = "analytic"
    spice_value: float | None = None

    @property
    def ok(self) -> bool:
        if self.lo is not None and self.value < self.lo - 1e-9:
            return False
        if self.hi is not None and self.value > self.hi + 1e-9:
            return False
        if self.spice_value is not None and self.value and \
                abs(self.spice_value - self.value) > 0.01 * abs(self.value):
            return False
        return True


@dataclass
class Result:
    checks: list[Check] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    engine: str = "analytic (closed-form linear solutions)"

    @property
    def errors(self) -> list[str]:
        out = []
        for ch in self.checks:
            if not ch.ok:
                rng = (f"[{'' if ch.lo is None else f'{ch.lo:g}'} .. "
                       f"{'' if ch.hi is None else f'{ch.hi:g}'}] {ch.unit}")
                extra = (f"; ngspice={ch.spice_value:g}"
                         if ch.spice_value is not None else "")
                out.append(f"{ch.sheet}:{ch.name} = {ch.value:g} {ch.unit} "
                           f"outside {rng} — {ch.detail}{extra}")
        return out

    @property
    def ok(self) -> bool:
        return not self.errors

    @property
    def n_checks(self) -> int:
        return len(self.checks)


def _net_of(c, ref: str, pin: str):
    return c.net_of(PinRef(ref, pin))


def _resistors_on(c, net_name: str):
    out = []
    for ref, part in sorted(c.parts.items()):
        if not part.lib_id.endswith(":R"):
            continue
        n1, n2 = _net_of(c, ref, "1"), _net_of(c, ref, "2")
        if n1 is None or n2 is None:
            continue
        ohms = parse_si(part.value)
        if ohms is None:
            continue
        if n1.name == net_name:
            out.append((ref, ohms, n2))
        elif n2.name == net_name:
            out.append((ref, ohms, n1))
    return out


def _caps_on(c, net_name: str):
    out = []
    for ref, part in sorted(c.parts.items()):
        if not part.lib_id.endswith(":C"):
            continue
        n1, n2 = _net_of(c, ref, "1"), _net_of(c, ref, "2")
        if n1 is None or n2 is None:
            continue
        f = parse_si(part.value)
        if f is None:
            continue
        if n1.name == net_name:
            out.append((ref, f, n2))
        elif n2.name == net_name:
            out.append((ref, f, n1))
    return out


SOURCE_VOLTS: dict[str, float] = {
    "USB_UART_VBUS": 5.0,
    "HDMI_RX_5V": 5.0,
}

NAMED_DIVIDERS: dict[str, tuple[str, list, str]] = {
    "CP2102N_VBUS_SNS": (
        "USB_UART_VBUS",
        [(5.25, None, CP2102N_VBUS_MAX, "abs-max at 5.25 V VBUS"),
         (4.75, CP2102N_VBUS_DETECT, None, "detect at 4.75 V VBUS")],
        "CP2102N self-powered VBUS sense (DS 22k1/47k5 reference): must "
        "read VBUS-present yet never exceed the pin abs-max 5.8 V"),
    "PG_1V8_G": (
        "+1V8",
        [(1.8, AO3400A_VGS_TH_MAX, 1.8, "FET on at nominal rail")],
        "+1V8 PG sense: gate divider must exceed the AO3400A max "
        "Vgs(th)=1.45 V so the PG LED is guaranteed on"),
    "HDMI_RX_5V_DET": (
        "HDMI_RX_5V",
        [(5.25, None, LVCMOS33_VMAX, "bank abs-max at 5.25 V cable"),
         (4.75, LVCMOS33_VIH, None, "VIH at 4.75 V cable")],
        "cable-5V presence divider into an LVCMOS33 bank"),
    "PD_OVP_SET": (
        "+VBUS_IN",
        [(PD_CONTRACT_VMAX, None, TPS2663_OVPR_MIN,
          "no false trip at 21 V (contract max)"),
         (SMBJ22A_VBR_MIN, TPS2663_OVPR_MAX, None,
          "guaranteed cutoff below the TVS VBR min")],
        "TPS26631 OVP set divider (pd_input): must NOT trip inside the "
        "valid 20 V +5% contract window yet MUST cut off before the "
        "SMBJ22A starts clamping (V_OVPR 1.2 V +/-2%, SLVSE94G)"),
}


def extract_checks(sheets) -> Result:
    res = Result()
    for sc in sheets:
        c = sc.circuit
        _auto_dividers(sc.name, c, res)
        _rc_networks(sc.name, c, res)
        _sy7201_iset(sc.name, c, res)
        _buck_fb(sc.name, c, res)
        _en_clamp(sc.name, c, res)
        _boot0(sc.name, c, res)
    found = {ch.name for ch in res.checks}
    for net, (_src, _subs, why) in NAMED_DIVIDERS.items():
        if any(net in n for n in found):
            continue
        if any(net in sc.circuit.nets for sc in sheets):
            res.notes.append(f"NOTE: named divider {net} exists but was not "
                             f"extracted — check the topology ({why})")
    return res


def _auto_dividers(sheet: str, c, res: Result) -> None:
    for net in c.nets.values():
        if net.net_class not in (NetClass.SIGNAL, NetClass.PORT):
            continue
        rs = _resistors_on(c, net.name)
        if len(rs) != 2:
            continue
        tops = [(r, o, n) for r, o, n in rs
                if n.net_class is NetClass.POWER or n.name in SOURCE_VOLTS]
        bots = [(r, o, n) for r, o, n in rs
                if n.net_class is NetClass.GROUND]
        if len(tops) != 1 or len(bots) != 1:
            continue
        r_top, o_top, src = tops[0]
        r_bot, o_bot, _g = bots[0]
        ratio = o_bot / (o_top + o_bot)
        named = NAMED_DIVIDERS.get(net.name)
        if named is None:
            v_src = SOURCE_VOLTS.get(src.name, rail_volts(src.name) or 0.0)
            if not v_src:
                continue
            res.checks.append(Check(
                name=f"divider {net.name}", sheet=sheet, kind="divider",
                detail=f"{src.name} -[{r_top}={o_top:g}R]- {net.name} "
                       f"-[{r_bot}={o_bot:g}R]- GND @ {v_src:g} V "
                       f"(informational, no named threshold)",
                value=round(v_src * ratio, 4), unit="V", lo=None, hi=None))
            continue
        expected_src, subchecks, why = named
        src_ok = src.name == expected_src
        for v, lo, hi, tag in subchecks:
            if not src_ok:
                v = SOURCE_VOLTS.get(src.name, rail_volts(src.name) or 0.0)
                tag = (f"{tag}; SOURCE IS {src.name} ({v:g} V), expected "
                       f"{expected_src}")
            res.checks.append(Check(
                name=f"divider {net.name} [{tag}]", sheet=sheet,
                kind="divider",
                detail=f"{src.name} -[{r_top}={o_top:g}R]- {net.name} "
                       f"-[{r_bot}={o_bot:g}R]- GND @ {v:g} V: {why}",
                value=round(v * ratio, 4), unit="V", lo=lo, hi=hi))
            if not src_ok:
                break


def _rc_networks(sheet: str, c, res: Result) -> None:
    for net in c.nets.values():
        if net.net_class not in (NetClass.SIGNAL, NetClass.PORT):
            continue
        has_switch = any(c.parts[pr.ref].lib_id.lower().find("sw") >= 0
                         or c.parts[pr.ref].value in ("RESET", "USER")
                         or c.parts[pr.ref].ref.startswith("SW")
                         for pr in net.pins if pr.ref in c.parts)
        if not has_switch:
            continue
        caps = [(r, f) for r, f, other in _caps_on(c, net.name)
                if other.net_class is NetClass.GROUND]
        if not caps:
            continue
        pulls = [(r, o) for r, o, other in _resistors_on(c, net.name)
                 if other.net_class is NetClass.POWER]
        if pulls:
            r_ref, ohms = pulls[0]
            src = f"{r_ref}={ohms:g}R"
        elif net.name == "STM32_NRST":
            ohms = STM32_NRST_PULLUP
            src = "STM32 internal ~40k NRST pull-up (contract)"
        else:
            continue
        farads = sum(f for _r, f in caps)
        tau_ms = ohms * farads * 1e3
        res.checks.append(Check(
            name=f"RC {net.name}", sheet=sheet, kind="rc",
            detail=f"debounce/reset ramp: {src} with "
                   f"{'+'.join(r for r, _f in caps)}={farads*1e9:g}n -> "
                   f"tau must mask >=0.2 ms bounce, release <20 ms",
            value=round(tau_ms, 3), unit="ms", lo=0.2, hi=20.0))


def _sy7201_iset(sheet: str, c, res: Result) -> None:
    for ref, part in sorted(c.parts.items()):
        if not part.value.startswith("SY7201"):
            continue
        fb_pins = [n for n in (part.pin_names or {}).get("FB", ["?"])]
        fb_net = None
        for p in fb_pins:
            fb_net = _net_of(c, ref, p)
            if fb_net is not None:
                break
        if fb_net is None:
            res.notes.append(f"NOTE: {sheet}:{ref} SY7201 FB pin not netted")
            continue
        rs = [(r, o) for r, o, other in _resistors_on(c, fb_net.name)
              if other.net_class is NetClass.GROUND]
        if not rs:
            res.notes.append(f"NOTE: {sheet}:{ref} SY7201 ISET resistor "
                             f"not found on {fb_net.name}")
            continue
        r_ref, ohms = rs[0]
        i_ma = SY7201_VFB / ohms * 1e3
        res.checks.append(Check(
            name=f"SY7201 ISET ({r_ref})", sheet=sheet, kind="iset",
            detail=f"I_LED = {SY7201_VFB} V / {ohms:g}R; panel-class window "
                   f"125-150 mA (lcd_backlight.md)",
            value=round(i_ma, 1), unit="mA", lo=125.0, hi=150.0))


def _buck_fb(sheet: str, c, res: Result) -> None:
    from schgen.generate.bringup_facts import FB_VREF
    from schgen.verify.powertree import _detect_regs

    class _One:
        def __init__(self, name, circuit):
            self.name, self.circuit = name, circuit
    regs, _errs = _detect_regs([_One(sheet, c)])
    for reg in regs:
        if reg.kind != "buck":
            continue
        vref = next((v for k, v in FB_VREF.items() if reg.value.startswith(k)),
                    None)
        if vref is None:
            res.notes.append(f"NOTE: {sheet}:{reg.ref} ({reg.value}) has no "
                             f"FB_VREF entry — FB divider unchecked")
            continue
        fb_net = None
        tops = bots = []
        for net in c.nets.values():
            if net.net_class is not NetClass.SIGNAL \
                    or not any(pr.ref == reg.ref for pr in net.pins):
                continue
            t = [(r, o) for r, o, other in _resistors_on(c, net.name)
                 if other.name == reg.vout]
            b = [(r, o) for r, o, other in _resistors_on(c, net.name)
                 if other.net_class is NetClass.GROUND]
            if t and b:
                fb_net, tops, bots = net, t, b
                break
        if fb_net is None:
            res.notes.append(f"NOTE: {sheet}:{reg.ref} FB divider not found")
            continue
        (rt, ot), (rb, ob) = tops[0], bots[0]
        vout = vref * (1 + ot / ob)
        nominal = rail_volts(reg.vout) or 0.0
        res.checks.append(Check(
            name=f"{reg.value} FB ({reg.vout})", sheet=sheet,
            kind="fb_divider",
            detail=f"Vout = {vref} * (1 + {rt}/{rb} = "
                   f"{ot:g}/{ob:g}) vs nominal {nominal:g} V +/-3%",
            value=round(vout, 4), unit="V",
            lo=nominal * 0.97, hi=nominal * 1.03))


def _en_pin(c, ref: str) -> str | None:
    part = c.parts.get(ref)
    if part is not None and part.pin_names:
        for name, nums in part.pin_names.items():
            if name.upper().startswith("EN") and nums:
                return nums[0]
    return "5"


def _en_clamp(sheet: str, c, res: Result) -> None:
    from schgen.verify.powertree import _detect_regs

    class _One:
        def __init__(self, name, circuit):
            self.name, self.circuit = name, circuit

    regs, _errs = _detect_regs([_One(sheet, c)])
    for reg in regs:
        if reg.kind != "buck":
            continue
        en_net = _net_of(c, reg.ref, _en_pin(c, reg.ref))
        if en_net is None or en_net.net_class is not NetClass.SIGNAL:
            continue
        series = [(r, o, other) for r, o, other in _resistors_on(c, en_net.name)
                  if other.net_class is NetClass.POWER]
        zeners = []
        for ref, part in sorted(c.parts.items()):
            if not part.lib_id.endswith(":D_Zener"):
                continue
            n1, n2 = _net_of(c, ref, "1"), _net_of(c, ref, "2")
            if n1 is None or n2 is None:
                continue
            nm = {n1.name, n2.name}
            if en_net.name in nm and any(
                    n.net_class is NetClass.GROUND for n in (n1, n2)):
                zeners.append((ref, part.value))
        if not series:
            continue
        if not zeners:
            r_ref, r_ohm, rail = series[0]
            v_rail = rail_volts(rail.name) or 0.0
            bots = [(r, o) for r, o, other in _resistors_on(c, en_net.name)
                    if other.net_class is NetClass.GROUND]
            if bots:
                _rb, ob = bots[0]
                en_hi = PD_CONTRACT_VMAX * ob / (r_ohm + ob)
                topo = f"divider {r_ref}={r_ohm:g}R/{_rb}={ob:g}R"
            else:
                en_hi = PD_CONTRACT_VMAX - TPS54302_EN_IHYS * r_ohm
                topo = f"series {r_ref}={r_ohm:g}R only (no shunt)"
            res.checks.append(Check(
                name=f"EN clamp ceiling ({reg.ref})", sheet=sheet,
                kind="en_clamp",
                detail=f"{rail.name}={v_rail:g}V EN strap {topo}, NO clamp "
                       f"zener: EN at VIN={PD_CONTRACT_VMAX}V must stay <= the"
                       f" EN recommended-max {TPS54302_EN_RECMAX}V (TPS54302 "
                       f"has NO internal EN clamp — SLVSDG6C; PWR-1)",
                value=round(en_hi, 3), unit="V",
                lo=None, hi=TPS54302_EN_RECMAX))
            continue
        r_ref, r_ohm, rail = series[0]
        v_rail = rail_volts(rail.name) or 0.0
        z_ref, z_val = zeners[0]
        mpn = next((k for k in ZENER_5V1_VZ if z_val.startswith(k)), None)
        if mpn is None:
            res.notes.append(f"NOTE: {sheet}:{z_ref} zener {z_val} has no "
                             f"modelled Vz — EN clamp not checked")
            continue
        vz_lo, _vz_nom, vz_hi = ZENER_5V1_VZ[mpn]

        def en_at(vin: float, vz_test: float, r_ohm: float = r_ohm) -> float:
            vz_knee = vz_test - ZENER_5V1_IZT * ZENER_5V1_ZZT
            en_open = vin - TPS54302_EN_IHYS * r_ohm
            if en_open <= vz_knee:
                return en_open
            iz = (vin - vz_test + ZENER_5V1_IZT * ZENER_5V1_ZZT
                  - r_ohm * TPS54302_EN_IHYS) / (r_ohm + ZENER_5V1_ZZT)
            return vz_test + (iz - ZENER_5V1_IZT) * ZENER_5V1_ZZT

        en_turnon = min(en_at(PD_VIN_CONTRACT_LO, vz_lo),
                        en_at(PD_VIN_CONTRACT_LO, vz_hi))
        en_ceiling = en_at(PD_CONTRACT_VMAX, vz_hi)
        res.checks.append(Check(
            name=f"EN clamp turn-on ({reg.ref})", sheet=sheet, kind="en_clamp",
            detail=f"{rail.name}={v_rail:g}V -[{r_ref}={r_ohm:g}R]- EN, "
                   f"{z_ref}={z_val} zener->GND: EN at VIN={PD_VIN_CONTRACT_LO}"
                   f"V (5V contract low) must exceed enable+margin "
                   f"{TPS54302_EN_ENABLE_FLOOR}V (threshold 1.21V typ, "
                   f"SLVSDG6C) so the always-on buck is sure to start",
            value=round(en_turnon, 3), unit="V",
            lo=TPS54302_EN_ENABLE_FLOOR, hi=None))
        res.checks.append(Check(
            name=f"EN clamp ceiling ({reg.ref})", sheet=sheet, kind="en_clamp",
            detail=f"{rail.name}={v_rail:g}V -[{r_ref}={r_ohm:g}R]- EN, "
                   f"{z_ref}={z_val} zener->GND: EN at VIN={PD_CONTRACT_VMAX}"
                   f"V (20V+5%) worst-case (Vz {vz_hi}V) must stay <= the EN "
                   f"recommended-max {TPS54302_EN_RECMAX}V (no internal clamp,"
                   f" I_hys 1.55uA only — SLVSDG6C)",
            value=round(en_ceiling, 3), unit="V",
            lo=None, hi=TPS54302_EN_RECMAX))


def _boot0(sheet: str, c, res: Result) -> None:
    net = c.nets.get("BOOT0_SET")
    if net is None:
        return
    rs = [(r, o) for r, o, other in _resistors_on(c, net.name)
          if other.net_class is NetClass.POWER]
    if not rs:
        return
    r_ref, ohms = rs[0]
    v = STM32_VDD * STM32_BOOT0_PULLDOWN / (STM32_BOOT0_PULLDOWN + ohms)
    res.checks.append(Check(
        name="BOOT0 strap VIH", sheet=sheet, kind="divider",
        detail=f"DIP closed: {STM32_VDD} V through {r_ref}={ohms:g}R vs the "
               f"SoM 1k5 pull-down (contract) -> must exceed STM32 "
               f"VIH = 0.7*VDD = {STM32_VIH:.2f} V",
        value=round(v, 3), unit="V", lo=STM32_VIH, hi=STM32_VDD))


def ngspice_available() -> str | None:
    return shutil.which("ngspice")


def run_ngspice(res: Result) -> None:
    exe = ngspice_available()
    if exe is None:
        return
    ran = 0
    for ch in res.checks:
        if ch.kind not in ("divider", "fb_divider"):
            continue
        m = re.search(r"-\[\w+=([\d.eE+-]+)R\]-.*-\[\w+=([\d.eE+-]+)R\]-",
                      ch.detail)
        v = re.search(r"@ ([\d.]+) V", ch.detail)
        if ch.kind == "fb_divider":
            continue
        if not m or not v:
            continue
        rt, rb, vs = float(m.group(1)), float(m.group(2)), float(v.group(1))
        cir = (f"* schgen divider check: {ch.name}\n"
               f"V1 in 0 {vs}\nR1 in mid {rt}\nR2 mid 0 {rb}\n"
               f".op\n.print op v(mid)\n.end\n")
        with tempfile.NamedTemporaryFile("w", suffix=".cir",
                                         delete=False) as tf:
            tf.write(cir)
            path = tf.name
        proc = subprocess.run([exe, "-b", path], capture_output=True,
                              text=True, timeout=30)
        mm = re.search(r"mid\s*=?\s*([\d.eE+-]+)", proc.stdout)
        if mm:
            ch.spice_value = round(float(mm.group(1)), 4)
            ch.engine = "analytic+ngspice"
            ran += 1
    if ran:
        res.engine = (f"analytic (gate) + ngspice .op cross-check on "
                      f"{ran} divider(s), 1% agreement enforced")
    else:
        res.notes.append("NOTE: ngspice present but no check was "
                         "cross-runnable")


def report(res: Result) -> str:
    lines = ["schgen spice / analytic spot-check gate", "=" * 64, ""]
    lines.append(f"engine: {res.engine}")
    if ngspice_available() is None:
        lines.append("ngspice: NOT INSTALLED (brew install ngspice) — the "
                     "closed-form analytic layer IS the gate; every check "
                     "below is an exact linear-network solution, not an "
                     "approximation. ngspice adds an independent recompute "
                     "when present.")
    lines.append("")
    lines.append(f"checks ({len(res.checks)}):")
    for ch in res.checks:
        rng = (f"{'' if ch.lo is None else f'{ch.lo:g}'} .. "
               f"{'' if ch.hi is None else f'{ch.hi:g}'}")
        sp = f"  ngspice={ch.spice_value:g}" if ch.spice_value is not None \
            else ""
        lines.append(f"  [{'PASS' if ch.ok else 'FAIL'}] {ch.sheet}: "
                     f"{ch.name} = {ch.value:g} {ch.unit} "
                     f"(limits {rng} {ch.unit}; {ch.engine}){sp}")
        lines.append(f"         {ch.detail}")
    if res.notes:
        lines.append("")
        for n in res.notes:
            lines.append(f"  {n}")
    lines.append("")
    if res.errors:
        lines.append(f"ERRORS ({len(res.errors)}):")
        for e in res.errors:
            lines.append(f"  ERROR: {e}")
    else:
        lines.append("errors: none")
    lines.append("")
    lines.append(f"SPICE GATE: {'PASS' if res.ok else 'FAIL'} "
                 f"({len(res.checks)} checks)")
    return "\n".join(lines)


def run(sheets, reports_dir: Path, allow_ngspice: bool = True) -> Result:
    res = extract_checks(sheets)
    if allow_ngspice:
        run_ngspice(res)
    reports_dir.mkdir(parents=True, exist_ok=True)
    (reports_dir / "spice.txt").write_text(report(res) + "\n")
    return res


def cmd_spice(args) -> int:
    from schgen.core.link import all_subsystem_paths, load_subsystem
    names = args.subsystems or [p.stem for p in all_subsystem_paths()]
    sheets = [load_subsystem(n) for n in names]
    repo = Path(__file__).resolve().parents[2]
    res = run(sheets, repo / "carrier" / "reports",
              allow_ngspice=not args.no_ngspice)
    print(report(res))
    print(f"\nreport: {repo / 'carrier' / 'reports' / 'spice.txt'}")
    return 0 if res.ok else 1
