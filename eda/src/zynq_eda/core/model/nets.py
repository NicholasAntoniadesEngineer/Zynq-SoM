"""Canonical net naming and io_assignment cross-reference for schematic connectivity."""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field


POWER_RAIL_PREFIXES: tuple[str, ...] = ("+", "CHASSIS")
POWER_INPUT_PIN_NAMES: frozenset[str] = frozenset({
    "VDD", "VCC", "VIN", "VBUS", "AVDD", "DVDD", "PVIN", "VIN_P", "VIN_N",
})


def is_power_rail(net_name: str) -> bool:
    if not net_name:
        return False
    if net_name.upper() == "GND":
        return True
    return net_name.startswith(POWER_RAIL_PREFIXES)


def is_system_signal_net(net_name: str) -> bool:
    """True when the net should use a global label (visible across the sheet)."""
    if is_power_rail(net_name):
        return True
    if net_name.startswith("NET_"):
        return False
    return True


def is_local_fallback_net(net_name: str) -> bool:
    return net_name.startswith("NET_")


@dataclass
class NetRegistry:
    """Maps io_assignment destinations to carrier-side signal names."""

    signals_by_destination: dict[str, set[str]] = field(default_factory=dict)
    destinations_by_signal: dict[str, set[str]] = field(default_factory=dict)

    @classmethod
    def from_io_rows(
        cls,
        io_rows: tuple[object, ...],
    ) -> "NetRegistry":
        signals_by_destination: dict[str, set[str]] = defaultdict(set)
        destinations_by_signal: dict[str, set[str]] = defaultdict(set)
        for row in io_rows:
            destination = getattr(row, "destination", "")
            carrier_signal = getattr(row, "carrier_signal", "")
            if not destination or not carrier_signal:
                continue
            signals_by_destination[destination].add(carrier_signal)
            destinations_by_signal[carrier_signal].add(destination)
        return cls(
            signals_by_destination=dict(signals_by_destination),
            destinations_by_signal=dict(destinations_by_signal),
        )

    def signals_for_destination(self, destination: str) -> set[str]:
        return self.signals_by_destination.get(destination, set())


def pin_net_overrides_map(
    overrides: tuple[tuple[str, str], ...],
) -> dict[str, str]:
    return dict(overrides)


def resolve_ic_pin_net_name(
    ic_reference: str,
    pin_name: str,
    pin_overrides: dict[str, str],
    supply_rail: str,
    external_to_net: str | None = None,
) -> str:
    """Choose a human-readable net name for an IC pin."""
    if pin_name in pin_overrides:
        return pin_overrides[pin_name]

    if external_to_net is not None:
        pin_upper = pin_name.upper()
        if external_to_net.upper() == "GND" and pin_upper in POWER_INPUT_PIN_NAMES:
            if supply_rail:
                return supply_rail
            return "+3V3"
        if is_power_rail(external_to_net):
            return external_to_net
        return external_to_net

    sanitised = (
        pin_name
        .replace(" ", "_")
        .replace("/", "_")
        .replace("+", "P")
        .replace("-", "N")
    )
    return f"NET_{ic_reference}_{sanitised}"


def record_label_emission(
    label_counts: Counter[str],
    net_name: str,
) -> None:
    label_counts[net_name] += 1
