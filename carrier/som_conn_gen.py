"""SoM mezzanine connector sheets (J1/J2/J3) — GENERATED, never hand-typed.

The pin→net map is loaded from ``carrier/som_interface.json`` (itself
extracted from the SoM KiCad project by ``schgen som-interface``); each
``circuit()`` instantiates the mating DF40C-100DS-0.4V(51) receptacle
(parts/DF40C-100DS-0.4V_51/, LCSC C597931) and binds EVERY pin to its
contract net VERBATIM:

- power pins  -> POWER nets (carrier spelling). The P0 rebind below maps the
  SoM ``VIN`` (J1.1-14) onto the carrier always-on ``+5V_SOM`` buck — the SoM
  is a 4.2-5V module, never the 20V PD rail (REBOUND_SOM_RAILS, twin of
  schgen.link.REBOUND_SOM_RAILS). All other rails are identity spellings,
  EXCEPT the round-5 ISOLATED SoM rails (below) which are explicit author
  no-connects,
- GND pins    -> the GROUND net,
- signal pins -> PORT nets. No ``expect=`` deferrals here BY DESIGN: these
  sheets ARE the SoM side of the contract, so every port resolves against
  ``som_interface.json`` by construction; consumers (ethernet, usb_pd, …)
  bind to the same names from their own sheets.

WAVE-3 FUNCTION MAP (``FUNCTION_MAP``, this module): the raw SoM contract
names are mostly abstract (``STM32_GPIO1``, ``IO_L16_P_13``, ``ZYNQ_PS_MIO10``
…). The wave-3 binding (carrier/research/wave3_function_map.md, PLAN "P0 +
wave-3 decisions") assigns each a concrete carrier FUNCTION
(``STM32_RAIL_EN_5V0``, ``LCD_CTP_SDA``, ``ZYNQ_PS_UART0_RXD`` …). The J-sheet
generator emits the FUNCTION name as the port net for every mapped pin, so the
consumer subsystem (bringup_en, lcd, uart_bridge, …) resolves its same-named
port against THIS sheet — retiring its ``expect=`` deferral. Unmapped pins
(spares, plain MIO, already-bound contract names like the ETH/USB/SDIO/JTAG
nets) keep their verbatim contract spelling. The map is the netlist-visible
half of wave-3: every entry is a real port-label rename on som_j1/j2/j3, so the
goldens for the three J sheets re-bless. ``SC_INT_N`` (STM32_GPIO4) binds TWO
consumers (bringup_rails INT# + usb_pd FUSB302 INT) onto one J port — the
linker accepts a multi-consumer merge, exactly like STM32_NRST.

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

from schgen.core.model import Circuit, NetClass

CONTRACT = Path(__file__).resolve().parent / "som_interface.json"

# PLAN "P0 + wave-3 decisions" REBIND (UNIT 2, user-signed-off 2026-06-12):
# the SoM net VIN (J1.1-14) is the module's 4.2-5V input. Binding it to the
# carrier 20V PD rail +VIN destroys the SoM at the first PD contract
# (wave3_function_map.md P0). It is REBOUND to the carrier +5V_SOM rail —
# the always-on TPS54302 buck added in UNIT 1 (power.py U4). This is NEVER a
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

# ===========================================================================
# WAVE-3 FUNCTION MAP  {som_contract_net: carrier_function_net}
# ---------------------------------------------------------------------------
# The authoritative source is carrier/research/wave3_function_map.md (sections
# 1, 2, 4) as adopted in carrier/PLAN.md "P0 + wave-3 decisions" (with the
# round-5 reconciliation: USBOTG_FLT_N lands on TCA9535 P14 — handled on
# bringup_rails, not here). EVERY entry was verified pin-by-pin against
# som_interface.json before commit. A mapped pin emits the FUNCTION name as its
# port; the matching consumer sheet binds to it (its expect= deferral retires).
# Spare/plain/already-bound contract nets are NOT listed (they keep verbatim
# names): ETH_*, USB_*, SDIO_*, ZYNQ_T*, STM32_USB_*, ZYNQ_PS_MIO0/9/12 spares,
# ZYNQ_PS_MIO7/VM0 + MIO8\VM1 straps (on-SoM, carrier NC — see ISOLATED below),
# and the pmod/user_io bank-13 pairs (those consumers use the raw bank names).
FUNCTION_MAP: dict[str, str] = {
    # -- G1: rail-EN override vetoes (sec 1, bringup_en) -----------------
    "STM32_GPIO1": "STM32_RAIL_EN_5V0",   # PC11, J1.33
    "STM32_GPIO2": "STM32_RAIL_EN_3V3",   # PB5,  J1.35
    "STM32_GPIO3": "STM32_RAIL_EN_1V8",   # PC10, J1.43
    # -- G2: shared open-drain SC interrupt (sec 1.1) -------------------
    # PA15, J1.41. Wire-OR of TCA9535 INT# (bringup_rails) + FUSB302 INT
    # (usb_pd). BOTH consumers carry a SC_INT_N port -> 2-consumer merge.
    "STM32_GPIO4": "SC_INT_N",
    # -- G3: bit-banged STM32_I2C2 on the DAC pins (sec 2) --------------
    # PA4/PA5 have no I2C AF (real I2C2 PA8/PA9 is consumed on-module as the
    # SC<->Zynq link) -> firmware GPIO bit-bang. The DAC analog outputs are
    # sacrificed (no carrier subsystem ever claimed STM32_DAC*).
    "STM32_DAC1": "STM32_I2C2_SDA",       # PA4, J1.49
    "STM32_DAC2": "STM32_I2C2_SCL",       # PA5, J1.55
    # -- G5/4.5: PS UART0 console MIO group (sec 4.5, uart_bridge) ------
    "ZYNQ_PS_MIO10": "ZYNQ_PS_UART0_RXD",  # G7 ball, J1.42 (bridge TXD)
    "ZYNQ_PS_MIO11": "ZYNQ_PS_UART0_TXD",  # B4 ball, J1.48 (Zynq TXD)
    # -- G5/4.4: FMC LA08-11 on bank-35 J1 pairs (fmc.md sec 1) ---------
    "IO_L1_P_35": "FMC_LA08_P",  "IO_L1_N_35": "FMC_LA08_N",   # J1.74/92
    "IO_L4_P_35": "FMC_LA09_P",  "IO_L4_N_35": "FMC_LA09_N",   # J1.80/84
    "IO_L5_P_35": "FMC_LA10_P",  "IO_L5_N_35": "FMC_LA10_N",   # J1.90/88
    "IO_L6_P_35": "FMC_LA11_P",  "IO_L6_VREF_N_35": "FMC_LA11_N",  # J1.78/76

    # -- G5/4.1: bank 13 (J2) — LCD touch, UART0 modem EMIO, SD detect --
    "IO_L16_P_13": "LCD_CTP_SDA",   # J2.30
    "IO_L16_N_13": "LCD_CTP_SCL",   # J2.28
    "IO_L17_P_13": "LCD_CTP_RST",   # J2.34
    "IO_L17_N_13": "LCD_CTP_INT",   # J2.32
    "IO_L18_P_13": "ZYNQ_PS_UART0_CTS_N",  # J2.11 (EMIO — no MIO route)
    "IO_L18_N_13": "ZYNQ_PS_UART0_RTS_N",  # J2.8  (EMIO)
    "IO_L6_N_VREF_13": "SD_CARD_DETECT",   # J2.17 (PS SDIO0 CD via EMIO)
    # -- G5/4.2: bank 33 (J2) — HDMI RX + TX, PL buttons, FMC present ---
    "IO_L12_MRCC_P_33": "HDMI_RX_CLK_P",  "IO_L12_MRCC_N_33": "HDMI_RX_CLK_N",
    "IO_L10_P_33": "HDMI_RX_D0_P",        "IO_L10_N_33": "HDMI_RX_D0_N",
    "IO_L17_P_33": "HDMI_RX_D1_P",        "IO_L17_N_33": "HDMI_RX_D1_N",
    "IO_L18_P_33": "HDMI_RX_D2_P",        "IO_L18_N_33": "HDMI_RX_D2_N",
    "IO_L20_P_33": "HDMI_RX_CEC",         "IO_L20_N_33": "HDMI_RX_5V_DET",
    "IO_L21_DQS_P_33": "ZYNQ_HDMI_TX_TMDS_CLK_P",
    "IO_L21_DQS_N_33": "ZYNQ_HDMI_TX_TMDS_CLK_N",
    "IO_L22_P_33": "ZYNQ_HDMI_TX_TMDS_0_P", "IO_L22_N_33": "ZYNQ_HDMI_TX_TMDS_0_N",
    "IO_L23_P_33": "ZYNQ_HDMI_TX_TMDS_1_P", "IO_L23_N_33": "ZYNQ_HDMI_TX_TMDS_1_N",
    "IO_L24_P_33": "ZYNQ_HDMI_TX_TMDS_2_P", "IO_L24_N_33": "ZYNQ_HDMI_TX_TMDS_2_N",
    "IO_L19_P_33": "ZYNQ_HDMI_TX_SCL",      "IO_L19_VREF_N_33": "ZYNQ_HDMI_TX_SDA",
    "IO_L15_P_33": "ZYNQ_HDMI_TX_CEC",      "IO_L15_N_33": "ZYNQ_HDMI_TX_HPD",
    "IO_25_33": "PL_BTN0",                  "IO_L16_N_33": "PL_BTN1",
    "IO_L6_P_33": "FMC_PRSNT_N",            # J2.89
    # -- G5/4.2: bank 33 (J3) — camera control --------------------------
    "IO_L1_P_33": "CAM_SCL",  "IO_L1_N_33": "CAM_SDA",   # J3.86/89
    "IO_L2_P_33": "CAM_EN",   "IO_L2_N_33": "CAM_LED",   # J3.85/87
    # -- G5/4.4: bank 35 (J3) — camera CSI + FMC CLK/LA -----------------
    "IO_L13_MRCC_P_35": "CAM_CLK_P", "IO_L13_MRCC_N_35": "CAM_CLK_N",  # J3.9/11
    "IO_L10_P_35": "CAM_D0_P",       "IO_L10_N_35": "CAM_D0_N",        # J3.5/7
    "IO_L15_DQS_P_35": "CAM_D1_P",   "IO_L15_DQS_N_35": "CAM_D1_N",    # J3.17/15
    "IO_L12_MRCC_P_35": "FMC_CLK0_M2C_P", "IO_L12_MRCC_N_35": "FMC_CLK0_M2C_N",
    "IO_L11_SRCC_P_35": "FMC_CLK1_M2C_P", "IO_L11_SRCC_N_35": "FMC_CLK1_M2C_N",
    "IO_L14_SRCC_P_35": "FMC_LA00_CC_P",  "IO_L14_SRCC_N_35": "FMC_LA00_CC_N",
    "IO_L21_DQS_P_35": "FMC_LA01_CC_P",   "IO_L21_DQS_N_35": "FMC_LA01_CC_N",
    "IO_L17_P_35": "FMC_LA02_P", "IO_L17_N_35": "FMC_LA02_N",
    "IO_L20_P_35": "FMC_LA03_P", "IO_L20_N_35": "FMC_LA03_N",
    "IO_L22_P_35": "FMC_LA04_P", "IO_L22_N_35": "FMC_LA04_N",
    "IO_L23_P_35": "FMC_LA05_P", "IO_L23_N_35": "FMC_LA05_N",
    "IO_L24_P_35": "FMC_LA06_P", "IO_L24_N_35": "FMC_LA06_N",
    "IO_L19_P_35": "FMC_LA07_P", "IO_L19_N_VREF_35": "FMC_LA07_N",
    # -- G5/4.3: bank 34 (J3) — LCD RGB888 + sync (skip PUDC J3.39) -----
    "IO_L7_P_34": "LCD_R0",  "IO_L24_N_34": "LCD_R1", "IO_L20_P_34": "LCD_R2",
    "IO_L5_N_34": "LCD_R3",  "IO_L7_N_34": "LCD_R4",  "IO_L4_N_34": "LCD_R5",
    "IO_L12_MRCC_P_34": "LCD_R6", "IO_L11_SRCC_P_34": "LCD_R7",
    "IO_L8_P_34": "LCD_G0",  "IO_L11_SRCC_N_34": "LCD_G1", "IO_L8_N_34": "LCD_G2",
    "IO_L9_DQS_P_34": "LCD_G3", "IO_L5_P_34": "LCD_G4", "IO_L9_DQS_N_34": "LCD_G5",
    "IO_L12_MRCC_N_34": "LCD_G6", "IO_L13_MRCC_N_34": "LCD_G7",
    "IO_L10_N_34": "LCD_B0", "IO_L13_MRCC_P_34": "LCD_B1", "IO_L10_P_34": "LCD_B2",
    "IO_L15_DQS_N_34": "LCD_B3", "IO_L14_SRCC_N_34": "LCD_B4",
    "IO_L15_DQS_P_34": "LCD_B5", "IO_L14_SRCC_P_34": "LCD_B6", "IO_L18_N_34": "LCD_B7",
    "IO_L16_P_34": "LCD_PCLK",   "IO_L20_N_34": "LCD_HSYNC", "IO_L16_N_34": "LCD_VSYNC",
    "IO_L6_VREF_N_34": "LCD_DE", "IO_L17_P_34": "LCD_DISP",  "IO_L17_N_34": "LCD_BL_PWM",
}

# Bank-34 PUDC pin -> carrier function port. IO_L3P_PUDC_34 (J3.39) is the
# pull-up-during-config pin and has NO resistor on the SoM (wave3_function_map
# .md sec 3.3 / UG470). It needs a 10k strap to GND (internal pull-ups enabled
# during config — friendly to the LCD "DISP defaults on" + active-low buttons).
# The strap RESISTOR is a carrier-side part, but the J-sheets are
# connector-ONLY by construction (the placement engine's connector-fan template
# fires only for a lone >=40-pin part — a discrete here would break it). So the
# pin is renamed to the function port PUDC_34 here, and the strap resistor lives
# on bringup_rails (the carrier config-strap surface sheet, which already hosts
# the DIP/pull networks); the linker binds PUDC_34 J3<->bringup_rails. Kept OUT
# of FUNCTION_MAP's IO->signal renames is unnecessary — it IS a function rename,
# just one whose carrier part lands on another sheet. {som_contract_net: port}.
PUDC_STRAPS: dict[str, str] = {
    "IO_L3P_PUDC_34": "PUDC_34",          # J3.39 -> PUDC_34 (strap on bringup_rails)
}

# Differential-pair TYPES for the function nets, applied on the J sheets so the
# constraints exporter sees both ends (wave3_function_map.md sec 4.6.4). Each
# entry: (P, N, kind, impedance). Mirrors the consumer sheet's own typing.
FUNCTION_PAIR_TYPES = [
    # HDMI TMDS (100R, tmds_pair) — hdmi_tx / hdmi_rx
    ("ZYNQ_HDMI_TX_TMDS_CLK_P", "ZYNQ_HDMI_TX_TMDS_CLK_N", "tmds_pair", None),
    ("ZYNQ_HDMI_TX_TMDS_0_P", "ZYNQ_HDMI_TX_TMDS_0_N", "tmds_pair", None),
    ("ZYNQ_HDMI_TX_TMDS_1_P", "ZYNQ_HDMI_TX_TMDS_1_N", "tmds_pair", None),
    ("ZYNQ_HDMI_TX_TMDS_2_P", "ZYNQ_HDMI_TX_TMDS_2_N", "tmds_pair", None),
    ("HDMI_RX_CLK_P", "HDMI_RX_CLK_N", "tmds_pair", None),
    ("HDMI_RX_D0_P", "HDMI_RX_D0_N", "tmds_pair", None),
    ("HDMI_RX_D1_P", "HDMI_RX_D1_N", "tmds_pair", None),
    ("HDMI_RX_D2_P", "HDMI_RX_D2_N", "tmds_pair", None),
    # camera MIPI CSI (100R diff, LVDS_25) — camera
    ("CAM_CLK_P", "CAM_CLK_N", "diff_pair", 100),
    ("CAM_D0_P", "CAM_D0_N", "diff_pair", 100),
    ("CAM_D1_P", "CAM_D1_N", "diff_pair", 100),
    # FMC LVDS_25 pairs (100R diff) — fmc
    ("FMC_CLK0_M2C_P", "FMC_CLK0_M2C_N", "diff_pair", 100),
    ("FMC_CLK1_M2C_P", "FMC_CLK1_M2C_N", "diff_pair", 100),
    ("FMC_LA00_CC_P", "FMC_LA00_CC_N", "diff_pair", 100),
    ("FMC_LA01_CC_P", "FMC_LA01_CC_N", "diff_pair", 100),
    ("FMC_LA02_P", "FMC_LA02_N", "diff_pair", 100),
    ("FMC_LA03_P", "FMC_LA03_N", "diff_pair", 100),
    ("FMC_LA04_P", "FMC_LA04_N", "diff_pair", 100),
    ("FMC_LA05_P", "FMC_LA05_N", "diff_pair", 100),
    ("FMC_LA06_P", "FMC_LA06_N", "diff_pair", 100),
    ("FMC_LA07_P", "FMC_LA07_N", "diff_pair", 100),
    ("FMC_LA08_P", "FMC_LA08_N", "diff_pair", 100),
    ("FMC_LA09_P", "FMC_LA09_N", "diff_pair", 100),
    ("FMC_LA10_P", "FMC_LA10_N", "diff_pair", 100),
    ("FMC_LA11_P", "FMC_LA11_N", "diff_pair", 100),
]

# VCCO bank rail map (wave3_function_map.md sec 3): the carrier MUST SOURCE
# every Zynq bank VCCO — these pins float otherwise and ALL PL I/O is dead (plus
# the on-SoM BMI323 VDDIO, a +VCCO_33 rider, browns out). 13/33/34 = +3V3
# (LVCMOS33 banks), 35 = +2V5_VADJ (LVDS_25, shared camera/FMC 2.5V). SYS-1
# (2026-06-13): the bind is now APPLIED — resolve_net() merges each +VCCO_*
# contact pin onto its carrier rail (an in-fan RAIL TAP), exactly like GND /
# +5V_SOM pins. The carrier rail's own buck/LDO is the source; the DF40 pin is
# just one more tap on it. The earlier "keep contract names / defer" stance was
# retired once the placement engine learned to fan a POWER rail whose taps form
# SEVERAL non-contiguous clusters on one DF40 side (e.g. +VCCO_13 at J2.1-3 top
# + +VCCO_33 at J2.98-100 bottom both -> +3V3): place.py's connector template
# now routes each contiguous tap CLUSTER as its own short trunk + power symbol
# (the GND-style local-tap idiom), so a split rail no longer trips the
# "foreign rail row inside trunk span" assertion. {som_contract_net: source_rail}.
VCCO_RAIL_MAP: dict[str, str] = {
    "+VCCO_13": "+3V3",
    "+VCCO_33": "+3V3",
    "+VCCO_34": "+3V3",
    "+VCCO_35": "+2V5_VADJ",
}

# PLAN round-5 RAIL ISOLATION (user decision 2026-06-12) — carrier bucks WIN.
# The SoM exports its own +3V3 (J1.24-27) and +1V8 (J1.56/58/60) from its
# on-module MPM3834 stages, while carrier power.py regulates same-named
# rails from its own bucks (TPS54302 U2 / AP2112K U3). Binding these pins
# would put two regulators in parallel on one net (the power-tree gate's
# PARALLEL-SOURCE finding). Resolution: the pins become EXPLICIT author
# no-connects on the carrier — never silently dropped. Each isolated pin is
# emitted as a KiCad no-connect and the per-sheet netlist gate proves every
# one; schgen.link.ISOLATED_SOM_RAILS (this map's policy twin, next to
# RAIL_ALIASES) reports the isolation in the rail census and ERRORs if a
# connector sheet ever re-binds an isolated rail. The nets stay distinct;
# the SoM-side rails remain on-module only.
ISOLATED_SOM_RAILS: dict[str, str] = {
    "+3V3": "SoM MPM3834 3V3 output on J1.24-27 — carrier TPS54302 "
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
    c.use_part("DF40C-100DS-0.4V_51", ref=jref)   # 100 bare-number pins
    seen_ports: set[str] = set()
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
    # case AT 5 V -> ~2.0 A (wave3_function_map.md P0 point 2); this is the
    # SoM module draw, declared where the module is the consumer. The
    # +5V_SOM buck (power.py U4) is a 3 A TPS54302 — 2 A leaves headroom.
    # ESTIMATE pending an SoM power-budget measurement at bring-up.
    if jref == "J1":
        c.draws("+5V_SOM", 2.0, "SoM module (Zynq+DDR3L+PHYs) ~10 W class "
                                "at 5 V (P0 rebind) — estimate, refine at "
                                "bring-up")
    # VCCO bank-rail LOADS (SYS-1): the +VCCO_* contact pins now MERGE onto the
    # carrier rails (resolve_net via VCCO_RAIL_MAP) — so each connector draws its
    # banks' VCCO current from +3V3 / +2V5_VADJ, declared where the bank is the
    # consumer. The Zynq SelectIO VCCO is mA-class static (bank logic + LVCMOS
    # output drive); the dominant +2V5_VADJ entry (bank 35) is the 0.050 A the
    # FMC re-budget reserves (wave3_function_map.md sec 3.1 — fmc.py dropped its
    # mezzanine allocation 0.400 -> 0.350 A to fit the TLV75725 DBV envelope).
    # No waive_tp: the rails are sourced (their bucks/LDO), so the power-tree
    # gate sees a real, sourced load — not a deferred orphan.
    vcco_draw = {  # carrier rail -> (amps, basis) for THIS connector's banks
        ("J2", "+3V3"): (0.020, "Zynq banks 13+33 VCCO (LVCMOS33 static + "
                                "PL output drive) + on-SoM BMI323 VDDIO rider"),
        ("J3", "+3V3"): (0.010, "Zynq bank 34 VCCO (LCD LVCMOS33 bus drive)"),
        ("J3", "+2V5_VADJ"): (0.050, "Zynq bank 35 VCCO (LVDS_25 drivers, "
                                     "camera/FMC) — sec 3.1 re-budget"),
    }
    for rail in sorted(c.nets):
        spec = vcco_draw.get((jref, rail))
        if spec is not None:
            c.draws(rail, spec[0], spec[1])
    return c
