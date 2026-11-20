# document_consistency origin

## 1. What it was and who used it

`doc_consistency` was a checker of two stored, hand-written carrier documents, `carrier/docs/DESIGN_SPEC.md` and `carrier/docs/COMPLIANCE.md`: nine named families of checks (packet files present, rail-table rails are real, core rails documented, cited sheets exist, interfaces covered, power sequence partitions every regulator, sequence build deterministic, sequence drawing byte deterministic, artifacts referenced). Its only caller was its own test; no pipeline step, command or gate called it. The two documents stay where they are as hand-maintained files; the tool no longer reads them and the manifest no longer hashes them.

## 2. Files moved (5)

| original path | archive path | git hash-object |
|---|---|---|
| `native/src/doc_consistency.cpp` | `removed/document_consistency/source/doc_consistency.cpp` | `a66c4c65bbf127bd7673cc8457aee82163ac3370` |
| `native/include/schgen/doc_consistency.hpp` | `removed/document_consistency/source/doc_consistency.hpp` | `702de2d5071d9261fe522ad6fbdb6e50c0fd7b44` |
| `native/tests/data/doc_consistency/python_reference.json` | `removed/document_consistency/tests/data/doc_consistency/python_reference.json` | `b96323f2523d170c08ac2cfd953f5c1e08427dca` |
| `native/tests/doc_consistency_INTEGRATION.md` | `removed/document_consistency/tests/doc_consistency_INTEGRATION.md` | `4f8adf7ed8ec1268d2191221d92debfbce1bb804` |
| `native/tests/doc_consistency_contracts.cpp` | `removed/document_consistency/tests/doc_consistency_contracts.cpp` | `8fb3e92a3692ce227690c8b60eeefd7933ec0784` |

## 3. Source commit

`e95a7702bfddd6775b5b0c482e90d29cf3c178b5` (the last commit in which these files were at their original paths; the parent of the move commit). Line numbers below are from that commit unless they name an archive path. The move commit's own hash is in `removed/INDEX.md`.

## 4. What produced it

- No pipeline step, gate or command. Entry points: `schgen::load_doc_consistency_input`, `schgen::build_doc_consistency_input`, `schgen::check_doc_consistency`, `schgen::doc_consistency_families` (`removed/document_consistency/source/doc_consistency.hpp`), called only from `removed/document_consistency/tests/doc_consistency_contracts.cpp`.
- Build: `native/CMakeLists.txt:79` (`target_sources(schgen_core PRIVATE src/doc_consistency.cpp)`), `native/CMakeLists.txt:109-110` (strict compile options), `native/CMakeLists.txt:785` and `native/CMakeLists.txt:1101-1103` (test `native_doc_consistency_contracts`).
- Manifest: the two document names were in the artifact list, `native/src/manufacturing_exports_manifest.cpp:71`; they were hashed when the file existed (carrier only).

## 5. What it read

- `docs/DESIGN_SPEC.md` and `docs/COMPLIANCE.md` of the selected board (`removed/document_consistency/source/doc_consistency.cpp:91-94`), all authored circuits, the power analysis (`analyze_power`) and the power sequence builder and renderer, run twice for the determinism families.
- Typed in the checker: required rail names, required interface names and artifact names (`doc_consistency.cpp:121`, `:129`, `:155`) and the family names (:69-77).
- The test also read the fixture `removed/firmware_contract/tests/data/firmware_docs/carrier` (the frozen contract header, now archived with the firmware outputs) and `tests/data/doc_consistency/python_reference.json`.

## 6. Why it was removed

The owner: "lets clear out handwritten things completely and we can deal with them later. The tool must be as programmatic as possible and extensive as what that allows". Specific reason: it checked prose that the tool does not write, and it was reachable only from its own test. Families 6 to 8 (power sequence partition and the two determinism checks) exercised the power sequence builder and renderer rather than the documents; that builder is now covered by `native/tests/power_sequence_contracts.cpp`, which compares both boards' drawings byte for byte against the frozen files and runs the cycle and drawing-status mutants. The partition rule ("every regulator lands in a stage") has no separate test since this move.

## 7. What could be generated

Nothing: the documents are prose. The consistency the checker enforced (rails named in the document exist in the circuits) would be automatic if the document tables were generated from the power result, which is the budget table N6 of the study.

## 8. Bringing it back

1. `git mv` `source/doc_consistency.cpp` to `native/src/`, `source/doc_consistency.hpp` to `native/include/schgen/`, `tests/doc_consistency_contracts.cpp` and `tests/doc_consistency_INTEGRATION.md` to `native/tests/`, `tests/data/doc_consistency/python_reference.json` to `native/tests/data/doc_consistency/`.
2. Restore the build lines:

`native/CMakeLists.txt:79` at `e95a7702`:

```
target_sources(schgen_core PRIVATE src/doc_consistency.cpp)
```

`native/CMakeLists.txt:109-110` at `e95a7702`:

```
set_source_files_properties(src/doc_consistency.cpp
    PROPERTIES COMPILE_OPTIONS "-Wall;-Wextra;-Wpedantic;-Werror;-ffp-contract=off")
```

`native/CMakeLists.txt:785` at `e95a7702`:

```
    add_executable(schgen_doc_consistency_contracts tests/doc_consistency_contracts.cpp)
```

`native/CMakeLists.txt:1101-1103` at `e95a7702`:

```
    target_link_libraries(schgen_doc_consistency_contracts PRIVATE schgen_core)
    target_compile_options(schgen_doc_consistency_contracts PRIVATE -Wall -Wextra -Wpedantic -Werror -ffp-contract=off)
    add_test(NAME native_doc_consistency_contracts COMMAND schgen_doc_consistency_contracts "${CMAKE_CURRENT_SOURCE_DIR}/.." "${CMAKE_CURRENT_BINARY_DIR}/doc-consistency-contract-output")
```

3. Restore the manifest artifact names:

`native/src/manufacturing_exports_manifest.cpp:71` at `e95a7702`:

```
    for(const auto& rel:std::vector<std::string>{board_file_name(file_stem,BoardFileKind::Schematic),board_file_name(file_stem,BoardFileKind::Project),board_file_name(file_stem,BoardFileKind::Pcb),"manufacturing/SI_CONSTRAINTS.md","docs/FLOORPLAN.md","docs/DESIGN_SPEC.md","docs/COMPLIANCE.md"})add(root/rel);
```

4. The test needs the frozen contract header fixture back at `native/tests/data/firmware_docs/carrier/zynq_carrier_contract.h` (now in `removed/firmware_contract/tests/data/firmware_docs/carrier/`), and `carrier/docs/DESIGN_SPEC.md` and `carrier/docs/COMPLIANCE.md`, which were not moved.
5. What changed since: `doc_consistency.hpp` includes `schgen/firmware_docs.hpp` for `PowerSequence`; that header remains.
