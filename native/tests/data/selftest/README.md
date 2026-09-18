# Frozen native placer mutation proofs

Captured on 2026-09-18 from the original Python `schgen/verify/selftest.py`
and its original `schgen/layout/place.py` Engine, copied to `/tmp` before
adapter removal. SHA-256 source hashes are recorded in `manifest.json`.
No native selftest result was used to generate expected verdicts or messages.
The fixtures include the actual ordered IR and all seven resolved symbol
definitions; no live board files, installed KiCad library or Python runtime
are required by these contracts.

`rail_decoup_dropped` retains C1 in the electrical circuit while discarding the
test-local Engine's rail-decoupling queue. On this fixture that has the same
effect as the former no-op `_rail_decoupling_columns` monkeypatch. The ordinary
`Engine::run()` missing-part gate rejects C1 as unplaced. Neither the part nor
the gate is deleted, waived, replaced or simulated.

`clamp_thresh_strict` applies the former strict-run classifier mutation exactly:
every signal/port of a multi-pin component must touch two **other** multi-pin
components. This removes the real ESD array's shunt classification. A private
PageOperations build callback constructs that mutated Engine; routing and
visual callbacks call the actual native checks. All eight ordinary spacing
attempts execute, and the real router rejects the contested SIG_1 cell.
No production Engine/global policy or shared symbol definition is changed.

The two additional controls delete the respective target from the *fixture*,
then prove that the same mutation survives: baseline true, killed false,
`(no error)`. Their expected triples also came from the original Python tests.
The suite checks exact descriptions/failure messages, every ordered fixture
field, unchanged inputs, clean builds after repeated mutations, and propagation
of incomplete/unresolved fixture errors instead of crediting them as kills.
It currently runs 195 assertions. Both `baseline_ok` and `mutation_killed` must
be true for a successful model-gate proof, as in the original runner.

Integration adds `native/src/selftest.cpp` to the native core and binds:

```cpp
selftest_rail_decoup_dropped(library)
selftest_clamp_thresh_strict(library)
```

Each returns `PlacerMutationProof` (`baseline_ok`, `mutation_killed`,
`diagnostic`, untruncated `baseline_failure`/`mutation_failure`, and
`mutation_attempts`). Explicit `CircuitSheetIr` overloads never reload input.
The original Python return tuple is the first three fields. Parent owns all
CMake, binding and Python adapter edits.

Independent compile against an already completed native core archive:

```sh
clang++ -std=c++17 -O1 -DNDEBUG -Wall -Wextra -Wpedantic -Werror \
  -ffp-contract=off -I native/include \
  native/tests/selftest_contracts.cpp native/src/selftest.cpp \
  native/build/standalone/libschgen_core.a -o /tmp/selftest_contracts
/tmp/selftest_contracts native/tests/data/selftest
```

No shared-output build, full-board regeneration, Python file edit or commit
was performed by this stage. The remaining selftest/power-family migration is
separate; this stage replaces only the two Python Engine monkeypatch proofs.
