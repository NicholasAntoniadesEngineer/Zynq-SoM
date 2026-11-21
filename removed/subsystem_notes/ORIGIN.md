# subsystem_notes origin

## 1. What it was and who used it

The hand-written note files of the subsystem library and of the boards' module-connector sheets: one `README.md` (purpose, interface, parts, design rationale) and one `<name>.cir` (a SPICE sub-circuit of the passive parts between the external nets, the ICs left unmodelled) per subsystem, plus the two index READMEs `subsystems/README.md` and `carrier/subsystems/README.md`. Readers were people reviewing a subsystem; the pipeline only checked that the two files existed (`check_subsystem_package`, `check_carrier_package`), copied them into the published board output (`publish_board_pipeline_inputs`), listed them as rows of `schgen board-check`, and one test (`carrier_spice_identity_contracts.cpp`) compared the `.cir` files of `board_aux` and `hdmi_rx_term` with the live circuits. The electrical check gate does not read them; it writes its own decks (`native/src/spice_process.cpp:50`).

## 2. Files moved (85 whole files, 51 fragments, 1 extracted fixture key)

Whole files: 69 under `library/` (34 `README.md`, 34 `.cir`, `subsystems/README.md` as `library/README.md`), 7 under `carrier/` (`carrier/subsystems/README.md` as `carrier/README.md`, and README and `.cir` of `som_j1`, `som_j2`, `som_j3`), 8 under `devkit_mini/` (README and `.cir` of `debug_boot`, `som_j1`, `som_j2`, `som_j3`), and 1 test under `tests/`. That is 84 note files, the study's count. The published copies the pipeline wrote into board output folders were never tracked, so there are no `outputs/` copies. The live-tree frozen gate-report fixtures `native/tests/data/authoring/gate_*.json` were not edited: they describe the retired Python package mode, which is unchanged.

| original path | archive path | git hash-object |
|---|---|---|
| `carrier/subsystems/README.md` | `removed/subsystem_notes/carrier/README.md` | `9c7d45dfe49e08d731e13ec2993220a3f2ab5c4a` |
| `carrier/subsystems/som_j1/README.md` | `removed/subsystem_notes/carrier/som_j1/README.md` | `efbb3ed78f34b3b44ecf20440e00d026f0bf7f3b` |
| `carrier/subsystems/som_j1/som_j1.cir` | `removed/subsystem_notes/carrier/som_j1/som_j1.cir` | `43f3e4e08098b0ff486ceb8a236a8223674965f6` |
| `carrier/subsystems/som_j2/README.md` | `removed/subsystem_notes/carrier/som_j2/README.md` | `7d3d026a3c0f0020d89708f8893c4ccbe7f43bef` |
| `carrier/subsystems/som_j2/som_j2.cir` | `removed/subsystem_notes/carrier/som_j2/som_j2.cir` | `9e3b8e47cf3b9a3000e826eed63695869d6121ac` |
| `carrier/subsystems/som_j3/README.md` | `removed/subsystem_notes/carrier/som_j3/README.md` | `9f18ae63e1f95a8053009701474a2b5459901fb4` |
| `carrier/subsystems/som_j3/som_j3.cir` | `removed/subsystem_notes/carrier/som_j3/som_j3.cir` | `c0e377efc3468637c7a3e02bd93549067c3eb76a` |
| `devkit_mini/subsystems/debug_boot/README.md` | `removed/subsystem_notes/devkit_mini/debug_boot/README.md` | `9c1fdd8b615f63d246c69d5c6a77a7544c5db21b` |
| `devkit_mini/subsystems/debug_boot/debug_boot.cir` | `removed/subsystem_notes/devkit_mini/debug_boot/debug_boot.cir` | `51b1cb0ac4bfba44d53b28e2e9485101c13a4cb4` |
| `devkit_mini/subsystems/som_j1/README.md` | `removed/subsystem_notes/devkit_mini/som_j1/README.md` | `7e4fa525c97a7a3cea071ff3bfd5a84d6fa53c8a` |
| `devkit_mini/subsystems/som_j1/som_j1.cir` | `removed/subsystem_notes/devkit_mini/som_j1/som_j1.cir` | `8eb36626d359e0cf66203438da29683438d5e3fd` |
| `devkit_mini/subsystems/som_j2/README.md` | `removed/subsystem_notes/devkit_mini/som_j2/README.md` | `ecd67d5c558f010ed5ec174ecfeea33d2a72802f` |
| `devkit_mini/subsystems/som_j2/som_j2.cir` | `removed/subsystem_notes/devkit_mini/som_j2/som_j2.cir` | `aaeeb898e8d3bbd0cd03e1b2ab492d1cf47fe372` |
| `devkit_mini/subsystems/som_j3/README.md` | `removed/subsystem_notes/devkit_mini/som_j3/README.md` | `5748de1e9799e95236a0ba3d2bb61bfd36e5248e` |
| `devkit_mini/subsystems/som_j3/som_j3.cir` | `removed/subsystem_notes/devkit_mini/som_j3/som_j3.cir` | `2e6b6708f3eb1b0d36733e317b5678a40d65c611` |
| `native/tests/carrier_spice_identity_contracts.cpp` | `removed/subsystem_notes/tests/carrier_spice_identity_contracts.cpp` | `36861b9f1a9533aab265eea329ba97c448c80fdb` |
| `subsystems/README.md` | `removed/subsystem_notes/library/README.md` | `e25e5aa1c95831fc9da06cb56b0814b072957a04` |
| `subsystems/board_aux/README.md` | `removed/subsystem_notes/library/board_aux/README.md` | `1dc219f0c545c770ca108491048934c386866ee8` |
| `subsystems/board_aux/board_aux.cir` | `removed/subsystem_notes/library/board_aux/board_aux.cir` | `4732856f1cc8f3c75ea73ddb5f32d3ffd168a5c6` |
| `subsystems/board_qwiic/README.md` | `removed/subsystem_notes/library/board_qwiic/README.md` | `575af6d6d184be1ee9d69913d346389910720ce1` |
| `subsystems/board_qwiic/board_qwiic.cir` | `removed/subsystem_notes/library/board_qwiic/board_qwiic.cir` | `0d5d46d2fbfbfd552a398abeaf069bbd5b58fd4a` |
| `subsystems/board_services/README.md` | `removed/subsystem_notes/library/board_services/README.md` | `19e74f19bc9a0195af343f88b76f25e463137bc4` |
| `subsystems/board_services/board_services.cir` | `removed/subsystem_notes/library/board_services/board_services.cir` | `3746dd071ecbb537f5602507c950c375504bda3f` |
| `subsystems/bringup_en/README.md` | `removed/subsystem_notes/library/bringup_en/README.md` | `72e1bda0659a0237cc922b000cae1f5e12b4f868` |
| `subsystems/bringup_en/bringup_en.cir` | `removed/subsystem_notes/library/bringup_en/bringup_en.cir` | `0fdce854f84e75df4307a202dbc1c38bc3d70bd3` |
| `subsystems/bringup_en_modules/README.md` | `removed/subsystem_notes/library/bringup_en_modules/README.md` | `e1e36a7814c5662713eacbe4e5325bde0f139efa` |
| `subsystems/bringup_en_modules/bringup_en_modules.cir` | `removed/subsystem_notes/library/bringup_en_modules/bringup_en_modules.cir` | `c0bcf4b532afe0b4c1c16469566c5868c499b23f` |
| `subsystems/bringup_modules/README.md` | `removed/subsystem_notes/library/bringup_modules/README.md` | `1c0cdc2b8d94be2256c517c2ba4a1c696ac8e43e` |
| `subsystems/bringup_modules/bringup_modules.cir` | `removed/subsystem_notes/library/bringup_modules/bringup_modules.cir` | `9cac96e906f42bb6c4a01b8e0af78a42e86f0cf4` |
| `subsystems/bringup_rails/README.md` | `removed/subsystem_notes/library/bringup_rails/README.md` | `196a8fde7599ba4a5c4bc8b92e9bd2bb3fc4b74f` |
| `subsystems/bringup_rails/bringup_rails.cir` | `removed/subsystem_notes/library/bringup_rails/bringup_rails.cir` | `d6e165580ada9621a9f99e74c153c01368a7eb52` |
| `subsystems/camera/README.md` | `removed/subsystem_notes/library/camera/README.md` | `0bf180eda4f5cf088c544f0201d9db79fe3c3583` |
| `subsystems/camera/camera.cir` | `removed/subsystem_notes/library/camera/camera.cir` | `51a58646e770d6eabca2e252bddacec91c82ae1c` |
| `subsystems/debug_boot/README.md` | `removed/subsystem_notes/library/debug_boot/README.md` | `43295886dfb967d5f4987449e17ed44314001ffb` |
| `subsystems/debug_boot/debug_boot.cir` | `removed/subsystem_notes/library/debug_boot/debug_boot.cir` | `5872364d5026c755c09810133f5077c1d0340b43` |
| `subsystems/ethernet/README.md` | `removed/subsystem_notes/library/ethernet/README.md` | `b9f9fc009272572240cdef6136c2e2f1020e348c` |
| `subsystems/ethernet/ethernet.cir` | `removed/subsystem_notes/library/ethernet/ethernet.cir` | `9b983318e0ab7fd6d05528bb5834f71bb0c5112e` |
| `subsystems/fmc/README.md` | `removed/subsystem_notes/library/fmc/README.md` | `0b64e6f194114f6e4bbcb65df8ef0f3c5c390f05` |
| `subsystems/fmc/fmc.cir` | `removed/subsystem_notes/library/fmc/fmc.cir` | `c35abb00990fe378666352c6b51716ad16f15b89` |
| `subsystems/hdmi_rx/README.md` | `removed/subsystem_notes/library/hdmi_rx/README.md` | `8fac6b7679babb23ad84ab0f5d804ff13c4b141a` |
| `subsystems/hdmi_rx/hdmi_rx.cir` | `removed/subsystem_notes/library/hdmi_rx/hdmi_rx.cir` | `3168a37df7a6b00d9442181a5dbbe56207678dd9` |
| `subsystems/hdmi_rx_term/README.md` | `removed/subsystem_notes/library/hdmi_rx_term/README.md` | `535616cfcebb7270fd7b40e2509412dfdaf78af2` |
| `subsystems/hdmi_rx_term/hdmi_rx_term.cir` | `removed/subsystem_notes/library/hdmi_rx_term/hdmi_rx_term.cir` | `96dd062c96f4f9e09b2f4c633bdb483a0ce0f61f` |
| `subsystems/hdmi_tx/README.md` | `removed/subsystem_notes/library/hdmi_tx/README.md` | `a574824f504162be5150ecd0d24ba7e113d99301` |
| `subsystems/hdmi_tx/hdmi_tx.cir` | `removed/subsystem_notes/library/hdmi_tx/hdmi_tx.cir` | `dc835d3585851f1bddfb3fae9274d2983cfeed37` |
| `subsystems/lcd/README.md` | `removed/subsystem_notes/library/lcd/README.md` | `001cf201e8700f972c0ddcb91717abfcb406cab7` |
| `subsystems/lcd/lcd.cir` | `removed/subsystem_notes/library/lcd/lcd.cir` | `78179bd26acf1c74743e1e507447e4f28dfc508a` |
| `subsystems/mechanical/README.md` | `removed/subsystem_notes/library/mechanical/README.md` | `7644d389cba4920132915257f0911976c0d9103c` |
| `subsystems/mechanical/mechanical.cir` | `removed/subsystem_notes/library/mechanical/mechanical.cir` | `a38cd2d85976727c7174f914d1e97cbca6249496` |
| `subsystems/microsd/README.md` | `removed/subsystem_notes/library/microsd/README.md` | `579942ef35f78bd5fe79a8305aa6fa0b43060a02` |
| `subsystems/microsd/microsd.cir` | `removed/subsystem_notes/library/microsd/microsd.cir` | `d71059c0761699ccfdb3849ee72e1154ca034184` |
| `subsystems/motor_pwm/README.md` | `removed/subsystem_notes/library/motor_pwm/README.md` | `1d3bd41719ebd08019dc4cf9968edd91f75360e6` |
| `subsystems/motor_pwm/motor_pwm.cir` | `removed/subsystem_notes/library/motor_pwm/motor_pwm.cir` | `edc87b78fd0e1bb2ed26de9a879750b5f03a7157` |
| `subsystems/motor_sense/README.md` | `removed/subsystem_notes/library/motor_sense/README.md` | `289452f54d7c139992b57a28bb90f57de7660e7d` |
| `subsystems/motor_sense/motor_sense.cir` | `removed/subsystem_notes/library/motor_sense/motor_sense.cir` | `72b93a5446a158c2af12771b7be75d858b6bdac8` |
| `subsystems/pd_input/README.md` | `removed/subsystem_notes/library/pd_input/README.md` | `fbc0f04987ea8f8f425bb8d57a4428bb8e4ef176` |
| `subsystems/pd_input/pd_input.cir` | `removed/subsystem_notes/library/pd_input/pd_input.cir` | `4456896076ffe1dc2d5f96e0c6709cf219123df0` |
| `subsystems/pmod/README.md` | `removed/subsystem_notes/library/pmod/README.md` | `e4a1499469bc1cb6fa416150f1910d920fc87add` |
| `subsystems/pmod/pmod.cir` | `removed/subsystem_notes/library/pmod/pmod.cir` | `1b495d478fb176d286afd705b66a23a8fe69b9a2` |
| `subsystems/pmod_expansion/README.md` | `removed/subsystem_notes/library/pmod_expansion/README.md` | `c8ae77c7ce6ba775d9ba9440845700ac0045aa80` |
| `subsystems/pmod_expansion/pmod_expansion.cir` | `removed/subsystem_notes/library/pmod_expansion/pmod_expansion.cir` | `e1cae8c3b0711299b48585163647bcb428fd9e6e` |
| `subsystems/power/README.md` | `removed/subsystem_notes/library/power/README.md` | `3466b1d706284f273f4c3bb6362784c9ba382a14` |
| `subsystems/power/power.cir` | `removed/subsystem_notes/library/power/power.cir` | `264ac747975d9d33e35aa2b292f2461ec4e1a496` |
| `subsystems/power_mon/README.md` | `removed/subsystem_notes/library/power_mon/README.md` | `444b00ea89514eeb895761faa1f4368bea772656` |
| `subsystems/power_mon/power_mon.cir` | `removed/subsystem_notes/library/power_mon/power_mon.cir` | `5b9291f382eb63844f3347f6e4b647ff80e66c5e` |
| `subsystems/power_som/README.md` | `removed/subsystem_notes/library/power_som/README.md` | `941a5b13b0c73cd8161baf06ff3895fbdee20c15` |
| `subsystems/power_som/power_som.cir` | `removed/subsystem_notes/library/power_som/power_som.cir` | `f68fd9a4e9751e7ca1fcf34375265ec79066f9bd` |
| `subsystems/rj45_connector/README.md` | `removed/subsystem_notes/library/rj45_connector/README.md` | `3d3c0edaea7e7da78e250b07aafd8f71aa13ea2b` |
| `subsystems/rj45_connector/rj45_connector.cir` | `removed/subsystem_notes/library/rj45_connector/rj45_connector.cir` | `cb3d12704e91f64c0ba8776047fc1ccba6f3e660` |
| `subsystems/som_decoupling/README.md` | `removed/subsystem_notes/library/som_decoupling/README.md` | `74724a1c0c1f906b2ec9fc823af21e439c7ef382` |
| `subsystems/som_decoupling/som_decoupling.cir` | `removed/subsystem_notes/library/som_decoupling/som_decoupling.cir` | `15ad12e2354c2fb8292edb7da04af7933349d4ab` |
| `subsystems/uart_bridge/README.md` | `removed/subsystem_notes/library/uart_bridge/README.md` | `d8021846bb9a231a2c063c8d7638a89696cd521c` |
| `subsystems/uart_bridge/uart_bridge.cir` | `removed/subsystem_notes/library/uart_bridge/uart_bridge.cir` | `77587154084ec08b61530567b1a1de13195c1e11` |
| `subsystems/usb_jtag/README.md` | `removed/subsystem_notes/library/usb_jtag/README.md` | `a3980059b108f0588387a614cb17b199bad1e5df` |
| `subsystems/usb_jtag/usb_jtag.cir` | `removed/subsystem_notes/library/usb_jtag/usb_jtag.cir` | `508368439e29b95f2b5d9d600b6e9e8dd8021d5d` |
| `subsystems/usb_jtag_connector/README.md` | `removed/subsystem_notes/library/usb_jtag_connector/README.md` | `8b3f1461de8c2c4a25f2b2a7b6d5fb524fe4245d` |
| `subsystems/usb_jtag_connector/usb_jtag_connector.cir` | `removed/subsystem_notes/library/usb_jtag_connector/usb_jtag_connector.cir` | `37e860ab29212b626148534c442e4f206fa2cd4d` |
| `subsystems/usb_pd/README.md` | `removed/subsystem_notes/library/usb_pd/README.md` | `10c835f2e82a63c4f13aed5e2db21a24b934911b` |
| `subsystems/usb_pd/usb_pd.cir` | `removed/subsystem_notes/library/usb_pd/usb_pd.cir` | `facabde2018a0c5a757ae6a2c3b1f75826566616` |
| `subsystems/usb_uart_connector/README.md` | `removed/subsystem_notes/library/usb_uart_connector/README.md` | `5ca50d9aee185a98145eb299308647774a5e51dc` |
| `subsystems/usb_uart_connector/usb_uart_connector.cir` | `removed/subsystem_notes/library/usb_uart_connector/usb_uart_connector.cir` | `393d195a6e34641a21d233e1c705a7d52501d71e` |
| `subsystems/usbc_otg/README.md` | `removed/subsystem_notes/library/usbc_otg/README.md` | `edd390fc5771fca05ce161a37d18a0f8b0cacf8b` |
| `subsystems/usbc_otg/usbc_otg.cir` | `removed/subsystem_notes/library/usbc_otg/usbc_otg.cir` | `cc05c5fd9cbbe6c8a1fef8e1353559f7fbb5fa39` |
| `subsystems/user_io/README.md` | `removed/subsystem_notes/library/user_io/README.md` | `9dbe010818779eac904c32699f5c05e9a03b177c` |
| `subsystems/user_io/user_io.cir` | `removed/subsystem_notes/library/user_io/user_io.cir` | `7d038c6ba77f8cae27ad5c93c16cab01c1b64ecb` |
| `native/src/authoring_gates.cpp:76-76` | `removed/subsystem_notes/fragments/authoring_gates.cpp.L76-76.txt` | `2b9b61b637af9d29a4da7fa6fac3178dc2dce409` |
| `native/src/authoring_gates.cpp:79-82` | `removed/subsystem_notes/fragments/authoring_gates.cpp.L79-82.txt` | `c85faf53a1e96258c34d5f954ab45e5cb6fe406b` |
| `native/src/authoring_gates.cpp:85-87` | `removed/subsystem_notes/fragments/authoring_gates.cpp.L85-87.txt` | `6ef857877d2d0578b4c5b8333f4d4cb0ba392f6f` |
| `native/src/authoring_gates.cpp:214-214` | `removed/subsystem_notes/fragments/authoring_gates.cpp.L214-214.txt` | `0bc6a3f4812ff8ee38735d30a6eb91274b631b80` |
| `native/src/authoring_gates.cpp:242-243` | `removed/subsystem_notes/fragments/authoring_gates.cpp.L242-243.txt` | `c2be3e54ef89cbee0ab2875f7f70d73a87fc13f9` |
| `native/include/schgen/authoring_gates.hpp:71-76` | `removed/subsystem_notes/fragments/authoring_gates.hpp.L71-76.txt` | `d7da6cdd93958c82d3e168322c5620d08fc1a6b9` |
| `native/include/schgen/authoring_gates.hpp:80-80` | `removed/subsystem_notes/fragments/authoring_gates.hpp.L80-80.txt` | `41609face1b26bda4b7134e3a47c0721680853ba` |
| `native/src/board_check.cpp:3-3` | `removed/subsystem_notes/fragments/board_check.cpp.L3-3.txt` | `2d36a953c8cc8126c6e01ad31ac16eeb62bfbaa9` |
| `native/src/board_check.cpp:216-217` | `removed/subsystem_notes/fragments/board_check.cpp.L216-217.txt` | `debf81edd01ef99e67e6564846a2ed057f530a1e` |
| `native/src/board_pipeline_authoring.cpp:60-60` | `removed/subsystem_notes/fragments/board_pipeline_authoring.cpp.L60-60.txt` | `a162be67b489e1c3b5852c437217e9feaad163ba` |
| `native/src/board_pipeline_authoring.cpp:71-75` | `removed/subsystem_notes/fragments/board_pipeline_authoring.cpp.L71-75.txt` | `153c09cfb3f1053132ab1392b416215ae1879029` |
| `native/include/schgen/board_pipeline.hpp:70-70` | `removed/subsystem_notes/fragments/board_pipeline.hpp.L70-70.txt` | `aa570b65ea9629d69ab5efa900c14422c52d79c0` |
| `native/src/board_pipeline.cpp:157-157` | `removed/subsystem_notes/fragments/board_pipeline.cpp.L157-157.txt` | `50553d231019bfc98c46a6f39b71b8319540bb7f` |
| `native/tests/board_pipeline_contracts.cpp:401-401` | `removed/subsystem_notes/fragments/board_pipeline_contracts.cpp.L401-401.txt` | `fbaa237569ab71dbfa1f8ae39661e035874d3e17` |
| `native/src/subsystem_scaffold_templates.cpp:110-110` | `removed/subsystem_notes/fragments/subsystem_scaffold_templates.cpp.L110-110.txt` | `0348eb5234207a9308e9c1b6be37c7ff291e9608` |
| `native/src/subsystem_scaffold_templates.cpp:114-127` | `removed/subsystem_notes/fragments/subsystem_scaffold_templates.cpp.L114-127.txt` | `111eb60d829be0159f44b57861ac90b09cccf3eb` |
| `native/src/subsystem_scaffold_templates.cpp:128-201` | `removed/subsystem_notes/fragments/subsystem_scaffold_templates.cpp.L128-201.txt` | `e397c70d18ba568b5d331971cb11b374286eebb0` |
| `native/src/subsystem_scaffold_templates.cpp:214-215` | `removed/subsystem_notes/fragments/subsystem_scaffold_templates.cpp.L214-215.txt` | `fb179bf11e95797ba2fde4cbefbf9faa2af822d2` |
| `native/src/subsystem_scaffold_publish.cpp:143-143` | `removed/subsystem_notes/fragments/subsystem_scaffold_publish.cpp.L143-143.txt` | `b84bdbf5556d11db7d9bc7cad8d814ef513a8ad1` |
| `native/CMakeLists.txt:402-406` | `removed/subsystem_notes/fragments/CMakeLists.txt.L402-406.txt` | `4e719c4b51b5b2e035b6a820a4c25b178ffb7a53` |
| `native/cmake/SubsystemPackages.cmake:11-11` | `removed/subsystem_notes/fragments/SubsystemPackages.cmake.L11-11.txt` | `d9d1c10a267ae5d55d7e25143a834d86618eab66` |
| `native/tests/authoring_gates_contracts.cpp:58-59` | `removed/subsystem_notes/fragments/authoring_gates_contracts.cpp.L58-59.txt` | `e6c3265b5daec705f22925a618db183fd093a1db` |
| `native/tests/authoring_gates_contracts.cpp:62-63` | `removed/subsystem_notes/fragments/authoring_gates_contracts.cpp.L62-63.txt` | `32904d8f340ce8f4ea6a66960f58de320a4d2d05` |
| `native/tests/authoring_gates_contracts.cpp:263-264` | `removed/subsystem_notes/fragments/authoring_gates_contracts.cpp.L263-264.txt` | `9ebac6f3f3f764b668a43ea68a02eb94ac17530b` |
| `native/tests/authoring_gates_contracts.cpp:266-267` | `removed/subsystem_notes/fragments/authoring_gates_contracts.cpp.L266-267.txt` | `b5db571911199b4e0ca9e8702854897e528ffb7c` |
| `native/tests/authoring_gates_contracts.cpp:316-316` | `removed/subsystem_notes/fragments/authoring_gates_contracts.cpp.L316-316.txt` | `e21b4b33c790d86a3fc4c13df97f3349162856df` |
| `native/tests/authoring_gates_contracts.cpp:318-318` | `removed/subsystem_notes/fragments/authoring_gates_contracts.cpp.L318-318.txt` | `0376d58e5912c237bb65417e1cddb9957fe6db12` |
| `native/tests/authoring_gates_contracts.cpp:325-325` | `removed/subsystem_notes/fragments/authoring_gates_contracts.cpp.L325-325.txt` | `8f6fe9220d00c3c27cf240550f808f29057a3b38` |
| `native/tests/geometry_cli_contracts.cpp:156-156` | `removed/subsystem_notes/fragments/geometry_cli_contracts.cpp.L156-156.txt` | `4246c9e33f9674b431151b20d648e5f0bb68a4b1` |
| `native/tests/geometry_cli_contracts.cpp:226-227` | `removed/subsystem_notes/fragments/geometry_cli_contracts.cpp.L226-227.txt` | `4b27d34cdd3e6837e20814350deee090f09157a2` |
| `native/tests/geometry_cli_contracts.cpp:229-235` | `removed/subsystem_notes/fragments/geometry_cli_contracts.cpp.L229-235.txt` | `51da3bf8e7f6c82b770a38de335b7dcd86f01765` |
| `native/tests/geometry_cli_contracts.cpp:249-251` | `removed/subsystem_notes/fragments/geometry_cli_contracts.cpp.L249-251.txt` | `928702f91fe1a0159585f943c994e8f10128d4fd` |
| `native/tests/subsystem_scaffold_contracts.cpp:60-60` | `removed/subsystem_notes/fragments/subsystem_scaffold_contracts.cpp.L60-60.txt` | `8551c141390890e1cb83d7b9bcbd200c2058dfcd` |
| `native/tests/subsystem_scaffold_contracts.cpp:62-62` | `removed/subsystem_notes/fragments/subsystem_scaffold_contracts.cpp.L62-62.txt` | `6910516a93f73b817247430f335bd54c66573e36` |
| `native/tests/subsystem_scaffold_contracts.cpp:70-77` | `removed/subsystem_notes/fragments/subsystem_scaffold_contracts.cpp.L70-77.txt` | `28ce765fe01082e2d96bca5b1f8083dc6cbcf99d` |
| `native/tests/subsystem_scaffold_contracts.cpp:108-108` | `removed/subsystem_notes/fragments/subsystem_scaffold_contracts.cpp.L108-108.txt` | `5c43d30aad047897a654a4fd9a0f9472adf03c79` |
| `native/tests/subsystem_scaffold_contracts.cpp:266-266` | `removed/subsystem_notes/fragments/subsystem_scaffold_contracts.cpp.L266-266.txt` | `84558e35367787a5de96c9395fa4cb1596c17924` |
| `native/tests/subsystem_scaffold_contracts.cpp:269-269` | `removed/subsystem_notes/fragments/subsystem_scaffold_contracts.cpp.L269-269.txt` | `2017a5a560011a434e10abfb1cb6888bb9dae981` |
| `native/tests/subsystem_scaffold_build_contracts.cpp:155-155` | `removed/subsystem_notes/fragments/subsystem_scaffold_build_contracts.cpp.L155-155.txt` | `9c9a03e419c1193706f7b31cfbcb9af1ef7b4520` |
| `native/tests/subsystem_scaffold_build_contracts.cpp:157-157` | `removed/subsystem_notes/fragments/subsystem_scaffold_build_contracts.cpp.L157-157.txt` | `688b7faf5abab4c9d2505e6b5b4dec697e84fcd9` |
| `native/tests/subsystem_scaffold_INTEGRATION.md:5-5` | `removed/subsystem_notes/fragments/subsystem_scaffold_INTEGRATION.md.L5-5.txt` | `d9e5aa2c0dbb839ffe145bcf22a50f764f0659ac` |
| `native/tests/subsystem_scaffold_INTEGRATION.md:101-101` | `removed/subsystem_notes/fragments/subsystem_scaffold_INTEGRATION.md.L101-101.txt` | `d9d1c10a267ae5d55d7e25143a834d86618eab66` |
| `docs/OVERVIEW.md:33-33` | `removed/subsystem_notes/fragments/OVERVIEW.md.L33-33.txt` | `98c237296313a54a702754f0fa69b865d592525b` |
| `docs/OVERVIEW.md:36-37` | `removed/subsystem_notes/fragments/OVERVIEW.md.L36-37.txt` | `e34c12df39e22f58fda675775702b927b8f32a42` |
| `docs/OVERVIEW.md:42-42` | `removed/subsystem_notes/fragments/OVERVIEW.md.L42-42.txt` | `5c7f8068799f3f539e117403d427992a125b736a` |
| `docs/OVERVIEW.md:112-112` | `removed/subsystem_notes/fragments/OVERVIEW.md.L112-112.txt` | `0c192aa6077786d29e5306fc95de0fe4a1a2baa8` |
| `docs/OVERVIEW.md:132-132` | `removed/subsystem_notes/fragments/OVERVIEW.md.L132-132.txt` | `dbaa30ea2916228212586ddee0f2c25f5b1594ba` |
| `docs/OVERVIEW.md:134-134` | `removed/subsystem_notes/fragments/OVERVIEW.md.L134-134.txt` | `9afddaad43e3b6989b460a4ef35071e777873734` |
| `docs/SUBSYSTEM_FORMAT.md:306-306` | `removed/subsystem_notes/fragments/SUBSYSTEM_FORMAT.md.L306-306.txt` | `343969326c83a14bc62b1412be878fee51f6c841` |
| `docs/WORKING_GUIDELINES.txt:308-311` | `removed/subsystem_notes/fragments/WORKING_GUIDELINES.txt.L308-311.txt` | `88ffbe418382632e8bf5331208eb1b9eb4e42ead` |
| `native/README.md:95-96` | `removed/subsystem_notes/fragments/README.md.L95-96.txt` | `fc8282b5d459612166c3cdb30aee03f255fdc1da` |
| `native/tests/data/subsystem_scaffold/python_reference.json` key `widget_cir` | `removed/subsystem_notes/tests/data/subsystem_scaffold/python_reference_widget_cir.json` | `3949fede580cdcadfcafd966b83da0c40bdb7fd0` |

## 3. Source commit

`63c8ebf32d5f19e3dda76b4f0ada25ca66af032d` (the last commit in which these files were at their original paths; the parent of the move commit). Line numbers of fragments are from that commit. The move commit's own hash is in `removed/INDEX.md`.

## 4. What produced it

- Nobody: hand-written. The consumers were the gates `subsystem_structure` and `carrier_structure` (required list, `native/src/board_pipeline.cpp:83`), whose package checks demanded the two files (`native/src/authoring_gates.cpp:75-88`, fragments `authoring_gates.cpp.L76-76`, `.L79-82`, `.L85-87`), the input publication step (`board_pipeline.cpp:157`, `publish_board_pipeline_inputs`, copy at `board_pipeline_authoring.cpp:71-75`), the `board-check` rows (`native/src/board_check.cpp:216-217`), the registration check of the CMake function `schgen_register_subsystem_package` (`native/cmake/SubsystemPackages.cmake:11`), the scaffold command `subsystem-new` (`native/src/subsystem_scaffold_templates.cpp:110,114-201,214-215`) and the test `native_carrier_spice_identity_contracts` (`native/CMakeLists.txt:402-406`).
- Gate report text that named the files (`authoring_gates.cpp:214,242-243`).

## 5. What it read

Nothing: the files are prose and netlists typed by hand. The identity test read `subsystems/board_aux/board_aux.cir` and `subsystems/hdmi_rx_term/hdmi_rx_term.cir` (`removed/subsystem_notes/tests/carrier_spice_identity_contracts.cpp`, `:111` and the default path of `board_aux`), typed the rail map `+3V3 -> V3V3`, `+3V3_AUX -> V3V3_AUX`, `+3V3_SC -> V3V3_SC` and the passive counts 11 and 10, and compared them with the circuits `board_aux` and `hdmi_rx_term` authored for the carrier.

## 6. Why it was removed

The owner: "lets clear out handwritten things completely and we can deal with them later. The tool must be as programmatic as possible and extensive as what that allows". Specific reasons: the files were typed, not derived; several are stale (`subsystems/power_mon/README.md` ends with a `pytest` command on a file that no longer exists; `subsystems/README.md` describes Python adapters in a tree where a test forbids any `.py` file); the `.cir` files hold only passives with the ICs unmodelled by their own statement and nothing consumed them beyond the one identity test, which only proves the hand-written copy equals the circuit.

## 7. What could be generated

A reference card per subsystem rendered from `subsystem.json` alone (study section 2.12 and N12: title, interface, ports with bus and expected peer, parts, served pins with roles and reach, draws, waivers, I2C addresses). It cannot go stale and needs no new fact. It is the programmatic replacement for the README; it is not built in this task. The design rationale prose of the READMEs has no data source and stays here. A generated `.cir` would carry no information beyond the circuit and nothing would consume it, so none is proposed.

## 8. Bringing it back

1. `git mv` every file in the table from its archive path to its original path (`library/<name>/X` to `subsystems/<name>/X`, `library/README.md` to `subsystems/README.md`, `carrier/README.md` to `carrier/subsystems/README.md`, `carrier/<name>/X` to `carrier/subsystems/<name>/X`, `devkit_mini/<name>/X` to `devkit_mini/subsystems/<name>/X`), and `tests/carrier_spice_identity_contracts.cpp` to `native/tests/`.
2. Restore each fragment at its recorded line range (the fragment file holds the exact removed lines): the requirement in `authoring_gates.cpp` and `authoring_gates.hpp` (including `local_package_authored_files`), the copy in `board_pipeline_authoring.cpp` (this also needs the `ProjectPaths` parameter of `publish_board_pipeline_inputs` back, fragments for `board_pipeline.hpp:70`, `board_pipeline.cpp:157`, `board_pipeline_contracts.cpp:401`), the rows in `board_check.cpp` and its include, the asset list in `SubsystemPackages.cmake:11`, the test registration `CMakeLists.txt:402-406`, the scaffold templates and the `"spice"` metadata key, and the package README sentence in `subsystem_scaffold_publish.cpp:143`.
3. Restore the test edits recorded in the fragments of `authoring_gates_contracts.cpp`, `geometry_cli_contracts.cpp`, `subsystem_scaffold_contracts.cpp` (also the `widget_cir` key of `native/tests/data/subsystem_scaffold/python_reference.json` from `tests/data/subsystem_scaffold/python_reference_widget_cir.json`, and the 7-file counts), `subsystem_scaffold_build_contracts.cpp`, and the doc lines in the fragments of `docs/OVERVIEW.md`, `docs/SUBSYSTEM_FORMAT.md`, `docs/WORKING_GUIDELINES.txt`, `native/README.md`.
4. What changed in this task and would have to be undone: the native library requirement is now one regular file, `subsystem.json` (replacing the two note files), so that a registered library package whose folder is absent is still reported missing; the adapter check requires the same file in the generic library; local packages require `circuit.json` and `layout.json` only. The retired Python package mode of `authoring_gates.cpp` (`legacy_python`, inert fixtures from the Python tool) still lists README and `.cir` and was not touched.
5. The committed generated report files of the boards (`carrier/reports/gates.txt`, `carrier_structure.txt`, `subsystem_structure.txt`, `board_verdicts.json`, and the same for `devkit_mini`) still show the old contract lines until the next publication.
