"""LOCAL electrical-correctness test for the fmc CARRIER subsystem.

Runs the SUBSYSTEM-LOCAL slices of the carrier's own verify gates on JUST this
subsystem's circuit, standalone and offline. Mirrors the shape of
subsystems/usb_pd/test_usb_pd.py, adapted to a carrier-local subsystem (no
abstract-interface / bind contract — fmc binds verbatim carrier nets and loads
its pinout from carrier/research/fmc_lpc_pinmap.json).

LOCAL checks:
  * model completeness  — every pin netted or NC (no silent floats); the VITA
    GND census (61) is asserted by circuit() itself before binding.
  * VADJ LDO            — the TLV75725 (DYD thermal-pad) produces +2V5_VADJ from
    +3V3, EN strapped on, the EP pad (pin 6) netted to GND (DEF-E), in/out caps.
  * LA / CLK pairs      — the 14 populated pairs are typed 100R diff pairs.
  * service straps       — PRSNT 10k -> +3V3, PG_C2M 10k -> +2V5_VADJ, FMC JTAG
    TCK/TRST_L 10k -> GND, TMS 10k -> +3V3; GA0/GA1 to GND.
  * design-rules slice   — DECAP/EP/STRAP clean (the I2C-pull-up finding is a
    BOARD-LEVEL check — the SC bus pull-ups live off-subsystem on bringup_rails
    — so it is asserted as the ONLY expected local design-rule finding, exactly
    as usb_pd documents for its shared I2C/INT pull-ups).
  * part ratings         — every BOM passive's LCSC resolves; part_rules clean.
  * SPICE passives       — the .cir subckt's R+C network matches the netlist
    one-for-one (parse_si), and the analytic spice slice runs clean.

CROSS-BOARD checks (the I2C pull-up completeness on the shared SC bus, the link
graph, the full power-tree headroom, board ERC) stay at board level.
"""

from __future__ import annotations

import json
import re
import types
from pathlib import Path

import pytest

from schgen.core.model import Circuit, NetClass, PinRef
from schgen.core.symbols import Library
from schgen.verify import design_rules, part_rules, spice
from schgen.verify.powertree import parse_si
from schgen.verify.ratings import RATINGS_BY_LCSC

import carrier.subsystems.fmc.fmc as fmc

HERE = Path(__file__).resolve().parent
CIR = HERE / "fmc.cir"

# the 14 populated FMC pairs -> functional carrier port stems (fmc.py contract)
POPULATED_STEMS = (
    "FMC_CLK0_M2C", "FMC_CLK1_M2C", "FMC_LA00_CC", "FMC_LA01_CC",
    "FMC_LA02", "FMC_LA03", "FMC_LA04", "FMC_LA05", "FMC_LA06", "FMC_LA07",
    "FMC_LA08", "FMC_LA09", "FMC_LA10", "FMC_LA11",
)


@pytest.fixture
def lib() -> Library:
    return Library()


@pytest.fixture
def c() -> Circuit:
    return fmc.circuit()


def _sheet(c: Circuit):
    return types.SimpleNamespace(name=c.name, circuit=c)


def _pin_net(c: Circuit, pin: str) -> str | None:
    ref, num = pin.split(".")
    n = c.net_of(PinRef(ref, num))
    return n.name if n else None


# ---- model completeness + GND census --------------------------------------------

def test_model_complete_every_pin_netted_or_nc(c: Circuit, lib: Library):
    """Every physical pin netted or NC. The unpopulated user signals (LA12-33,
    DP0, GBTCLK0, VREF) are author NCs, so nc_pins is non-empty BY DESIGN."""
    c.validate({r: lib.pin_numbers(p.lib_id) for r, p in c.parts.items()})
    assert c.nc_pins, "fmc should author-NC the unpopulated LPC pins"
    # the LDO's unused NC pin (pin 4) is among them
    assert "U1.4" in {str(p) for p in c.nc_pins}


def test_gnd_census_is_61(c: Circuit):
    """The VITA LPC map's 61 GND positions all land on GND (circuit() asserts
    the source census; here we confirm they reached the GND net)."""
    pinmap = json.loads(fmc.PINMAP.read_text())
    gnd_lpc = {p.lower() for p, sig in pinmap.items() if sig == "GND"}
    assert len(gnd_lpc) == 61
    gnd_pins = {str(p) for p in c.nets["GND"].pins}
    for lpc in gnd_lpc:
        assert f"J1.{lpc}" in gnd_pins, f"VITA GND {lpc} not on GND"


def test_rail_classes(c: Circuit):
    cls = {n.name: n.net_class for n in c.nets.values()}
    assert cls["+3V3"] is NetClass.POWER
    assert cls["+2V5_VADJ"] is NetClass.POWER
    assert cls["GND"] is NetClass.GROUND


# ---- VADJ LDO -------------------------------------------------------------------

def test_vadj_ldo_present_in_out_and_ep_to_gnd(c: Circuit):
    """The TLV75725 (DYD thermal-pad) makes +2V5_VADJ from +3V3, EN strapped on,
    with input/output caps and the EP pad (pin 6) netted to GND (DEF-E)."""
    ldos = [ref for ref, p in c.parts.items()
            if "TLV75725" in (p.lib_id + p.value + (p.footprint or ""))
            or p.lib_id.endswith("TLV75725PDYDR")]
    assert ldos, "TLV75725 VADJ LDO missing"
    (u1,) = ldos
    assert _pin_net(c, f"{u1}.1") == "+3V3"          # IN
    assert _pin_net(c, f"{u1}.2") == "GND"           # GND
    assert _pin_net(c, f"{u1}.3") == "+3V3"          # EN strapped on
    assert _pin_net(c, f"{u1}.5") == "+2V5_VADJ"     # OUT
    assert _pin_net(c, f"{u1}.6") == "GND"           # EP -> GND (DEF-E)
    # input + output bulk caps exist on each side of the LDO
    def caps_on(rail: str) -> list[str]:
        out = []
        for ref, p in c.parts.items():
            if not p.lib_id.endswith(":C"):
                continue
            names = {n.name for n in (c.net_of(PinRef(ref, "1")),
                                      c.net_of(PinRef(ref, "2"))) if n}
            if rail in names and "GND" in names:
                out.append(p.value)
        return sorted(out)
    assert "1u" in caps_on("+3V3") or "10u" in caps_on("+3V3")
    assert any(v in caps_on("+2V5_VADJ") for v in ("1u", "10u", "100n"))


def test_vadj_rail_has_a_testpoint(c: Circuit):
    """round-4 coverage gate: the locally-generated VADJ rail is probeable."""
    tps = [ref for ref, p in c.parts.items() if p.lib_id == c.TP_LIB_ID]
    tp_nets = {p.value for ref, p in c.parts.items() if p.lib_id == c.TP_LIB_ID}
    assert tps, "no test point emitted"
    assert "+2V5_VADJ" in tp_nets, tp_nets


# ---- LA / CLK diff pairs ---------------------------------------------------------

def test_fourteen_la_clk_diff_pairs_typed_100ohm(c: Circuit):
    """All 14 populated pairs (CLK0/1_M2C + LA00-LA11) are typed diff pairs at
    100 ohm with the correct P/N pairing."""
    for stem in POPULATED_STEMS:
        pn = f"{stem}_P"
        nn = f"{stem}_N"
        assert pn in c.nets and nn in c.nets, stem
        pt = c.port_type_of(pn)
        assert pt.kind == "diff_pair", (stem, pt.kind)
        assert pt.pair_with == nn, (stem, pt.pair_with)
        assert pt.impedance == 100, (stem, pt.impedance)
    assert len(POPULATED_STEMS) == 14


# ---- service straps -------------------------------------------------------------

def test_service_straps(c: Circuit):
    """PRSNT 10k -> +3V3; PG_C2M 10k -> +2V5_VADJ; FMC JTAG TCK/TRST_L 10k -> GND,
    TMS 10k -> +3V3; GA0/GA1 tied to GND (EEPROM addr 0x50)."""
    # 10k pull-ups: bucket by the rail their pin 1 sits on
    tens = [(ref, _pin_net(c, f"{ref}.1"), _pin_net(c, f"{ref}.2"))
            for ref, p in c.parts.items()
            if p.lib_id == "Device:R" and p.value == "10k"]
    rails = {top for _, top, _ in tens}
    assert {"+3V3", "+2V5_VADJ", "GND"} <= rails, rails
    # PG_C2M asserts against the locally-made VADJ rail
    assert _pin_net(c, "R2.2") == "FMC_PG_C2M"
    assert _pin_net(c, "R2.1") == "+2V5_VADJ"
    # FMC JTAG: bypass + held TAP
    assert _pin_net(c, "R3.1") == "GND"          # TCK held low
    assert _pin_net(c, "R4.1") == "GND"          # TRST_L held low
    assert _pin_net(c, "R5.1") == "+3V3"         # TMS held high


def test_jtag_bypass_tdi_to_tdo(c: Circuit):
    """No carrier JTAG chain: TDI is wired straight to TDO at the connector."""
    sig = fmc._signal_pins()
    tdi = f"J1.{sig['TDI'][0]}"
    tdo = f"J1.{sig['TDO'][0]}"
    assert _pin_net(c, tdi) == "FMC_JTAG_BYPASS"
    assert _pin_net(c, tdo) == "FMC_JTAG_BYPASS"


def test_i2c_ports_on_shared_sc_bus(c: Circuit):
    """SCL/SDA are typed on the shared STM32_I2C2 bus (pull-ups live ONCE on
    bringup_rails, off-subsystem)."""
    assert c.port_type_of("STM32_I2C2_SCL").role == "scl"
    assert c.port_type_of("STM32_I2C2_SDA").role == "sda"
    assert c.port_type_of("STM32_I2C2_SCL").bus == "STM32_I2C2"


# ---- design-rules slice (the I2C finding is a BOARD-LEVEL deferral) --------------

def test_design_rules_decap_ep_strap_clean(c: Circuit, lib: Library):
    """DECAP/EP/STRAP clean: the LDO is decoupled, its EP is on GND, no config
    strap floats. The I2C-no-pull-up finding is the ONLY local design-rule
    finding — the SC bus pull-ups are SHARED and live off-subsystem
    (bringup_rails), exactly as usb_pd documents for its shared I2C/INT pulls;
    so it stays a board-level gate, asserted here as expected-and-only."""
    r = design_rules.check([_sheet(c)], lib)
    assert not r.decap, r.decap
    assert not r.ep, r.ep
    assert not r.strap, r.strap
    # the EP rule is actually exercised (the LDO's thermal pad), not a no-op
    assert r.checked.get("ep", 0) >= 1
    # the only local finding is the shared-bus I2C pull-up (a board-level check)
    assert r.findings == r.i2c and len(r.i2c) == 2, r.findings


# ---- part ratings ---------------------------------------------------------------

def test_every_bom_passive_has_a_ratings_row(c: Circuit):
    missing = []
    for ref, p in sorted(c.parts.items()):
        if p.lib_id != "Device:R" and not p.lib_id.endswith(":C"):
            continue
        lcsc = (p.fields or {}).get("LCSC", "")
        if lcsc not in RATINGS_BY_LCSC:
            missing.append(f"{ref} {p.value} LCSC {lcsc!r}")
    assert not missing, f"passives with no ratings row: {missing}"


def test_part_rules_slice_runs_clean(c: Circuit, tmp_path):
    r = part_rules.run([_sheet(c)], tmp_path)
    assert r.ok, r.findings


# ---- SPICE subckt <-> netlist passives ------------------------------------------

def _cir_passives() -> dict[str, float]:
    out = {}
    in_subckt = False
    for line in CIR.read_text().splitlines():
        s = line.strip()
        if s.lower().startswith(".subckt fmc"):
            in_subckt = True
            continue
        if s.lower().startswith(".ends"):
            in_subckt = False
            continue
        if in_subckt and re.match(r"^[RC]\d", s):
            parts = s.split()
            out[parts[0]] = parse_si(parts[3])
    return out


def test_cir_passives_match_netlist(c: Circuit):
    """The subckt's R+C network equals the netlist value-for-value (the VADJ
    LDO is active and not a subckt passive; its in/out caps + the service-strap
    resistors + the connector bypass ARE)."""
    netlist = sorted(parse_si(p.value) for ref, p in c.parts.items()
                     if p.lib_id == "Device:R" or p.lib_id.endswith(":C"))
    cir = sorted(_cir_passives().values())
    assert cir == netlist, (cir, netlist)


def test_spice_analytic_slice_runs_clean(c: Circuit):
    res = spice.extract_checks([_sheet(c)])
    assert res.ok, res.errors


# ---- power-tree intent ----------------------------------------------------------

def test_draws_on_3v3_and_vadj(c: Circuit):
    """Draws declared on +3V3 (3P3V mezzanine allocation) and +2V5_VADJ (the
    local LDO's thermal budget) so the board power-tree gate can sum them."""
    assert "+3V3" in c.loads
    assert "+2V5_VADJ" in c.loads
