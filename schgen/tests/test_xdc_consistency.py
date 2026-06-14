"""The bank -> VCCO rail map lives in TWO independent places that must agree
(re-audit finding): schgen/xdc.py BANK_RAIL chooses each pin's IOSTANDARD, and
carrier/som_conn_gen.py VCCO_RAIL_MAP drives the real +VCCO_<bank> net sourcing.
If they drift, the XDC emits the wrong IOSTANDARD on a re-railed bank — a
board-bring-up fault no other gate catches. xdc.generate() gates on their
agreement; this locks the same invariant as a fast, offline unit (and documents
that under C3 a SoM / bank re-rail MUST touch both).
"""

from __future__ import annotations

from schgen.core.link import _vcco_rail_map
from schgen.generate.xdc import BANK_RAIL


def test_bank_rail_matches_vcco_rail_map():
    vcco = {k.removeprefix("+VCCO_"): v for k, v in _vcco_rail_map().items()}
    assert BANK_RAIL == vcco, (
        "bank->VCCO drift: xdc.BANK_RAIL and som_conn_gen.VCCO_RAIL_MAP "
        f"disagree — BANK_RAIL={BANK_RAIL}, VCCO_RAIL_MAP(by bank)={vcco}")


def test_every_bank_has_a_known_iostandard_voltage():
    # each mapped rail must resolve to a voltage xdc can turn into a LVCMOS std,
    # so no bank is left without an IOSTANDARD
    from schgen.generate.xdc import _IOSTD_SINGLE, _rail_volts
    for bank, rail in BANK_RAIL.items():
        assert _rail_volts(rail) in _IOSTD_SINGLE, (
            f"bank {bank} rail {rail} has no single-ended LVCMOS standard")
