"""SoM mezzanine connector sheets (J1/J2/J3) — GENERATED, never hand-typed.

devkit_mini copy of carrier/som_conn_gen.py; same SoM, same DF40C-100DP plug
(LCSC C531031), same P0 VIN->+5V_SOM rebind and round-5 +3V3/+1V8 isolation.
The pin->net map loads from devkit_mini/som_interface.json. Every unmapped
signal pin keeps its verbatim contract spelling and resolves against the
contract by construction.

Devkit deltas vs the carrier (each a deliberate authoring decision):
- FUNCTION_MAP is reduced to the consumers this board carries: the PS UART0
  console MIO pins + the bank-13 EMIO CTS/RTS pair (uart_bridge) and the
  bit-banged STM32_I2C2 on the DAC pins (power_mon). Every other carrier
  function (bringup EN vetoes, SC_INT_N, LCD/HDMI/FMC/CAM/PMOD/ESC/microSD,
  DBG_UART) has no consumer sheet here, so those pins stay verbatim spares.
- PUDC_STRAPS is empty: the bank-34 PUDC pin (J3.39) is exposed verbatim.
  The 10k strap the carrier places on bringup_rails DOES NOT EXIST YET on
  this board — it must land on a devkit straps sheet before fabrication.
- VCCO_RAIL_MAP powers ALL four HR banks (13/33/34/35) from +3V3. The
  carrier's +2V5_VADJ rail exists only for its LVDS_25 camera/FMC loads;
  this board has none, and an unused HR bank VCCO at 3.3 V is in-spec.
- FUNCTION_PAIR_TYPES is empty (no mapped function nets form pairs here).
- STM32_I2C2 pull-ups live on the carrier's bringup_rails; on this board the
  bus is pulled NOWHERE yet — same straps-sheet debt as PUDC.

MIO voltage-mode straps ZYNQ_PS_MIO7/VM0 (J1.40) + ZYNQ_PS_MIO8\\VM1 (J1.36)
are sampled at POR and strapped ON THE SoM: DO NOT LOAD — never add a pull,
driver, or consumer on the carrier side.
"""

from __future__ import annotations

import json
from pathlib import Path

from schgen.core.model import Circuit, NetClass

CONTRACT = Path(__file__).resolve().parent / "som_interface.json"

# PLAN "P0 + wave-3 decisions" REBIND (UNIT 2, user-signed-off 2026-06-12):
# the SoM net VIN (J1.1-14) is the module's 4.2-5V input. Binding it to the
# carrier 20V PD rail +VIN destroys the SoM at the first PD contract
# (wave3_function_map.md P0). It is REBOUND to the carrier +5V_SOM rail —
# the always-on LM61460 buck (power_som.py U4, 6 A). This is NEVER a
# silent spelling change: REBOUND_SOM_RAILS documents the SoM-net ->
# carrier-rail map with its rationale, schgen.link.REBOUND_SOM_RAILS is the
# policy twin (it accounts the SoM VIN census under +5V_SOM), and the linker
# ERRORs if the two maps drift. The carrier +VIN rail still exists (pd_input/
# power/power_mon) but NO LONGER reaches the SoM connector.
REBOUND_SOM_RAILS: dict[str, str] = {
    "VIN": "+5V_SOM",   # SoM 4.2-5V input -> carrier always-on +5V_SOM buck
}

# Carrier house spelling for SoM rail names. Only the P0 rebind above (no
# plain spelling aliases remain — the former VIN -> +VIN was the rebind's
# pre-P0 form). Signals are NEVER respelled.
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

# PLAN round-5 RAIL ISOLATION (user decision 2026-06-12) — carrier bucks WIN.
# The SoM exports its own +3V3 (J1.24-27) and +1V8 (J1.56/58/60) from its
# on-module MPM3834 stages, while carrier power.py regulates same-named
# rails from its own bucks (LM61460 U2 / AP2112K U3). Binding these pins
# would put two regulators in parallel on one net (the power-tree gate's
# PARALLEL-SOURCE finding). Resolution: the pins become EXPLICIT author
# no-connects on the carrier — never silently dropped. Each isolated pin is
# emitted as a KiCad no-connect and the per-sheet netlist gate proves every
# one; schgen.link.ISOLATED_SOM_RAILS (this map's policy twin, next to
# RAIL_ALIASES) reports the isolation in the rail census and ERRORs if a
# connector sheet ever re-binds an isolated rail. The nets stay distinct;
# the SoM-side rails remain on-module only.
ISOLATED_SOM_RAILS: dict[str, str] = {
    "+3V3": "SoM MPM3834 3V3 output on J1.24-27 — carrier LM61460 "
            "(power:U2) is the only +3V3 source",
    "+1V8": "SoM MPM3834 1V8 output on J1.56/58/60 — carrier AP2112K "
            "(power:U3) is the only +1V8 source",
}

# Differential pairs on the contract (applied only when both nets are on the
# connector being generated). Impedances per the JLC04161H-7628 stackup plan.
PAIR_TYPES = [
    ("ETH_PHY_MDI0_P", "ETH_PHY_MDI0_N", "diff_pair", 100),
    ("ETH_PHY_MDI1_P", "ETH_PHY_MDI1_N", "diff_pair", 100),
    ("ETH_PHY_MDI2_P", "ETH_PHY_MDI2_N", "diff_pair", 100),
    ("ETH_PHY_MDI3_P", "ETH_PHY_MDI3_N", "diff_pair", 100),
    ("STM32_USB_D_P", "STM32_USB_D_N", "usb_hs_pair", None),
    ("USB_D+", "USB_D-", "usb_hs_pair", None),
]
# SoM-side SDIO runs at 1.8 V (verified against the SoM netlist 2026-06-10).
SD_BUS = ["SDIO_CLK", "SDIO_CMD", "SDIO_D0", "SDIO_D1", "SDIO_D2", "SDIO_D3"]


def contract_pins(jref: str) -> dict[str, str]:
    data = json.loads(CONTRACT.read_text())
    return data["connectors"][jref]["pins"]


def resolve_net(som_net: str) -> str:
    """The carrier net a SoM contract pin lands on, after the wave-3 binds:
    P0 rail rebind > VCCO bank-rail source tie > wave-3 FUNCTION map >
    PUDC strap port > verbatim. The VCCO tie (SYS-1) merges each +VCCO_* contact
    pin onto its carrier rail (+3V3 / +2V5_VADJ) as an in-fan RAIL TAP — the
    carrier buck/LDO is the source; the DF40 pin is one more tap on the rail."""
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
    # DF40 PLUG (DP), not the receptacle (DS). The SOM is fabricated with the DS
    # receptacle on J1/J2/J3, and DF40 mates ONLY DP-plug <-> DS-receptacle — two
    # DS would never interlock (a 300-pin system no-mate the SOM<->carrier audit
    # caught, 2026-06-20). The carrier is the schgen-controlled side, so it carries
    # the plug. Signal pins 1-100 keep the SAME contract net->pad-number map (the
    # Hirose DP/DS pair mates pad-N<->pad-N by design — the DP's mirrored pin-1
    # X=-9.8 vs DS X=+9.8 IS the face-to-face mating geometry); the DP's 4 extra
    # pads (101-104) are mechanical hold-down nails -> NC below.
    c.use_part("DF40C-100DP-0.4V_51", ref=jref)   # 100 signal + 4 hold-down pads
    seen_ports: set[str] = set()
    for pin in ("101", "102", "103", "104"):      # plug mechanical hold-downs
        c.nc(f"{jref}.{pin}")
    for pin, som_net in sorted(contract_pins(jref).items(), key=lambda kv: int(kv[0])):
        if som_net in ISOLATED_SOM_RAILS:
            # round-5 isolation: explicit per-pin no-connect (see map above).
            # keyed on the SoM contract name, never a rebound spelling.
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
                    f"— the engine's connector fan assumes one row per signal; extend it")
            seen_ports.add(net)
            c.port(net, f"{jref}.{pin}")
    # typed pairs: the verbatim contract pairs (ethernet/USB) AND the wave-3
    # function pairs (HDMI/camera/FMC) — applied only when both ends are on
    # THIS connector, so the constraints exporter sees both
    for p, n, kind, imp in PAIR_TYPES + FUNCTION_PAIR_TYPES:
        if p in c.nets and n in c.nets:
            c.port_type(p, kind=kind, pair_with=n, impedance=imp)
    if all(s in c.nets for s in SD_BUS):
        for s in SD_BUS:
            c.port_type(s, kind="sd_bus", bus="SDIO", level_v=1.8)
    # power-tree budget (round 4 + P0 rebind): the SoM module is now a
    # +5V_SOM load (J1.1-14 -> on-module TPS7A20/2x MPM3834/MPM3822/
    # TPSM82864 regulators feeding Zynq + DDR3L + PHYs). 10 W class worst
    # case AT the regulated 4.65 V -> ~2.15 A (10 W / 4.65 V; wave3_function_map
    # P0 point 2) — booked at the regulated rail, not 5 V. The +5V_SOM buck
    # (power_som.py U4) is a 6 A LM61460 — 2.15 A is ~36 %, ample headroom.
    # ESTIMATE pending an SoM power-budget measurement at bring-up.
    if jref == "J1":
        c.draws("+5V_SOM", 2.15, "SoM module (Zynq+DDR3L+PHYs) ~10 W class "
                                 "at the regulated 4.65 V (P0 rebind) — "
                                 "estimate, refine at bring-up")
    # VCCO bank-rail LOADS (SYS-1): the +VCCO_* contact pins now MERGE onto the
    # carrier rails (resolve_net via VCCO_RAIL_MAP) — so each connector draws its
    # banks' VCCO current from +3V3 / +2V5_VADJ, declared where the bank is the
    # consumer. The Zynq SelectIO VCCO is mA-class static (bank logic + LVCMOS
    # output drive); the dominant +2V5_VADJ entry (bank 35) is the 0.050 A the
    # FMC re-budget reserves (wave3_function_map.md sec 3.1 — fmc.py dropped its
    # mezzanine allocation 0.400 -> 0.350 A to fit the TLV75725 DBV envelope).
    # No waive_tp: the rails are sourced (their bucks/LDO), so the power-tree
    # gate sees a real, sourced load — not a deferred orphan.
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
