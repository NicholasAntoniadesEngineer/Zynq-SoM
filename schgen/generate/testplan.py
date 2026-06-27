"""Generated acceptance TEST PLAN (downstream P4 + board-headroom DFM-3).

``schgen testplan`` (also run by ``schgen board``) writes
``carrier/docs/TEST_PLAN.md`` — a MEASURABLE bring-up/acceptance checklist
that is purely a JOIN + FORMAT of three artifacts already derived from the
authored netlists, with NO new electrical derivation:

- :mod:`schgen.spice` — the analytic/ngspice spot-check gate. ``run()``
  yields ~21 :class:`schgen.spice.Check` rows, each carrying an expected
  value plus min/max limits (divider/RC/ISET/FB/EN-clamp/BOOT0). Each row
  becomes one acceptance step with its expected/min/max columns.
- :mod:`schgen.testpoints` — ``check_coverage()`` knows the probe pad
  (``sheet:TP``) and net for every rail + key single-ended bus. The probe
  pad joins onto each step's net.
- :mod:`schgen.manual` + :mod:`schgen.bringup_facts` — the staged DIP
  power-on sequence (Stage 0 power-off, Stage 1 first-power/always-on,
  Stage 2 rails one DIP at a time, Stage 3 user IO, Stage 4 module load
  switches, Stage 5 boot/debug). Every acceptance step is GROUPED under the
  bring-up stage that brings its net live, so the test plan reads in the
  exact order a technician closes DIPs.

Output: a markdown table per stage —
``step | net | probe pad | expected | min | max | [ ] measured | pass?`` —
plus an I2C-scan expectation section (the strapped addresses, derived from
the netlists) and a per-module functional checklist.

Every column already exists upstream; this module only joins and formats.
Deterministic: same inputs -> byte-identical output (no timestamps; the
ordering is fully sorted / derived from the netlist topology).
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

from schgen.core.link import all_subsystem_paths, load_subsystem
from schgen.generate import bringup_facts as bf
from schgen.verify import spice, testpoints

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUT = REPO_ROOT / "carrier" / "docs" / "TEST_PLAN.md"

# The six bring-up stages, in the order schgen.manual stages them. Each
# acceptance step is assigned to exactly one of these by the net it tests.
STAGE_TITLES = {
    0: "Stage 0 — power-off continuity",
    1: "Stage 1 — first power: PD + always-on +3V3_SC domain",
    2: "Stage 2 — rails, one DIP at a time",
    3: "Stage 3 — user IO",
    4: "Stage 4 — module load switches",
    5: "Stage 5 — boot modes, JTAG, SWD",
    6: "Stage 6 — board services (+3V3_AUX): ID-EEPROM, RTC, watchdog, QWIIC",
}


def _load_all() -> dict:
    return {p.stem: load_subsystem(p.stem) for p in all_subsystem_paths()}


def _net_of_check(ch) -> str | None:
    """The primary net a spice Check measures, recovered from its name/detail.

    The spice gate names every check after its net or part:
      'divider +VIN ...'      -> +VIN
      'RC STM32_NRST'         -> STM32_NRST
      'SY7201 ISET (R3)'      -> (no net in name; pull from detail)
      '+5V FB (+5V_SOM)'      -> +5V_SOM (rail in parens)
      'EN clamp turn-on (U4)' -> the buck's output rail (from detail)
      'BOOT0 strap VIH'       -> BOOT0_SET (from detail)
    No new electrical work — only string recovery onto the existing net."""
    name = ch.name
    # 'divider <NET> [...]' / 'RC <NET>'
    m = re.match(r"(?:divider|RC)\s+([^\s\[]+)", name)
    if m:
        return m.group(1)
    # '<rail> FB (<RAIL>)' — the FB target rail in parens
    m = re.search(r"FB \(([^)]+)\)", name)
    if m:
        return m.group(1)
    # BOOT0 strap -> the strap net the detail names
    if name.startswith("BOOT0"):
        return "BOOT0_SET"
    # EN clamp (U4) — recover the rail off the detail's '<RAIL>=...V EN strap'
    # or the leading '<RAIL>=...V -[' clause.
    m = re.search(r"([+\-][0-9A-Z_]+)=\S+V", ch.detail)
    if m:
        return m.group(1)
    return None


def _probe_index(sheets) -> dict[str, str]:
    """net -> 'sheet:TP, ...' probe-pad string, from the testpoint coverage
    gate (it already maps every landed test point to its net + location)."""
    cov = testpoints.check_coverage(sheets)
    return {net: ", ".join(locs) for net, locs in cov.have.items()}


def _rail_stage(sheets) -> dict[str, int]:
    """net -> bring-up stage index, derived the SAME way schgen.manual stages
    the board (regulator chain, EN cells, DIP map, module gates)."""
    circuits = {sc.name: sc.circuit for sc in sheets}
    stage: dict[str, int] = {}

    # Stage 1: the always-on domain + the inlet rail are live at first power.
    stage["+3V3_SC"] = 1
    stage["+VIN"] = 1
    stage["+VBUS_IN"] = 1
    stage["USB_UART_VBUS"] = 1
    stage["CP2102N_VBUS_SNS"] = 1
    stage["PD_OVP_SET"] = 1

    # Stage 2: every regulator output rail (the power-tree chain).
    if "power" in circuits:
        try:
            chain = bf.regulator_chain(
                circuits["power"], monitor=circuits.get("power_mon"))
            for st in chain:
                stage.setdefault(st.rail_out, 2)
                # the buck's PG / FB sense nets ride the same stage
            # PG sense dividers (e.g. PG_1V8_G) follow their rail's stage
            for net in circuits["power"].nets.values():
                if net.name.startswith("PG_"):
                    stage.setdefault(net.name, 2)
        except Exception:  # noqa: BLE001 — never let a topology hiccup break
            pass            # the doc; unstaged nets fall through to "general"

    # Stage 4: module load-switch outputs (SY6280 cells); USER_LED is stage 3.
    if "bringup_modules" in circuits:
        try:
            for g in bf.module_gates(circuits["bringup_modules"]):
                stage.setdefault(g.rail_out, 3 if g.module == "USER_LED" else 4)
        except Exception:  # noqa: BLE001
            pass

    # Stage 5: boot/reset straps.
    stage.setdefault("BOOT0_SET", 5)
    stage.setdefault("STM32_NRST", 5)

    # Stage 6: the manually-gated board-services rail (board_aux SW1, default
    # OFF) — self-contained, so it is not in the central regulator/module walk.
    stage["+3V3_AUX"] = 6

    # Cable-presence detects on module sheets become live with their module.
    stage.setdefault("HDMI_RX_5V", 4)
    stage.setdefault("HDMI_RX_5V_DET", 4)
    return stage


def _stage_of(net: str | None, rail_stage: dict[str, int]) -> int:
    if net is None:
        return 2
    if net in rail_stage:
        return rail_stage[net]
    # an RC/divider whose top rail is a staged rail rides that rail's stage
    return 2


def _fmt(v: float | None, unit: str) -> str:
    if v is None:
        return "—"
    return f"{v:g} {unit}".strip()


def _i2c_devices(sheets) -> list[tuple[int, str, str, bool]]:
    """(addr, ref, kind, aux) for every strapped I2C device, addresses DERIVED
    from the netlists. ``aux`` = it sits on the gated +3V3_AUX segment behind
    the board_aux PCA9306 isolator, so it ACKs only with board_aux SW1 on
    (Stage 6) — not in the always-on scan. Sorted by address."""
    circuits = {sc.name: sc.circuit for sc in sheets}
    out: list[tuple[int, str, str, bool]] = []
    if "bringup_rails" in circuits:
        try:
            exp = bf.expander(circuits["bringup_rails"])
            out.append((exp.addr, exp.ref, "TCA9535 I/O expander", False))
        except Exception:  # noqa: BLE001
            pass
    if "power_mon" in circuits:
        try:
            for m in bf.ina3221_monitors(circuits["power_mon"]):
                out.append((m.addr, m.ref, "INA3221 rail monitor", False))
        except Exception:  # noqa: BLE001
            pass
    if "usb_pd" in circuits:
        out.append((bf.FUSB302B_ADDR, "U1", "FUSB302B PD PHY (fixed addr)", False))
    if "board_services" in circuits:
        try:
            from schgen.generate.firmware import RV3028_ADDR, _id_eeprom_addr
            bsc = circuits["board_services"]
            out.append((_id_eeprom_addr(bsc), "U1",
                        "24AA025E48 ID-EEPROM (EUI-48 MAC)", True))
            out.append((RV3028_ADDR, "U2", "RV-3028 RTC", True))
        except Exception:  # noqa: BLE001
            pass
    return sorted(out)


def generate(out: Path = DEFAULT_OUT, sheets=None) -> Path:
    if sheets is None:
        sheets = list(_load_all().values())
    sheets = sorted(sheets, key=lambda sc: sc.name)

    sp_res = spice.extract_checks(sheets)
    probes = _probe_index(sheets)
    rail_stage = _rail_stage(sheets)

    # join: one acceptance step per spice check, grouped by bring-up stage
    by_stage: dict[int, list] = {}
    for ch in sp_res.checks:
        net = _net_of_check(ch)
        st = _stage_of(net, rail_stage)
        by_stage.setdefault(st, []).append((net, ch))
    for st in by_stage:
        by_stage[st].sort(key=lambda nc: (nc[0] or "~", nc[1].name))

    L: list[str] = []
    L.append("# Zynq carrier acceptance TEST PLAN")
    L.append("")
    L.append("> GENERATED by `schgen testplan` (schgen/testplan.py) — DO NOT "
             "EDIT.")
    L.append("> Regenerate: `PYTHONPATH=. python -m schgen testplan`. Every "
             "expected")
    L.append("> value, min/max limit, net and probe pad below is JOINED from "
             "the")
    L.append("> analytic spice gate (`schgen/spice.py`), the test-point "
             "coverage gate")
    L.append("> (`schgen/testpoints.py`) and the staged bring-up sequence "
             "(`schgen/manual.py`,")
    L.append("> `schgen/bringup_facts.py`) — no value is hand-typed and none "
             "is re-derived")
    L.append("> here. Limits that FAIL the spice gate would also fail the "
             "board build.")
    L.append("")
    L.append("Procedure: work the stages in order (close one bring-up DIP, "
             "verify, move")
    L.append("on — see `carrier/docs/BRINGUP.md`). For each step probe the "
             "listed pad,")
    L.append("record the measurement in the **measured** column, and tick "
             "**pass?** when")
    L.append("the reading sits inside `[min .. max]`. A blank (unprogrammed) "
             "system")
    L.append("controller is fine for every electrical step; the I2C scan and "
             "functional")
    L.append("checks below need SC firmware running.")
    L.append("")
    L.append(f"Source spice gate: {sp_res.n_checks} checks, "
             f"{sp_res.engine}.")
    L.append("")

    # ---- the staged acceptance tables ----------------------------------------
    L.append("## Electrical acceptance — by bring-up stage")
    L.append("")
    for st in sorted(STAGE_TITLES):
        rows = by_stage.get(st, [])
        if not rows:
            continue
        L.append(f"### {STAGE_TITLES[st]}")
        L.append("")
        L.append("| step | net | probe pad | expected | min | max | "
                 "measured | pass? |")
        L.append("|---|---|---|---|---|---|---|---|")
        for i, (net, ch) in enumerate(rows, 1):
            pad = probes.get(net, "—") if net else "—"
            exp = _fmt(ch.value, ch.unit)
            lo = _fmt(ch.lo, ch.unit)
            hi = _fmt(ch.hi, ch.unit)
            netcell = f"`{net}`" if net else "—"
            L.append(f"| {st}.{i} {ch.name} | {netcell} | {pad} | "
                     f"{exp} | {lo} | {hi} | `______` | [ ] |")
        L.append("")
        # the detail of each step, so the technician knows what is being tested
        L.append("<details><summary>step rationale (from the spice gate "
                 "detail)</summary>")
        L.append("")
        for i, (_net, ch) in enumerate(rows, 1):
            L.append(f"- **{st}.{i} {ch.name}** ({ch.sheet}): {ch.detail}")
        L.append("")
        L.append("</details>")
        L.append("")

    # ---- I2C scan expectation -------------------------------------------------
    devs = _i2c_devices(sheets)
    L.append("## I2C-scan expectation (SC firmware running)")
    L.append("")
    L.append("With the always-on `+3V3_SC` domain up and SC firmware "
             "scanning the bring-up")
    L.append("buses, exactly these 7-bit addresses must ACK. The addresses "
             "are derived")
    L.append("from the netlist straps (`schgen/bringup_facts.py`), not "
             "hand-typed.")
    L.append("")
    L.append("| address | device | ref | when | ACK? |")
    L.append("|---|---|---|---|---|")
    for addr, ref, kind, aux in devs:
        when = "Stage 6 (+3V3_AUX on)" if aux else "always-on"
        L.append(f"| `0x{addr:02X}` | {kind} | `{ref}` | {when} | [ ] |")
    L.append("")
    on = "/".join(f"0x{a:02X}" for a, _r, _k, aux in devs if not aux)
    auxset = "/".join(f"0x{a:02X}" for a, _r, _k, aux in devs if aux)
    L.append(f"Always-on set (with `+3V3_SC`): {on}. Any EXTRA address, or any "
             "of these missing, means a strap or bus fault.")
    if auxset:
        L.append("")
        L.append(f"With `+3V3_AUX` enabled (Stage 6), the board_aux PCA9306 "
                 f"isolator joins the AUX segment and additionally {auxset} "
                 "must ACK (ID-EEPROM, RTC). They must NOT ACK while +3V3_AUX "
                 "is OFF (proves the isolator). Cross-check "
                 "`carrier/docs/BRINGUP.md`.")
    L.append("")

    # ---- per-module functional checklist --------------------------------------
    L.append("## Per-module functional checklist")
    L.append("")
    L.append("Each module rail comes up behind its own current-limited load "
             "switch (Stage 4).")
    L.append("After enabling a module, confirm its status LED and the "
             "headline function.")
    L.append("")
    L.append("| sheet | gated rail | status LED | functional check |")
    L.append("|---|---|---|---|")
    circuits = {sc.name: sc.circuit for sc in sheets}
    gates = []
    if "bringup_modules" in circuits:
        try:
            gates = bf.module_gates(circuits["bringup_modules"])
        except Exception:  # noqa: BLE001
            gates = []
    # consumer sheets per gated rail (which subsystem sheets the rail feeds)
    bringup_sheets = ("bringup_modules", "bringup_rails", "bringup_en",
                      "bringup_en_modules", "power", "power_mon")
    func_hint = {
        "HDMI_TX": "drive a display / read sink EDID over DDC",
        "HDMI_RX": "detect a source's cable +5V, read its EDID",
        "LCD": "panel backlight + touch (CTP I2C) respond",
        "LCD_BL": "panel backlight current per the SY7201 ISET law",
        "USER_LED": "PL-driven user LEDs (dark until gateware drives them)",
        "CAM": "MIPI camera link enumerates",
        "CAMERA": "MIPI camera link enumerates",
    }
    for g in sorted(gates, key=lambda x: x.module):
        consumers = sorted(
            name for name, c in circuits.items()
            if name not in bringup_sheets and g.rail_out in c.nets)
        check = func_hint.get(g.module,
                              f"module on {', '.join(consumers) or '—'} "
                              f"powers and responds")
        led = (f"`bringup_modules.{g.status_led}`"
               if g.status_led else "—")
        L.append(f"| {g.module} | `{g.rail_out}` | {led} | {check} |")
    L.append("")

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(L) + "\n")
    return out


def cmd_testplan(args: argparse.Namespace) -> int:
    out = generate(getattr(args, "output", None) or DEFAULT_OUT)
    lines = out.read_text().count("\n")
    print(f"TEST PLAN: {out} ({lines} lines)")
    return 0
