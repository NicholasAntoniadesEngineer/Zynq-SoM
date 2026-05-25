"""Smoke tests: the package imports cleanly and the ported catalog loads."""

from __future__ import annotations


def test_package_version() -> None:
    import zynq_eda

    assert zynq_eda.__version__


def test_core_model_exports() -> None:
    from zynq_eda.core.model import (
        KICAD_GRID_MM,
        ExternalPart,
        HierarchicalPin,
        IcBlockTemplate,
        LayoutNote,
        NetRegistry,
        PinDirection,
        PinGroup,
        PinGroupOffset,
        Point,
        ReferenceCircuit,
        SheetEdge,
        StrapPin,
        assert_on_grid,
        is_power_rail,
        snap_to_grid,
    )

    assert KICAD_GRID_MM == 1.27
    assert snap_to_grid(1.27 * 7 + 0.0001) == 1.27 * 7
    assert is_power_rail("+3V3")
    assert is_power_rail("GND")
    assert not is_power_rail("SDA")
    # IDE / linter sanity: every imported symbol is exported
    assert all(
        sym is not None
        for sym in (
            ExternalPart,
            HierarchicalPin,
            IcBlockTemplate,
            LayoutNote,
            NetRegistry,
            PinDirection,
            PinGroup,
            PinGroupOffset,
            Point,
            ReferenceCircuit,
            SheetEdge,
            StrapPin,
            assert_on_grid,
        )
    )


def test_refcircuits_load() -> None:
    """All 29 ported refcircuits import + register without error.

    29 refcircuits map to 28 distinct datasheet PDFs because the TPD12S016
    datasheet covers both the TX and RX instances and the 24LC256 datasheet
    covers both the data EEPROM and EDID EEPROM instances.
    """
    from zynq_eda.catalog.refcircuits import IC_INSTANCE_COUNT, REFCIRCUITS

    assert len(REFCIRCUITS) == 29
    assert len(IC_INSTANCE_COUNT) == 29
    assert set(IC_INSTANCE_COUNT.keys()) == set(REFCIRCUITS.keys())

    distinct_pdfs = {
        rc.local_datasheet_path
        for rc in REFCIRCUITS.values()
        if rc.local_datasheet_path
    }
    # 29 refcircuits → 27 distinct PDFs (TPD12S016PWR.pdf serves both TX/RX
    # variants; 24LC256T-I_SN.pdf serves both data and EDID instances).
    assert len(distinct_pdfs) == 27

    unverified = [
        mpn for mpn, rc in REFCIRCUITS.items()
        if not rc.minimum_circuit_verified
    ]
    assert unverified == [], f"unverified refcircuits: {unverified}"

    fusb302 = REFCIRCUITS["FUSB302BMPX"]
    assert fusb302.part_mpn == "FUSB302BMPX"
    assert fusb302.lcsc == "C442699"
    assert len(fusb302.external_parts) > 0


def test_parts_registry_loads() -> None:
    """Catalog parts registry imports + has plausible content."""
    from zynq_eda.catalog.registry import REGISTRY, get_part

    # registry maps every canonical token to a BOMPart
    assert len(REGISTRY) > 50
    # spot-check a known token
    part = get_part("100n_0402_X7R")
    assert part.value
    assert part.footprint
    assert part.lcsc.startswith("C")
