"""SoM mezzanine connector sheets (J1/J2/J3) — GENERATED, never hand-typed.

The pin→net map is loaded from ``carrier/som_interface.json`` (itself
extracted from the SoM KiCad project by ``schgen som-interface``); each
``circuit()`` instantiates the mating DF40C-100DS-0.4V(51) receptacle
(parts/DF40C-100DS-0.4V_51/, LCSC C597931) and binds EVERY pin to its
contract net VERBATIM:

- power pins  -> POWER nets (carrier spelling: the SoM writes ``VIN``, the
  carrier writes ``+VIN`` — the ONLY rail alias, mirrored from
  schgen.link.RAIL_ALIASES; all other rails are identity spellings),
- GND pins    -> the GROUND net,
- signal pins -> PORT nets. No ``expect=`` deferrals here BY DESIGN: these
  sheets ARE the SoM side of the contract, so every port resolves against
  ``som_interface.json`` by construction; consumers (ethernet, usb_pd, …)
  bind to the same names from their own sheets.

Typed ports (only applied to nets present on the connector): the four
ethernet MDI pairs (100R diff, matching the ethernet sheet), the two USB 2.0
pairs (90R), and the SDIO bus typed ``sd_bus(level_v=1.8)`` — the SoM runs
SDIO at 1.8 V straight into the Zynq (carrier/PLAN.md round 2: the carrier
microSD subsystem must level-translate).

Layout: NONE here — this module is netlist-only. The placement engine
(schgen/place.py) detects the lone >=40-pin connector and derives the
two-column label fan, per-rail trunks, sideways mid-column rail strips and
the PWR_FLAG corner row from the topology alone.
"""

from __future__ import annotations

import json
from pathlib import Path

from schgen.model import Circuit, NetClass

CONTRACT = Path(__file__).resolve().parent / "som_interface.json"

# Carrier house spelling for SoM rail names (inverse of link.RAIL_ALIASES —
# the single enumerated rail alias; signals are NEVER respelled).
RAIL_SPELLING = {"VIN": "+VIN"}

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


def connector_circuit(jref: str, name: str, title: str) -> Circuit:
    c = Circuit(name, title)
    c.use_part("DF40C-100DS-0.4V_51", ref=jref)   # 100 bare-number pins
    seen_ports: set[str] = set()
    for pin, som_net in sorted(contract_pins(jref).items(), key=lambda kv: int(kv[0])):
        net = RAIL_SPELLING.get(som_net, som_net)
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
    for p, n, kind, imp in PAIR_TYPES:
        if p in c.nets and n in c.nets:
            c.port_type(p, kind=kind, pair_with=n, impedance=imp)
    if all(s in c.nets for s in SD_BUS):
        for s in SD_BUS:
            c.port_type(s, kind="sd_bus", bus="SDIO", level_v=1.8)
    return c
