"""Tests for the reusable-subsystem foundation: the Circuit.bind() contract,
the subsystem-structure gate, the scaffolder, and the usb_pd exemplar's
byte-identical carrier adapter. Offline (model + symbol pin tables; no network,
no kicad-cli render here — the byte-identical sheet emit is proven separately by
`schgen board` + the golden check)."""

from __future__ import annotations

from schgen.core.model import Circuit, CircuitError, NetClass
from schgen.core.subsystem import Meta
from schgen.verify import subsystem_structure


# ---- the standard meta contract (schgen.core.subsystem.Meta) --------------------

def test_meta_none_is_all_defaults():
    m = Meta(None)
    assert m.bind_map is None
    assert m.expects == {}
    assert m.bus("i2c", "DEFAULT") == "DEFAULT"
    assert m.note("draws", "DEFAULT") == "DEFAULT"
    assert m.expect_kw("ANY") == {}


def test_meta_reads_standard_keys():
    m = Meta({"bind": {"A": "B"}, "expects": {"P": "deferred"},
              "buses": {"i2c": "MY_BUS"}, "notes": {"draws": "n"}})
    assert m.bind_map == {"A": "B"}
    assert m.bus("i2c", "x") == "MY_BUS"
    assert m.bus("spi", "x") == "x"          # unset role falls back to default
    assert m.note("draws", "x") == "n"
    assert m.expect_kw("P") == {"expect": "deferred"}
    assert m.expect_kw("Q") == {}


def test_meta_rejects_unknown_key_and_nondict():
    try:
        Meta({"bus": {"i2c": "X"}})          # typo: 'bus' not 'buses'
    except CircuitError as e:
        assert "unknown subsystem meta key" in str(e)
    else:
        raise AssertionError("a typo'd meta key must raise")
    try:
        Meta({"bind": ["not", "a", "dict"]})
    except CircuitError as e:
        assert "must be a dict" in str(e)
    else:
        raise AssertionError("a non-dict meta value must raise")


def test_meta_is_idempotent():
    inner = Meta({"buses": {"i2c": "B"}})
    assert Meta(inner).bus("i2c", "x") == "B"


def test_meta_finish_applies_bind():
    c = Circuit("t", "t")
    c.part("R1", "Device:R", "1k", "")
    c.net("+VDD", "R1.1")
    c.net("GND", "R1.2")
    out = Meta({"bind": {"+VDD": "+3V3", "GND": "GND"}}).finish(c)
    assert "+3V3" in out.nets and "+VDD" not in out.nets


# ---- Circuit.bind() -------------------------------------------------------------

def _ext_circuit() -> Circuit:
    c = Circuit("t", "t")
    c.part("R1", "Device:R", "1k", "")
    c.part("R2", "Device:R", "1k", "")
    c.part("R3", "Device:R", "1k", "")
    c.net("+VDD", "R1.1")                   # POWER external
    c.net("GND", "R3.2")                    # GROUND external
    c.port("SIG", "R2.1")                   # PORT external
    c.net("MID", "R1.2", "R2.2", "R3.1")    # SIGNAL internal (>=2 pins)
    return c


def test_bind_renames_externals_preserves_order():
    c = _ext_circuit()
    before = list(c.nets)
    c.bind({"+VDD": "+3V3", "GND": "GND", "SIG": "BOARD_SIG"})
    assert list(c.nets) == ["+3V3" if n == "+VDD" else
                            "BOARD_SIG" if n == "SIG" else n for n in before]
    assert c.nets["+3V3"].net_class is NetClass.POWER
    assert c.nets["BOARD_SIG"].net_class is NetClass.PORT


def test_bind_rejects_signal_net():
    c = _ext_circuit()
    try:
        c.bind({"MID": "X"})
    except CircuitError as e:
        assert "SIGNAL" in str(e)
    else:
        raise AssertionError("binding a SIGNAL net must raise")


def test_bind_rejects_unknown_and_collision():
    c = _ext_circuit()
    try:
        c.bind({"NOPE": "+3V3"})
    except CircuitError as e:
        assert "not a net" in str(e)
    else:
        raise AssertionError("unknown abstract name must raise")
    c2 = _ext_circuit()
    try:
        c2.bind({"+VDD": "SHARED", "GND": "SHARED"})
    except CircuitError as e:
        assert "merge" in str(e) or "collides" in str(e)
    else:
        raise AssertionError("a colliding bind must raise")


def test_bind_carries_port_type_and_load():
    c = Circuit("t", "t")
    c.part("U1", "Device:R", "1k", "")
    c.net("+VDD", "U1.1")
    c.port("SDA", "U1.2", kind="i2c", role="sda", bus="B")
    c.draws("+VDD", 0.001, "x")
    c.bind({"+VDD": "+3V3", "SDA": "MY_SDA"})
    assert c.port_type_of("MY_SDA").role == "sda"
    assert "+3V3" in c.loads and "+VDD" not in c.loads


# ---- usb_pd exemplar ------------------------------------------------------------

def test_usb_pd_adapter_matches_library_bound():
    """The carrier adapter is exactly the library bound to the carrier META."""
    from schgen.core.link import load_subsystem
    adapter = load_subsystem("usb_pd").circuit
    import subsystems.usb_pd.usb_pd as lib
    from carrier.subsystems.usb_pd import META  # type: ignore
    direct = lib.circuit(META)
    assert list(adapter.nets) == list(direct.nets)
    assert set(adapter.parts) == set(direct.parts)
    # the carrier net names the binding must reproduce
    for real in ("+3V3_SC", "+VBUS_IN", "STM32_USB_CC1", "STM32_USB_CC2",
                 "STM32_I2C2_SDA", "STM32_I2C2_SCL", "SC_INT_N", "GND"):
        assert real in adapter.nets, real


def test_usb_pd_library_is_carrier_free():
    """The library exposes only abstract externals — no carrier net name."""
    import subsystems.usb_pd.usb_pd as lib
    c = lib.circuit()
    externals = {n.name for n in c.nets.values()
                 if n.net_class is not NetClass.SIGNAL}
    assert externals == set(lib.INTERFACE)
    assert not any("STM32" in n or n.endswith("_SC") or n == "+VBUS_IN"
                   for n in externals)


# ---- structure gate -------------------------------------------------------------

def test_structure_gate_usb_pd_ok():
    res = subsystem_structure.check()
    by_name = {p.name: p for p in res.packages}
    assert "usb_pd" in by_name, [p.name for p in res.packages]
    up = by_name["usb_pd"]
    assert up.ok, (up.missing, up.interface_drift, up.errors)
    assert up.accepts_meta and up.has_circuit
    assert set(up.declared_interface) == {
        "+VDD_LOGIC", "+VBUS_SENSE", "GND", "CC1", "CC2",
        "I2C_SDA", "I2C_SCL", "INT_N"}


# ---- scaffolder -----------------------------------------------------------------

def test_scaffolder_writes_contract_files(tmp_path, monkeypatch):
    from schgen.generate import subsystem_scaffold as ss
    monkeypatch.setattr(ss, "SUBSYSTEMS_DIR", tmp_path)
    pkg = ss.scaffold("widget")
    names = {p.name for p in pkg.iterdir()}
    assert names == {"widget.py", "__init__.py", "README.md", "widget.cir",
                     "test_widget.py"}
    # refuses to clobber
    try:
        ss.scaffold("widget")
    except SystemExit:
        pass
    else:
        raise AssertionError("scaffold must refuse to overwrite without --force")
    ss.scaffold("widget", force=True)      # --force overwrites
