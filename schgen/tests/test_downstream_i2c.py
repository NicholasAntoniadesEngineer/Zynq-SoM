"""The board-services AUX I2C devices (ID-EEPROM 0x51, RTC 0x52) must appear in
EVERY downstream artifact's I2C map — firmware, testplan, manifest — all
single-sourced from firmware._id_eeprom_addr. These lock the audit-3 downstream-
completeness fixes so a future board-HW edit can't silently drop them from one
generator. Pure, offline (no kicad-cli, no board build)."""

from __future__ import annotations

from schgen.core.link import load_subsystem


def _services_only():
    # the AUX devices are defined on board_services; the generators scan all
    # sheets, so a one-sheet list is enough to exercise the AUX branch.
    return [load_subsystem("board_services")]


def test_manifest_i2c_map_has_aux_devices():
    from schgen.generate.manifest import _i2c_map
    rows = {r["addr"]: r for r in _i2c_map(_services_only())}
    assert 0x51 in rows, "manifest i2c_map missing the ID-EEPROM (0x51)"
    assert 0x52 in rows, "manifest i2c_map missing the RTC (0x52)"
    assert rows[0x51]["bus"] == "AUX_I2C"           # the isolated segment
    assert rows[0x52]["bus"] == "AUX_I2C"
    assert "24AA025E48" in rows[0x51]["device"]


def test_testplan_i2c_devices_marks_aux_conditional():
    from schgen.generate.testplan import _i2c_devices
    devs = {addr: (ref, kind, is_aux) for addr, ref, kind, is_aux
            in _i2c_devices(_services_only())}
    assert devs[0x51][2] is True, "ID-EEPROM must be flagged AUX (Stage 6)"
    assert devs[0x52][2] is True, "RTC must be flagged AUX (Stage 6)"


def test_all_three_generators_agree_on_the_eeprom_address():
    # one source of truth: firmware._id_eeprom_addr (strap-derived 0x51)
    from schgen.generate.firmware import _id_eeprom_addr
    from schgen.generate.manifest import _i2c_map
    from schgen.generate.testplan import _i2c_devices
    sheets = _services_only()
    fw = _id_eeprom_addr(sheets[0].circuit)
    mf = next(r["addr"] for r in _i2c_map(sheets) if "24AA025E48" in r["device"])
    tp = next(addr for addr, _r, kind, _a in _i2c_devices(sheets)
              if "24AA025E48" in kind)
    assert fw == mf == tp == 0x51
