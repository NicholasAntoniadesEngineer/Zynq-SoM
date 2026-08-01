from __future__ import annotations

import os

from schgen.core import sexpr, symbols
from schgen.core.symbols import Library

_MINIMAL_LIB = """\
(kicad_symbol_lib (version 20211014) (generator test)
  (symbol "FOO" (pin_names) (pin_numbers)
    (symbol "FOO_0_1"
      (pin passive line (at 0 0 0) (length 2.54)
        (name "A" (effects (font (size 1.27 1.27))))
        (number "1" (effects (font (size 1.27 1.27))))))))
"""


def _write_lib(path):
    path.write_text(_MINIMAL_LIB)


def test_parse_is_cached_across_library_instances(tmp_path, monkeypatch):
    lib_file = tmp_path / "MYLIB.kicad_sym"
    _write_lib(lib_file)

    calls = {"n": 0}
    real_loads = sexpr.loads

    def _counting_loads(text):
        calls["n"] += 1
        return real_loads(text)

    monkeypatch.setattr(sexpr, "loads", _counting_loads)
    symbols._FILE_PARSE_CACHE.clear()

    for _ in range(2):
        lib = Library(extra_paths=[tmp_path])
        assert lib.pin_numbers("MYLIB:FOO") == {"1"}

    assert calls["n"] == 1, f"expected 1 parse across 2 instances, got {calls['n']}"


def test_changed_file_is_reparsed(tmp_path, monkeypatch):
    lib_file = tmp_path / "MYLIB.kicad_sym"
    _write_lib(lib_file)

    calls = {"n": 0}
    real_loads = sexpr.loads

    def _counting_loads(text):
        calls["n"] += 1
        return real_loads(text)

    monkeypatch.setattr(sexpr, "loads", _counting_loads)
    symbols._FILE_PARSE_CACHE.clear()

    Library(extra_paths=[tmp_path]).get("MYLIB:FOO")
    assert calls["n"] == 1

    lib_file.write_text(_MINIMAL_LIB.replace('"FOO"', '"FOO"  '))
    st = lib_file.stat()
    os.utime(lib_file, ns=(st.st_atime_ns, st.st_mtime_ns + 1_000_000))
    Library(extra_paths=[tmp_path]).get("MYLIB:FOO")
    assert calls["n"] == 2, "a changed-on-disk lib file must be re-parsed"
