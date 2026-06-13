"""Fast unit tests for schgen.model — the netlist truth layer.

Pure, deterministic, millisecond: no kicad-cli, no board build. Covers net
classification, the decouple/pullup/series macros, the DEF-3 default-footprint
rule, port_type pair-polarity inference + conflict errors, duplicate-ref and
bad-pin CircuitError, and net_of correctness. Every assertion checks the REAL
API as it exists; known-BAD inputs assert the gate raises.
"""

from __future__ import annotations

import pytest

from schgen.model import (Circuit, CircuitError, NetClass, PinRef, PortType,
                          _default_footprint, _passive_uF, pair_polarity)


# --------------------------------------------------------------------------- #
# net classification
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("name", ["GND", "GNDA", "DGND", "AGND", "PGND",
                                  "VSS", "VSS_CORE", "CHASSIS_GND"])
def test_classify_ground(name):
    assert Circuit.classify(name) is NetClass.GROUND


@pytest.mark.parametrize("name", ["+3V3", "+5V", "+VIN", "VBUS",
                                  "VDD", "VDD_CORE", "VCC", "VCCO_34"])
def test_classify_power(name):
    assert Circuit.classify(name) is NetClass.POWER


@pytest.mark.parametrize("name", ["MID", "USB_DP", "SDA", "RESET_N",
                                  "TMDS0_P", "vbus_lower"])
def test_classify_signal(name):
    # only ^+ / ^VBUS$ / ^VDD / ^VCC are power; bare 'VBUS' is power but a
    # lower-case or suffixed near-miss is a plain signal.
    assert Circuit.classify(name) is NetClass.SIGNAL


def test_classify_vbus_is_anchored():
    # _POWER_RE is ^VBUS$ — exact only; a longer name beginning VBUS is NOT power
    assert Circuit.classify("VBUS") is NetClass.POWER
    assert Circuit.classify("VBUS_DET") is NetClass.SIGNAL


# --------------------------------------------------------------------------- #
# DEF-3 default footprint + _passive_uF
# --------------------------------------------------------------------------- #
def test_default_footprint_resistor_0603():
    assert _default_footprint("Device:R", "1k") == "Resistor_SMD:R_0603_1608Metric"
    assert _default_footprint("Device:R", "22k1") == "Resistor_SMD:R_0603_1608Metric"


def test_default_footprint_small_cap_0603():
    assert _default_footprint("Device:C", "100n") == "Capacitor_SMD:C_0603_1608Metric"
    assert _default_footprint("Device:C", "200p") == "Capacitor_SMD:C_0603_1608Metric"


def test_default_footprint_bulk_cap_0805():
    assert _default_footprint("Device:C", "10u") == "Capacitor_SMD:C_0805_2012Metric"
    # the 1.0 uF boundary is inclusive (>= 1.0 -> 0805)
    assert _default_footprint("Device:C", "1u") == "Capacitor_SMD:C_0805_2012Metric"


def test_default_footprint_non_passive_is_empty():
    assert _default_footprint("schgen_local:FUSB302B", "FUSB302BMPX") == ""
    assert _default_footprint("Connector:TestPoint", "GND") == ""


@pytest.mark.parametrize("value,uF", [
    ("100n", 0.1), ("10u", 10.0), ("1u", 1.0), ("200p", 200e-6),
    ("4u7", None),  # not parseable by the p/n/u single-decimal grammar
])
def test_passive_uF(value, uF):
    if uF is None:
        assert _passive_uF(value) is None
    else:
        assert _passive_uF(value) == pytest.approx(uF)


def test_part_applies_def3_footprint_when_omitted():
    c = Circuit("t")
    c.part("C1", "Device:C", "10u")
    c.part("R1", "Device:R", "1k")
    assert c.parts["C1"].footprint == "Capacitor_SMD:C_0805_2012Metric"
    assert c.parts["R1"].footprint == "Resistor_SMD:R_0603_1608Metric"


def test_part_explicit_footprint_wins_over_def3():
    c = Circuit("t")
    c.part("C1", "Device:C", "10u", "Capacitor_SMD:C_0402_1005Metric")
    assert c.parts["C1"].footprint == "Capacitor_SMD:C_0402_1005Metric"


# --------------------------------------------------------------------------- #
# decouple / pullup / series macros
# --------------------------------------------------------------------------- #
def test_decouple_makes_caps_on_rail_and_gnd():
    c = Circuit("t")
    c.part("U1", "Device:R", "x")
    c.net("+3V3", "U1.1")
    caps = c.decouple("U1.1", "100n", "10u")
    assert [p.ref for p in caps] == ["C1", "C2"]
    assert [p.value for p in caps] == ["100n", "10u"]
    # rail gets each cap's pin .1, GND gets each cap's pin .2
    assert "C1.1" in {str(p) for p in c.nets["+3V3"].pins}
    assert "C2.1" in {str(p) for p in c.nets["+3V3"].pins}
    assert {str(p) for p in c.nets["GND"].pins} == {"C1.2", "C2.2"}
    # DEF-3 applied: 100n -> 0603, 10u -> 0805
    assert c.parts["C1"].footprint.endswith("0603_1608Metric")
    assert c.parts["C2"].footprint.endswith("0805_2012Metric")


def test_decouple_unknown_rail_raises():
    c = Circuit("t")
    c.part("U1", "Device:R", "x")  # U1.1 is on no net yet
    with pytest.raises(CircuitError):
        c.decouple("U1.1", "100n")


def test_pullup_ties_signal_to_rail_via_resistor():
    c = Circuit("t")
    c.part("U1", "Device:R", "x")
    c.net("SDA", "U1.1")
    r = c.pullup("U1.1", "4k7", "+3V3")
    assert r.ref == "R1" and r.value == "4k7"
    # R pin .2 joins the signal, pin .1 joins the rail
    assert "R1.2" in {str(p) for p in c.nets["SDA"].pins}
    assert "R1.1" in {str(p) for p in c.nets["+3V3"].pins}


def test_pullup_unnetted_signal_raises():
    c = Circuit("t")
    c.part("U1", "Device:R", "x")
    with pytest.raises(CircuitError):
        c.pullup("U1.1", "4k7", "+3V3")


def test_series_splits_in_out_through_resistor():
    c = Circuit("t")
    r = c.series("VIN_RAW", "VIN", "22R")
    assert r.ref == "R1"
    assert {str(p) for p in c.nets["VIN_RAW"].pins} == {"R1.1"}
    assert {str(p) for p in c.nets["VIN"].pins} == {"R1.2"}


def test_series_custom_prefix():
    c = Circuit("t")
    f = c.series("A", "B", "0R", prefix="FB")
    assert f.ref == "FB1"


# --------------------------------------------------------------------------- #
# pair_polarity + port_type inference / conflict errors
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("name,pol", [
    ("USB_DP", "P"), ("USB_DM", "N"), ("TMDS0_P", "P"), ("TMDS0_N", "N"),
    ("CC1_DP", "P"), ("LANE_DN", "N"), ("D+", "P"), ("D-", "N"),
])
def test_pair_polarity_infers_suffix(name, pol):
    assert pair_polarity(name) == pol


def test_pair_polarity_uninferable():
    assert pair_polarity("MID") is None
    assert pair_polarity("CLK") is None


def test_port_type_usb_pair_defaults_90R_and_reciprocates():
    c = Circuit("t")
    c.part("U1", "Device:R", "x")
    c.port("USB_DP", "U1.1")
    c.port("USB_DM", "U1.2")
    pt = c.port_type("USB_DP", kind="usb_hs_pair", pair_with="USB_DM")
    assert pt.kind == "usb_hs_pair" and pt.impedance == 90
    # reciprocal type auto-registered on the complement, pointing back
    recip = c.port_types["USB_DM"]
    assert recip.kind == "usb_hs_pair" and recip.pair_with == "USB_DP"


def test_port_type_tmds_defaults_100R():
    c = Circuit("t")
    c.part("U1", "Device:R", "x")
    c.port("TMDS_P", "U1.1")
    c.port("TMDS_N", "U1.2")
    pt = c.port_type("TMDS_P", kind="tmds_pair", pair_with="TMDS_N")
    assert pt.impedance == 100


def test_port_type_diff_pair_requires_explicit_impedance():
    c = Circuit("t")
    c.part("U1", "Device:R", "x")
    c.port("A_P", "U1.1")
    c.port("A_N", "U1.2")
    with pytest.raises(CircuitError):
        c.port_type("A_P", kind="diff_pair", pair_with="A_N")
    # supplying impedance succeeds
    pt = c.port_type("A_P", kind="diff_pair", pair_with="A_N", impedance=100)
    assert pt.impedance == 100


def test_port_type_pair_requires_pair_with():
    c = Circuit("t")
    c.part("U1", "Device:R", "x")
    c.port("X_P", "U1.1")
    with pytest.raises(CircuitError):
        c.port_type("X_P", kind="usb_hs_pair")


def test_port_type_pair_with_must_be_a_port():
    c = Circuit("t")
    c.part("U1", "Device:R", "x")
    c.port("X_P", "U1.1")
    c.net("X_N", "U1.2")  # plain SIGNAL, not a PORT
    with pytest.raises(CircuitError):
        c.port_type("X_P", kind="usb_hs_pair", pair_with="X_N")


def test_port_type_unknown_kind_raises():
    c = Circuit("t")
    c.part("U1", "Device:R", "x")
    c.port("S", "U1.1")
    with pytest.raises(CircuitError):
        c.port_type("S", kind="banana")


def test_port_type_on_non_port_net_raises():
    c = Circuit("t")
    c.part("U1", "Device:R", "x")
    c.net("SIG", "U1.1")  # SIGNAL, not PORT
    with pytest.raises(CircuitError):
        c.port_type("SIG", kind="single")


def test_port_type_i2c_requires_role():
    c = Circuit("t")
    c.part("U1", "Device:R", "x")
    c.port("I2C", "U1.1")
    with pytest.raises(CircuitError):
        c.port_type("I2C", kind="i2c")
    pt = c.port_type("I2C", kind="i2c", role="scl")
    assert pt.role == "scl"


def test_port_type_role_only_for_i2c():
    c = Circuit("t")
    c.part("U1", "Device:R", "x")
    c.port("S", "U1.1")
    with pytest.raises(CircuitError):
        c.port_type("S", kind="single", role="scl")


def test_port_type_sd_bus_requires_level_v():
    c = Circuit("t")
    c.part("U1", "Device:R", "x")
    c.port("SD0", "U1.1")
    with pytest.raises(CircuitError):
        c.port_type("SD0", kind="sd_bus")
    pt = c.port_type("SD0", kind="sd_bus", level_v=3.3)
    assert pt.level_v == 3.3


def test_port_type_retype_conflict_raises():
    c = Circuit("t")
    c.part("U1", "Device:R", "x")
    c.port("S", "U1.1")
    c.port_type("S", kind="single")
    with pytest.raises(CircuitError):
        c.port_type("S", kind="i2c", role="sda")


def test_port_type_idempotent_same_type_ok():
    c = Circuit("t")
    c.part("U1", "Device:R", "x")
    c.port("S", "U1.1")
    c.port_type("S", kind="single")
    # re-declaring the identical type must NOT raise
    c.port_type("S", kind="single")
    assert c.port_type_of("S").kind == "single"


def test_port_kwargs_forward_through_port():
    # port() forwards kind= + kwargs straight to port_type()
    c = Circuit("t")
    c.part("U1", "Device:R", "x")
    c.port("DM", "U1.2")
    c.port("DP", "U1.1", kind="usb_hs_pair", pair_with="DM")
    assert c.port_type_of("DP").kind == "usb_hs_pair"
    assert c.port_type_of("DP").impedance == 90


def test_port_type_of_untyped_reads_single():
    c = Circuit("t")
    c.part("U1", "Device:R", "x")
    c.port("S", "U1.1")
    assert c.port_type_of("S") == PortType()  # default kind 'single'


# --------------------------------------------------------------------------- #
# duplicate-ref + bad-pin CircuitError
# --------------------------------------------------------------------------- #
def test_duplicate_reference_raises():
    c = Circuit("t")
    c.part("U1", "Device:R", "x")
    with pytest.raises(CircuitError):
        c.part("U1", "Device:R", "y")


def test_bad_pin_spec_missing_dot_raises():
    c = Circuit("t")
    c.part("U1", "Device:R", "x")
    with pytest.raises(CircuitError):
        c.net("N", "U1")  # no '.PIN'


def test_unknown_part_in_pin_raises():
    c = Circuit("t")
    with pytest.raises(CircuitError):
        c.net("N", "U9.1")  # U9 was never declared


def test_bad_inline_pin_number_raises():
    # Device:R has pins 1 and 2 only; pin 7 is invalid and validated eagerly
    c = Circuit("t")
    c.part("R1", "Device:R", "10k")
    with pytest.raises(CircuitError):
        c.net("N", "R1.7")


def test_pin_already_on_another_net_raises():
    c = Circuit("t")
    c.part("R1", "Device:R", "10k")
    c.net("A", "R1.1")
    with pytest.raises(CircuitError):
        c.net("B", "R1.1")


def test_nc_then_net_conflict_raises():
    c = Circuit("t")
    c.part("R1", "Device:R", "10k")
    c.nc("R1.1")
    with pytest.raises(CircuitError):
        c.net("A", "R1.1")


def test_net_reclassify_conflict_raises():
    c = Circuit("t")
    c.part("R1", "Device:R", "10k")
    c.net("FOO", "R1.1")  # classifies SIGNAL
    with pytest.raises(CircuitError):
        c.net("FOO", net_class=NetClass.POWER)


# --------------------------------------------------------------------------- #
# net_of correctness
# --------------------------------------------------------------------------- #
def test_net_of_finds_owning_net():
    c = Circuit("t")
    c.part("R1", "Device:R", "10k")
    c.net("SIG", "R1.1")
    assert c.net_of(PinRef("R1", "1")).name == "SIG"


def test_net_of_unassigned_is_none():
    c = Circuit("t")
    c.part("R1", "Device:R", "10k")
    c.net("SIG", "R1.1")
    assert c.net_of(PinRef("R1", "2")) is None


def test_net_extends_existing_and_dedups():
    c = Circuit("t")
    c.part("R1", "Device:R", "10k")
    c.part("R2", "Device:R", "10k")
    c.net("SIG", "R1.1")
    c.net("SIG", "R2.1")
    c.net("SIG", "R1.1")  # repeat must not duplicate
    pins = [str(p) for p in c.nets["SIG"].pins]
    assert pins == ["R1.1", "R2.1"]
