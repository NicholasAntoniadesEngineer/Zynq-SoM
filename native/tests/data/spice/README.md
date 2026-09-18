# Frozen analytic/ngspice verification contracts

Captured 2026-09-18 from original `schgen/verify/spice.py` and its original
`powertree.py` dependency. Source SHA-256 hashes are in `manifest.json`.
Both originals were copied to `/tmp` and loaded independently; native results
were never used to manufacture expectations. Canonical circuit snapshots are
frozen, not regenerated after board changes. The standalone test requires no
Python runtime or live project files.

50 cases exercise carrier (17 checks), devkit (11 checks), all named divider
windows, wrong/missing divider topology, informational and unknown rails,
RC bounce/release windows and the internal NRST pullup, SY7201 FB/ISET notes,
buck FB drift/missing divider, BOOT0 threshold, EN clamps with/without zeners,
unknown zener notes, enable aliases, zero denominators and invalid SI syntax.
Nine additional vectors freeze 1e-9 limit tolerance and 1% ngspice agreement,
including the original zero-valued-check exception to the agreement check.
All numeric values, check ordering, details, errors, notes and reports are exact.

Seven cases also contain results from real `/opt/homebrew/bin/ngspice` execution,
including both boards (carrier: seven independently recomputed dividers).
The native test reruns those cases when ngspice is installed and compares
every field and report byte. Missing ngspice skips only live execution tests;
analytic and process-contract tests always run. No synthetic success is used.

The same test executable acts as a controlled child process for separate
output/error-path tests: usable stdout on a nonzero exit remains consumed,
missing measurements retain the analytic gate and add the original note,
disagreement fails, timeout/spawn failures propagate, argv is never interpreted
by a shell, malformed/invalid UTF-8 output fails rather than manufacturing a
measurement, Unicode reference names/measurement text retain Python behavior,
and disabled ngspice performs no execution. Temporary decks and
captured outputs live in private RAII scratch directories and are cleaned up.
Deck names are comments; CR/LF in names cannot inject ngspice control commands.

Final release and fully instrumented ASan/UBSan result: 50 frozen cases +
9 tolerance vectors + 7 live ngspice cases, 3,850 exact checks. Run:

```sh
spice_contracts native/tests/data/spice
```

Integration sources are `spice.cpp`, `spice_process.cpp`, and the shared
shell-free `process.cpp` (public `process.hpp`). Parent owns CMake and bindings.
The existing private KiCad runner is not edited by this batch; parent can
later consolidate it onto `run_process`. `extract_spice_checks` reuses
`parse_si_value`, `rail_volts`, and the pure `detect_power_regulators` stage
from `power_checks.hpp`, not unrelated whole-board power analysis. The first
independent test used a `/tmp` bridge to the exact native detector while its
owner exposed that public seam; the final build uses the public API directly,
with no temporary bridge, duplicated detector or interpreter fallback.

Independent release compile (using an already completed native core archive):

```sh
clang++ -std=c++17 -O1 -Wall -Wextra -Wpedantic -Werror -ffp-contract=off \
  -I native/include native/tests/spice_contracts.cpp native/src/spice.cpp \
  native/src/spice_process.cpp native/src/process.cpp native/src/power_checks.cpp \
  native/build/standalone/libschgen_core.a -o /tmp/spice_contracts
/tmp/spice_contracts native/tests/data/spice
```

Per-sheet indexed pin/net and passive-neighbor data preserve first-net and
sorted-ref semantics. Passive values are parsed lazily once per component
class, preserving the original error boundary while removing repeated scans.
Ngspice remains optional; reports take availability explicitly, and the run
wrapper creates the requested report directory and writes `spice.txt` with
one final newline.
