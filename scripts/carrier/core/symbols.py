"""Embedded KiCad symbol library for the carrier generator.

Each symbol is a (lib_id, body) tuple emitted into the (lib_symbols ...)
section of every sheet that uses it. Symbols use simple rectangular
bodies with pins arranged on a grid; the user can replace individual
symbols with KiCad library equivalents post-generation if desired.

Symbol pin counts are validated against the BOM footprint pad counts
by the validator (rule B3).

Geometry model (kicad-sch-api compatible):
    SymbolDef.bounding_box        -> BoundingBox in symbol-local coordinates
    SymbolDef.pin_position(name)  -> Point in symbol-local coordinates
    PlacedSymbol.origin           -> Point in schematic-space coordinates
    PlacedSymbol.bounding_box     -> BoundingBox in schematic-space coordinates
    PlacedSymbol.pin_position(name) -> Point in schematic-space coordinates

These methods feed the obstacle-aware Manhattan router and the
``place_decoupling`` helper.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from scripts.carrier.core.geometry import BoundingBox
from scripts.carrier.core.sexpr import Point, make_uuid


PIN_PITCH_MM: float = 2.54
PIN_LENGTH_MM: float = 2.54


@dataclass(frozen=True)
class SymbolPin:
    """A single pin on a SymbolDef (in symbol-local coordinates).

    Attributes:
        number: Pad/pin number as a string ("1", "EP", "A4", "SH1").
        name: Pin name as it appears on the schematic ("VDD", "SDA", "~").
        side: "L" or "R" - which side of the rectangular symbol body.
        electrical_type: KiCad pin electrical type. One of:
            bidirectional, input, output, power_in, power_out, passive,
            open_collector, open_emitter, no_connect.
    """

    number: str
    name: str
    side: str
    electrical_type: str = "bidirectional"


# Public alias for clarity at call sites that want the kicad-sch-api naming.
Pin = SymbolPin


@dataclass(frozen=True)
class SymbolDef:
    lib_id: str
    width_mm: float
    pins: tuple[SymbolPin, ...]
    description: str = ""

    def height_mm(self) -> float:
        left_count = sum(1 for pin in self.pins if pin.side == "L")
        right_count = sum(1 for pin in self.pins if pin.side == "R")
        return max(left_count, right_count) * PIN_PITCH_MM + PIN_PITCH_MM

    @property
    def bounding_box(self) -> BoundingBox:
        """Symbol-local bounding box (origin at left edge centre Y=0).

        The body rectangle spans X=[0, width_mm] and Y=[-h/2, +h/2]. Pins
        protrude PIN_LENGTH_MM beyond each side, so the obstacle box
        includes them.
        """
        half_height_mm = self.height_mm() / 2
        return BoundingBox(
            top_left=Point(-PIN_LENGTH_MM, -half_height_mm),
            bottom_right=Point(self.width_mm + PIN_LENGTH_MM, half_height_mm),
        )

    def pin_position(self, name_or_number: str) -> Point:
        """Return the pin's tip coordinate in symbol-local space.

        ``name_or_number`` matches against ``SymbolPin.number`` first, then
        against ``SymbolPin.name``. Raises KeyError if unmatched.
        """
        target_pin, side_index = self._lookup_pin(name_or_number)
        half_height_mm = self.height_mm() / 2
        pin_y = half_height_mm - (side_index + 1) * PIN_PITCH_MM
        if target_pin.side == "L":
            return Point(-PIN_LENGTH_MM, pin_y)
        return Point(self.width_mm + PIN_LENGTH_MM, pin_y)

    def _lookup_pin(self, name_or_number: str) -> tuple[SymbolPin, int]:
        for side_label in ("L", "R"):
            side_pins = [pin for pin in self.pins if pin.side == side_label]
            for index, pin in enumerate(side_pins):
                if pin.number == name_or_number or pin.name == name_or_number:
                    return pin, index
        raise KeyError(
            f"SymbolDef {self.lib_id!r} has no pin matching {name_or_number!r}; "
            f"valid numbers: {[pin.number for pin in self.pins]}"
        )


# ---------------------------------------------------------------------------
# Generic two-pin part symbols (R, C, L, D, LED)
# ---------------------------------------------------------------------------

GENERIC_R = SymbolDef(
    lib_id="Carrier:R",
    width_mm=2.54,
    pins=(
        SymbolPin("1", "~", "L", "passive"),
        SymbolPin("2", "~", "R", "passive"),
    ),
    description="Resistor",
)

GENERIC_C = SymbolDef(
    lib_id="Carrier:C",
    width_mm=2.54,
    pins=(
        SymbolPin("1", "~", "L", "passive"),
        SymbolPin("2", "~", "R", "passive"),
    ),
    description="Capacitor",
)

GENERIC_L = SymbolDef(
    lib_id="Carrier:L",
    width_mm=2.54,
    pins=(
        SymbolPin("1", "~", "L", "passive"),
        SymbolPin("2", "~", "R", "passive"),
    ),
    description="Inductor / ferrite bead",
)

GENERIC_LED = SymbolDef(
    lib_id="Carrier:LED",
    width_mm=2.54,
    pins=(
        SymbolPin("1", "K", "L", "passive"),
        SymbolPin("2", "A", "R", "passive"),
    ),
    description="LED (K=cathode, A=anode)",
)

GENERIC_D_SCHOTTKY = SymbolDef(
    lib_id="Carrier:D_Schottky",
    width_mm=2.54,
    pins=(
        SymbolPin("1", "K", "L", "passive"),
        SymbolPin("2", "A", "R", "passive"),
    ),
    description="Schottky diode",
)

GENERIC_TVS = SymbolDef(
    lib_id="Carrier:TVS",
    width_mm=2.54,
    pins=(
        SymbolPin("1", "1", "L", "passive"),
        SymbolPin("2", "2", "R", "passive"),
    ),
    description="TVS diode (bidirectional)",
)

# ---------------------------------------------------------------------------
# Active part symbols (one per IC)
# ---------------------------------------------------------------------------

USBLC6_SYMBOL = SymbolDef(
    lib_id="Carrier:USBLC6-4SC6",
    width_mm=15.24,
    pins=(
        SymbolPin("1", "I/O1", "L"),
        SymbolPin("2", "GND", "L", "power_in"),
        SymbolPin("3", "VBUS", "L", "power_in"),
        SymbolPin("4", "I/O2", "R"),
        SymbolPin("5", "I/O3", "R"),
        SymbolPin("6", "I/O4", "R"),
    ),
    description="STMicro USBLC6-4SC6 USB 2.0 ESD",
)

SS14_SYMBOL = SymbolDef(
    lib_id="Carrier:SS14",
    width_mm=2.54,
    pins=(
        SymbolPin("1", "K", "L", "passive"),
        SymbolPin("2", "A", "R", "passive"),
    ),
    description="onsemi SS14 Schottky 40V/1A",
)

FUSB302_SYMBOL = SymbolDef(
    lib_id="Carrier:FUSB302BMPX",
    width_mm=20.32,
    pins=(
        SymbolPin("1", "VBUS", "L", "input"),
        SymbolPin("2", "GND", "L", "power_in"),
        SymbolPin("3", "VDD", "L", "power_in"),
        SymbolPin("4", "CC1", "L"),
        SymbolPin("5", "CC2", "L"),
        SymbolPin("6", "VCONN_1", "L"),
        SymbolPin("7", "VCONN_2", "L"),
        SymbolPin("8", "SDA", "R"),
        SymbolPin("9", "SCL", "R"),
        SymbolPin("10", "INT_N", "R", "output"),
        SymbolPin("11", "GND", "R", "power_in"),
        SymbolPin("12", "GND", "R", "power_in"),
        SymbolPin("13", "GND", "R", "power_in"),
        SymbolPin("14", "GND_EP", "R", "power_in"),
    ),
    description="ONsemi FUSB302BMPX USB-PD CC controller",
)

TPS2051_SYMBOL = SymbolDef(
    lib_id="Carrier:TPS2051CDBVR",
    width_mm=12.7,
    pins=(
        SymbolPin("1", "IN", "L", "power_in"),
        SymbolPin("2", "GND", "L", "power_in"),
        SymbolPin("3", "EN_N", "L", "input"),
        SymbolPin("4", "OC_N", "R", "output"),
        SymbolPin("5", "OUT", "R", "power_out"),
    ),
    description="TI TPS2051C USB load switch",
)

CP2102N_SYMBOL = SymbolDef(
    lib_id="Carrier:CP2102N",
    width_mm=25.4,
    pins=(
        SymbolPin("1", "DCD_N", "L"),
        SymbolPin("2", "RI_N", "L"),
        SymbolPin("3", "GND", "L", "power_in"),
        SymbolPin("4", "D+", "L"),
        SymbolPin("5", "D-", "L"),
        SymbolPin("6", "VDD", "L", "power_in"),
        SymbolPin("7", "REGIN", "L", "power_in"),
        SymbolPin("8", "VBUS", "L", "power_in"),
        SymbolPin("9", "RST_N", "L", "input"),
        SymbolPin("10", "NC1", "L"),
        SymbolPin("11", "CHREN", "L"),
        SymbolPin("12", "SUSPEND", "R", "output"),
        SymbolPin("13", "SUSPEND_N", "R", "output"),
        SymbolPin("14", "NC2", "R"),
        SymbolPin("15", "GPIO3", "R", "bidirectional"),
        SymbolPin("16", "GPIO2", "R", "bidirectional"),
        SymbolPin("17", "GPIO1", "R", "bidirectional"),
        SymbolPin("18", "GPIO0", "R", "bidirectional"),
        SymbolPin("19", "RXD", "R", "input"),
        SymbolPin("20", "TXD", "R", "output"),
        SymbolPin("21", "RTS_N", "R", "output"),
        SymbolPin("22", "CTS_N", "R", "input"),
        SymbolPin("23", "DSR_N", "R", "input"),
        SymbolPin("24", "DTR_N", "R", "output"),
        SymbolPin("EP", "GND", "R", "power_in"),
    ),
    description="Silicon Labs CP2102N USB-UART",
)

INA226_SYMBOL = SymbolDef(
    lib_id="Carrier:INA226AIDGSR",
    width_mm=15.24,
    pins=(
        SymbolPin("1", "IN+", "L", "input"),
        SymbolPin("2", "IN-", "L", "input"),
        SymbolPin("3", "VBUS", "L", "input"),
        SymbolPin("4", "GND", "L", "power_in"),
        SymbolPin("5", "VS", "L", "power_in"),
        SymbolPin("6", "SCL", "R"),
        SymbolPin("7", "SDA", "R"),
        SymbolPin("8", "ALERT", "R", "output"),
        SymbolPin("9", "A0", "R"),
        SymbolPin("10", "A1", "R"),
    ),
    description="TI INA226 current/power monitor",
)

DS3231_SYMBOL = SymbolDef(
    lib_id="Carrier:DS3231SN",
    width_mm=17.78,
    pins=(
        SymbolPin("1", "32kHz", "L", "output"),
        SymbolPin("2", "VCC", "L", "power_in"),
        SymbolPin("3", "INT_SQW", "L", "output"),
        SymbolPin("4", "RST_N", "L", "bidirectional"),
        SymbolPin("5", "NC1", "L"),
        SymbolPin("6", "NC2", "L"),
        SymbolPin("7", "NC3", "L"),
        SymbolPin("8", "NC4", "L"),
        SymbolPin("9", "NC5", "R"),
        SymbolPin("10", "NC6", "R"),
        SymbolPin("11", "NC7", "R"),
        SymbolPin("12", "NC8", "R"),
        SymbolPin("13", "GND", "R", "power_in"),
        SymbolPin("14", "VBAT", "R", "power_in"),
        SymbolPin("15", "SDA", "R"),
        SymbolPin("16", "SCL", "R"),
    ),
    description="Maxim DS3231 RTC with TCXO",
)

EEPROM_24LC256_SYMBOL = SymbolDef(
    lib_id="Carrier:24LC256",
    width_mm=12.7,
    pins=(
        SymbolPin("1", "A0", "L"),
        SymbolPin("2", "A1", "L"),
        SymbolPin("3", "A2", "L"),
        SymbolPin("4", "VSS", "L", "power_in"),
        SymbolPin("5", "SDA", "R"),
        SymbolPin("6", "SCL", "R"),
        SymbolPin("7", "WP", "R"),
        SymbolPin("8", "VCC", "R", "power_in"),
    ),
    description="Microchip 24LC256 I2C EEPROM",
)

TLV757_SYMBOL = SymbolDef(
    lib_id="Carrier:TLV757",
    width_mm=12.7,
    pins=(
        SymbolPin("1", "IN", "L", "power_in"),
        SymbolPin("2", "GND", "L", "power_in"),
        SymbolPin("3", "EN", "L", "input"),
        SymbolPin("4", "NR_SS", "R"),
        SymbolPin("5", "OUT", "R", "power_out"),
    ),
    description="TI TLV75718/25/33 LDO",
)

TPD12S016_SYMBOL = SymbolDef(
    lib_id="Carrier:TPD12S016PWR",
    width_mm=25.4,
    pins=(
        SymbolPin("1", "CEC_A", "L"),
        SymbolPin("2", "HPD_A", "L"),
        SymbolPin("3", "GND", "L", "power_in"),
        SymbolPin("4", "SDA_A", "L"),
        SymbolPin("5", "SCL_A", "L"),
        SymbolPin("6", "CT_CP_HPD", "L"),
        SymbolPin("7", "HPD_B", "L"),
        SymbolPin("8", "GND", "L", "power_in"),
        SymbolPin("9", "SDA_B", "L"),
        SymbolPin("10", "SCL_B", "L"),
        SymbolPin("11", "CEC_B", "L"),
        SymbolPin("12", "GND", "L", "power_in"),
        SymbolPin("13", "D2-", "R"),
        SymbolPin("14", "D2+", "R"),
        SymbolPin("15", "D1-", "R"),
        SymbolPin("16", "D1+", "R"),
        SymbolPin("17", "D0-", "R"),
        SymbolPin("18", "D0+", "R"),
        SymbolPin("19", "CLK-", "R"),
        SymbolPin("20", "CLK+", "R"),
        SymbolPin("21", "VCCB", "R", "power_in"),
        SymbolPin("22", "VCCA", "R", "power_in"),
        SymbolPin("23", "AGND", "R", "power_in"),
        SymbolPin("24", "5V_HDMI", "R", "power_out"),
    ),
    description="TI TPD12S016 HDMI companion",
)

USBC_16P_SYMBOL = SymbolDef(
    lib_id="Carrier:USBC_16P",
    width_mm=20.32,
    pins=(
        SymbolPin("A1", "GND", "L", "power_in"),
        SymbolPin("A4", "VBUS", "L", "power_in"),
        SymbolPin("A5", "CC1", "L"),
        SymbolPin("A6", "D+", "L"),
        SymbolPin("A7", "D-", "L"),
        SymbolPin("A8", "SBU1", "L"),
        SymbolPin("A9", "VBUS", "L", "power_in"),
        SymbolPin("A12", "GND", "L", "power_in"),
        SymbolPin("B1", "GND", "R", "power_in"),
        SymbolPin("B4", "VBUS", "R", "power_in"),
        SymbolPin("B5", "CC2", "R"),
        SymbolPin("B6", "D+", "R"),
        SymbolPin("B7", "D-", "R"),
        SymbolPin("B8", "SBU2", "R"),
        SymbolPin("B9", "VBUS", "R", "power_in"),
        SymbolPin("B12", "GND", "R", "power_in"),
        SymbolPin("SH", "SHIELD", "R", "passive"),
    ),
    description="USB Type-C 16P receptacle (USB 2.0)",
)

HDMI_A_SYMBOL = SymbolDef(
    lib_id="Carrier:HDMI_A_Receptacle",
    width_mm=25.4,
    pins=(
        SymbolPin("1", "TMDS_D2+", "L"),
        SymbolPin("2", "TMDS_D2_SH", "L"),
        SymbolPin("3", "TMDS_D2-", "L"),
        SymbolPin("4", "TMDS_D1+", "L"),
        SymbolPin("5", "TMDS_D1_SH", "L"),
        SymbolPin("6", "TMDS_D1-", "L"),
        SymbolPin("7", "TMDS_D0+", "L"),
        SymbolPin("8", "TMDS_D0_SH", "L"),
        SymbolPin("9", "TMDS_D0-", "L"),
        SymbolPin("10", "TMDS_CLK+", "L"),
        SymbolPin("11", "TMDS_CLK_SH", "L"),
        SymbolPin("12", "TMDS_CLK-", "L"),
        SymbolPin("13", "CEC", "R"),
        SymbolPin("14", "HEC-", "R"),
        SymbolPin("15", "SCL", "R"),
        SymbolPin("16", "SDA", "R"),
        SymbolPin("17", "DDC_GND", "R", "power_in"),
        SymbolPin("18", "+5V", "R", "power_in"),
        SymbolPin("19", "HPD", "R"),
        SymbolPin("SHIELD", "SHIELD", "R", "passive"),
    ),
    description="HDMI Type-A receptacle",
)

MICROSD_SYMBOL = SymbolDef(
    lib_id="Carrier:microSD_DM3AT",
    width_mm=20.32,
    pins=(
        SymbolPin("1", "DAT2", "L"),
        SymbolPin("2", "DAT3_CD", "L"),
        SymbolPin("3", "CMD", "L"),
        SymbolPin("4", "VDD", "L", "power_in"),
        SymbolPin("5", "CLK", "L", "input"),
        SymbolPin("6", "VSS", "L", "power_in"),
        SymbolPin("7", "DAT0", "R"),
        SymbolPin("8", "DAT1", "R"),
        SymbolPin("9", "CD_SW", "R", "output"),
        SymbolPin("10", "CD_SW_COM", "R", "power_in"),
        SymbolPin("SH", "SHIELD", "R", "passive"),
    ),
    description="Hirose DM3AT-SF-PEJM5 microSD socket",
)

RJ45_SYMBOL = SymbolDef(
    lib_id="Carrier:RJ45_RJHSE5380",
    width_mm=22.86,
    pins=(
        SymbolPin("1", "MDI0_P", "L"),
        SymbolPin("2", "MDI0_N", "L"),
        SymbolPin("3", "MDI1_P", "L"),
        SymbolPin("4", "MDI2_P", "L"),
        SymbolPin("5", "MDI2_N", "L"),
        SymbolPin("6", "MDI1_N", "L"),
        SymbolPin("7", "MDI3_P", "L"),
        SymbolPin("8", "MDI3_N", "L"),
        SymbolPin("9", "LED1_A", "R", "passive"),
        SymbolPin("10", "LED1_K", "R", "passive"),
        SymbolPin("11", "LED2_A", "R", "passive"),
        SymbolPin("12", "LED2_K", "R", "passive"),
        SymbolPin("SH1", "SHIELD", "R", "passive"),
        SymbolPin("SH2", "SHIELD", "R", "passive"),
        SymbolPin("SH3", "SHIELD", "R", "passive"),
        SymbolPin("SH4", "SHIELD", "R", "passive"),
    ),
    description="Amphenol RJHSE5380 bare RJ45 with LEDs",
)

HX5008NLT_SYMBOL = SymbolDef(
    lib_id="Carrier:HX5008NLT",
    width_mm=25.4,
    pins=(
        # PHY side (left)
        SymbolPin("1",  "TD0+", "L"),
        SymbolPin("2",  "TD0-", "L"),
        SymbolPin("3",  "CT_PHY0", "L"),
        SymbolPin("7",  "TD1+", "L"),
        SymbolPin("8",  "TD1-", "L"),
        SymbolPin("9",  "CT_PHY1", "L"),
        SymbolPin("13", "TD2+", "L"),
        SymbolPin("14", "TD2-", "L"),
        SymbolPin("15", "CT_PHY2", "L"),
        SymbolPin("19", "TD3+", "L"),
        SymbolPin("20", "TD3-", "L"),
        SymbolPin("21", "CT_PHY3", "L"),
        # Line side (right)
        SymbolPin("4",  "MDI0+", "R"),
        SymbolPin("5",  "MDI0-", "R"),
        SymbolPin("6",  "CT_PAIR0", "R"),
        SymbolPin("10", "MDI1+", "R"),
        SymbolPin("11", "MDI1-", "R"),
        SymbolPin("12", "CT_PAIR1", "R"),
        SymbolPin("16", "MDI2+", "R"),
        SymbolPin("17", "MDI2-", "R"),
        SymbolPin("18", "CT_PAIR2", "R"),
        SymbolPin("22", "MDI3+", "R"),
        SymbolPin("23", "MDI3-", "R"),
        SymbolPin("24", "CT_PAIR3", "R"),
    ),
    description="Pulse HX5008NLT 1000BASE-T magnetics",
)

# Generic pin header symbol (variable pin count). We emit specific variants
# (2x6 PMOD, 2x7 JTAG, 2x5 SWD) by adapting at sheet-build time.


# ---------------------------------------------------------------------------
# PlacedSymbol - one instance of a SymbolDef on the schematic
# ---------------------------------------------------------------------------


@dataclass
class PlacedSymbol:
    """A single placed symbol instance on the schematic.

    Attributes:
        reference: KiCad reference designator (e.g. "U_PD1", "C_BULK_VDD").
        symbol: SymbolDef this instance was made from.
        value: Schematic value field (e.g. "FUSB302BMPX", "100n").
        footprint: KiCad footprint reference.
        origin: Placement coordinate of the symbol's local-(0,0) point in
            schematic space.
        uuid: KiCad object UUID for this placement.
        pin_uuids: One UUID per pin number, generated lazily.
    """

    reference: str
    symbol: SymbolDef
    value: str
    footprint: str
    origin: Point
    uuid: str = field(default_factory=make_uuid)
    pin_uuids: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.pin_uuids:
            self.pin_uuids = {pin.number: make_uuid() for pin in self.symbol.pins}

    @property
    def lib_id(self) -> str:
        return self.symbol.lib_id

    @property
    def bounding_box(self) -> BoundingBox:
        local_box = self.symbol.bounding_box
        return BoundingBox(
            top_left=Point(
                self.origin.x + local_box.top_left.x,
                self.origin.y + local_box.top_left.y,
            ),
            bottom_right=Point(
                self.origin.x + local_box.bottom_right.x,
                self.origin.y + local_box.bottom_right.y,
            ),
        )

    def pin_position(self, name_or_number: str) -> Point:
        """Pin tip position in schematic space."""
        local_position = self.symbol.pin_position(name_or_number)
        return Point(
            self.origin.x + local_position.x,
            self.origin.y + local_position.y,
        )


# Master registry
SYMBOL_LIBRARY: dict[str, SymbolDef] = {
    "R": GENERIC_R,
    "C": GENERIC_C,
    "L": GENERIC_L,
    "LED": GENERIC_LED,
    "D_Schottky": GENERIC_D_SCHOTTKY,
    "TVS": GENERIC_TVS,
    "USBLC6-4SC6": USBLC6_SYMBOL,
    "SS14": SS14_SYMBOL,
    "FUSB302BMPX": FUSB302_SYMBOL,
    "TPS2051CDBVR": TPS2051_SYMBOL,
    "CP2102N": CP2102N_SYMBOL,
    "INA226AIDGSR": INA226_SYMBOL,
    "DS3231SN": DS3231_SYMBOL,
    "24LC256": EEPROM_24LC256_SYMBOL,
    "TLV757": TLV757_SYMBOL,
    "TLV75718PDBVR": TLV757_SYMBOL,
    "TLV75725PDBVR": TLV757_SYMBOL,
    "TLV75733PDBVR": TLV757_SYMBOL,
    "TPD12S016PWR": TPD12S016_SYMBOL,
    "USBC_16P": USBC_16P_SYMBOL,
    "HDMI_A_Receptacle": HDMI_A_SYMBOL,
    "microSD_DM3AT": MICROSD_SYMBOL,
    "RJ45_RJHSE5380": RJ45_SYMBOL,
    "HX5008NLT": HX5008NLT_SYMBOL,
}
