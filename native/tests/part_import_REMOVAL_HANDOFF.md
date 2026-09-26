# Partlib adapter / removal-safe handoff

## Integration

Parent-owned `module.cpp` needs:

```cpp
#include "schgen/part_import_bindings.hpp"
// During NB_MODULE registration:
schgen::bind_part_import(m);
```

No new production `.cpp` or CMake source entries. Existing part-import sources
and `native_part_import_contracts` are extended. Recompile against the parent's
new `run_process_bytes` API in `process.hpp` / `process.cpp`. Keep the existing
`-ffp-contract=off` properties on symbol/footprint sources. The new binding uses
the existing JSON boundary and existing model3d OBJ binding; do not register
`model3d_obj_to_wrl` a second time.

`part_import_contracts` now also reads `../part_import_utilities/python.json` and
the existing `../render_models/reference.json` relative to its first fixture
argument. Its self-child curl mode is exercised through the actual subprocess
boundary. No network, Python, shared catalog writes or board generation occur.

## Validated independently

- 2,189 native contracts passed, including all 62 x 3 byte-exact recorded cases,
  synthetic live parameter tests, explicit writes, model cache/download/publication,
  transport failures and real subprocess binary gzip/STEP preservation.
- 227 focused Python tests passed: `schgen/tests/test_part_gen_ep.py` and
  `schgen/tests/test_part_import_native.py` against an actual private nanobind
  extension linked to the copied existing core archive plus updated source objects.
- Strict C++17 `-Wall -Wextra -Wpedantic -Werror -ffp-contract=off`, optimized O2.
- Private build: `/private/tmp/schgen-part-adapter-uLY7Zl`. Shared `.so` and builds
  were not touched. Parent must rebuild the registered shared binding before
  running the root suite. The private test run used `-o addopts=` because that
  interpreter does not have the configured pytest-xdist plugin installed.

Additional live-input tests found and fixed underscore-run sanitization (`A_ B`
must become `A__B`), Unicode glyph widths, and absent optional footprint metadata.
No oracle bytes were changed to accommodate C++ output.

## Inventory and safe deletion boundaries

- `schgen/partlib/__init__.py`: empty package marker; retain until all imports go.
- `schgen/partlib/part_gen.py`: reduced from 974 to 217 lines. All conversion,
  geometry, symbol/footprint construction, SVG/pad parsing, HTTP/download and OBJ
  bodies are removed. Remaining code is data classes, compatibility constants,
  native calls, tagged-tree conversion, diagnostics and the existing catalog
  lifecycle selection for the Python CLI.
- Retained public APIs: `PartGenError`, `PinInfo`, `part_info`, `parse_pins`,
  `normalize_etypes`, `safe_name`, `group_pins`, `gen_symbol`, `synth_ep_pin`,
  `synth_ep_pad_nodes`, `synth_silk_plus_nodes`, `convert_footprint`, `fetch_cad`,
  `fetch_3d_models`, `gen_part_json`, `add_part`, `cmd_part_add`.
- Retained compatibility helpers: `_Groups`, `_ep_number`, `_http_get`,
  `_obj_to_wrl`, `_EpSpec`, `_PolaritySpec`; dimensional/URL constants and the
  package-specification metadata tables remain. Native policy is authoritative;
  these tables are not a Python policy override channel.
- `schgen/__main__.py:cmd_part_add` import is still a real consumer. Do not delete
  `part_gen.py` until the Python CLI itself is removed or routed to standalone
  `schgen part-import` (parent ownership). `docs/LAWS.md` also names `fetch_cad`.
- `schgen/tests/test_part_gen_ep.py`: all six original tests retained; the silent
  missing-fixture return is replaced by an assertion. The helpers now run native.
- `schgen/tests/test_part_import_native.py`: adapter/data-transport compatibility
  tests. Safe to retire with Python adapters once the native contract target is
  required; do not delete the immutable fixtures or native contracts.
- `schgen/tests/test_part_rules.py`: unrelated electrical verification tests,
  already using native part-rule analysis. Not a partlib consumer; left intact.
- `scripts/*.py` / `scripts/*.sh`: no partlib/part_gen imports or importer-specific
  utility bodies. No script edits required.
- Native production files consume `part_import.hpp`, not Python. Existing
  `part_import_cli.cpp` remains parent-owned and unchanged by this batch.

Do not remove any retained API while the callers above remain.

## Intentional boundary differences from unsafe legacy behavior

`add_part` and `fetch_3d_models` now require `overwrite=True` to replace existing
files, matching native `--overwrite`. Existing positional parameters are retained;
the new permission is keyword-only. `_http_get` raises `PartGenError` on transport
failure instead of silently returning `None`. Optional model failures remain
non-fatal but their real diagnostics are printed. Replay cache files retain the
exact provider response bytes. Multi-file publication is atomic per file, not a
transaction; failures identify the file and warn that earlier files may exist.

The old Python CLI parser does not yet expose `--overwrite`; adding that flag is
parent-owned. Standalone CLI and Python `add_part(..., overwrite=True)` already
support the explicit permission. No shared assets were rewritten during validation.
