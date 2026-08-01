from __future__ import annotations

from schgen.core.link import _vcco_rail_map
from schgen.generate.xdc import bank_rail_map


def test_bank_rail_matches_vcco_rail_map():
    bank_rail = bank_rail_map()
    vcco = {k.removeprefix("+VCCO_"): v for k, v in _vcco_rail_map().items()}
    assert bank_rail == vcco, (
        "bank->VCCO drift: project.json fpga.bank_rails and "
        "som_conn_gen.VCCO_RAIL_MAP disagree — "
        f"bank_rails={bank_rail}, VCCO_RAIL_MAP(by bank)={vcco}")


def test_every_bank_has_a_known_iostandard_voltage():
    from schgen.generate.xdc import _IOSTD_SINGLE, _rail_volts
    for bank, rail in bank_rail_map().items():
        assert _rail_volts(rail) in _IOSTD_SINGLE, (
            f"bank {bank} rail {rail} has no single-ended LVCMOS standard")
