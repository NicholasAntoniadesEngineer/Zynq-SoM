# i2c_chip_facts origin

## 1. What it was and who used it

Three chip-specific fact functions computed the I2C address of three parts from the netlist: `bringup_expander` (TCA9535, `0x20` plus A0..A2 against the VCC net, and its port list), `ina3221_monitors` (INA3221, `0x40` plus the index of the net under A0 among GND, VS, SDA, SCL, and its channel nets), and `bringup_id_eeprom_addr` (24AA025E48, `0x50` plus pins 5 and 4 on a power net). Two FUSB302B and RV-3028 addresses were typed constants next to them. Their readers were two pipeline consumers in `native/src/manufacturing_exports_manifest.cpp` at the source commit: the manifest's `i2c_map` section (`:32-43`, called from `manufacturing_manifest`, `:93` before the cut) and `check_i2c_address_collisions` (`:53-66`), called by the manifest step (`native/src/board_pipeline_documents.cpp:22`). The reader of the map is the system-controller firmware engineer.

## 2. Files moved (0 whole files, 7 fragments)

Fragments are text cut out of files that stay; each is the exact removed lines, named `<original file name>.L<first>-<last>.txt`. The three `manufacturing_exports_manifest.cpp` fragments were replaced in place: `L32-43` is the whole old `i2c` function, whose new body reads the inventory; `L9-15` and `L53-66` were removed outright.

| original | archive path | git hash-object |
|---|---|---|
| `native/src/bringup_facts.cpp:25-60` | `removed/i2c_chip_facts/fragments/bringup_facts.cpp.L25-60.txt` | `3d23cdeb89b3dc347180d11c26f6bed81deee47e` |
| `native/include/schgen/bringup_facts.hpp:19-24` | `removed/i2c_chip_facts/fragments/bringup_facts.hpp.L19-24.txt` | `56ada0973adddb1ae0fb188c2760b5d9f8f682c4` |
| `native/include/schgen/bringup_facts.hpp:27-29` | `removed/i2c_chip_facts/fragments/bringup_facts.hpp.L27-29.txt` | `cdfec3319659472aaf7a06a15e0e74591d2d34af` |
| `native/src/bringup_internal.hpp:73-111` | `removed/i2c_chip_facts/fragments/bringup_internal.hpp.L73-111.txt` | `07344a2b9947c83518b3d8d0d5ac40a6835c4ffe` |
| `native/src/manufacturing_exports_manifest.cpp:9-15` | `removed/i2c_chip_facts/fragments/manufacturing_exports_manifest.cpp.L9-15.txt` | `ce0576387adcf0554de9ccb455eb301151b1c58d` |
| `native/src/manufacturing_exports_manifest.cpp:32-43` | `removed/i2c_chip_facts/fragments/manufacturing_exports_manifest.cpp.L32-43.txt` | `e7e2ae027f9591d2b0820e7e1a3a02ba99dac41f` |
| `native/src/manufacturing_exports_manifest.cpp:53-66` | `removed/i2c_chip_facts/fragments/manufacturing_exports_manifest.cpp.L53-66.txt` | `d9ad2f60f16a26ffcf4fa0fd92c9d3eefbf58629` |

`bringup_internal.hpp:73-111` is the `Index` helper (part, pin-net and pin-name lookup over one sheet); only the three functions used it. The neighbouring `quoted` and `repr` helpers stay: `native/src/manufacturing_assembly_internal.hpp:49` still uses `repr`.

## 3. Source commit

`48d29d0194a10565be61ef5d8391051b1e0f7944` (the parent of the move commit). Line numbers are from that commit. The move commit's own hash is in `removed/INDEX.md`.

## 4. What produced it

- No pipeline step of its own. The manifest step `manifest` (`native/src/board_pipeline_documents.cpp:20-29`) called `check_i2c_address_collisions(c.circuits)` and then `run_manufacturing_manifest`, whose `manufacturing_manifest` built `i2c_map` with the old `i2c` function.
- Command `schgen manifest` (`native/src/project_cli.cpp`, the `manifest` branch) reached the same `i2c` function.
- Build files: `native/CMakeLists.txt:40` (`src/bringup_facts.cpp`) and `:62` (`src/manufacturing_exports_manifest.cpp`); both files stay.

## 5. What it read

- Sheets by name: `bringup_rails`, `power_mon`, `usb_pd`, `board_services` (`manufacturing_exports_manifest.cpp:9-12`); the map tested `board_services` by name (`:39`); the 24AA025E48 error text named `board_services` (`bringup_facts.cpp:53`).
- Parts recognised by value or symbol substring: `TCA9535` (`bringup_facts.cpp:26`, `manufacturing_exports_manifest.cpp:36`), `INA3221` (`bringup_facts.cpp:40`), `24AA025E48` (`bringup_facts.cpp:52`), `FUSB302` (`manufacturing_exports_manifest.cpp:13`).
- Pins by name or number: TCA9535 `VCC`, `A0`..`A2`, ports `P[01][0-7]` (`bringup_facts.cpp:28-35`); INA3221 `A0`, `VS`, `SDA`, `SCL`, `IN+n`, `IN-n` (`:41-46`); 24AA025E48 pins `5` and `4` (`:56`).
- Nets: `GND` by name (`bringup_facts.cpp:32,42`); bus names `STM32_I2C2` and `AUX_I2C` typed per device (`manufacturing_exports_manifest.cpp:36-39`).
- Typed numbers: bases `0x20`, `0x40`, `0x50` (`bringup_facts.cpp:28,45,54`), fixed `0x22` and `0x52` (`manufacturing_exports_manifest.cpp:14-15`).

## 6. Why it was removed

The owner: "lets clear out handwritten things completely and we can deal with them later. The tool must be as programmatic as possible and extensive as what that allows". Specific reason: every address rule, every bus name and every sheet the check looked at was typed in C++. The collision check therefore never saw a device on a sheet it did not name (the third current monitor at 0x42 on `motor_sense`, and the HDMI-RX EDID EEPROM), and the 24AA025E48 rule read any non-power strap net as a 0.

## 7. What replaced it (generated)

Task F-B (`programmatic_outputs_study.md` section 6): the address rules are part data (`parts/part_facts.json` `i2c_devices` and `i2c_bridges`, schema `schgen.part_facts/4`), one inventory derives every device instance, its bus and address space from the netlist (`native/src/i2c_inventory.cpp`), the manifest's `i2c_map` and `check_i2c_address_collisions` read that inventory, and the gate `i2c_bus_map` publishes `reports/i2c_bus_map.txt`. The expander port list and the monitor channel list the old functions also returned were read only by the archived firmware documents (`removed/firmware_contract/`); nothing reads them now.

## 8. Bringing it back

1. Paste `bringup_facts.cpp.L25-60.txt` back after line 24 of `native/src/bringup_facts.cpp`, `bringup_facts.hpp.L19-24.txt` after line 18 and `bringup_facts.hpp.L27-29.txt` after line 26 of `native/include/schgen/bringup_facts.hpp`, and `bringup_internal.hpp.L73-111.txt` after line 72 of `native/src/bringup_internal.hpp`.
2. Paste the three `manufacturing_exports_manifest.cpp` fragments back at their line ranges, replacing the new `i2c` function, and restore the declaration `void check_i2c_address_collisions(const std::vector<ProjectCircuit>&);` in `native/include/schgen/manufacturing_exports.hpp` after the `ManufacturingManifestInput` struct, removing it from `native/include/schgen/i2c_inventory.hpp`.
3. Restore the two allow-list rows in `native/tests/data/vocabulary_allowlist.json`: `"native/src/bringup_facts.cpp": {"part": 5, "subsystem": 1}` and `"native/src/manufacturing_exports_manifest.cpp": {"part": 7, "reference": 2, "subsystem": 4}`.
4. The tests that exercised them at the source commit are `native/tests/i2c_collision_contracts.cpp` and `native/tests/downstream_i2c_contracts.cpp`, both since ported to the inventory; `git show 48d29d01:<path>` gives the old versions. Since then the old functions would also miss the HDMI-RX EDID EEPROM, so the manifest would lose that row again.
