from __future__ import annotations

import json
from pathlib import Path

from carrier.basis import register
from schgen.core.model import Circuit, NetClass

CONTRACT = Path(__file__).resolve().parent / "som_interface.json"

MEZZANINE_PLUG = register(
    "som_conn.mezzanine_plug", "DF40C-100DP-0.4V_51", "part",
    "The carrier carries the PLUG (DP), never a second receptacle: the SoM is "
    "fabricated with the DS receptacle on J1/J2/J3 and DF40 mates ONLY "
    "DP<->DS. Two DS would not interlock — a 300-pin no-mate the SoM<->carrier "
    "audit caught 2026-06-20. Signal pins 1-100 keep the same net->pad map "
    "(the Hirose DP/DS pair mates pad-N<->pad-N; the DP's mirrored pin-1 "
    "X=-9.8 vs DS X=+9.8 IS the face-to-face mating geometry); pads 101-104 "
    "are mechanical hold-down nails.",
    "datasheet")

MODULE_DRAW_A = register(
    "som_conn.module_draw", 2.15, "A",
    "SoM module (Zynq + DDR3L + PHYs) ~10 W class booked AT the regulated "
    "4.65 V, not at 5 V: 10/4.65 = 2.15 A (wave3_function_map P0 point 2). The "
    "+5V_SOM buck is a 6 A LM61460, so this is ~36 %. ESTIMATE pending an SoM "
    "power-budget measurement at bring-up.",
    "policy")

SDIO_LEVEL_V = register(
    "som_conn.sdio_level", 1.8, "V",
    "The SoM runs SDIO at 1.8 V straight into the Zynq (verified against the "
    "SoM netlist 2026-06-10), which is why the carrier microSD subsystem must "
    "level-translate.",
    "measured")

REBOUND_SOM_RAILS: dict[str, str] = {
    "VIN": register(
        "som_conn.vin_rebind", "+5V_SOM", "net",
        "P0, user-signed-off 2026-06-12: the SoM VIN (J1.1-14) is the module's "
        "4.2-5 V input. Binding it to the carrier 20 V PD rail destroys the SoM "
        "at the first PD contract, so it is REBOUND to the always-on LM61460 "
        "buck. schgen.link.REBOUND_SOM_RAILS is the policy twin and the linker "
        "ERRORs if the two maps drift.",
        "datasheet"),
}

# Sampled at POR to set the MIO bank I/O voltage and strapped ON THE SoM: a
# carrier pull/driver/consumer would fight the strap and mis-set that voltage.
DO_NOT_LOAD_STRAPS: frozenset[str] = frozenset({
    "ZYNQ_PS_MIO7/VM0", "ZYNQ_PS_MIO8\\VM1",
})

RAIL_SPELLING = dict(REBOUND_SOM_RAILS)

FUNCTION_MAP: dict[str, str] = {
    "STM32_GPIO1": "STM32_RAIL_EN_5V0",
    "STM32_GPIO2": "STM32_RAIL_EN_3V3",
    "STM32_GPIO3": "STM32_RAIL_EN_1V8",
    "STM32_GPIO4": "SC_INT_N",
    "STM32_DAC1": "STM32_I2C2_SDA",
    "STM32_DAC2": "STM32_I2C2_SCL",
    "ZYNQ_PS_MIO10": "ZYNQ_PS_UART0_RXD",
    "ZYNQ_PS_MIO11": "ZYNQ_PS_UART0_TXD",
    "IO_L1_P_35": "FMC_LA08_P",  "IO_L1_N_35": "FMC_LA08_N",
    "IO_L4_P_35": "FMC_LA09_P",  "IO_L4_N_35": "FMC_LA09_N",
    "IO_L5_P_35": "FMC_LA10_P",  "IO_L5_N_35": "FMC_LA10_N",
    "IO_L6_P_35": "FMC_LA11_P",  "IO_L6_VREF_N_35": "FMC_LA11_N",

    "IO_L16_P_13": "LCD_CTP_SDA",
    "IO_L16_N_13": "LCD_CTP_SCL",
    "IO_L17_P_13": "LCD_CTP_RST",
    "IO_L17_N_13": "LCD_CTP_INT",
    "IO_L18_P_13": "ZYNQ_PS_UART0_CTS_N",
    "IO_L18_N_13": "ZYNQ_PS_UART0_RTS_N",
    "IO_L6_N_VREF_13": "SD_CARD_DETECT",
    "IO_L13_MRCC_P_13": "PMODX_IO1",  "IO_L13_MRCC_N_13": "PMODX_IO2",
    "IO_L23_P_13": "PMODX_IO3",       "IO_L23_N_13": "PMODX_IO4",
    "IO_L14_P_SRCC_13": "PMODX_IO5",  "IO_L14_N_SRCC_13": "PMODX_IO6",
    "IO_L12_MRCC_P_13": "PMODX_IO7",  "IO_L12_MRCC_N_13": "PMODX_IO8",
    "IO_L11_SRCC_P_13": "DBG_UART_RXD",
    "IO_L11_SRCC_N_13": "DBG_UART_TXD",
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
    "IO_L1_P_33": "CAM_SCL",  "IO_L1_N_33": "CAM_SDA",
    "IO_L2_P_33": "CAM_EN",   "IO_L2_N_33": "CAM_LED",
    "IO_L4_P_33": "WATCHDOG_RST_N",
    "IO_L4_N_33": "WATCHDOG_KICK",
    "IO_L13_MRCC_P_35": "CAM_CLK_P", "IO_L13_MRCC_N_35": "CAM_CLK_N",
    "IO_L10_P_35": "CAM_D0_P",       "IO_L10_N_35": "CAM_D0_N",
    "IO_L15_DQS_P_35": "CAM_D1_P",   "IO_L15_DQS_N_35": "CAM_D1_N",
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
    "IO_L14_SRCC_P_33": "ESC_PWM_IN0", "IO_L14_SRCC_N_33": "ESC_PWM_IN1",
    "IO_L11_SRCC_P_33": "ESC_PWM_IN2", "IO_L11_SRCC_N_33": "ESC_PWM_IN3",
    "IO_L3_DQS_P_33": "ESC_PWM_IN4",   "IO_L3_DQS_N_33": "ESC_PWM_IN5",
    "IO_L5_P_33": "ESC_PWM_IN6",       "IO_L5_N_33": "ESC_PWM_IN7",
    "IO_L1P_13": "ESC_BUF_OE_N",       "IO_L1_N_13": "ESC_FAULT_N",
}

PUDC_STRAPS: dict[str, str] = {
    "IO_L3P_PUDC_34": "PUDC_34",
}

FUNCTION_PAIR_TYPES = [
    ("ZYNQ_HDMI_TX_TMDS_CLK_P", "ZYNQ_HDMI_TX_TMDS_CLK_N", "tmds_pair", None),
    ("ZYNQ_HDMI_TX_TMDS_0_P", "ZYNQ_HDMI_TX_TMDS_0_N", "tmds_pair", None),
    ("ZYNQ_HDMI_TX_TMDS_1_P", "ZYNQ_HDMI_TX_TMDS_1_N", "tmds_pair", None),
    ("ZYNQ_HDMI_TX_TMDS_2_P", "ZYNQ_HDMI_TX_TMDS_2_N", "tmds_pair", None),
    ("HDMI_RX_CLK_P", "HDMI_RX_CLK_N", "tmds_pair", None),
    ("HDMI_RX_D0_P", "HDMI_RX_D0_N", "tmds_pair", None),
    ("HDMI_RX_D1_P", "HDMI_RX_D1_N", "tmds_pair", None),
    ("HDMI_RX_D2_P", "HDMI_RX_D2_N", "tmds_pair", None),
    ("CAM_CLK_P", "CAM_CLK_N", "diff_pair", 100),
    ("CAM_D0_P", "CAM_D0_N", "diff_pair", 100),
    ("CAM_D1_P", "CAM_D1_N", "diff_pair", 100),
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

VCCO_RAIL_MAP: dict[str, str] = {
    "+VCCO_13": "+3V3",
    "+VCCO_33": "+3V3",
    "+VCCO_34": "+3V3",
    "+VCCO_35": "+2V5_VADJ",
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
            f"carrier — {sorted(loaded)} would fight the SoM strap at POR")


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
                    f"— the engine's connector fan assumes one row per signal; extend it")
            seen_ports.add(net)
            c.port(net, f"{jref}.{pin}")
        if som_net in DO_NOT_LOAD_STRAPS and net != som_net:
            raise AssertionError(
                f"{jref}.{pin}: MIO voltage-mode strap {som_net!r} resolved to "
                f"{net!r} — it must stay verbatim and unloaded on the carrier")
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
        ("J3", "+3V3"): (0.010, "Zynq bank 34 VCCO (LCD LVCMOS33 bus drive)"),
        ("J3", "+2V5_VADJ"): (0.050, "Zynq bank 35 VCCO (LVDS_25 drivers, "
                                     "camera/FMC) — sec 3.1 re-budget"),
    }
    for rail in sorted(c.nets):
        spec = vcco_draw.get((jref, rail))
        if spec is not None:
            c.draws(rail, spec[0], spec[1])
    return c
