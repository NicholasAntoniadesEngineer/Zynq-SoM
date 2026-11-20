# removed/

Hand-written outputs that were taken out of the schgen tool. Nothing here is deleted: every file was moved with `git mv`, so `git log --follow <archive path>` shows its history.

The owner's ruling: "lets clear out handwritten things completely and we can deal with them later. The tool must be as programmatic as possible and extensive as what that allows".

Each subfolder has an `ORIGIN.md` that records, in order: what the output was and who used it; every file moved (original path, archive path, `git hash-object`); the source commit; what produced it; what it read; why it was removed; what part of it can be generated; what bringing it back would take. The template is `ORIGIN_TEMPLATE.md`.

Rules the tool relies on (enforced by `native_removed_archive_contracts`):

- `removed/board.json` must not exist: a direct child of the repository root holding `board.json` is read as a board folder.
- `removed/project.json` must not exist: a direct child of the repository root holding `project.json` is read as a fallback baseline.
- No `.py`, `.pyc` or `.pyo` file may be placed under `removed/`.
- Never archive under `subsystems/` or `<board>/subsystems/`.

## Subfolders

| folder | what it holds | source commit | move commit |
|---|---|---|---|
| `bringup_manual/` | docs/BRINGUP.md and the renderer that wrote it | `f32ac35a280d8cca496f4dbec4dde9f51c63600d` | `e95a7702bfddd6775b5b0c482e90d29cf3c178b5` |
| `test_plan/` | docs/TEST_PLAN.md and the renderer that wrote it | `f32ac35a280d8cca496f4dbec4dde9f51c63600d` | `e95a7702bfddd6775b5b0c482e90d29cf3c178b5` |
| `sc_firmware_scaffold/` | firmware/sc/* system-controller scaffold and its generator | `f32ac35a280d8cca496f4dbec4dde9f51c63600d` | `e95a7702bfddd6775b5b0c482e90d29cf3c178b5` |
| `firmware_contract/` | firmware/zynq_carrier_contract.h, the shared template header, provenance, fixtures | `f32ac35a280d8cca496f4dbec4dde9f51c63600d` | `e95a7702bfddd6775b5b0c482e90d29cf3c178b5` |
| `device_tree/` | firmware/carrier_pl.dtsi and its generator | `9d2961a723a8b27af61bd49606abaea8f8ebaed4` | `f32ac35a280d8cca496f4dbec4dde9f51c63600d` |
| `vivado_script/` | fpga/create_project.tcl and its generator | `9d2961a723a8b27af61bd49606abaea8f8ebaed4` | `f32ac35a280d8cca496f4dbec4dde9f51c63600d` |
| `document_consistency/` | checker of the stored DESIGN_SPEC.md and COMPLIANCE.md | `e95a7702bfddd6775b5b0c482e90d29cf3c178b5` | `e4fd185c3ec9aac237b3c00f1ce534d5632d4152` |
| `floorplan_prose/` | typed per-sheet placement notes and framing text of docs/FLOORPLAN.md and FLOORPLAN.svg | `9301deeda9d6c31cc06fc5f9230519033cd464c9` | PENDING |

## Files

Original path, then archive path.

### bringup_manual

- `carrier/docs/BRINGUP.md` -> `removed/bringup_manual/outputs/carrier/docs/BRINGUP.md`
- `native/src/firmware_docs_manual.cpp` -> `removed/bringup_manual/source/firmware_docs_manual.cpp`
- `native/tests/data/firmware_docs/carrier/BRINGUP.md` -> `removed/bringup_manual/tests/data/firmware_docs/carrier/BRINGUP.md`
- `native/include/schgen/firmware_docs.hpp:27-27` -> `removed/bringup_manual/fragments/firmware_docs.hpp.L27-27.txt`
- `native/include/schgen/firmware_docs.hpp:31-31` -> `removed/bringup_manual/fragments/firmware_docs.hpp.L31-31.txt`

### test_plan

- `carrier/docs/TEST_PLAN.md` -> `removed/test_plan/outputs/carrier/docs/TEST_PLAN.md`
- `devkit_mini/docs/TEST_PLAN.md` -> `removed/test_plan/outputs/devkit_mini/docs/TEST_PLAN.md`
- `native/src/firmware_docs_testplan.cpp` -> `removed/test_plan/source/firmware_docs_testplan.cpp`
- `native/tests/data/firmware_docs/carrier/TEST_PLAN.md` -> `removed/test_plan/tests/data/firmware_docs/carrier/TEST_PLAN.md`
- `native/tests/data/firmware_docs/devkit_mini/TEST_PLAN.md` -> `removed/test_plan/tests/data/firmware_docs/devkit_mini/TEST_PLAN.md`
- `native/include/schgen/firmware_docs.hpp:32-39` -> `removed/test_plan/fragments/firmware_docs.hpp.L32-39.txt`

### sc_firmware_scaffold

- `carrier/firmware/sc/README.md` -> `removed/sc_firmware_scaffold/outputs/carrier/firmware/sc/README.md`
- `carrier/firmware/sc/sc_app.c` -> `removed/sc_firmware_scaffold/outputs/carrier/firmware/sc/sc_app.c`
- `carrier/firmware/sc/sc_hal.h` -> `removed/sc_firmware_scaffold/outputs/carrier/firmware/sc/sc_hal.h`
- `carrier/firmware/sc/sc_hal_zephyr.c.txt` -> `removed/sc_firmware_scaffold/outputs/carrier/firmware/sc/sc_hal_zephyr.c.txt`
- `carrier/firmware/sc/sc_pd.c` -> `removed/sc_firmware_scaffold/outputs/carrier/firmware/sc/sc_pd.c`
- `carrier/firmware/sc/sc_pd.h` -> `removed/sc_firmware_scaffold/outputs/carrier/firmware/sc/sc_pd.h`
- `carrier/firmware/sc/sc_rtc.c` -> `removed/sc_firmware_scaffold/outputs/carrier/firmware/sc/sc_rtc.c`
- `carrier/firmware/sc/sc_rtc.h` -> `removed/sc_firmware_scaffold/outputs/carrier/firmware/sc/sc_rtc.h`
- `carrier/firmware/sc/sc_seq.c` -> `removed/sc_firmware_scaffold/outputs/carrier/firmware/sc/sc_seq.c`
- `carrier/firmware/sc/sc_seq.h` -> `removed/sc_firmware_scaffold/outputs/carrier/firmware/sc/sc_seq.h`
- `carrier/firmware/sc/sc_tables.c` -> `removed/sc_firmware_scaffold/outputs/carrier/firmware/sc/sc_tables.c`
- `carrier/firmware/sc/sc_tables.h` -> `removed/sc_firmware_scaffold/outputs/carrier/firmware/sc/sc_tables.h`
- `carrier/firmware/sc/sc_wdt.c` -> `removed/sc_firmware_scaffold/outputs/carrier/firmware/sc/sc_wdt.c`
- `carrier/firmware/sc/sc_wdt.h` -> `removed/sc_firmware_scaffold/outputs/carrier/firmware/sc/sc_wdt.h`
- `native/src/firmware_docs_scfw.cpp` -> `removed/sc_firmware_scaffold/source/firmware_docs_scfw.cpp`
- `native/tests/data/firmware_docs/carrier/sc/README.md` -> `removed/sc_firmware_scaffold/tests/data/firmware_docs/carrier/sc/README.md`
- `native/tests/data/firmware_docs/carrier/sc/sc_app.c` -> `removed/sc_firmware_scaffold/tests/data/firmware_docs/carrier/sc/sc_app.c`
- `native/tests/data/firmware_docs/carrier/sc/sc_hal.h` -> `removed/sc_firmware_scaffold/tests/data/firmware_docs/carrier/sc/sc_hal.h`
- `native/tests/data/firmware_docs/carrier/sc/sc_hal_zephyr.c.txt` -> `removed/sc_firmware_scaffold/tests/data/firmware_docs/carrier/sc/sc_hal_zephyr.c.txt`
- `native/tests/data/firmware_docs/carrier/sc/sc_pd.c` -> `removed/sc_firmware_scaffold/tests/data/firmware_docs/carrier/sc/sc_pd.c`
- `native/tests/data/firmware_docs/carrier/sc/sc_pd.h` -> `removed/sc_firmware_scaffold/tests/data/firmware_docs/carrier/sc/sc_pd.h`
- `native/tests/data/firmware_docs/carrier/sc/sc_rtc.c` -> `removed/sc_firmware_scaffold/tests/data/firmware_docs/carrier/sc/sc_rtc.c`
- `native/tests/data/firmware_docs/carrier/sc/sc_rtc.h` -> `removed/sc_firmware_scaffold/tests/data/firmware_docs/carrier/sc/sc_rtc.h`
- `native/tests/data/firmware_docs/carrier/sc/sc_seq.c` -> `removed/sc_firmware_scaffold/tests/data/firmware_docs/carrier/sc/sc_seq.c`
- `native/tests/data/firmware_docs/carrier/sc/sc_seq.h` -> `removed/sc_firmware_scaffold/tests/data/firmware_docs/carrier/sc/sc_seq.h`
- `native/tests/data/firmware_docs/carrier/sc/sc_tables.c` -> `removed/sc_firmware_scaffold/tests/data/firmware_docs/carrier/sc/sc_tables.c`
- `native/tests/data/firmware_docs/carrier/sc/sc_tables.h` -> `removed/sc_firmware_scaffold/tests/data/firmware_docs/carrier/sc/sc_tables.h`
- `native/tests/data/firmware_docs/carrier/sc/sc_wdt.c` -> `removed/sc_firmware_scaffold/tests/data/firmware_docs/carrier/sc/sc_wdt.c`
- `native/tests/data/firmware_docs/carrier/sc/sc_wdt.h` -> `removed/sc_firmware_scaffold/tests/data/firmware_docs/carrier/sc/sc_wdt.h`
- `native/include/schgen/firmware_docs.hpp:28-28` -> `removed/sc_firmware_scaffold/fragments/firmware_docs.hpp.L28-28.txt`
- `native/include/schgen/firmware_docs.hpp:40-41` -> `removed/sc_firmware_scaffold/fragments/firmware_docs.hpp.L40-41.txt`

### firmware_contract

- `carrier/firmware/zynq_carrier_contract.h` -> `removed/firmware_contract/outputs/carrier/firmware/zynq_carrier_contract.h`
- `devkit_mini/firmware/zynq_carrier_contract.h` -> `removed/firmware_contract/outputs/devkit_mini/firmware/zynq_carrier_contract.h`
- `native/src/firmware_docs.cpp` -> `removed/firmware_contract/source/firmware_docs.cpp`
- `native/src/firmware_docs_templates.hpp` -> `removed/firmware_contract/source/firmware_docs_templates.hpp`
- `native/src/firmware_provenance.cpp` -> `removed/firmware_contract/source/firmware_provenance.cpp`
- `native/include/schgen/firmware_provenance.hpp` -> `removed/firmware_contract/source/firmware_provenance.hpp`
- `native/tests/data/downstream_i2c/README.md` -> `removed/firmware_contract/tests/data/downstream_i2c/README.md`
- `native/tests/data/firmware_docs/README.md` -> `removed/firmware_contract/tests/data/firmware_docs/README.md`
- `native/tests/data/firmware_docs/carrier/mutants.json` -> `removed/firmware_contract/tests/data/firmware_docs/carrier/mutants.json`
- `native/tests/data/firmware_docs/carrier/zynq_carrier_contract.h` -> `removed/firmware_contract/tests/data/firmware_docs/carrier/zynq_carrier_contract.h`
- `native/tests/data/firmware_docs/devkit_mini/mutants.json` -> `removed/firmware_contract/tests/data/firmware_docs/devkit_mini/mutants.json`
- `native/tests/data/firmware_docs/devkit_mini/zynq_carrier_contract.h` -> `removed/firmware_contract/tests/data/firmware_docs/devkit_mini/zynq_carrier_contract.h`
- `native/tests/data/firmware_provenance/carrier_sources.txt` -> `removed/firmware_contract/tests/data/firmware_provenance/carrier_sources.txt`
- `native/tests/data/firmware_provenance/devkit_mini_sources.txt` -> `removed/firmware_contract/tests/data/firmware_provenance/devkit_mini_sources.txt`
- `native/tests/firmware_docs_CORRECTIONS.md` -> `removed/firmware_contract/tests/firmware_docs_CORRECTIONS.md`
- `native/tests/firmware_docs_NATIVE_NOTICES.md` -> `removed/firmware_contract/tests/firmware_docs_NATIVE_NOTICES.md`
- `native/tests/firmware_docs_contracts.cpp` -> `removed/firmware_contract/tests/firmware_docs_contracts.cpp`
- `native/tests/firmware_provenance_contracts.cpp` -> `removed/firmware_contract/tests/firmware_provenance_contracts.cpp`
- `native/src/authoring_purity_scope.cpp:66-68` -> `removed/firmware_contract/fragments/authoring_purity_scope.cpp.L66-68.txt`
- `native/src/bringup_facts.cpp:11-31` -> `removed/firmware_contract/fragments/bringup_facts.cpp.L11-31.txt`
- `native/src/bringup_facts.cpp:175-194` -> `removed/firmware_contract/fragments/bringup_facts.cpp.L175-194.txt`
- `native/src/bringup_facts.cpp:3-5` -> `removed/firmware_contract/fragments/bringup_facts.cpp.L3-5.txt`
- `native/src/bringup_facts.cpp:49-68` -> `removed/firmware_contract/fragments/bringup_facts.cpp.L49-68.txt`
- `native/src/bringup_facts.cpp:94-174` -> `removed/firmware_contract/fragments/bringup_facts.cpp.L94-174.txt`
- `native/include/schgen/bringup_facts.hpp:19-20` -> `removed/firmware_contract/fragments/bringup_facts.hpp.L19-20.txt`
- `native/include/schgen/bringup_facts.hpp:27-36` -> `removed/firmware_contract/fragments/bringup_facts.hpp.L27-36.txt`
- `native/include/schgen/bringup_facts.hpp:38-39` -> `removed/firmware_contract/fragments/bringup_facts.hpp.L38-39.txt`
- `native/include/schgen/bringup_facts.hpp:41-44` -> `removed/firmware_contract/fragments/bringup_facts.hpp.L41-44.txt`
- `native/include/schgen/bringup_facts.hpp:47-51` -> `removed/firmware_contract/fragments/bringup_facts.hpp.L47-51.txt`
- `native/src/bringup_internal.hpp:112-130` -> `removed/firmware_contract/fragments/bringup_internal.hpp.L112-130.txt`
- `native/src/bringup_internal.hpp:134-140` -> `removed/firmware_contract/fragments/bringup_internal.hpp.L134-140.txt`
- `native/tests/downstream_i2c_contracts.cpp:1-203` -> `removed/firmware_contract/fragments/downstream_i2c_contracts.cpp.L1-203.txt`
- `native/include/schgen/firmware_docs.hpp:15-26` -> `removed/firmware_contract/fragments/firmware_docs.hpp.L15-26.txt`
- `native/include/schgen/firmware_docs.hpp:29-30` -> `removed/firmware_contract/fragments/firmware_docs.hpp.L29-30.txt`

### device_tree

- `carrier/firmware/carrier_pl.dtsi` -> `removed/device_tree/outputs/carrier/firmware/carrier_pl.dtsi`
- `devkit_mini/firmware/carrier_pl.dtsi` -> `removed/device_tree/outputs/devkit_mini/firmware/carrier_pl.dtsi`
- `native/src/devicetree.cpp` -> `removed/device_tree/source/devicetree.cpp`
- `native/include/schgen/devicetree.hpp` -> `removed/device_tree/source/devicetree.hpp`
- `native/tests/data/devicetree_carrier_golden.dtsi` -> `removed/device_tree/tests/devicetree_carrier_golden.dtsi`
- `native/tests/data/devicetree_cases.json` -> `removed/device_tree/tests/devicetree_cases.json`
- `native/tests/devicetree_contracts.cpp` -> `removed/device_tree/tests/devicetree_contracts.cpp`
- `native/tests/data/devicetree_devkit_mini_golden.dtsi` -> `removed/device_tree/tests/devicetree_devkit_mini_golden.dtsi`

### vivado_script

- `carrier/fpga/create_project.tcl` -> `removed/vivado_script/outputs/carrier/fpga/create_project.tcl`
- `devkit_mini/fpga/create_project.tcl` -> `removed/vivado_script/outputs/devkit_mini/fpga/create_project.tcl`
- `native/src/vivado.cpp` -> `removed/vivado_script/source/vivado.cpp`
- `native/include/schgen/vivado.hpp` -> `removed/vivado_script/source/vivado.hpp`
- `native/tests/vivado_contracts.cpp` -> `removed/vivado_script/tests/vivado_contracts.cpp`
- `native/tests/data/vivado_golden.tcl` -> `removed/vivado_script/tests/vivado_golden.tcl`

### document_consistency

- `native/src/doc_consistency.cpp` -> `removed/document_consistency/source/doc_consistency.cpp`
- `native/include/schgen/doc_consistency.hpp` -> `removed/document_consistency/source/doc_consistency.hpp`
- `native/tests/data/doc_consistency/python_reference.json` -> `removed/document_consistency/tests/data/doc_consistency/python_reference.json`
- `native/tests/doc_consistency_INTEGRATION.md` -> `removed/document_consistency/tests/doc_consistency_INTEGRATION.md`
- `native/tests/doc_consistency_contracts.cpp` -> `removed/document_consistency/tests/doc_consistency_contracts.cpp`

### floorplan_prose

- `native/src/floorplan_notes.cpp` -> `removed/floorplan_prose/source/floorplan_notes.cpp`
- `native/tests/data/floorplan/carrier.json` key `expected.notes` -> `removed/floorplan_prose/tests/data/floorplan/carrier_expected_notes.json`
- `native/tests/data/floorplan/devkit_mini.json` key `expected.notes` -> `removed/floorplan_prose/tests/data/floorplan/devkit_mini_expected_notes.json`
- `native/include/schgen/floorplan.hpp:248-251` -> `removed/floorplan_prose/fragments/floorplan.hpp.L248-251.txt`
- `native/include/schgen/floorplan.hpp:328-329` -> `removed/floorplan_prose/fragments/floorplan.hpp.L328-329.txt`
- `native/include/schgen/floorplan.hpp:331-331` -> `removed/floorplan_prose/fragments/floorplan.hpp.L331-331.txt`
- `native/include/schgen/floorplan.hpp:334-334` -> `removed/floorplan_prose/fragments/floorplan.hpp.L334-334.txt`
- `native/include/schgen/floorplan.hpp:343-343` -> `removed/floorplan_prose/fragments/floorplan.hpp.L343-343.txt`
- `native/tests/floorplan_contracts.cpp:1298-1301` -> `removed/floorplan_prose/fragments/floorplan_contracts.cpp.L1298-1301.txt`
- `native/tests/floorplan_contracts.cpp:1315-1317` -> `removed/floorplan_prose/fragments/floorplan_contracts.cpp.L1315-1317.txt`
- `native/src/floorplan_md.cpp:110-111` -> `removed/floorplan_prose/fragments/floorplan_md.cpp.L110-111.txt`
- `native/src/floorplan_md.cpp:112-116` -> `removed/floorplan_prose/fragments/floorplan_md.cpp.L112-116.txt`
- `native/src/floorplan_md.cpp:19-19` -> `removed/floorplan_prose/fragments/floorplan_md.cpp.L19-19.txt`
- `native/src/floorplan_md.cpp:20-21` -> `removed/floorplan_prose/fragments/floorplan_md.cpp.L20-21.txt`
- `native/src/floorplan_md.cpp:23-24` -> `removed/floorplan_prose/fragments/floorplan_md.cpp.L23-24.txt`
- `native/src/floorplan_md.cpp:26-26` -> `removed/floorplan_prose/fragments/floorplan_md.cpp.L26-26.txt`
- `native/src/floorplan_md.cpp:28-28` -> `removed/floorplan_prose/fragments/floorplan_md.cpp.L28-28.txt`
- `native/src/floorplan_md.cpp:31-31` -> `removed/floorplan_prose/fragments/floorplan_md.cpp.L31-31.txt`
- `native/src/floorplan_output.cpp:9-11` -> `removed/floorplan_prose/fragments/floorplan_output.cpp.L9-11.txt`
- `native/src/floorplan_svg.cpp:103-107` -> `removed/floorplan_prose/fragments/floorplan_svg.cpp.L103-107.txt`
- `native/src/floorplan_svg.cpp:124-130` -> `removed/floorplan_prose/fragments/floorplan_svg.cpp.L124-130.txt`
- `native/src/floorplan_svg.cpp:131-131` -> `removed/floorplan_prose/fragments/floorplan_svg.cpp.L131-131.txt`
- `native/src/floorplan_svg.cpp:30-30` -> `removed/floorplan_prose/fragments/floorplan_svg.cpp.L30-30.txt`
- `native/src/floorplan_svg.cpp:36-38` -> `removed/floorplan_prose/fragments/floorplan_svg.cpp.L36-38.txt`
- `native/src/floorplan_svg.cpp:40-40` -> `removed/floorplan_prose/fragments/floorplan_svg.cpp.L40-40.txt`
- `native/tests/output_precision_contracts.cpp:129-129` -> `removed/floorplan_prose/fragments/output_precision_contracts.cpp.L129-129.txt`
- `native/tests/output_precision_contracts.cpp:130-133` -> `removed/floorplan_prose/fragments/output_precision_contracts.cpp.L130-133.txt`
