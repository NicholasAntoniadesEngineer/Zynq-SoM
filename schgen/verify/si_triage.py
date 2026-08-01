from __future__ import annotations

import importlib.util
import re
from dataclasses import dataclass
from pathlib import Path

from schgen.core.project import PROJECT_ROOT

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SOM_CONN_GEN = PROJECT_ROOT / "som_conn_gen.py"

GENUINE = "GENUINE"
MODERATE = "MODERATE"
LOW = "LOW"
RANK = {GENUINE: 0, MODERATE: 1, LOW: 2}


class SiTriageError(ValueError):
    pass


@dataclass(frozen=True)
class SiClass:
    net: str
    function: str
    klass: str
    basis: str


_RULES: list[tuple[str, str, str]] = [
    (r"HDMI_RX_(D\d|CLK)_[PN]", GENUINE,
     "TMDS sink lane, 742.5 Mbps/lane at 720p60 — eye budget is real"),
    (r"ZYNQ_HDMI_TX_TMDS_(\d|CLK)_[PN]", GENUINE,
     "TMDS source lane, 742.5 Mbps/lane at 720p60 — eye budget is real"),
    (r"ETH_PHY_MDI\d_[PN]", GENUINE,
     "100BASE-TX MDI pair, 125 MBd MLT-3 through the mated interface"),
    (r"CAM_(D\d|CLK)_[PN]", GENUINE,
     "CSI-2 D-PHY lane (LVDS_25 on bank 35) — sub-ns edges"),
    (r"USB_D[+-]", GENUINE,
     "USB 2.0 HS 480 Mbps PS-OTG pair — safe-direction high (not among the "
     "69 v1 P/N-token pairs; class affects ordering only)"),
    (r"FMC_(LA\d\d(_CC)?|CLK\d_M2C)_[PN]", MODERATE,
     "FMC LVDS user pair (LVDS_25) — speed set by the mezzanine, budget "
     "relaxed vs TMDS"),
    (r"STM32_USB_D_[PN]", MODERATE,
     "USB full-speed 12 Mbps device pair — edges matter, budget generous"),
    (r"LCD_(R|G|B)\d", MODERATE,
     "LCD parallel RGB data @ ~33 MHz pixel clock, simultaneous-switching bus"),
    (r"LCD_(PCLK|HSYNC|VSYNC|DE)", MODERATE,
     "LCD pixel clock / sync — the timing edge of the parallel RGB bus"),
    (r"LCD_CTP_(SDA|SCL|INT|RST)", LOW,
     "capacitive-touch-panel I2C + control — 400 kHz class"),
    (r"LCD_(BL_PWM|DISP)", LOW, "LCD backlight PWM / display-enable control"),
    (r"PMODX?_IO\d", LOW, "PMOD expansion header GPIO"),
    (r"IO_(L\d.*|\d+_\d+|0_\d+)", LOW,
     "unclaimed SoM contract GPIO (pmod/user_io headers — no function sheet)"),
    (r"DBG_UART_(RXD|TXD)", LOW, "debug UART, <= 1 MBd"),
    (r"ZYNQ_PS_UART0_(RXD|TXD|CTS_N|RTS_N)", LOW, "PS UART + flow control"),
    (r"ESC_(PWM_IN\d|BUF_OE_N|FAULT_N)", LOW,
     "ESC PWM (50-490 Hz class) + buffer control"),
    (r"ETH_LED\d", LOW, "PHY LED indicator"),
    (r"CAM_(EN|LED|SCL|SDA)", LOW, "camera control / SCCB I2C"),
    (r"HDMI_RX_(CEC|5V_DET)", LOW, "HDMI CEC (kHz) / cable-detect level"),
    (r"ZYNQ_HDMI_TX_(CEC|HPD|SCL|SDA)", LOW,
     "HDMI CEC / hot-plug / DDC I2C — 100 kHz class"),
    (r"SDIO_(CLK|CMD|D\d)", LOW,
     "SDIO @ 50 MHz single-ended, short reach, terminated at the SoM"),
    (r"SD_CARD_DETECT", LOW, "card-detect level"),
    (r"STM32_(BOOT0|NRST|GPIO\d|I2C2_SCL|I2C2_SDA|RAIL_EN_\dV\d|USB_CC\d)",
     LOW, "supervisor control / I2C / CC lines"),
    (r"ZYNQ_PS_MIO\d+([/\\]VM\d)?", LOW, "PS MIO GPIO / voltage-monitor strap"),
    (r"ZYNQ_T(CK|DI|DO|MS)", LOW, "JTAG — held static outside debug"),
    (r"(WATCHDOG_(KICK|RST_N)|SC_INT_N|PL_BTN\d|PUDC_\d+)", LOW,
     "supervisor watchdog / interrupt / button / pull-up-during-config strap"),
    (r"(USB_ID|USB_VBUS|VBUS_OUT_EN)", LOW, "USB OTG ID / VBUS sense + enable"),
    (r"VIN", LOW,
     "power inlet leaked under a signal-style name (no '+' prefix) — carried "
     "by planes, not lanes"),
]
_COMPILED = [(re.compile(p), k, b) for p, k, b in _RULES]

_function_map_cache: dict[str, str] | None = None


def _function_map() -> dict[str, str]:
    global _function_map_cache
    if _function_map_cache is None:
        spec = importlib.util.spec_from_file_location(
            "_si_triage_som_conn_gen", _SOM_CONN_GEN)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        m = dict(mod.FUNCTION_MAP)
        m.update(mod.PUDC_STRAPS)
        _function_map_cache = m
    return _function_map_cache


def classify(net: str) -> SiClass:
    function = _function_map().get(net, net)
    for rx, klass, basis in _COMPILED:
        if rx.fullmatch(function):
            return SiClass(net=net, function=function, klass=klass, basis=basis)
    raise SiTriageError(
        f"uncurated DF40 signal net {net!r} (function {function!r}) — add a "
        f"curated class row to schgen/verify/si_triage.py (LAW 7: never a "
        f"silent default)")


def classify_all(nets: list[str] | set[str]) -> dict[str, SiClass]:
    return {n: classify(n) for n in sorted(nets)}


def rank(net: str) -> int:
    return RANK[classify(net).klass]
