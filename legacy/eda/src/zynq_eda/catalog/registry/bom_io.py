"""Generators for carrier_BOM.csv and io_assignment.csv.

io_assignment.csv: maps every SoM pin (from symbol_J1/J2/J3.csv) to its
destination on the carrier (FMC pin, HDMI lane, PMOD bit, LCD pair, etc.).
Single source of truth for sheet generators.

carrier_BOM.csv: aggregates every part the carrier needs.  IC counts
come from refcircuits.IC_INSTANCE_COUNT; external part counts come
from each ReferenceCircuit's external_parts list multiplied by the
IC instance count.
"""

from __future__ import annotations

import csv
import os
import re
from collections import Counter
from pathlib import Path

from zynq_eda.catalog.registry.parts_registry import REGISTRY
from zynq_eda.catalog.components import (
    IC_INSTANCE_COUNT,
    REFCIRCUITS,
    build_quantity_per_token,
)

SCRIPTS_DIR = Path(__file__).resolve().parents[2]
CARRIER_TEMPLATE_DIR = SCRIPTS_DIR / "carrier_template"
SYMBOL_CSV_DIR = CARRIER_TEMPLATE_DIR
BOM_PATH = CARRIER_TEMPLATE_DIR / "carrier_BOM.csv"
IO_ASSIGN_PATH = CARRIER_TEMPLATE_DIR / "io_assignment.csv"

_LCD_PAIR_BUDGET = 4
_HDMIRX_PAIR_BUDGET = 4
_FMC_LA12_PAIR_BUDGET = 12

_BANK33_LCD_LANES: frozenset[int] = frozenset()
_BANK33_HDMIRX_LANES: frozenset[int] = frozenset()
_BANK35_FMC_LANES: frozenset[int] = frozenset()
_BANK35_CAM_LANES: frozenset[int] = frozenset()


def _lane_index(net_name: str) -> int | None:
    match = re.search(r"IO_L(\d+)", net_name)
    if match is None:
        return None
    return int(match.group(1))


def _is_diff_pair_net(net_name: str) -> bool:
    return "_L" in net_name and (
        "_P_" in net_name or "_N_" in net_name or net_name.endswith("_P") or net_name.endswith("_N")
    )


def _init_lane_splits(all_som_nets: tuple[str, ...]) -> None:
    global _BANK33_LCD_LANES, _BANK33_HDMIRX_LANES, _BANK35_FMC_LANES, _BANK35_CAM_LANES

    bank33_lanes = sorted(
        {
            lane
            for net_name in all_som_nets
            if net_name.endswith("_33") and _is_diff_pair_net(net_name)
            for lane in [_lane_index(net_name)]
            if lane is not None
        }
    )
    _BANK33_LCD_LANES = frozenset(bank33_lanes[:_LCD_PAIR_BUDGET])
    _BANK33_HDMIRX_LANES = frozenset(
        bank33_lanes[_LCD_PAIR_BUDGET : _LCD_PAIR_BUDGET + _HDMIRX_PAIR_BUDGET]
    )

    bank35_lanes = sorted(
        {
            lane
            for net_name in all_som_nets
            if net_name.endswith("_35") and _is_diff_pair_net(net_name)
            for lane in [_lane_index(net_name)]
            if lane is not None and lane != 1
        }
    )
    _BANK35_FMC_LANES = frozenset(bank35_lanes[:_FMC_LA12_PAIR_BUDGET])
    _BANK35_CAM_LANES = frozenset(bank35_lanes[_FMC_LA12_PAIR_BUDGET:])


def _bank33_destination(net_name: str) -> str:
    lane = _lane_index(net_name)
    if lane is not None and lane in _BANK33_HDMIRX_LANES:
        return "J_HDMIRX"
    return "J_LCD"


def _bank35_fmc_cam_destination(net_name: str) -> str:
    lane = _lane_index(net_name)
    if lane is not None and lane in _BANK35_CAM_LANES:
        return "J_CAM"
    return "J_FMC.LA12-LA23"


# ---------------------------------------------------------------------------
# IO assignment: SoM bank pin -> carrier destination
# ---------------------------------------------------------------------------

# Carrier-side destinations (per architecture decisions):
#   Power/Ground:  via power rails
#   USB Comms:     USBC1 (STM32), USBC2 (Zynq OTG via FUSB302+USB3318)
#   JTAG:          J_JTAG header (Xilinx 14p)
#   SWD:           J_SWD header (Cortex Debug 10p)
#   SDIO:          J_SD microSD socket
#   STM32:         CP2102N (UART), USR LED/BTN, RTC/EEPROM/INA226 (I2C)
#   Ethernet MDI:  T_ETH magnetics -> J_RJ45
#   Ethernet LED:  RJ45 integrated LEDs
#   PL Banks:      FMC_LPC, HDMI TX/RX, LVDS LCD, MIPI Camera, PMODs, XADC SMA

# Banks layout strategy:
#   Bank 13 -> HDMI TX (3 TMDS + CLK = 4 pairs), PMOD1+PMOD2 (single-ended)
#   Bank 33 split -> J2 half goes to LVDS LCD pairs; J3 half goes to HDMI RX
#   Bank 34 -> FMC LA00..LA11 (12 pairs)
#   Bank 35 -> FMC LA12..LA23 (12 pairs) + MIPI Camera (2 data + clk = 3 pairs)
#            + XADC L1_P/N dedicated analog + MRCC clock input via SMA

# Manual pin-by-pin map for clarity. Keys are (connector, pin_str).
# Each value is a dict with destination and signal name.
# This is hand-curated from the SoM symbol CSVs.

# Note: keep this lookup small and exhaustive across the 300 pins -
# every pin is listed exactly once, with either a "destination" or NOTE_NC.


def _power_dest(net: str) -> dict:
    return {"destination": "power_rail", "carrier_signal": net, "interface": "POWER"}


def _gnd_dest() -> dict:
    return {"destination": "ground", "carrier_signal": "GND", "interface": "POWER"}


def _make_io_assignment() -> list[dict]:
    """Return list of rows for io_assignment.csv."""

    # Load SoM pin definitions from the existing symbol_J*.csv files
    rows: list[dict] = []
    for jname in ("J1", "J2", "J3"):
        csv_path = SYMBOL_CSV_DIR / f"symbol_{jname}.csv"
        with open(csv_path, newline="", encoding="utf-8") as f:
            # The CSV format is:
            #   row 1: "Zynq_SoM_J1"
            #   row 2: header "Pin,Name,Side"
            #   rows 3+: pin,name,side
            reader = csv.reader(f)
            next(reader)  # skip name row
            next(reader)  # skip header row
            for r in reader:
                if not r:
                    continue
                pin_no, net_name, side = r[0], r[1], r[2]
                # Normalise net_name (KiCad slash escape etc.)
                normalised = (
                    net_name.replace("{slash}", "/")
                    .replace("\\", "/")
                    .strip()
                )
                rows.append({
                    "som_connector": jname,
                    "som_pin": pin_no,
                    "som_net": normalised,
                    "side": side,
                })
    return rows


def _classify_destination(som_net: str) -> dict:
    """Map a SoM net name to a carrier destination."""
    n = som_net

    # Power rails
    if n == "VIN":
        return {"destination": "power_input", "carrier_signal": "+VIN", "interface": "POWER", "notes": "From FUSB302 PD output / barrel jack / consigned"}
    if n == "GND":
        return {"destination": "ground", "carrier_signal": "GND", "interface": "POWER", "notes": "Star ground"}
    if n == "+3V3":
        return {"destination": "power_rail", "carrier_signal": "+3V3", "interface": "POWER", "notes": "From SoM internal 3V3"}
    if n == "+1V8":
        return {"destination": "power_rail", "carrier_signal": "+1V8", "interface": "POWER", "notes": "From SoM internal 1V8"}
    if n == "+3V3_SC":
        return {"destination": "power_rail", "carrier_signal": "+3V3_SC", "interface": "POWER", "notes": "STM32G431 3V3 supply"}
    if n.startswith("+VCCO_"):
        bank = n.split("_", 1)[1]
        return {"destination": "carrier_LDO", "carrier_signal": n, "interface": "POWER", "notes": f"Bank {bank} VCCO; carrier-side LDO (TLV757 family)"}

    # USB-C STM32 connector (STM32_USB_*)
    if n.startswith("STM32_USB_"):
        return {"destination": "J_USBC1", "carrier_signal": n, "interface": "USB-C_STM32", "notes": "USB-C device port for STM32 PD + DFU"}
    if n in {"USB_VBUS", "USB_ID"}:
        return {"destination": "J_USBC2_OTG", "carrier_signal": n, "interface": "USB-C_OTG", "notes": "USB 2.0 HS OTG via USB3318 ULPI PHY on SoM"}
    if n in {"USB_D+", "USB_D-"}:
        return {"destination": "J_USBC2_OTG", "carrier_signal": n, "interface": "USB-C_OTG", "notes": "Zynq USB data line via USBLC6 ESD"}
    if n == "VBUS_OUT_EN":
        return {"destination": "U_LS1", "carrier_signal": "VBUS_OUT_EN", "interface": "USB-C_OTG", "notes": "Enables TPS2051C VBUS source to USB OTG host mode"}

    # Ethernet MDI direct from SoM PHY -> magnetics -> RJ45
    if n.startswith("ETH_PHY_MDI"):
        return {"destination": "T_ETH", "carrier_signal": n, "interface": "ETHERNET", "notes": "Direct to Pulse HX5008NLT magnetics module"}
    if n.startswith("ETH_LED"):
        led = n[-1]
        return {"destination": "J_RJ45", "carrier_signal": n, "interface": "ETHERNET", "notes": f"RJ45 LED {led} drive (active low)"}

    # JTAG (Zynq PL)
    if n in {"ZYNQ_TCK", "ZYNQ_TMS", "ZYNQ_TDO", "ZYNQ_TDI"}:
        return {"destination": "J_JTAG", "carrier_signal": n, "interface": "JTAG", "notes": "Xilinx JTAG 14-pin header"}

    # SDIO
    if n.startswith("SDIO_"):
        return {"destination": "J_SD", "carrier_signal": n, "interface": "SDIO", "notes": "microSD socket DM3AT-SF-PEJM5"}

    # STM32 controller pins
    if n.startswith("STM32_GPIO"):
        return {"destination": "STM32_breakout", "carrier_signal": n, "interface": "STM32_GPIO", "notes": "Breakout to USR LED / USB-UART CP2102N / SWD pins (PA13/PA14 assumed)"}
    if n == "STM32_NRST":
        return {"destination": "SW_RST_STM32", "carrier_signal": n, "interface": "STM32_CTL", "notes": "STM32 reset button"}
    if n == "STM32_BOOT0":
        return {"destination": "SW_BOOT", "carrier_signal": n, "interface": "STM32_CTL", "notes": "BOOT0 DIP switch position 1 (high = DFU)"}
    if n.startswith("STM32_DAC"):
        return {"destination": "PMOD_AUX", "carrier_signal": n, "interface": "STM32_DAC", "notes": "STM32 DAC output to PMOD or test point"}

    # Zynq PS MIO (configurable - we'll plan: console UART on MIO10/11, I2C on MIO12, GPIO others)
    if n.startswith("ZYNQ_PS_MIO"):
        mio_num = n.replace("ZYNQ_PS_MIO", "").split("/", 1)[0].split("\\", 1)[0]
        if mio_num == "10":
            return {"destination": "U_USBUART", "carrier_signal": "PS_UART0_TX", "interface": "UART", "notes": "MIO10 -> CP2102N RXD (Zynq -> PC)"}
        if mio_num == "11":
            return {"destination": "U_USBUART", "carrier_signal": "PS_UART0_RX", "interface": "UART", "notes": "MIO11 -> CP2102N TXD (PC -> Zynq)"}
        if mio_num == "12":
            return {"destination": "I2C_BUS_PS", "carrier_signal": "PS_I2C_SDA", "interface": "I2C", "notes": "MIO12 -> I2C SDA (shared bus to RTC/EEPROM/INA226)"}
        if mio_num == "9":
            return {"destination": "I2C_BUS_PS", "carrier_signal": "PS_I2C_SCL", "interface": "I2C", "notes": "MIO9 -> I2C SCL"}
        return {"destination": "USR_GPIO_PS", "carrier_signal": n, "interface": "GPIO", "notes": f"PS MIO{mio_num} to user LED/button"}

    # PL bank IOs - dispatch based on bank
    if n.startswith("IO_"):
        return _classify_pl_io(n)

    # Default - unmapped (flag as NC for now)
    return {"destination": "NOT_ASSIGNED", "carrier_signal": n, "interface": "UNKNOWN", "notes": "Pin not mapped - inspect"}


def _classify_pl_io(n: str) -> dict:
    """Classify a PL bank pin to its carrier destination based on simple rules."""
    # Extract bank suffix (e.g. _13, _33, _34, _35)
    bank = None
    for tail in ("_13", "_33", "_34", "_35"):
        if n.endswith(tail):
            bank = tail[1:]
            break
    if bank is None:
        return {"destination": "NOT_ASSIGNED", "carrier_signal": n, "interface": "PL_IO", "notes": "Bank unknown"}

    # Differential pairs (LVDS_P/N pattern) - "_L<index>_P/N_<bank>" pattern
    # MRCC / SRCC pins are clock-capable
    is_mrcc = "_MRCC" in n
    is_srcc = "_SRCC" in n
    is_diff = "_L" in n and ("_P_" in n or "_N_" in n or n.endswith("_P") or n.endswith("_N"))

    if bank == "13":
        # Bank 13 -> HDMI TX (3 TMDS + CLK pairs) + PMOD1/2 single-ended
        if is_diff:
            return {"destination": "U_HDMITX", "carrier_signal": f"HDMI_TX_{n}", "interface": "HDMI_TX", "notes": "Bank 13 LVDS -> HDMI TMDS lane (via TPD12S016)"}
        if is_mrcc:
            return {"destination": "J_MRCC_SMA", "carrier_signal": n, "interface": "CLOCK", "notes": "MRCC clock input via SMA"}
        return {"destination": "J_PMOD1", "carrier_signal": n, "interface": "PMOD", "notes": "Bank 13 single-ended to PMOD1/2"}

    if bank == "33":
        if is_diff:
            destination = _bank33_destination(n)
            interface = "LVDS_LCD" if destination == "J_LCD" else "HDMI_RX"
            note = (
                "Bank 33 LVDS -> LCD panel"
                if destination == "J_LCD"
                else "Bank 33 LVDS -> HDMI RX TMDS"
            )
            return {
                "destination": destination,
                "carrier_signal": n,
                "interface": interface,
                "notes": note,
            }
        return {"destination": "J_PMOD3", "carrier_signal": n, "interface": "PMOD", "notes": "Bank 33 single-ended to PMOD3"}

    if bank == "34":
        if is_mrcc:
            return {"destination": "J_FMC.CLK0", "carrier_signal": n, "interface": "FMC_CLK", "notes": "FMC LA clock pair (CLK0_M2C)"}
        if is_diff:
            return {"destination": "J_FMC.LA00-LA11", "carrier_signal": n, "interface": "FMC_LA", "notes": "Bank 34 LVDS -> FMC LA00..LA11 differential"}
        return {"destination": "J_PMOD4", "carrier_signal": n, "interface": "PMOD", "notes": "Bank 34 single-ended to PMOD4"}

    if bank == "35":
        # Bank 35 special: L1 -> XADC, others -> FMC LA12..LA23 + MIPI Camera
        if "L1_P_35" in n or "L1_N_35" in n:
            return {"destination": "J_XADC_SMA", "carrier_signal": n, "interface": "XADC", "notes": "Dedicated XADC differential analog input"}
        if is_mrcc:
            return {"destination": "J_MRCC_SMA", "carrier_signal": n, "interface": "CLOCK", "notes": "MRCC clock input via SMA"}
        if is_diff:
            destination = _bank35_fmc_cam_destination(n)
            interface = "FMC_LA" if destination.startswith("J_FMC") else "MIPI"
            note = (
                "Bank 35 LVDS -> FMC LA12..LA23 differential"
                if destination.startswith("J_FMC")
                else "Bank 35 LVDS -> MIPI camera FFC"
            )
            return {
                "destination": destination,
                "carrier_signal": n,
                "interface": interface,
                "notes": note,
            }
        return {"destination": "J_PMOD4", "carrier_signal": n, "interface": "PMOD", "notes": "Bank 35 single-ended to PMOD4"}

    return {"destination": "NOT_ASSIGNED", "carrier_signal": n, "interface": "PL_IO", "notes": "Bank unknown"}


def emit_io_assignment_csv(output_path: Path = IO_ASSIGN_PATH) -> int:
    rows_in = _make_io_assignment()
    _init_lane_splits(tuple(row["som_net"] for row in rows_in))
    rows_out: list[dict] = []
    for r in rows_in:
        dest = _classify_destination(r["som_net"])
        rows_out.append({
            "som_connector": r["som_connector"],
            "som_pin": r["som_pin"],
            "som_net": r["som_net"],
            "side": r["side"],
            "destination": dest["destination"],
            "carrier_signal": dest["carrier_signal"],
            "interface": dest["interface"],
            "notes": dest.get("notes", ""),
            "shared": "false",
        })

    with open(output_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=[
            "som_connector", "som_pin", "som_net", "side",
            "destination", "carrier_signal", "interface", "notes", "shared",
        ])
        w.writeheader()
        w.writerows(rows_out)
    return len(rows_out)


# ---------------------------------------------------------------------------
# Master BOM emission
# ---------------------------------------------------------------------------


def emit_bom_csv(output_path: Path = BOM_PATH) -> int:
    """Aggregate BOM from IC instance counts + reference circuit externals."""

    # Collect all tokens used + their total quantities
    token_qty: Counter[str] = Counter()

    # ICs themselves
    for ic_name, count in IC_INSTANCE_COUNT.items():
        if count == 0:
            continue
        circuit = REFCIRCUITS.get(ic_name)
        if circuit is None:
            continue
        # Find the IC's BOM token by matching the LCSC
        ic_token = None
        for tok, part in REGISTRY.items():
            if part.lcsc == circuit.lcsc:
                ic_token = tok
                break
        if ic_token is None:
            print(f"WARN: no BOM token for IC {ic_name} (lcsc {circuit.lcsc})")
            continue
        token_qty[ic_token] += count

    # External parts
    externals = build_quantity_per_token()
    for tok, qty in externals.items():
        token_qty[tok] += qty

    # Add non-refcircuit parts that the carrier still needs (test points,
    # mounting holes, JTAG header, PMOD headers, SMA jacks, etc.)
    # These have IC_INSTANCE_COUNT-equivalent counts here.
    extra_parts: dict[str, int] = {
        # Connectors not in REFCIRCUITS
        "conn_FMC_FX10A_168P": 1,
        "conn_PMOD_2x6_RA": 4,
        "conn_JTAG_2x7_THT": 1,
        "conn_SWD_2x5_1.27mm": 1,
        "conn_SMA_RA_TH": 2,  # XADC + MRCC
        "conn_FFC_40P_0.5mm": 1,  # LCD
        "conn_FFC_15P_1mm": 1,    # MIPI camera
        # Switches and battery
        "sw_tactile_6x6": 4,  # RST, USR1-3
        "sw_dip_4pos_1.27mm": 1,
        "batt_CR2032_holder": 1,
        # User LEDs (8 user LEDs + 2 RJ45 LEDs handled in refcircuit + 4 PG indicators)
        "LED_green_0603": 4,   # PG indicators
        "LED_red_0603": 2,     # fault / error
        "LED_yellow_0603": 2,  # activity (separate from RJ45)
        "LED_blue_0603": 4,    # user LEDs
        # Protection
        "schottky_SS14": 2,    # VIN reverse polarity, USB host VBUS
        "tvs_PESD5V0S2BT": 8,  # Ethernet MDI line protection (one per line)
        # Ferrite beads on power rails
        "ferrite_600R_0402": 4,  # one per VCCO bank
        "ferrite_120R_0402": 4,  # general filter
        # Bob Smith common cap already in HX5008NLT refcircuit
        # Termination resistors (extra for HDMI source TMDS series)
        "33R_0402_1%": 8,  # HDMI TMDS series (4 pairs)
        # User LED current-limit resistors
        "330R_0402_1%": 12,
        # PMOD ESD - placeholder
        # Bulk caps on power rails
        "22u_0805_X5R": 2,  # VIN bulk
        "47u_0805_X5R": 4,  # VCCO bulk (one per bank)
    }
    for tok, qty in extra_parts.items():
        token_qty[tok] += qty

    # Write BOM
    rows = []
    total_cost = 0.0
    for tok in sorted(token_qty):
        part = REGISTRY.get(tok)
        if part is None:
            print(f"WARN: token {tok!r} in BOM but not in REGISTRY")
            continue
        qty = token_qty[tok]
        line_cost = qty * part.unit_price_usd
        total_cost += line_cost
        rows.append({
            "category": _category_of(part),
            "value": part.value,
            "manufacturer": part.manufacturer,
            "mpn": part.mpn,
            "lcsc": part.lcsc,
            "footprint": part.footprint,
            "package": part.package,
            "quantity": qty,
            "unit_price_usd": f"{part.unit_price_usd:.4f}",
            "line_cost_usd": f"{line_cost:.3f}",
            "stock_at_lcsc": part.stock_at_lcsc,
            "datasheet_url": part.datasheet_url,
            "description": part.description,
            "alt_lcsc": part.alt_lcsc,
            "alt_digikey": part.alt_digikey,
        })

    with open(output_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=[
            "category", "value", "manufacturer", "mpn", "lcsc", "footprint", "package",
            "quantity", "unit_price_usd", "line_cost_usd", "stock_at_lcsc",
            "datasheet_url", "description", "alt_lcsc", "alt_digikey",
        ])
        w.writeheader()
        w.writerows(rows)
    return total_cost


def _category_of(part) -> str:
    """Group BOM rows by category for human readability."""
    fp = part.footprint
    if fp.startswith("Capacitor_SMD:"):
        return "1-Caps"
    if fp.startswith("Resistor_SMD:"):
        return "2-Resistors"
    if fp.startswith("Inductor_SMD:"):
        return "3-Inductors"
    if fp.startswith("LED_SMD:"):
        return "4-LEDs"
    if fp.startswith("Diode_SMD:"):
        return "5-Diodes"
    if fp.startswith("Package_TO_SOT_SMD:"):
        return "6-SOT"
    if fp.startswith("Package_SO:"):
        return "7-SOIC"
    if fp.startswith("Package_DFN_QFN:"):
        return "8-QFN"
    if fp.startswith("Connector_"):
        return "9-Connectors"
    if fp.startswith("Switch_"):
        return "A-Switches"
    if fp.startswith("Battery:"):
        return "B-Battery"
    return "Z-Other"


if __name__ == "__main__":
    n_io = emit_io_assignment_csv()
    cost = emit_bom_csv()
    print(f"Wrote io_assignment.csv with {n_io} rows")
    print(f"Wrote carrier_BOM.csv; total board cost: ${cost:.2f}")
