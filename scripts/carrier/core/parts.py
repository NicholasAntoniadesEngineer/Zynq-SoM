"""Canonical part registry mapping part tokens to LCSC parts and footprints.

Every cap/resistor/IC/connector is referenced throughout the generator by
a stable token (e.g. "100n_0402_X7R", "FUSB302BMPX"). This module is the
single source of truth that maps tokens to concrete LCSC part numbers,
manufacturer P/Ns, footprints, datasheet URLs, and verified stock figures.

The BOM CSV is generated from this registry; reference circuits reference
these tokens; the validator checks that every token resolves cleanly.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

_LCSC_REGEX = re.compile(r"^C\d{4,9}$")
_REF_REGEX = re.compile(
    r"^(R|C|L|D|Q|U|J|SW|Y|X|H|TP|FB|F|B|T)[\dA-Z_]+$"
)


@dataclass(frozen=True)
class BOMPart:
    """A single concrete part in the BOM.

    Attributes:
        token: Stable canonical name (used everywhere in the generator).
        value: Schematic value field (e.g. "100n", "10k", "FUSB302BMPX").
        footprint: KiCad footprint reference (e.g. "Capacitor_SMD:C_0402_1005Metric").
        lcsc: LCSC part number (Cxxxxx).
        mpn: Manufacturer part number.
        manufacturer: Manufacturer name.
        package: Mechanical package (e.g. "0402", "SOT-23-5", "QFN-14").
        datasheet_url: URL to the datasheet PDF.
        description: Short human-readable description.
        stock_at_lcsc: Quantity in stock at LCSC (informational).
        unit_price_usd: Unit price at the build quantity (informational).
        alt_lcsc: Alternative LCSC parts (comma-separated).
        alt_digikey: Alternative DigiKey part number.
        rohs: RoHS3 compliance flag.
        temp_min_c: Operating temperature minimum (C).
        temp_max_c: Operating temperature maximum (C).
        allow_low_stock: Override for stock check in validator.
    """

    token: str
    value: str
    footprint: str
    lcsc: str
    mpn: str
    manufacturer: str
    package: str
    datasheet_url: str
    description: str
    stock_at_lcsc: int = 0
    unit_price_usd: float = 0.0
    alt_lcsc: str = ""
    alt_digikey: str = ""
    rohs: bool = True
    temp_min_c: int = -40
    temp_max_c: int = 85
    allow_low_stock: bool = False

    def __post_init__(self) -> None:
        if not self.token:
            raise ValueError("BOMPart.token must be non-empty")
        if not _LCSC_REGEX.fullmatch(self.lcsc):
            raise ValueError(
                f"BOMPart {self.token}: LCSC must match ^C\\d{{4,9}}$, got {self.lcsc!r}"
            )
        if not self.footprint:
            raise ValueError(f"BOMPart {self.token}: footprint must be non-empty")
        if not self.mpn:
            raise ValueError(f"BOMPart {self.token}: mpn must be non-empty")
        if not self.datasheet_url:
            raise ValueError(f"BOMPart {self.token}: datasheet_url must be non-empty")
        if not self.value:
            raise ValueError(f"BOMPart {self.token}: value must be non-empty")
        if not self.package:
            raise ValueError(f"BOMPart {self.token}: package must be non-empty")


@dataclass(frozen=True)
class PartInstance:
    """A specific use of a BOMPart on the schematic.

    Attributes:
        ref: Reference designator (e.g. "U_PD1", "C_BULK_VDD").
        token: Token into the BOMPart registry.
        sheet: Sheet name where this instance lives.
        notes: Optional notes specific to this instance.
    """

    ref: str
    token: str
    sheet: str
    notes: str = ""

    def __post_init__(self) -> None:
        if not _REF_REGEX.fullmatch(self.ref):
            raise ValueError(
                f"PartInstance ref {self.ref!r} does not match required pattern "
                "(class prefix R/C/L/D/Q/U/J/SW/Y/X/H/TP/FB/F/B/T followed by digits/letters)"
            )


# ---------------------------------------------------------------------------
# Canonical part registry (single source of truth)
# ---------------------------------------------------------------------------

# Allowed library prefixes for footprints (Rule B2)
ALLOWED_FOOTPRINT_PREFIXES = frozenset({
    "fp:",
    "Capacitor_SMD:",
    "Resistor_SMD:",
    "Inductor_SMD:",
    "LED_SMD:",
    "Diode_SMD:",
    "Package_TO_SOT_SMD:",
    "Package_SO:",
    "Package_DFN_QFN:",
    "Package_SON:",
    "Package_BGA:",
    "Package_QFP:",
    "Connector:",
    "Connector_PinHeader_2.54mm:",
    "Connector_PinHeader_1.27mm:",
    "Connector_USB:",
    "Connector_HDMI:",
    "Connector_RJ:",
    "Connector_FFC-FPC:",
    "Connector_Card:",
    "Connector_Coaxial:",
    "Connector_Samtec:",
    "Connector_Hirose:",
    "Switch_THT:",
    "Switch_SMD:",
    "Crystal:",
    "Oscillator:",
    "Battery:",
    "TestPoint:",
    "MountingHole:",
})

# Package -> expected footprint regex (Rule A5)
PACKAGE_TO_FOOTPRINT_PATTERN: dict[str, str] = {
    "0402": r".*0402.*1005Metric",
    "0603": r".*0603.*1608Metric",
    "0805": r".*0805.*2012Metric",
    "0201": r".*0201.*0603Metric",
    "1206": r".*1206.*3216Metric",
    "1210": r".*1210.*3225Metric",
    "SOT-23": r".*SOT-23.*",
    "SOT-23-5": r".*SOT-23-5.*",
    "SOT-23-6": r".*SOT-23-6.*",
    "SOIC-8": r".*SOIC-8.*",
    "SOIC-16": r".*SOIC-16.*",
    "TSSOP-24": r".*TSSOP-24.*",
    "MSOP-10": r".*(MSOP-10|VSSOP-10).*",
    "WQFN-14": r".*(WQFN-14|WFQFN-14).*",
    "QFN-24": r".*QFN-24.*",
    "QFN-32": r".*QFN-32.*",
}

# Decoupling pin-type whitelist (Rule C1)
DECOUPLING_REQUIRED_PIN_TYPES = frozenset({
    "power_in",
    "VCC", "VDD", "VDDIO", "VDDA", "AVDD", "+VDD",
    "VBAT",
})

# Connectors that must have ESD protection on data lines (Rule C6)
ESD_REQUIRED_CONNECTORS = frozenset({
    "USB-C",
    "USB-A",
    "USB-Micro-B",
    "HDMI-A",
    "HDMI-D",
    "RJ45",
    "FFC-LCD",
    "FFC-Camera",
    "microSD",
})

# Differential pair termination map (Rule C3)
DIFF_PAIR_TERMINATION: dict[str, tuple[str, str]] = {
    "TMDS": ("50R_to_AVCC", "Handled by HDMI source IC, not external"),
    "LVDS": ("100R_across_pair", "100R 0402 1% near receiver"),
    "MIPI_CSI": ("internal", "Handled by SerDes / phy IC"),
    "MIPI_DSI": ("internal", "Handled by SerDes / phy IC"),
    "USB_HS": ("internal", "Handled by USB PHY"),
    "ETH_MDI": ("internal_magnetics", "Handled by magnetics module"),
}
