"""USB-C OTG port with TPS2051 load switch and USBLC6."""

from __future__ import annotations

from pathlib import Path

from scripts.carrier.blocks._block_common import (
    load_io_rows,
    pin_direction_for_interface,
)
from scripts.carrier.blocks._geometry import SymbolGeometryCache
from scripts.carrier.blocks._hand_block import (
    HandSectionMerge,
    build_hand_section,
    connect,
    merge_hand_sections,
    wire_hier_from_taps,
)
from scripts.carrier.model.block import Block
from scripts.carrier.model.grid import Point
from scripts.carrier.refcircuits.tps2051 import TPS2051_REFCIRCUIT
from scripts.carrier.refcircuits.usbc_connector import USBC_DEVICE_REFCIRCUIT
from scripts.carrier.refcircuits.usblc6 import USBLC6_REFCIRCUIT


SCRIPTS_DIR = Path(__file__).resolve().parents[2]
CARRIER_SYMBOLS = (SCRIPTS_DIR / "carrier" / "symbols" / "carrier.kicad_sym").resolve()

USBC_LIB = "carrier:USBC_16P"
USBLC6_LIB = "carrier:USBLC6-4SC6"
TPS2051_LIB = "Power_Management:TPS2051CDBV"
USBC_ANCHOR = Point(50.8, 76.2)
USBLC6_ANCHOR = Point(127.0, 76.2)
LOADSW_ANCHOR = Point(203.2, 76.2)


def build() -> Block:
    usbc = build_hand_section(
        name="usbc_otg_usbc",
        title="USBC",
        ref_circuit=USBC_DEVICE_REFCIRCUIT,
        registry_token="conn_USB_C_16P",
        ic_reference="JUSBC2",
        ic_anchor=USBC_ANCHOR,
        io_destinations=(),
        designator_prefix="CO",
        require_all_hier_wired=False,
    )
    esd = build_hand_section(
        name="usbc_otg_esd",
        title="ESD",
        ref_circuit=USBLC6_REFCIRCUIT,
        registry_token="esd_USBLC6_4SC6",
        ic_lib_id=USBLC6_LIB,
        ic_reference="UESD2",
        ic_anchor=USBLC6_ANCHOR,
        io_destinations=(),
        designator_prefix="CE",
        require_all_hier_wired=False,
    )
    loadsw = build_hand_section(
        name="usbc_otg_ls",
        title="Load switch",
        ref_circuit=TPS2051_REFCIRCUIT,
        registry_token="loadsw_TPS2051C",
        ic_reference="ULS1",
        ic_anchor=LOADSW_ANCHOR,
        io_destinations=(),
        designator_prefix="CL",
        require_all_hier_wired=False,
    )

    geometry_cache = SymbolGeometryCache()
    geometry_cache.register_libraries((CARRIER_SYMBOLS,))

    usbc_d_plus = geometry_cache.absolute_pin_by_name(USBC_LIB, USBC_ANCHOR, "D+")
    usbc_d_minus = geometry_cache.absolute_pin_by_name(USBC_LIB, USBC_ANCHOR, "D-")
    usbc_vbus = geometry_cache.absolute_pin_by_name(USBC_LIB, USBC_ANCHOR, "VBUS")
    usbc_id = geometry_cache.absolute_pin_by_name(USBC_LIB, USBC_ANCHOR, "SBU1")
    esd_io1 = geometry_cache.absolute_pin_by_name(USBLC6_LIB, USBLC6_ANCHOR, "I/O1")
    esd_io2 = geometry_cache.absolute_pin_by_name(USBLC6_LIB, USBLC6_ANCHOR, "I/O2")
    vbus_out_en = geometry_cache.absolute_pin_by_name(
        TPS2051_LIB,
        LOADSW_ANCHOR,
        "EN",
    )

    inter_wires = connect(usbc_d_plus, esd_io1) + connect(usbc_d_minus, esd_io2)

    merged = merge_hand_sections(
        HandSectionMerge(
            name="usbc_otg",
            title="USB-C OTG (TPS2051 + USBLC6 + USBC)",
            sections=(usbc, esd, loadsw),
            inter_wires=tuple(inter_wires),
        )
    )

    interface_rows = load_io_rows("J_USBC2_OTG", "U_LS1")
    tap_points = {
        "USB_D+": esd_io1,
        "USB_D-": esd_io2,
        "USB_VBUS": usbc_vbus,
        "USB_ID": usbc_id,
        "VBUS_OUT_EN": vbus_out_en,
    }
    interface_nets: list[tuple[str, object]] = []
    seen_signals: set[str] = set()
    for row in interface_rows:
        if row.carrier_signal in seen_signals:
            continue
        seen_signals.add(row.carrier_signal)
        if row.carrier_signal not in tap_points:
            raise ValueError(
                f"usbc_otg: missing tap for signal {row.carrier_signal!r}"
            )
        interface_nets.append(
            (row.carrier_signal, pin_direction_for_interface(row.interface))
        )

    hierarchical_pins, hier_wires = wire_hier_from_taps(
        interface_nets=tuple(interface_nets),
        tap_points=tap_points,
        paper_width_mm=merged.layout.width_mm,
    )

    return Block(
        name=merged.name,
        title=merged.title,
        layout=merged.layout,
        components=merged.components,
        wires=merged.wires + tuple(hier_wires),
        local_labels=merged.local_labels,
        hierarchical_pins=tuple(hierarchical_pins),
        symbol_library_paths=merged.symbol_library_paths,
    )
