from __future__ import annotations

import copy
import os
from dataclasses import FrozenInstanceError

import pytest

from schgen.core import native as _nat
from schgen.core import sexpr, symbols
from schgen.core.symbols import Library, Pin, SymbolDef, SymbolError

_MINIMAL_LIB = """\
(kicad_symbol_lib (version 20211014) (generator test)
  (symbol "FOO" (pin_names) (pin_numbers)
    (symbol "FOO_0_1"
      (pin passive line (at 0 0 0) (length 2.54)
        (name "A" (effects (font (size 1.27 1.27))))
        (number "1" (effects (font (size 1.27 1.27))))))))
"""


def _write_lib(path, text=_MINIMAL_LIB):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


@pytest.fixture(autouse=True)
def _clear_native_cache():
    _nat.module().symbols_clear_file_cache()
    yield
    _nat.module().symbols_clear_file_cache()


def test_native_parse_and_dataclass_cache(tmp_path, monkeypatch):
    # Native C++ contracts assert actual parse sharing by pointer identity,
    # canonical path and timestamp/size. The adapter must never parse in Python.
    lib_file = tmp_path / "MYLIB.kicad_sym"
    _write_lib(lib_file)

    def _no_python_parse(_text):
        raise AssertionError("Library must parse entirely in C++")

    monkeypatch.setattr(sexpr, "loads", _no_python_parse)
    first = Library(extra_paths=[tmp_path])
    second = Library(extra_paths=[tmp_path])
    a, b = first.get("MYLIB:FOO"), second.get("MYLIB:FOO")
    assert type(a) is SymbolDef
    assert type(a.pins[0]) is Pin
    assert type(a.raw) is list and type(a.raw[0]) is sexpr.Sym
    assert type(a.raw[1]) is str and type(a.body) is tuple
    assert a is first.get("MYLIB:FOO")
    assert a == b and a is not b and a.raw is not b.raw
    assert first.pin_numbers("MYLIB:FOO") == {"1"}
    with pytest.raises(FrozenInstanceError):
        a.pins[0].number = "2"
    a.pins.append(Pin("2", "B", "passive", 0, 0, 0, 2.54))
    a.raw.append([sexpr.Sym("property"), "Custom", "caller-owned"])
    assert first.pin_numbers("MYLIB:FOO") == {"1", "2"}
    assert second.pin_numbers("MYLIB:FOO") == {"1"}
    assert not sexpr.find(b.raw, "property")


def test_changed_file_is_reparsed_without_mutating_existing_library(tmp_path):
    lib_file = tmp_path / "MYLIB.kicad_sym"
    _write_lib(lib_file)

    old = Library(extra_paths=[tmp_path])
    original = old.get("MYLIB:FOO")
    assert original.pins[0].number == "1"

    st = lib_file.stat()
    _write_lib(lib_file, _MINIMAL_LIB.replace('(number "1"', '(number "2"'))
    os.utime(lib_file, ns=(st.st_atime_ns, st.st_mtime_ns + 1))
    assert lib_file.stat().st_size == st.st_size
    fresh = Library(extra_paths=[tmp_path]).get("MYLIB:FOO")
    assert fresh.pins[0].number == "2"
    assert old.get("MYLIB:FOO") is original
    assert old.pin_numbers("MYLIB:FOO") == {"1"}


def test_deepcopy_preserves_loaded_snapshot_and_mutable_metadata(tmp_path):
    lib_file = tmp_path / "MYLIB.kicad_sym"
    # BAR has not been requested when copying, but its containing file has been
    # loaded. A correct snapshot must retain it even after the file is removed.
    text = _MINIMAL_LIB[:-2] + '\n(symbol "BAR"))\n'
    _write_lib(lib_file, text)
    library = Library(extra_paths=[tmp_path])
    symbol = library.get("MYLIB:FOO")
    symbol.pins.append(Pin("2", "caller-added", "passive", 0, 0, 0, 2.54))
    symbol.raw.append([sexpr.Sym("property"), "Custom", "caller-owned"])
    symbol.body = (-10, -20, 30, 40)
    snapshot, metadata, alias = copy.deepcopy([library, symbol, library])
    assert snapshot is alias and snapshot is not library
    assert snapshot.paths == library.paths and snapshot.paths is not library.paths
    copied = snapshot.get("MYLIB:FOO")
    assert copied is metadata and copied == symbol and copied is not symbol
    assert copied.raw is not symbol.raw and copied.pins is not symbol.pins
    assert snapshot.pin_numbers("MYLIB:FOO") == {"1", "2"}
    copied.pins.pop()
    sexpr.find(copied.raw, "property")[2] = "copied-only"
    assert library.pin_numbers("MYLIB:FOO") == {"1", "2"}
    assert sexpr.find(symbol.raw, "property")[2] == "caller-owned"
    lib_file.unlink()
    _nat.module().symbols_clear_file_cache()
    assert snapshot.get("MYLIB:BAR").lib_id == "MYLIB:BAR"
    assert library.get("MYLIB:BAR").lib_id == "MYLIB:BAR"
    assert snapshot.get("MYLIB:FOO") is copied


def test_shallow_copy_keeps_library_transport_identity(tmp_path):
    _write_lib(tmp_path / "MYLIB.kicad_sym")
    library = Library(extra_paths=[tmp_path])
    symbol = library.get("MYLIB:FOO")
    shallow = copy.copy(library)
    assert shallow is not library and shallow.paths is library.paths
    assert shallow.get("MYLIB:FOO") is symbol
    native_shallow = copy.copy(library._native)
    assert native_shallow.get("MYLIB:FOO") is symbol


def test_search_paths_remain_ordered_and_caller_configurable(tmp_path, monkeypatch):
    first, second = tmp_path / "first", tmp_path / "second"
    _write_lib(first / "MYLIB.kicad_sym")
    _write_lib(second / "MYLIB" / "MYLIB.kicad_sym",
               _MINIMAL_LIB.replace('(number "1"', '(number "2"'))
    monkeypatch.setattr(symbols, "_SEARCH_PATHS", [second])
    extra = Library(extra_paths=[first])
    assert extra.paths == [first, second]
    assert extra.pin_numbers("MYLIB:FOO") == {"1"}
    assert Library().pin_numbers("MYLIB:FOO") == {"2"}
    assert symbols._SEARCH_PATHS == [second]


def test_native_errors_keep_python_symbol_error(tmp_path):
    _write_lib(tmp_path / "MYLIB.kicad_sym")
    lib = Library(extra_paths=[tmp_path])
    with pytest.raises(SymbolError, match="symbol 'ABSENT' not in MYLIB"):
        lib.get("MYLIB:ABSENT")
    with pytest.raises(SymbolError, match="library 'NO_SUCH_LIBRARY'"):
        lib.pin_numbers("NO_SUCH_LIBRARY:ABSENT")
    _write_lib(tmp_path / "OFFGRID.kicad_sym",
               _MINIMAL_LIB.replace("(at 0 0 0)", "(at 0.1 0 0)"))
    with pytest.raises(SymbolError, match="OFF-GRID"):
        lib.get("OFFGRID:FOO")
    assert issubclass(SymbolError, ValueError)


def test_native_parse_and_full_pin_transform():
    raw = [sexpr.Sym("symbol"), "Direct", [sexpr.Sym("pin"),
           sexpr.Sym("passive"), sexpr.Sym("line"),
           [sexpr.Sym("at"), -3.81, 5.08, 0],
           [sexpr.Sym("number"), "1"]]]
    symbol = symbols._parse_symbol("test:Direct", raw)
    assert type(symbol) is SymbolDef and symbol.raw == raw
    assert symbol.body == (-3.81, 5.08, -3.81, 5.08)
    assert symbols.pin_page_position(symbol.pins[0], -0.00005, 0.00015, -30) == (
        1.2699, -8.8899)
    assert symbols._on_grid(1.27) and not symbols._on_grid(0.1)
    with pytest.raises(SymbolError, match="unresolved extends"):
        symbols._parse_symbol("test:Child", [sexpr.Sym("symbol"), "Child",
                              [sexpr.Sym("extends"), "Base"]])
