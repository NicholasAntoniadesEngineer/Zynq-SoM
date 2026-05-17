"""Carrier sheet layout: explicit IC zone allocation.

The carrier evaluation board contains many IC instances - some with multiple
copies of the same MPN (six INA226 power monitors, four TLV75733 LDOs, two
USBLC6 ESD diodes, two USB-C connectors, two HDMI connectors, two EEPROMs).
Every instance must appear on the schematic with its own reference designator,
its own datasheet-required external parts, and its own non-overlapping zone.

This module owns:
    * The full set of IC instances on the carrier (``IC_INSTANCES``).
      Sums must equal ``IC_INSTANCE_COUNT`` from ``scripts.carrier.refcircuits``.
    * The geometric layout (per-section grid) that allocates a unique
      ``IcZone`` to each instance (``compute_zones``).

Sheet generators consume zones produced by ``compute_zones`` so each IC has
its own dedicated rectangular area on the page; nothing is placed on top of
anything else.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from scripts.carrier.core.geometry import BoundingBox
from scripts.carrier.core.sexpr import Point, snap_to_grid
from scripts.carrier.refcircuits import IC_INSTANCE_COUNT


# ---------------------------------------------------------------------------
# Section layout: one rectangular area per functional block on the A1 page
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SectionSpec:
    """A rectangular region on the A1 page that hosts one or more IC zones."""

    origin: Point
    width_mm: float
    height_mm: float
    columns: int = 1
    label: str = ""

    def __post_init__(self) -> None:
        if self.columns < 1:
            raise ValueError(f"SectionSpec.columns must be >= 1, got {self.columns}")
        if self.width_mm <= 0 or self.height_mm <= 0:
            raise ValueError(
                f"SectionSpec dimensions must be positive: "
                f"width={self.width_mm}, height={self.height_mm}"
            )

    @property
    def bounding_box(self) -> BoundingBox:
        return BoundingBox(
            top_left=self.origin,
            bottom_right=Point(
                self.origin.x + self.width_mm,
                self.origin.y + self.height_mm,
            ),
        )


SECTION_LAYOUT: dict[str, SectionSpec] = {
    "som_j1":         SectionSpec(Point(10.16,   20.32), 60.96, 480.06, columns=1, label="SoM J1 (Power, USB OTG, JTAG, SDIO, Eth MDI)"),
    "som_j2":         SectionSpec(Point(76.20,   20.32), 60.96, 480.06, columns=1, label="SoM J2 (Bank 13 + Bank 33 IO)"),
    "som_j3":         SectionSpec(Point(142.24,  20.32), 60.96, 480.06, columns=1, label="SoM J3 (Bank 33/34/35 IO)"),
    "power":          SectionSpec(Point(208.28,  20.32), 100.33, 100.33, columns=2, label="Power: VCCO LDO bank (TLV757 family)"),
    "power_mon":      SectionSpec(Point(208.28, 125.73), 100.33, 220.98, columns=2, label="Power Monitoring: 6x INA226 + R_SENSE"),
    "aux_io":         SectionSpec(Point(208.28, 351.79), 100.33,  90.17, columns=1, label="Aux: RTC + Board ID EEPROM"),
    "usbc_stm32":     SectionSpec(Point(312.42,  20.32), 100.33,  90.17, columns=2, label="USB-C #1 (STM32 PD/Data via FUSB302)"),
    "usbc_otg":       SectionSpec(Point(312.42, 115.57), 100.33,  90.17, columns=2, label="USB-C #2 (Zynq OTG via TPS2051)"),
    "uart_bridge":    SectionSpec(Point(312.42, 210.82), 100.33,  60.96, columns=1, label="USB-UART Bridge (CP2102N)"),
    "jtag_swd":       SectionSpec(Point(312.42, 276.86), 100.33,  60.96, columns=2, label="JTAG (Zynq) + SWD (STM32)"),
    "boot_switches":  SectionSpec(Point(312.42, 342.90), 100.33,  60.96, columns=1, label="Boot Mode + Reset Switches"),
    "ethernet":       SectionSpec(Point(417.83,  20.32), 100.33, 130.81, columns=2, label="Ethernet: RJ45 + HX5008 Magnetics + ESD"),
    "microsd":        SectionSpec(Point(417.83, 156.21), 100.33,  60.96, columns=1, label="microSD Card Socket"),
    "hdmi_tx":        SectionSpec(Point(417.83, 222.25), 100.33,  90.17, columns=2, label="HDMI TX (Source) + EDID EEPROM"),
    "hdmi_rx":        SectionSpec(Point(417.83, 317.50), 100.33,  90.17, columns=1, label="HDMI RX (Sink)"),
    "lvds_lcd":       SectionSpec(Point(522.99,  20.32), 100.33,  60.96, columns=1, label="LVDS LCD Connector (40-pin FFC)"),
    "mipi_camera":    SectionSpec(Point(522.99,  86.36), 100.33,  60.96, columns=1, label="MIPI CSI-2 Camera (15-pin FFC)"),
    "fmc_lpc":        SectionSpec(Point(522.99, 152.40), 100.33, 152.40, columns=1, label="FMC-LPC Expansion Connector"),
    "pmod":           SectionSpec(Point(522.99, 309.88), 100.33, 100.33, columns=2, label="PMOD Headers x4"),
    "xadc_clk":       SectionSpec(Point(628.65,  20.32),  60.96,  60.96, columns=1, label="XADC + MRCC Clock SMA"),
}


# ---------------------------------------------------------------------------
# IC instance manifest (must reconcile with IC_INSTANCE_COUNT)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class IcInstance:
    """One instance of an IC on the carrier board."""

    ic_name: str
    reference: str
    section: str
    instance_index: int

    def __post_init__(self) -> None:
        if not self.ic_name:
            raise ValueError("IcInstance.ic_name must be non-empty")
        if not self.reference:
            raise ValueError("IcInstance.reference must be non-empty")
        if not self.section:
            raise ValueError("IcInstance.section must be non-empty")
        if self.instance_index < 0:
            raise ValueError(
                f"IcInstance.instance_index must be >= 0, got {self.instance_index}"
            )


IC_INSTANCES: tuple[IcInstance, ...] = (
    IcInstance("FUSB302BMPX",         "U_PD1",          "usbc_stm32", 0),
    IcInstance("USBLC6-4SC6",         "U_ESD_USB1",     "usbc_stm32", 0),
    IcInstance("USBLC6-4SC6",         "U_ESD_USB2",     "usbc_otg",   1),
    IcInstance("USBC_SINK",           "J_USBC1",        "usbc_stm32", 0),
    IcInstance("USBC_SINK",           "J_USBC2",        "usbc_otg",   1),
    IcInstance("TPS2051CDBVR",        "U_LS1",          "usbc_otg",   0),
    IcInstance("CP2102N-A02-GQFN24R", "U_UART",         "uart_bridge", 0),
    IcInstance("HDMI_A",              "J_HDMITX",       "hdmi_tx",    0),
    IcInstance("HDMI_A",              "J_HDMIRX",       "hdmi_rx",    1),
    IcInstance("TPD12S016PWR_TX",     "U_HDMITX",       "hdmi_tx",    0),
    IcInstance("TPD12S016PWR_RX",     "U_HDMIRX",       "hdmi_rx",    0),
    IcInstance("INA226AIDGSR",        "U_INA_VIN",      "power_mon",  0),
    IcInstance("INA226AIDGSR",        "U_INA_3V3",      "power_mon",  1),
    IcInstance("INA226AIDGSR",        "U_INA_1V8",      "power_mon",  2),
    IcInstance("INA226AIDGSR",        "U_INA_VCCO13",   "power_mon",  3),
    IcInstance("INA226AIDGSR",        "U_INA_VCCO33",   "power_mon",  4),
    IcInstance("INA226AIDGSR",        "U_INA_3V3_SC",   "power_mon",  5),
    IcInstance("DS3231SN#",           "U_RTC",          "aux_io",     0),
    IcInstance("24LC256T-I/SN",       "U_EEP_BOARDID",  "aux_io",     0),
    IcInstance("24LC256T-I/SN",       "U_EEP_EDID",     "hdmi_tx",    1),
    IcInstance("TLV75733PDBVR",       "U_LDO_VCCO13",   "power",      0),
    IcInstance("TLV75733PDBVR",       "U_LDO_VCCO33",   "power",      1),
    IcInstance("TLV75733PDBVR",       "U_LDO_VCCO34",   "power",      2),
    IcInstance("TLV75733PDBVR",       "U_LDO_VCCO35",   "power",      3),
    IcInstance("HX5008NLT",           "T_ETH",          "ethernet",   0),
    IcInstance("RJHSE5380",           "J_RJ45",         "ethernet",   0),
    IcInstance("DM3AT-SF-PEJM5",      "J_SD",           "microsd",    0),
)


def validate_instances_against_counts() -> None:
    """Fail hard if IC_INSTANCES counts don't match IC_INSTANCE_COUNT."""

    counts_per_name: Counter[str] = Counter(
        instance.ic_name for instance in IC_INSTANCES
    )
    discrepancies: list[str] = []
    for ic_name, expected_count in IC_INSTANCE_COUNT.items():
        actual_count = counts_per_name.get(ic_name, 0)
        if actual_count != expected_count:
            discrepancies.append(
                f"{ic_name}: IC_INSTANCE_COUNT={expected_count} but "
                f"IC_INSTANCES has {actual_count}"
            )
    extras = set(counts_per_name) - set(IC_INSTANCE_COUNT)
    for extra_name in sorted(extras):
        discrepancies.append(
            f"{extra_name}: appears in IC_INSTANCES but not in IC_INSTANCE_COUNT"
        )
    if discrepancies:
        raise ValueError(
            "IC_INSTANCES manifest does not reconcile with IC_INSTANCE_COUNT:\n  "
            + "\n  ".join(discrepancies)
        )


# ---------------------------------------------------------------------------
# Zone allocation: one rectangular zone per IC instance
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class IcZone:
    """A rectangular zone on the schematic dedicated to one IC instance."""

    instance: IcInstance
    origin: Point
    width_mm: float
    height_mm: float

    @property
    def bounding_box(self) -> BoundingBox:
        return BoundingBox(
            top_left=self.origin,
            bottom_right=Point(
                self.origin.x + self.width_mm,
                self.origin.y + self.height_mm,
            ),
        )

    @property
    def ic_origin(self) -> Point:
        """Snap the IC placement origin (top-left of IC body) inside the zone."""
        return Point(
            snap_to_grid(self.origin.x + IC_BODY_INSET_MM),
            snap_to_grid(self.origin.y + IC_BODY_INSET_MM),
        )


IC_BODY_INSET_MM: float = 5.08
"""Distance from the zone top-left to the IC body's top-left placement."""

ZONE_INTERIOR_MARGIN_MM: float = 1.27
"""Margin between adjacent zones in a section grid."""


def compute_zones() -> list[IcZone]:
    """Allocate one disjoint zone per ``IcInstance`` inside its section.

    Each section's IC instances are tiled in a grid (``columns`` columns,
    rows wrapping). Zone dimensions are uniform within a section and sized
    so the IC body, all external parts, and a margin all fit. Fails hard
    if any section runs out of room for its assigned instances.
    """

    validate_instances_against_counts()

    instances_by_section: dict[str, list[IcInstance]] = {}
    for instance in IC_INSTANCES:
        instances_by_section.setdefault(instance.section, []).append(instance)

    zones: list[IcZone] = []
    for section_name, section_instances in instances_by_section.items():
        if section_name not in SECTION_LAYOUT:
            raise KeyError(
                f"compute_zones: section {section_name!r} referenced by "
                f"{[i.reference for i in section_instances]} but missing from "
                f"SECTION_LAYOUT"
            )
        section_spec = SECTION_LAYOUT[section_name]
        column_count = section_spec.columns
        row_count = -(-len(section_instances) // column_count)  # ceil division
        zone_width_mm = snap_to_grid(
            (section_spec.width_mm - (column_count + 1) * ZONE_INTERIOR_MARGIN_MM)
            / column_count
        )
        zone_height_mm = snap_to_grid(
            (section_spec.height_mm - (row_count + 1) * ZONE_INTERIOR_MARGIN_MM)
            / row_count
        )
        if zone_width_mm <= IC_BODY_INSET_MM * 2:
            raise ValueError(
                f"compute_zones: section {section_name!r} zone width "
                f"{zone_width_mm}mm too narrow for IC body inset"
            )
        if zone_height_mm <= IC_BODY_INSET_MM * 2:
            raise ValueError(
                f"compute_zones: section {section_name!r} zone height "
                f"{zone_height_mm}mm too short for IC body inset"
            )

        for index, instance in enumerate(section_instances):
            grid_column = index % column_count
            grid_row = index // column_count
            zone_origin_x = snap_to_grid(
                section_spec.origin.x
                + ZONE_INTERIOR_MARGIN_MM
                + grid_column * (zone_width_mm + ZONE_INTERIOR_MARGIN_MM)
            )
            zone_origin_y = snap_to_grid(
                section_spec.origin.y
                + ZONE_INTERIOR_MARGIN_MM
                + grid_row * (zone_height_mm + ZONE_INTERIOR_MARGIN_MM)
            )
            zones.append(IcZone(
                instance=instance,
                origin=Point(zone_origin_x, zone_origin_y),
                width_mm=zone_width_mm,
                height_mm=zone_height_mm,
            ))
    return zones


__all__ = [
    "IC_BODY_INSET_MM",
    "IC_INSTANCES",
    "IcInstance",
    "IcZone",
    "SECTION_LAYOUT",
    "SectionSpec",
    "ZONE_INTERIOR_MARGIN_MM",
    "compute_zones",
    "validate_instances_against_counts",
]
