# Downstream I2C retirement join — frozen handoff

Only new `native/tests/downstream_i2c_contracts.cpp` and this handoff are added for
this follow-up. No production source, shared CMake/build, existing test, original
fixture or Python file was changed. The earlier SI test remains frozen at its
accepted handoff hash.

## Parent registration

```cmake
add_executable(schgen_downstream_i2c_contracts tests/downstream_i2c_contracts.cpp)
target_link_libraries(schgen_downstream_i2c_contracts PRIVATE schgen_core)
target_compile_options(schgen_downstream_i2c_contracts PRIVATE
    -Wall -Wextra -Wpedantic -Werror -ffp-contract=off)
add_test(NAME native_downstream_i2c_contracts
    COMMAND schgen_downstream_i2c_contracts "${CMAKE_CURRENT_SOURCE_DIR}/..")
set_tests_properties(native_downstream_i2c_contracts PROPERTIES TIMEOUT 120)
```

Executable takes **one argument: repository root**. No output directory, Python,
shell, KiCad process or network is needed. It performs no file writes. The native
part catalog and existing `native/tests/data/firmware_docs/carrier/inputs.json`
are required; missing inputs fail rather than skip.

## What closes the original gap

Fresh `author_project_subsystem` calls construct real carrier `board_services`
and `usb_pd` using actual catalog records. No circuit snapshot is loaded. The
same live services circuit is passed through:

- the firmware address helper **and actual generated firmware header**;
- the actual rendered manufacturing manifest, reparsed as its published JSON;
- the test-plan device helper **and actual rendered Markdown**.

The existing independently captured firmware INPUT fixture supplies only the
STM32 pin map required to render the header. It supplies no services circuit,
expected addresses or expected output. Literal 0x51 EEPROM / 0x52 RTC,
`AUX_I2C`, EEPROM part identity and AUX conditional assertions come from the
original `test_downstream_i2c.py` policy. There is no production algorithm copy.

Coverage includes:

- All three consumers agree on the fresh EEPROM address; published hexadecimal
  and integer manifest fields agree, and firmware macros remain 7-bit addresses.
- Both services have correct device/ref/sheet identity, AUX bus and Stage-6
  conditionality; the published test plan says they must not ACK with AUX off.
- Independently specified A1/A0 strap truth table 0x50/0x51/0x52/0x53 reaches the
  actual consumers. The 0x52 case preserves both colliding manifest/scan rows and
  **the actual firmware renderer rejects the collision**.
- Floating A0/A1, absent EEPROM and wrong EEPROM identity reject in firmware
  helper/header and manifest. The test-plan API retains its documented optional
  invalid-section omission: it emits no fabricated AUX rows. This is a transport
  behavior assertion, not a claim that the invalid board passed a gate.
- Fresh USB-PD is always-on / STM32_I2C2 while services are AUX; removing or
  renaming the services sheet removes AUX rows/macros without erasing USB-PD.
- Independent output mutations kill stale addresses, lost devices/ownership,
  wrong manifest bus, false AUX flags, mispublished stage and lost off-state
  boundary. Copied-input isolation and repeatability are checked.

## Proof

**635 assertions / 27 rejected mutations PASS**, strict C++17 and ASan/UBSan.
Sanitizer closure is all **66 repository translation units** in the actual link
map: 59 instrumented objects from the accepted private authoring snapshot plus
seven freshly instrumented consumer/dependency files. No uninstrumented core
archive is used in the sanitizer executable. LibXml2 and OS libraries are system
binaries; no macOS LeakSanitizer claim.

Both executables also PASS, with identical counts, against a private 246-file
input tree containing **no `.py`, `.pyc` or `.so`**, with every canonical
`circuit.json` invalid. The only extra test input is the immutable STM32 fixture.
Current repository headers also pass strict `-fsyntax-only` compilation.

Proof directory: `/private/tmp/native-downstream-i2c.oIlFfS` (`i2c-strict`,
`i2c-asan`, `strict.map`, `build-asan.sh`). Python-free poisoned input:
`/private/tmp/native-i2c-assets.RYIn6x`.

Strict linking used the same accepted private core snapshot as SI, SHA-256
`e26211c85bc7434300e96d5f0be26db2fa71998f32aaf2ffdf26eda9e8832786`.
This is isolated proof, not a claim to have rebuilt the concurrently edited
shared core; parent performs the coherent registration/integration build.

Flags: `-std=c++17 -O1 -g -Wall -Wextra -Wpedantic -Werror -ffp-contract=off`;
sanitizer adds `-fsanitize=address,undefined -fno-omit-frame-pointer`.
Runtime: `ASAN_OPTIONS=abort_on_error=1 UBSAN_OPTIONS=halt_on_error=1`.

Frozen hashes:

```text
de01c4816328945f9c0a517665e4d150994b4fda247261b21d32019fca153f3c  native/tests/downstream_i2c_contracts.cpp
4c19aeb6018f7c097d105bd55cc6eedc6200e335ad1f571efcf5ff4c94152e98  schgen/tests/test_downstream_i2c.py
e91abd3f5a21a4b4ab6c1ed8fd213732075e9910b8dad704c1f62162778fee83  native/tests/data/firmware_docs/carrier/inputs.json
```

## Retirement receipt

This closes the `bounded-join-gap` recorded in the immutable 393-file inventory.
After this target is integrated and accepted, `test_downstream_i2c.py` no longer
needs to be held. Similarly SI's held Python module can retire after its new
target is registered/accepted. Until then the approved 389-remove/4-preserve
plan remains unchanged; this worker did not delete files or grant itself broader
deletion authority. Parent owns the remaining build-twice/render-baseline
acceptance and all actual deletion/staging/commits.
