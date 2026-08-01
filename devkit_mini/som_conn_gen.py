from __future__ import annotations

import json
from pathlib import Path

from devkit_mini.basis import register
from schgen.core.model import Circuit, NetClass

CONTRACT = Path(__file__).resolve().parent / "som_interface.json"

MEZZANINE_PLUG = register(
    "som_conn.mezzanine_plug", "DF40C-100DP-0.4V_51", "part",
    "The board carries the PLUG (DP), never a second receptacle: the SoM is "
    "fabricated with the DS receptacle on J1/J2/J3 and DF40 mates ONLY "
    "DP<->DS. Two DS would not interlock — a 300-pin no-mate the SoM<->carrier "
    "audit caught 2026-06-20. Signal pins 1-100 keep the same net->pad map; "
    "pads 101-104 are mechanical hold-down nails.",
    "datasheet")

MODULE_DRAW_A = register(
    "som_conn.module_draw", 2.15, "A",
    "SoM module (Zynq + DDR3L + PHYs) ~10 W class booked AT the regulated "
    "4.65 V, not at 5 V: 10/4.65 = 2.15 A. ESTIMATE pending an SoM "
    "power-budget measurement at bring-up.",
    "policy")

SDIO_LEVEL_V = register(
    "som_conn.sdio_level", 1.8, "V",
    "The SoM runs SDIO at 1.8 V straight into the Zynq (verified against the "
    "SoM netlist 2026-06-10), which is why the microSD subsystem must "
    "level-translate.",
    "measured")

REBOUND_SOM_RAILS: dict[str, str] = {
    "VIN": register(
        "som_conn.vin_rebind", "+5V_SOM", "net",
        "P0, user-signed-off 2026-06-12: the SoM VIN (J1.1-14) is the module's "
        "4.2-5 V input. Binding it to a 20 V PD rail destroys the SoM at the "
        "first PD contract, so it is REBOUND to the always-on LM61460 buck. "
        "schgen.link.REBOUND_SOM_RAILS is the policy twin and the linker "
        "ERRORs if the two maps drift.",
        "datasheet"),
}

# Sampled at POR to set the MIO bank I/O voltage and strapped ON THE SoM: a
# board-side pull/driver/consumer would fight the strap and mis-set that voltage.
DO_NOT_LOAD_STRAPS: frozenset[str] = frozenset({
    "ZYNQ_PS_MIO7/VM0", "ZYNQ_PS_MIO8\\VM1",
})

RAIL_SPELLING = dict(REBOUND_SOM_RAILS)

FUNCTION_MAP: dict[str, str] = {
    "ZYNQ_PS_MIO10": "ZYNQ_PS_UART0_RXD",
    "ZYNQ_PS_MIO11": "ZYNQ_PS_UART0_TXD",
    "IO_L18_P_13": "ZYNQ_PS_UART0_CTS_N",
    "IO_L18_N_13": "ZYNQ_PS_UART0_RTS_N",
    "STM32_DAC1": "STM32_I2C2_SDA",
    "STM32_DAC2": "STM32_I2C2_SCL",
}

PUDC_STRAPS: dict[str, str] = {}

FUNCTION_PAIR_TYPES: list[tuple[str, str, str, int | None]] = []

VCCO_RAIL_MAP: dict[str, str] = {
    "+VCCO_13": "+3V3",
    "+VCCO_33": "+3V3",
    "+VCCO_34": "+3V3",
    "+VCCO_35": "+3V3",
}

ISOLATED_SOM_RAILS: dict[str, str] = {
    "+3V3": "SoM MPM3834 3V3 output on J1.24-27 — carrier LM61460 "
            "(power:U2) is the only +3V3 source",
    "+1V8": "SoM MPM3834 1V8 output on J1.56/58/60 — carrier AP2112K "
            "(power:U3) is the only +1V8 source",
}

PAIR_TYPES = [
    ("ETH_PHY_MDI0_P", "ETH_PHY_MDI0_N", "diff_pair", 100),
    ("ETH_PHY_MDI1_P", "ETH_PHY_MDI1_N", "diff_pair", 100),
    ("ETH_PHY_MDI2_P", "ETH_PHY_MDI2_N", "diff_pair", 100),
    ("ETH_PHY_MDI3_P", "ETH_PHY_MDI3_N", "diff_pair", 100),
    ("STM32_USB_D_P", "STM32_USB_D_N", "usb_hs_pair", None),
    ("USB_D+", "USB_D-", "usb_hs_pair", None),
]
SD_BUS = ["SDIO_CLK", "SDIO_CMD", "SDIO_D0", "SDIO_D1", "SDIO_D2", "SDIO_D3"]


def contract_pins(jref: str) -> dict[str, str]:
    data = json.loads(CONTRACT.read_text())
    return data["connectors"][jref]["pins"]


def _assert_straps_unloaded() -> None:
    loaded = DO_NOT_LOAD_STRAPS & (set(FUNCTION_MAP) | set(PUDC_STRAPS)
                                   | set(VCCO_RAIL_MAP) | set(RAIL_SPELLING))
    if loaded:
        raise AssertionError(
            f"som_conn_gen: MIO voltage-mode straps must stay unmapped on the "
            f"board — {sorted(loaded)} would fight the SoM strap at POR")


_assert_straps_unloaded()


def resolve_net(som_net: str) -> str:
    if som_net in RAIL_SPELLING:
        return RAIL_SPELLING[som_net]
    if som_net in VCCO_RAIL_MAP:
        return VCCO_RAIL_MAP[som_net]
    if som_net in FUNCTION_MAP:
        return FUNCTION_MAP[som_net]
    if som_net in PUDC_STRAPS:
        return PUDC_STRAPS[som_net]
    return som_net


def connector_circuit(jref: str, name: str, title: str) -> Circuit:
    c = Circuit(name, title)
    c.use_part(MEZZANINE_PLUG, ref=jref)
    seen_ports: set[str] = set()
    for pin in ("101", "102", "103", "104"):
        c.nc(f"{jref}.{pin}")
    for pin, som_net in sorted(contract_pins(jref).items(), key=lambda kv: int(kv[0])):
        if som_net in ISOLATED_SOM_RAILS:
            c.nc(f"{jref}.{pin}")
            continue
        net = resolve_net(som_net)
        cls = Circuit.classify(net)
        if cls in (NetClass.POWER, NetClass.GROUND):
            c.net(net, f"{jref}.{pin}")
        else:
            if net in seen_ports:
                raise ValueError(
                    f"{jref}: contract net {net!r} repeats on this connector "
                    f"— the engine's connector fan assumes one row per signal; "
                    f"extend it")
            seen_ports.add(net)
            c.port(net, f"{jref}.{pin}")
        if som_net in DO_NOT_LOAD_STRAPS and net != som_net:
            raise AssertionError(
                f"{jref}.{pin}: MIO voltage-mode strap {som_net!r} resolved to "
                f"{net!r} — it must stay verbatim and unloaded on the board")
    for p, n, kind, imp in PAIR_TYPES + FUNCTION_PAIR_TYPES:
        if p in c.nets and n in c.nets:
            c.port_type(p, kind=kind, pair_with=n, impedance=imp)
    if all(s in c.nets for s in SD_BUS):
        for s in SD_BUS:
            c.port_type(s, kind="sd_bus", bus="SDIO", level_v=SDIO_LEVEL_V)
    if jref == "J1":
        c.draws("+5V_SOM", MODULE_DRAW_A,
                "SoM module (Zynq+DDR3L+PHYs) ~10 W class "
                "at the regulated 4.65 V (P0 rebind) — "
                "estimate, refine at bring-up")
    vcco_draw = {
        ("J2", "+3V3"): (0.020, "Zynq banks 13+33 VCCO (LVCMOS33 static + "
                                "PL output drive) + on-SoM BMI323 VDDIO rider"),
        ("J3", "+3V3"): (0.020, "Zynq banks 34+35 VCCO static (both +3V3 on "
                                "this board; bank 35 unused, no LVDS load)"),
    }
    for rail in sorted(c.nets):
        spec = vcco_draw.get((jref, rail))
        if spec is not None:
            c.draws(rail, spec[0], spec[1])
    return c
