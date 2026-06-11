"""Generated SC-firmware contract header (PLAN.md round 4).

``schgen firmware`` (also run by ``schgen board``) writes
``carrier/firmware/zynq_carrier_contract.h`` — the SoM STM32 system
controller's hardware contract as pure C (no dependencies):

- every STM32-facing net: J1 pin (carrier/som_interface.json) + STM32
  GPIO port/pin (LIVE kicad-cli extraction of SoM U9 — never hand-typed),
- the BOOTSEL decode table (debug_boot dossier section (c)),
- the board I2C address map, each strapped address DERIVED from the
  authoring netlists (TCA9535 A-straps, INA3221 A0 straps),
- rail-sequencing order + per-rail/module EN mapping, READ from power.py /
  bringup_en.py / bringup_en_modules.py / bringup_rails.py netlists,
- the PA13/PA14 reserved-for-SWD warning, CROSS-CHECKED against the live
  U9 pin map (if the SoM ever moves SWD, generation fails loudly).

Deterministic: same inputs -> byte-identical header (no timestamps).
"""

from __future__ import annotations

import argparse
from pathlib import Path

from schgen import bringup_facts as bf
from schgen.link import load_subsystem

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = REPO_ROOT / "carrier" / "firmware" / "zynq_carrier_contract.h"

SOURCES = (
    "carrier/som_interface.json",
    "som/Zynq_SoM.kicad_sch (U9 pin map, live kicad-cli extraction)",
    "carrier/subsystems/power.py",
    "carrier/subsystems/power_mon.py",
    "carrier/subsystems/bringup_rails.py",
    "carrier/subsystems/bringup_en.py",
    "carrier/subsystems/bringup_en_modules.py",
    "carrier/subsystems/bringup_modules.py",
    "carrier/subsystems/debug_boot.py",
    "carrier/research/debug_boot_pmod.md (BOOTSEL decode, SWD reservation)",
    "carrier/research/power_mon.md (I2C address map)",
    "carrier/research/bringup_power_gating.md (EN-cell semantics, GPIO plan)",
)

# Rail-override GPIO plan (bringup dossier section 1: "Rails (3) = direct
# GPIOs"; the carrier->J1 binding itself is a wave-3 deferral — the GPIO
# names below are resolved to J1 pins + STM32 port/pin PROGRAMMATICALLY).
RAIL_OVERRIDE_GPIO = {
    "STM32_RAIL_EN_5V0": "STM32_GPIO1",
    "STM32_RAIL_EN_3V3": "STM32_GPIO2",
    "STM32_RAIL_EN_1V8": "STM32_GPIO3",
}
EXPANDER_INT_GPIO = ("STM32_BRINGUP_INT", "STM32_GPIO4")

# BOOTSEL decode (debug_boot dossier section (c)): value = (BOOTSEL1<<1) |
# BOOTSEL0; DIP closed = LOW (strap to GND), open = HIGH (10k to +3V3_SC).
BOOT_MODES = (("JTAG", 0x0), ("QSPI", 0x1), ("SD", 0x2), ("RESERVED", 0x3))
BOOTSEL_NETS = ("STM32_GPIO7", "STM32_GPIO8")        # BOOTSEL0, BOOTSEL1
SWD_RESERVED = {"STM32_GPIO6": ("A", 13, "SWDIO"),
                "STM32_GPIO5": ("A", 14, "SWCLK")}


class FirmwareError(ValueError):
    pass


def _jpin(entry: bf.Stm32Net) -> tuple[str, int]:
    conn, _, pin = entry.j_pins[0].partition(".")
    return conn, int(pin)


def _net_defines(entry: bf.Stm32Net, prefix: str = "ZC_") -> list[str]:
    ident = bf.c_ident(entry.net)
    lines = []
    if entry.j_pins:
        conn, pin = _jpin(entry)
        extra = ("" if len(entry.j_pins) == 1
                 else f"  /* also {', '.join(entry.j_pins[1:])} */")
        lines.append(f"#define {prefix}{ident}_{conn}_PIN {pin}{extra}")
    lines.append(f"#define {prefix}{ident}_GPIO_PORT '{entry.port}'")
    lines.append(f"#define {prefix}{ident}_GPIO_PIN {entry.pin}U")
    return lines


def _shunt_mohm(c, in_p: str, in_n: str) -> int | None:
    """The series shunt between two rail nets: the resistor with one pin on
    each (power_mon netlist)."""
    refs_p = {pr.ref for n in c.nets.values() if n.name == in_p
              for pr in n.pins if pr.ref.startswith("RS")}
    refs_n = {pr.ref for n in c.nets.values() if n.name == in_n
              for pr in n.pins if pr.ref.startswith("RS")}
    for ref in sorted(refs_p & refs_n):
        ohms = bf.parse_value_ohms(c.parts[ref].value)
        if ohms is not None:
            return round(ohms * 1000)
    return None


def generate(out: Path = DEFAULT_OUT) -> Path:
    stm32 = bf.stm32_pin_map()
    rails_c = load_subsystem("bringup_rails").circuit
    en_c = load_subsystem("bringup_en").circuit
    enm_c = load_subsystem("bringup_en_modules").circuit
    power_c = load_subsystem("power").circuit
    mods_c = load_subsystem("bringup_modules").circuit
    pmon_c = load_subsystem("power_mon").circuit
    usbpd_c = load_subsystem("usb_pd").circuit

    nets: dict[str, bf.Stm32Net] = stm32["nets"]
    internal: dict[str, bf.Stm32Net] = stm32["internal"]

    # -- cross-check the SWD reservation against the LIVE U9 pin map ----------
    for net, (port, pin, role) in SWD_RESERVED.items():
        live = nets.get(net)
        if live is None or (live.port, live.pin) != (port, pin):
            raise FirmwareError(
                f"SWD reservation drift: dossier says {net} = P{port}{pin} "
                f"({role}), live SoM netlist says "
                f"{'absent' if live is None else f'P{live.port}{live.pin}'}")

    chain = bf.regulator_chain(power_c)
    rail_cells = {c.enable: c for c in bf.en_cells(en_c)}
    mod_cells = bf.en_cells(enm_c)
    exp = bf.expander(rails_c)
    monitors = bf.ina3221_monitors(pmon_c)
    gates = {g.enable: g for g in bf.module_gates(mods_c)}
    sw1 = bf.dip_positions(rails_c, "SW1")
    sw2 = bf.dip_positions(rails_c, "SW2")
    dip_of = {p.net: f"SW{1 if p.switch == 'SW1' else 2} pos {p.position}"
              for p in sw1 + sw2}

    # -- I2C address map: strapped addresses DERIVED from the netlists --------
    if not any("FUSB302" in p.value for p in usbpd_c.parts.values()):
        raise FirmwareError("usb_pd netlist no longer carries a FUSB302 — "
                            "I2C address map stale")
    addr_rows = [
        ("ZC_I2C_ADDR_TCA9535", exp.addr,
         "bring-up override expander (bringup_rails; A2=A1=A0 straps read "
         "from the netlist)"),
        ("ZC_I2C_ADDR_FUSB302B", bf.FUSB302B_ADDR,
         "USB-PD PHY (usb_pd; fixed address, onsemi DS)"),
    ] + [
        (f"ZC_I2C_ADDR_INA3221_{k}", m.addr,
         f"rail monitor #{k} (power_mon {m.ref}; A0 strap read from the "
         f"netlist)")
        for k, m in enumerate(monitors, 1)
    ]
    addrs = [a for _, a, _ in addr_rows]
    if len(set(addrs)) != len(addrs):
        raise FirmwareError(f"I2C address collision: {[hex(a) for a in addrs]}")

    L: list[str] = []
    L.append("/*")
    L.append(" * zynq_carrier_contract.h — Zynq carrier <-> SoM STM32 system"
             "-controller")
    L.append(" * hardware contract.  GENERATED — DO NOT EDIT.")
    L.append(" *")
    L.append(" * generated-by: schgen firmware (schgen/firmware.py)")
    L.append(" * regenerate:   PYTHONPATH=. python -m schgen firmware")
    L.append(" * sources:")
    for s in SOURCES:
        L.append(f" *   {s}")
    L.append(" *")
    L.append(f" * system controller: SoM U9 = {stm32['value']}")
    L.append(" * All GPIO port/pin values are extracted LIVE from the SoM")
    L.append(" * KiCad netlist at generation time — they cannot drift from")
    L.append(" * the hardware.")
    L.append(" */")
    L.append("#ifndef ZYNQ_CARRIER_CONTRACT_H")
    L.append("#define ZYNQ_CARRIER_CONTRACT_H")
    L.append("")

    # -- section 1: the SWD warning (top — it is the one thing firmware must
    #    never break) -----------------------------------------------------------
    L.append("/* "+"="*72+" */")
    L.append("/* !! RESERVED FOR SWD — debug_boot dossier section 0, "
             "firmware contract: */")
    for net in sorted(SWD_RESERVED):
        port, pin, role = SWD_RESERVED[net]
        e = nets[net]
        conn, jp = _jpin(e)
        L.append(f"/* !!   {net} ({conn}.{jp}) = P{port}{pin} = {role} */")
    L.append("/* !! SC firmware must NEVER reconfigure PA13/PA14 — they "
             "are the SC's */")
    L.append("/* !! own SWD port (carrier SWD header, debug_boot J2). */")
    L.append("/* !! Reconfiguring them bricks debug until BOOT0-DFU "
             "recovery. */")
    L.append("/* "+"="*72+" */")
    L.append("")

    # -- section 2: STM32-facing nets on the J connectors ------------------------
    L.append("/* ---- STM32-facing nets on the SoM mezzanine connectors "
             "---------------- */")
    L.append("/* net <- J pin (carrier/som_interface.json) <- STM32 GPIO "
             "(live U9 map) */")
    for name in sorted(nets):
        e = nets[name]
        notes = []
        if name in SWD_RESERVED:
            notes.append(f"RESERVED: {SWD_RESERVED[name][2]} (see above)")
        if name == BOOTSEL_NETS[0]:
            notes.append("BOOTSEL0 request strap (debug_boot SW1 pos 2)")
        if name == BOOTSEL_NETS[1]:
            notes.append("BOOTSEL1 request strap (debug_boot SW1 pos 3)")
        for port_net, gpio in RAIL_OVERRIDE_GPIO.items():
            if name == gpio:
                notes.append(f"rail-EN override veto -> {port_net}")
        if name == EXPANDER_INT_GPIO[1]:
            notes.append("TCA9535 INT# (open-drain, 10k to +3V3_SC)")
        L.append(f"/* {name}" + (f" — {'; '.join(notes)}" if notes else "")
                 + " */")
        L.extend(_net_defines(e))
    L.append("")

    # -- section 3: STM32-driven SoM-internal control nets ------------------------
    L.append("/* ---- STM32-driven SoM-INTERNAL control nets (not on "
             "J1/J2/J3) -------- */")
    L.append("/* The SC drives Zynq boot mode / resets ON-MODULE; the "
             "carrier only */")
    L.append("/* requests via the BOOTSEL straps below (debug_boot dossier "
             "section 0). */")
    for name in sorted(n for n in internal if n.startswith("ZYNQ_")):
        e = internal[name]
        L.append(f"/* {name} — SoM-internal */")
        L.append(f"#define ZC_SOM_{bf.c_ident(name)}_GPIO_PORT '{e.port}'")
        L.append(f"#define ZC_SOM_{bf.c_ident(name)}_GPIO_PIN {e.pin}U")
    L.append("")

    # -- section 4: BOOTSEL decode table ------------------------------------------
    L.append("/* ---- BOOTSEL decode (debug_boot dossier section (c)) "
             "---------------- */")
    L.append("/* Carrier boot-request DIP (debug_boot SW1): pos 2 -> "
             "BOOTSEL0, pos 3 -> */")
    L.append("/* BOOTSEL1; closed = LOW, open = HIGH (10k pull-ups to "
             "+3V3_SC).        */")
    L.append("/* SC firmware samples BOOTSEL[1:0] at boot and drives "
             "ZYNQ_BMODE_0/2    */")
    L.append("/* on-module (constants above).  value = (BOOTSEL1 << 1) | "
             "BOOTSEL0      */")
    for k, net in enumerate(BOOTSEL_NETS):
        e = nets[net]
        conn, jp = _jpin(e)
        L.append(f"#define ZC_BOOTSEL{k}_GPIO_PORT '{e.port}'   "
                 f"/* {net}, {conn}.{jp} */")
        L.append(f"#define ZC_BOOTSEL{k}_GPIO_PIN {e.pin}U")
    for name, val in BOOT_MODES:
        L.append(f"#define ZC_BOOT_REQ_{name} 0x{val:X}")
    L.append("/* STM32_BOOT0 (debug_boot SW1 pos 1): closed pulls BOOT0 "
             "high through */")
    L.append("/* 100R against the SoM 1k5 pull-down -> closed + reset = "
             "USB DFU.      */")
    L.append("")

    # -- section 5: I2C address map ------------------------------------------------
    L.append("/* ---- I2C address map — bus STM32_I2C2, 7-bit addresses "
             "-------------- */")
    L.append("/* (power_mon dossier section 2; strapped addresses derived "
             "from the    */")
    L.append("/*  netlists at generation time)                             "
             "           */")
    for macro, addr, what in addr_rows:
        L.append(f"#define {macro} 0x{addr:02X}  /* {what} */")
    L.append("/* NOTE: the carrier J-pin binding for STM32_I2C2_SDA/SCL is "
             "a wave-3  */")
    L.append("/* deferral (no dedicated I2C nets on the J contract); "
             "bit-bang is the  */")
    L.append("/* documented fallback (bringup dossier risk R2).            "
             "           */")
    L.append("")

    # -- section 6: rail sequencing + EN cells --------------------------------------
    L.append("/* ---- Rail bring-up sequence (derived from the power.py "
             "regulator     */")
    L.append("/*      chain: each stage feeds the next) + EN-cell mapping "
             "            */")
    L.append("/* EN semantics (bringup_en): EN = DIP AND override; "
             "override is a VETO  */")
    L.append("/* — drive LOW to force a rail OFF; Hi-Z/HIGH leaves the DIP "
             "in charge. */")
    L.append("/* Software can NEVER force a rail ON with its DIP open.     "
             "           */")
    L.append(f"#define ZC_RAIL_COUNT {len(chain)}")
    for k, st in enumerate(chain):
        cell = rail_cells.get(st.enable)
        gpio_name = RAIL_OVERRIDE_GPIO.get(cell.override_net) if cell else None
        mv = round(st.vout * 1000) if st.vout is not None else 0
        L.append(f"/* stage {k}: {st.rail_in} -> {st.rail_out} "
                 f"({st.value} {st.ref}, power sheet; DIP "
                 f"{dip_of.get(cell.dip_net, '?') if cell else '?'}; "
                 f"PG LED {st.pg_led or '-'}) */")
        L.append(f"#define ZC_RAIL{k}_NAME \"{st.rail_out}\"")
        L.append(f"#define ZC_RAIL{k}_VOUT_MV {mv}")
        L.append(f"#define ZC_RAIL{k}_EN_NET \"{st.enable}\"")
        if gpio_name and gpio_name in nets:
            e = nets[gpio_name]
            L.append(f"#define ZC_RAIL{k}_OVERRIDE_GPIO_PORT '{e.port}'   "
                     f"/* {cell.override_net} -> {gpio_name} */")
            L.append(f"#define ZC_RAIL{k}_OVERRIDE_GPIO_PIN {e.pin}U")
    int_net, int_gpio = EXPANDER_INT_GPIO
    e = nets[int_gpio]
    L.append(f"#define ZC_BRINGUP_INT_GPIO_PORT '{e.port}'   "
             f"/* {int_net} -> {int_gpio} */")
    L.append(f"#define ZC_BRINGUP_INT_GPIO_PIN {e.pin}U")
    L.append("")

    # -- section 7: TCA9535 module-override port map ---------------------------------
    L.append("/* ---- TCA9535 module-override port map — READ from the "
             "bringup_rails  */")
    L.append("/*      netlist (P0x/P1x pin -> net), joined to its EN cell "
             "+ load      */")
    L.append("/*      switch.  Bit index = position in the 16-bit port "
             "word           */")
    L.append("/*      (P00=bit0 ... P17=bit15).  POR state = all inputs => "
             "DIP rules. */")
    for pname in sorted(exp.ports):
        net = exp.ports[pname]
        bit = int(pname[1]) * 8 + int(pname[2])
        cell = next((c for c in mod_cells if c.override_net == net), None)
        if cell is not None:
            g = gates.get(cell.enable)
            ctx = (f"{net} -> {cell.enable}"
                   + (f" ({g.rail_out}, ILIM {g.ilim_ma} mA, DIP "
                      f"{dip_of.get(cell.dip_net, '?')})" if g else
                      f" (DIP {dip_of.get(cell.dip_net, '?')})"))
            L.append(f"#define ZC_TCA9535_BIT_{bf.c_ident(cell.enable)} "
                     f"{bit}  /* {pname}: {ctx} */")
        else:
            note = (" (power_mon dossier reserves P11 for PMON_ALERT_N)"
                    if pname == "P11" else "")
            L.append(f"/* {pname} (bit {bit}): {net} — spare, 100k to GND"
                     f"{note} */")
    L.append("")

    # -- section 8: INA3221 channel map ------------------------------------------------
    L.append("/* ---- INA3221 rail-telemetry channel map (power_mon "
             "netlist) --------- */")
    for k, m in enumerate(monitors, 1):
        L.append(f"/* monitor #{k}: {m.ref} @ 0x{m.addr:02X} */")
        for ch in sorted(m.channels):
            inp, inn = m.channels[ch]
            if inp == "GND" and inn == "GND":
                L.append(f"/* {m.ref} ch{ch}: unused (inputs tied to GND "
                         f"per TI DS) */")
                continue
            shunt = _shunt_mohm(pmon_c, inp, inn)
            L.append(f"#define ZC_PMON{k}_CH{ch}_RAIL \"{inn}\"  "
                     f"/* {inp} -> {inn} */")
            if shunt is not None:
                L.append(f"#define ZC_PMON{k}_CH{ch}_SHUNT_MOHM {shunt}")
    L.append("")
    L.append("#endif /* ZYNQ_CARRIER_CONTRACT_H */")

    out.parent.mkdir(parents=True, exist_ok=True)
    # pure-ASCII for embedded toolchains (comments use em dashes upstream)
    text = "\n".join(L).replace("—", "--").replace("→", "->")
    out.write_text(text + "\n")
    return out


def cmd_firmware(args: argparse.Namespace) -> int:
    out = generate(args.output or DEFAULT_OUT)
    n_defines = sum(1 for line in out.read_text().splitlines()
                    if line.startswith("#define"))
    print(f"FIRMWARE CONTRACT: {out} ({n_defines} #defines)")
    return 0
