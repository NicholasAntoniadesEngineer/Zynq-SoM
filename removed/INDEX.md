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
| `i2c_chip_facts/` | chip-specific I2C address functions and the sheet-named collision check they fed | `48d29d0194a10565be61ef5d8391051b1e0f7944` | `92644cdeccc63d6def0e71d9fc5dc14e7918f0af` |
| `floorplan_prose/` | typed per-sheet placement notes and framing text of docs/FLOORPLAN.md and FLOORPLAN.svg | `9301deeda9d6c31cc06fc5f9230519033cd464c9` | `d6f1a6a4a9814aebb8fbf515e2494d38190bc922` |
| `drawing_titles/` | typed titles, headings and always-on rail names of docs/power_sequence.svg and docs/power_tree.svg | `d6f1a6a4a9814aebb8fbf515e2494d38190bc922` | `8409f27ff7892b01c336bc42ea0828f7a2d12957` |
| `subsystem_notes/` | READMEs and SPICE `.cir` files of the subsystem library and the board module sheets, the index READMEs, the SPICE identity test | `63c8ebf32d5f19e3dda76b4f0ada25ca66af032d` | `31f53061af1bd02339cbb345d89a98a83868f8cd` |

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

### i2c_chip_facts

- `native/src/bringup_facts.cpp:25-60` -> `removed/i2c_chip_facts/fragments/bringup_facts.cpp.L25-60.txt`
- `native/include/schgen/bringup_facts.hpp:19-24` -> `removed/i2c_chip_facts/fragments/bringup_facts.hpp.L19-24.txt`
- `native/include/schgen/bringup_facts.hpp:27-29` -> `removed/i2c_chip_facts/fragments/bringup_facts.hpp.L27-29.txt`
- `native/src/bringup_internal.hpp:73-111` -> `removed/i2c_chip_facts/fragments/bringup_internal.hpp.L73-111.txt`
- `native/src/manufacturing_exports_manifest.cpp:9-15` -> `removed/i2c_chip_facts/fragments/manufacturing_exports_manifest.cpp.L9-15.txt`
- `native/src/manufacturing_exports_manifest.cpp:32-43` -> `removed/i2c_chip_facts/fragments/manufacturing_exports_manifest.cpp.L32-43.txt`
- `native/src/manufacturing_exports_manifest.cpp:53-66` -> `removed/i2c_chip_facts/fragments/manufacturing_exports_manifest.cpp.L53-66.txt`

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

### drawing_titles

- `native/src/firmware_docs_power_sequence.cpp:44-44` -> `removed/drawing_titles/fragments/firmware_docs_power_sequence.cpp.L44-44.txt`
- `native/src/firmware_docs_power_sequence.cpp:74-78` -> `removed/drawing_titles/fragments/firmware_docs_power_sequence.cpp.L74-78.txt`
- `native/src/power_checks.cpp:286-286` -> `removed/drawing_titles/fragments/power_checks.cpp.L286-286.txt`

### subsystem_notes

- `carrier/subsystems/README.md` -> `removed/subsystem_notes/carrier/README.md`
- `carrier/subsystems/som_j1/README.md` -> `removed/subsystem_notes/carrier/som_j1/README.md`
- `carrier/subsystems/som_j1/som_j1.cir` -> `removed/subsystem_notes/carrier/som_j1/som_j1.cir`
- `carrier/subsystems/som_j2/README.md` -> `removed/subsystem_notes/carrier/som_j2/README.md`
- `carrier/subsystems/som_j2/som_j2.cir` -> `removed/subsystem_notes/carrier/som_j2/som_j2.cir`
- `carrier/subsystems/som_j3/README.md` -> `removed/subsystem_notes/carrier/som_j3/README.md`
- `carrier/subsystems/som_j3/som_j3.cir` -> `removed/subsystem_notes/carrier/som_j3/som_j3.cir`
- `devkit_mini/subsystems/debug_boot/README.md` -> `removed/subsystem_notes/devkit_mini/debug_boot/README.md`
- `devkit_mini/subsystems/debug_boot/debug_boot.cir` -> `removed/subsystem_notes/devkit_mini/debug_boot/debug_boot.cir`
- `devkit_mini/subsystems/som_j1/README.md` -> `removed/subsystem_notes/devkit_mini/som_j1/README.md`
- `devkit_mini/subsystems/som_j1/som_j1.cir` -> `removed/subsystem_notes/devkit_mini/som_j1/som_j1.cir`
- `devkit_mini/subsystems/som_j2/README.md` -> `removed/subsystem_notes/devkit_mini/som_j2/README.md`
- `devkit_mini/subsystems/som_j2/som_j2.cir` -> `removed/subsystem_notes/devkit_mini/som_j2/som_j2.cir`
- `devkit_mini/subsystems/som_j3/README.md` -> `removed/subsystem_notes/devkit_mini/som_j3/README.md`
- `devkit_mini/subsystems/som_j3/som_j3.cir` -> `removed/subsystem_notes/devkit_mini/som_j3/som_j3.cir`
- `native/tests/carrier_spice_identity_contracts.cpp` -> `removed/subsystem_notes/tests/carrier_spice_identity_contracts.cpp`
- `subsystems/README.md` -> `removed/subsystem_notes/library/README.md`
- `subsystems/board_aux/README.md` -> `removed/subsystem_notes/library/board_aux/README.md`
- `subsystems/board_aux/board_aux.cir` -> `removed/subsystem_notes/library/board_aux/board_aux.cir`
- `subsystems/board_qwiic/README.md` -> `removed/subsystem_notes/library/board_qwiic/README.md`
- `subsystems/board_qwiic/board_qwiic.cir` -> `removed/subsystem_notes/library/board_qwiic/board_qwiic.cir`
- `subsystems/board_services/README.md` -> `removed/subsystem_notes/library/board_services/README.md`
- `subsystems/board_services/board_services.cir` -> `removed/subsystem_notes/library/board_services/board_services.cir`
- `subsystems/bringup_en/README.md` -> `removed/subsystem_notes/library/bringup_en/README.md`
- `subsystems/bringup_en/bringup_en.cir` -> `removed/subsystem_notes/library/bringup_en/bringup_en.cir`
- `subsystems/bringup_en_modules/README.md` -> `removed/subsystem_notes/library/bringup_en_modules/README.md`
- `subsystems/bringup_en_modules/bringup_en_modules.cir` -> `removed/subsystem_notes/library/bringup_en_modules/bringup_en_modules.cir`
- `subsystems/bringup_modules/README.md` -> `removed/subsystem_notes/library/bringup_modules/README.md`
- `subsystems/bringup_modules/bringup_modules.cir` -> `removed/subsystem_notes/library/bringup_modules/bringup_modules.cir`
- `subsystems/bringup_rails/README.md` -> `removed/subsystem_notes/library/bringup_rails/README.md`
- `subsystems/bringup_rails/bringup_rails.cir` -> `removed/subsystem_notes/library/bringup_rails/bringup_rails.cir`
- `subsystems/camera/README.md` -> `removed/subsystem_notes/library/camera/README.md`
- `subsystems/camera/camera.cir` -> `removed/subsystem_notes/library/camera/camera.cir`
- `subsystems/debug_boot/README.md` -> `removed/subsystem_notes/library/debug_boot/README.md`
- `subsystems/debug_boot/debug_boot.cir` -> `removed/subsystem_notes/library/debug_boot/debug_boot.cir`
- `subsystems/ethernet/README.md` -> `removed/subsystem_notes/library/ethernet/README.md`
- `subsystems/ethernet/ethernet.cir` -> `removed/subsystem_notes/library/ethernet/ethernet.cir`
- `subsystems/fmc/README.md` -> `removed/subsystem_notes/library/fmc/README.md`
- `subsystems/fmc/fmc.cir` -> `removed/subsystem_notes/library/fmc/fmc.cir`
- `subsystems/hdmi_rx/README.md` -> `removed/subsystem_notes/library/hdmi_rx/README.md`
- `subsystems/hdmi_rx/hdmi_rx.cir` -> `removed/subsystem_notes/library/hdmi_rx/hdmi_rx.cir`
- `subsystems/hdmi_rx_term/README.md` -> `removed/subsystem_notes/library/hdmi_rx_term/README.md`
- `subsystems/hdmi_rx_term/hdmi_rx_term.cir` -> `removed/subsystem_notes/library/hdmi_rx_term/hdmi_rx_term.cir`
- `subsystems/hdmi_tx/README.md` -> `removed/subsystem_notes/library/hdmi_tx/README.md`
- `subsystems/hdmi_tx/hdmi_tx.cir` -> `removed/subsystem_notes/library/hdmi_tx/hdmi_tx.cir`
- `subsystems/lcd/README.md` -> `removed/subsystem_notes/library/lcd/README.md`
- `subsystems/lcd/lcd.cir` -> `removed/subsystem_notes/library/lcd/lcd.cir`
- `subsystems/mechanical/README.md` -> `removed/subsystem_notes/library/mechanical/README.md`
- `subsystems/mechanical/mechanical.cir` -> `removed/subsystem_notes/library/mechanical/mechanical.cir`
- `subsystems/microsd/README.md` -> `removed/subsystem_notes/library/microsd/README.md`
- `subsystems/microsd/microsd.cir` -> `removed/subsystem_notes/library/microsd/microsd.cir`
- `subsystems/motor_pwm/README.md` -> `removed/subsystem_notes/library/motor_pwm/README.md`
- `subsystems/motor_pwm/motor_pwm.cir` -> `removed/subsystem_notes/library/motor_pwm/motor_pwm.cir`
- `subsystems/motor_sense/README.md` -> `removed/subsystem_notes/library/motor_sense/README.md`
- `subsystems/motor_sense/motor_sense.cir` -> `removed/subsystem_notes/library/motor_sense/motor_sense.cir`
- `subsystems/pd_input/README.md` -> `removed/subsystem_notes/library/pd_input/README.md`
- `subsystems/pd_input/pd_input.cir` -> `removed/subsystem_notes/library/pd_input/pd_input.cir`
- `subsystems/pmod/README.md` -> `removed/subsystem_notes/library/pmod/README.md`
- `subsystems/pmod/pmod.cir` -> `removed/subsystem_notes/library/pmod/pmod.cir`
- `subsystems/pmod_expansion/README.md` -> `removed/subsystem_notes/library/pmod_expansion/README.md`
- `subsystems/pmod_expansion/pmod_expansion.cir` -> `removed/subsystem_notes/library/pmod_expansion/pmod_expansion.cir`
- `subsystems/power/README.md` -> `removed/subsystem_notes/library/power/README.md`
- `subsystems/power/power.cir` -> `removed/subsystem_notes/library/power/power.cir`
- `subsystems/power_mon/README.md` -> `removed/subsystem_notes/library/power_mon/README.md`
- `subsystems/power_mon/power_mon.cir` -> `removed/subsystem_notes/library/power_mon/power_mon.cir`
- `subsystems/power_som/README.md` -> `removed/subsystem_notes/library/power_som/README.md`
- `subsystems/power_som/power_som.cir` -> `removed/subsystem_notes/library/power_som/power_som.cir`
- `subsystems/rj45_connector/README.md` -> `removed/subsystem_notes/library/rj45_connector/README.md`
- `subsystems/rj45_connector/rj45_connector.cir` -> `removed/subsystem_notes/library/rj45_connector/rj45_connector.cir`
- `subsystems/som_decoupling/README.md` -> `removed/subsystem_notes/library/som_decoupling/README.md`
- `subsystems/som_decoupling/som_decoupling.cir` -> `removed/subsystem_notes/library/som_decoupling/som_decoupling.cir`
- `subsystems/uart_bridge/README.md` -> `removed/subsystem_notes/library/uart_bridge/README.md`
- `subsystems/uart_bridge/uart_bridge.cir` -> `removed/subsystem_notes/library/uart_bridge/uart_bridge.cir`
- `subsystems/usb_jtag/README.md` -> `removed/subsystem_notes/library/usb_jtag/README.md`
- `subsystems/usb_jtag/usb_jtag.cir` -> `removed/subsystem_notes/library/usb_jtag/usb_jtag.cir`
- `subsystems/usb_jtag_connector/README.md` -> `removed/subsystem_notes/library/usb_jtag_connector/README.md`
- `subsystems/usb_jtag_connector/usb_jtag_connector.cir` -> `removed/subsystem_notes/library/usb_jtag_connector/usb_jtag_connector.cir`
- `subsystems/usb_pd/README.md` -> `removed/subsystem_notes/library/usb_pd/README.md`
- `subsystems/usb_pd/usb_pd.cir` -> `removed/subsystem_notes/library/usb_pd/usb_pd.cir`
- `subsystems/usb_uart_connector/README.md` -> `removed/subsystem_notes/library/usb_uart_connector/README.md`
- `subsystems/usb_uart_connector/usb_uart_connector.cir` -> `removed/subsystem_notes/library/usb_uart_connector/usb_uart_connector.cir`
- `subsystems/usbc_otg/README.md` -> `removed/subsystem_notes/library/usbc_otg/README.md`
- `subsystems/usbc_otg/usbc_otg.cir` -> `removed/subsystem_notes/library/usbc_otg/usbc_otg.cir`
- `subsystems/user_io/README.md` -> `removed/subsystem_notes/library/user_io/README.md`
- `subsystems/user_io/user_io.cir` -> `removed/subsystem_notes/library/user_io/user_io.cir`
- `native/src/authoring_gates.cpp:76-76` -> `removed/subsystem_notes/fragments/authoring_gates.cpp.L76-76.txt`
- `native/src/authoring_gates.cpp:79-82` -> `removed/subsystem_notes/fragments/authoring_gates.cpp.L79-82.txt`
- `native/src/authoring_gates.cpp:85-87` -> `removed/subsystem_notes/fragments/authoring_gates.cpp.L85-87.txt`
- `native/src/authoring_gates.cpp:214-214` -> `removed/subsystem_notes/fragments/authoring_gates.cpp.L214-214.txt`
- `native/src/authoring_gates.cpp:242-243` -> `removed/subsystem_notes/fragments/authoring_gates.cpp.L242-243.txt`
- `native/include/schgen/authoring_gates.hpp:71-76` -> `removed/subsystem_notes/fragments/authoring_gates.hpp.L71-76.txt`
- `native/include/schgen/authoring_gates.hpp:80-80` -> `removed/subsystem_notes/fragments/authoring_gates.hpp.L80-80.txt`
- `native/src/board_check.cpp:3-3` -> `removed/subsystem_notes/fragments/board_check.cpp.L3-3.txt`
- `native/src/board_check.cpp:216-217` -> `removed/subsystem_notes/fragments/board_check.cpp.L216-217.txt`
- `native/src/board_pipeline_authoring.cpp:60-60` -> `removed/subsystem_notes/fragments/board_pipeline_authoring.cpp.L60-60.txt`
- `native/src/board_pipeline_authoring.cpp:71-75` -> `removed/subsystem_notes/fragments/board_pipeline_authoring.cpp.L71-75.txt`
- `native/include/schgen/board_pipeline.hpp:70-70` -> `removed/subsystem_notes/fragments/board_pipeline.hpp.L70-70.txt`
- `native/src/board_pipeline.cpp:157-157` -> `removed/subsystem_notes/fragments/board_pipeline.cpp.L157-157.txt`
- `native/tests/board_pipeline_contracts.cpp:401-401` -> `removed/subsystem_notes/fragments/board_pipeline_contracts.cpp.L401-401.txt`
- `native/src/subsystem_scaffold_templates.cpp:110-110` -> `removed/subsystem_notes/fragments/subsystem_scaffold_templates.cpp.L110-110.txt`
- `native/src/subsystem_scaffold_templates.cpp:114-127` -> `removed/subsystem_notes/fragments/subsystem_scaffold_templates.cpp.L114-127.txt`
- `native/src/subsystem_scaffold_templates.cpp:128-201` -> `removed/subsystem_notes/fragments/subsystem_scaffold_templates.cpp.L128-201.txt`
- `native/src/subsystem_scaffold_templates.cpp:214-215` -> `removed/subsystem_notes/fragments/subsystem_scaffold_templates.cpp.L214-215.txt`
- `native/src/subsystem_scaffold_publish.cpp:143-143` -> `removed/subsystem_notes/fragments/subsystem_scaffold_publish.cpp.L143-143.txt`
- `native/CMakeLists.txt:402-406` -> `removed/subsystem_notes/fragments/CMakeLists.txt.L402-406.txt`
- `native/cmake/SubsystemPackages.cmake:11-11` -> `removed/subsystem_notes/fragments/SubsystemPackages.cmake.L11-11.txt`
- `native/tests/authoring_gates_contracts.cpp:58-59` -> `removed/subsystem_notes/fragments/authoring_gates_contracts.cpp.L58-59.txt`
- `native/tests/authoring_gates_contracts.cpp:62-63` -> `removed/subsystem_notes/fragments/authoring_gates_contracts.cpp.L62-63.txt`
- `native/tests/authoring_gates_contracts.cpp:263-264` -> `removed/subsystem_notes/fragments/authoring_gates_contracts.cpp.L263-264.txt`
- `native/tests/authoring_gates_contracts.cpp:266-267` -> `removed/subsystem_notes/fragments/authoring_gates_contracts.cpp.L266-267.txt`
- `native/tests/authoring_gates_contracts.cpp:316-316` -> `removed/subsystem_notes/fragments/authoring_gates_contracts.cpp.L316-316.txt`
- `native/tests/authoring_gates_contracts.cpp:318-318` -> `removed/subsystem_notes/fragments/authoring_gates_contracts.cpp.L318-318.txt`
- `native/tests/authoring_gates_contracts.cpp:325-325` -> `removed/subsystem_notes/fragments/authoring_gates_contracts.cpp.L325-325.txt`
- `native/tests/geometry_cli_contracts.cpp:156-156` -> `removed/subsystem_notes/fragments/geometry_cli_contracts.cpp.L156-156.txt`
- `native/tests/geometry_cli_contracts.cpp:226-227` -> `removed/subsystem_notes/fragments/geometry_cli_contracts.cpp.L226-227.txt`
- `native/tests/geometry_cli_contracts.cpp:229-235` -> `removed/subsystem_notes/fragments/geometry_cli_contracts.cpp.L229-235.txt`
- `native/tests/geometry_cli_contracts.cpp:249-251` -> `removed/subsystem_notes/fragments/geometry_cli_contracts.cpp.L249-251.txt`
- `native/tests/subsystem_scaffold_contracts.cpp:60-60` -> `removed/subsystem_notes/fragments/subsystem_scaffold_contracts.cpp.L60-60.txt`
- `native/tests/subsystem_scaffold_contracts.cpp:62-62` -> `removed/subsystem_notes/fragments/subsystem_scaffold_contracts.cpp.L62-62.txt`
- `native/tests/subsystem_scaffold_contracts.cpp:70-77` -> `removed/subsystem_notes/fragments/subsystem_scaffold_contracts.cpp.L70-77.txt`
- `native/tests/subsystem_scaffold_contracts.cpp:108-108` -> `removed/subsystem_notes/fragments/subsystem_scaffold_contracts.cpp.L108-108.txt`
- `native/tests/subsystem_scaffold_contracts.cpp:266-266` -> `removed/subsystem_notes/fragments/subsystem_scaffold_contracts.cpp.L266-266.txt`
- `native/tests/subsystem_scaffold_contracts.cpp:269-269` -> `removed/subsystem_notes/fragments/subsystem_scaffold_contracts.cpp.L269-269.txt`
- `native/tests/subsystem_scaffold_build_contracts.cpp:155-155` -> `removed/subsystem_notes/fragments/subsystem_scaffold_build_contracts.cpp.L155-155.txt`
- `native/tests/subsystem_scaffold_build_contracts.cpp:157-157` -> `removed/subsystem_notes/fragments/subsystem_scaffold_build_contracts.cpp.L157-157.txt`
- `native/tests/subsystem_scaffold_INTEGRATION.md:5-5` -> `removed/subsystem_notes/fragments/subsystem_scaffold_INTEGRATION.md.L5-5.txt`
- `native/tests/subsystem_scaffold_INTEGRATION.md:101-101` -> `removed/subsystem_notes/fragments/subsystem_scaffold_INTEGRATION.md.L101-101.txt`
- `docs/OVERVIEW.md:33-33` -> `removed/subsystem_notes/fragments/OVERVIEW.md.L33-33.txt`
- `docs/OVERVIEW.md:36-37` -> `removed/subsystem_notes/fragments/OVERVIEW.md.L36-37.txt`
- `docs/OVERVIEW.md:42-42` -> `removed/subsystem_notes/fragments/OVERVIEW.md.L42-42.txt`
- `docs/OVERVIEW.md:112-112` -> `removed/subsystem_notes/fragments/OVERVIEW.md.L112-112.txt`
- `docs/OVERVIEW.md:132-132` -> `removed/subsystem_notes/fragments/OVERVIEW.md.L132-132.txt`
- `docs/OVERVIEW.md:134-134` -> `removed/subsystem_notes/fragments/OVERVIEW.md.L134-134.txt`
- `docs/SUBSYSTEM_FORMAT.md:306-306` -> `removed/subsystem_notes/fragments/SUBSYSTEM_FORMAT.md.L306-306.txt`
- `docs/WORKING_GUIDELINES.txt:308-311` -> `removed/subsystem_notes/fragments/WORKING_GUIDELINES.txt.L308-311.txt`
- `native/README.md:95-96` -> `removed/subsystem_notes/fragments/README.md.L95-96.txt`
- `native/tests/data/subsystem_scaffold/python_reference.json` key `widget_cir` -> `removed/subsystem_notes/tests/data/subsystem_scaffold/python_reference_widget_cir.json`
- `subsystems/board_control/README.md` -> `removed/subsystem_notes/library/board_control/README.md`
- `subsystems/board_control/board_control.cir` -> `removed/subsystem_notes/library/board_control/board_control.cir`
- `subsystems/can_bus/README.md` -> `removed/subsystem_notes/library/can_bus/README.md`
- `subsystems/can_bus/can_bus.cir` -> `removed/subsystem_notes/library/can_bus/can_bus.cir`
- `subsystems/esc_io/README.md` -> `removed/subsystem_notes/library/esc_io/README.md`
- `subsystems/esc_io/esc_io.cir` -> `removed/subsystem_notes/library/esc_io/esc_io.cir`
- `subsystems/esc_power/README.md` -> `removed/subsystem_notes/library/esc_power/README.md`
- `subsystems/esc_power/esc_power.cir` -> `removed/subsystem_notes/library/esc_power/esc_power.cir`
- `subsystems/pl_expansion/README.md` -> `removed/subsystem_notes/library/pl_expansion/README.md`
- `subsystems/pl_expansion/pl_expansion.cir` -> `removed/subsystem_notes/library/pl_expansion/pl_expansion.cir`
- `subsystems/vbat_supply/README.md` -> `removed/subsystem_notes/library/vbat_supply/README.md`
- `subsystems/vbat_supply/vbat_supply.cir` -> `removed/subsystem_notes/library/vbat_supply/vbat_supply.cir`
- `motor_carrier/subsystems/som_j1/README.md` -> `removed/subsystem_notes/motor_carrier/som_j1/README.md`
- `motor_carrier/subsystems/som_j1/som_j1.cir` -> `removed/subsystem_notes/motor_carrier/som_j1/som_j1.cir`
- `motor_carrier/subsystems/som_j2/README.md` -> `removed/subsystem_notes/motor_carrier/som_j2/README.md`
- `motor_carrier/subsystems/som_j2/som_j2.cir` -> `removed/subsystem_notes/motor_carrier/som_j2/som_j2.cir`
- `motor_carrier/subsystems/som_j3/README.md` -> `removed/subsystem_notes/motor_carrier/som_j3/README.md`
- `motor_carrier/subsystems/som_j3/som_j3.cir` -> `removed/subsystem_notes/motor_carrier/som_j3/som_j3.cir`
