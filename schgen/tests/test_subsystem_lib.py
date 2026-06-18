"""Tests for the reusable-subsystem foundation: the Circuit.bind() contract,
the subsystem-structure gate, the scaffolder, and the usb_pd exemplar's
byte-identical carrier adapter. Offline (model + symbol pin tables; no network,
no kicad-cli render here — the byte-identical sheet emit is proven separately by
`schgen board` + the golden check)."""

from __future__ import annotations

from schgen.core.model import Circuit, CircuitError, NetClass, PinRef
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


def test_bind_renames_diff_pair_complement():
    """A diff/tmds/usb_hs pair stores its complement as a net NAME (pair_with);
    bind must follow it on BOTH halves, else the bound pair's two ends disagree
    and the SI/XDC artifacts (keyed on pair_with) drift / report a half-pair."""
    c = Circuit("t", "t")
    c.part("U1", "Device:R", "1k", "")
    c.port("LANE_P", "U1.1")
    c.port("LANE_N", "U1.2")
    c.port_type("LANE_P", kind="diff_pair", pair_with="LANE_N", impedance=100)
    c.bind({"LANE_P": "BRD_P", "LANE_N": "BRD_N"})
    assert c.port_type_of("BRD_P").pair_with == "BRD_N"   # payload followed
    assert c.port_type_of("BRD_N").pair_with == "BRD_P"   # reciprocal too
    assert c.port_type_of("BRD_P").impedance == 100        # other fields intact


def test_bind_renames_testpoint_value():
    """A TestPoint carries the probed net NAME as its value; bind must rebind
    that too (else the abstract name stays in the render — byte-identicality)."""
    c = Circuit("t", "t")
    c.part("U1", "Device:R", "1k", "")
    c.port("PROBE", "U1.1")
    c.net("GND", "U1.2")
    tp = c.testpoint("PROBE")
    assert tp.value == "PROBE"
    c.bind({"PROBE": "BOARD_PROBE", "GND": "GND"})
    assert tp.value == "BOARD_PROBE"               # value followed the net
    assert c.net_of(PinRef(tp.ref, "1")).name == "BOARD_PROBE"


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


def test_structure_gate_all_packages_complete():
    """The board promotes this gate to HARD-FAIL: every subsystems/<name>/ on the
    repo must be a complete package. (If this trips, a package lost an artifact /
    its circuit() stopped accepting meta / its INTERFACE drifted from the build.)"""
    res = subsystem_structure.check()
    assert res.packages, "no subsystems/ packages found"
    assert res.ok, [(p.name, p.missing, p.interface_drift, p.errors)
                    for p in res.packages if not p.ok]


def test_carrier_structure_all_complete():
    """The board promotes the carrier structure gate to HARD-FAIL. After the
    adapter de-bloat each carrier subsystem matches the SHAPE its kind needs:
    an ADAPTER (has a generic subsystems/<name>/ library) is a FLAT <name>.py +
    test_<name>.py pair (NOT foldered); a LOCAL is a foldered 4-artifact package.
    All complete, and the split is the documented 17 flat adapters + 18 foldered
    locals = 35 (the `mechanical` board-fab-art sheet + `som_decoupling`, the
    bottom-side SoM-rail decoupling placed under the mezzanine — LAW 6)."""
    from schgen.verify import carrier_structure
    res = carrier_structure.check()
    assert res.packages, "no carrier/subsystems/ packages found"
    assert res.ok, [(p.name, p.kind, p.missing, p.errors) for p in res.packages
                    if not p.ok]
    assert res.n_adapters == 17, [p.name for p in res.packages if p.adapter]
    assert res.n_locals == 18, [p.name for p in res.packages if not p.adapter]
    assert len(res.packages) == 35
    # every adapter is flat (no leftover folder) + carries a META dict; every
    # local is foldered.
    for p in res.packages:
        if p.adapter:
            assert p.has_meta, p.name
            assert not (carrier_structure.CARRIER_SUBSYSTEMS_DIR / p.name).is_dir(), \
                f"adapter {p.name} re-bloated into a folder"


def _local_libdir(tmp_path):
    """A library dir with NO matching subsystem, so a 'widget' is classified
    LOCAL (must be foldered) by the gate."""
    libs = tmp_path / "_libs_empty"
    libs.mkdir()
    return libs


def _adapter_libdir(tmp_path, name="widget"):
    """A library dir that DOES own subsystems/<name>/, so the gate classifies
    that carrier name as an ADAPTER (must be flat)."""
    libs = tmp_path / "_libs"
    (libs / name).mkdir(parents=True)
    return libs


def test_carrier_structure_kills_incomplete_local(tmp_path):
    """Prove the carrier gate bites a LOCAL: a foldered package missing artifacts
    / with no circuit() is not ok (missing-set is the foldered 4-artifact set)."""
    from schgen.verify import carrier_structure
    base = tmp_path / "carrier_subsystems"
    base.mkdir()
    pkg = base / "widget"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    (pkg / "widget.py").write_text("x = 1\n")     # no circuit(); missing 3 files
    res = carrier_structure.check(base=base, lib_dir=_local_libdir(tmp_path))
    rep = {p.name: p for p in res.packages}["widget"]
    assert not rep.ok and not res.ok
    assert not rep.adapter                         # classified LOCAL (no library)
    assert not rep.has_circuit
    assert set(rep.missing) == {"README.md", "test_widget.py", "widget.cir"}


def test_carrier_structure_passes_a_well_formed_adapter(tmp_path):
    """Sanity baseline for the adapter mutants: a FLAT widget.py (with circuit()
    + META) plus a flat test_widget.py, classified ADAPTER, is OK."""
    from schgen.verify import carrier_structure
    base = tmp_path / "carrier_subsystems"
    base.mkdir()
    (base / "widget.py").write_text(
        "def circuit():\n    return 1\nMETA = {'bind': {}}\n")
    (base / "test_widget.py").write_text("def test_x():\n    assert True\n")
    res = carrier_structure.check(base=base,
                                  lib_dir=_adapter_libdir(tmp_path))
    rep = {p.name: p for p in res.packages}["widget"]
    assert rep.adapter and rep.ok and res.ok
    assert rep.has_circuit and rep.has_meta and not rep.missing


def test_carrier_structure_kills_adapter_left_foldered(tmp_path):
    """MUTANT (a): an ADAPTER that stayed FOLDERED must FAIL — the de-bloat is
    enforced, an adapter cannot re-grow its README/.cir/__init__ folder."""
    from schgen.verify import carrier_structure
    base = tmp_path / "carrier_subsystems"
    base.mkdir()
    pkg = base / "widget"            # foldered (the forbidden adapter shape)
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    (pkg / "widget.py").write_text(
        "def circuit():\n    return 1\nMETA = {'bind': {}}\n")
    (pkg / "test_widget.py").write_text("def test_x():\n    assert True\n")
    res = carrier_structure.check(base=base,
                                  lib_dir=_adapter_libdir(tmp_path))
    rep = {p.name: p for p in res.packages}["widget"]
    assert rep.adapter
    assert not rep.ok and not res.ok
    # the folder itself + the absent flat files are the violation
    assert any("foldered" in m for m in rep.missing), rep.missing
    assert "widget.py" in rep.missing and "test_widget.py" in rep.missing


def test_carrier_structure_kills_adapter_missing_flat_test(tmp_path):
    """MUTANT (b): a FLAT adapter widget.py with NO flat test_widget.py must
    FAIL — the bind guard is mandatory."""
    from schgen.verify import carrier_structure
    base = tmp_path / "carrier_subsystems"
    base.mkdir()
    (base / "widget.py").write_text(
        "def circuit():\n    return 1\nMETA = {'bind': {}}\n")
    # NB: no test_widget.py
    res = carrier_structure.check(base=base,
                                  lib_dir=_adapter_libdir(tmp_path))
    rep = {p.name: p for p in res.packages}["widget"]
    assert rep.adapter and rep.has_circuit
    assert not rep.ok and not res.ok
    assert rep.missing == ["test_widget.py"]


def test_carrier_structure_kills_local_that_got_flattened(tmp_path):
    """MUTANT (c): a LOCAL that lost its folder (flattened to a bare
    <name>.py) must FAIL — a carrier-local with no generic library to point at
    MUST keep its self-contained 4-artifact folder."""
    from schgen.verify import carrier_structure
    base = tmp_path / "carrier_subsystems"
    base.mkdir()
    (base / "widget.py").write_text(
        "def circuit():\n    return 1\n")          # flat, but it's a LOCAL
    res = carrier_structure.check(base=base, lib_dir=_local_libdir(tmp_path))
    rep = {p.name: p for p in res.packages}["widget"]
    assert not rep.adapter                          # LOCAL (no library)
    assert not rep.ok and not res.ok
    # the missing FOLDER + the foldered artifacts are the violation
    assert any("foldered package" in m for m in rep.missing), rep.missing
    assert {"__init__.py", "README.md", "test_widget.py",
            "widget.cir"} <= set(rep.missing)


def test_structure_gate_kills_incomplete_package(tmp_path, monkeypatch):
    """Prove the hard-fail bites: a package missing contract artifacts is NOT ok
    (the mutant the board gate must catch)."""
    monkeypatch.setattr(subsystem_structure, "SUBSYSTEMS_DIR", tmp_path)
    pkg = tmp_path / "widget"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    (pkg / "README.md").write_text("# widget\n")     # only 2 of 4 artifacts
    res = subsystem_structure.check()
    rep = {p.name: p for p in res.packages}["widget"]
    assert not rep.ok and not res.ok                 # gate fails the board
    assert set(rep.missing) == {"widget.py", "test_widget.py", "widget.cir"}


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
