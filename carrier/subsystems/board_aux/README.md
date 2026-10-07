# board_aux — manually-gated +3V3_AUX rail + PCA9306 I2C isolator

board_aux is the infrastructure half of the carrier's board-services block: it
makes a manually-enabled, default-OFF `+3V3_AUX` rail and bridges the always-on
STM32 management I2C onto that gated segment. The peripherals it powers live on
`board_services`; the QWIIC connector that re-exports the rail and bus lives on
`board_qwiic`. It is a carrier-LOCAL subsystem — real carrier net names are wired
directly, with no abstract-interface `META` bind contract.

## Interface

Carrier nets driven and ports published:

- **Input rail:** `+3V3` (always-on) into the load switch.
- **Gated rail:** `+3V3_AUX` — the switched output, default-OFF until SW1 is
  flipped. Published with `testpoint("+3V3_AUX")` and a 6 mA load declared to the
  power tree (status LED + the two 4k7 AUX-bus pull-ups).
- **Management bus ports (always-on side):** `STM32_I2C2_SCL` / `STM32_I2C2_SDA`,
  typed i2c (scl/sda, 400 kHz, bus `STM32_I2C2`), expecting bringup_rails /
  usb_pd / power_mon.
- **Isolated bus ports (gated side):** `AUX_I2C_SCL` / `AUX_I2C_SDA`, typed i2c
  (scl/sda, 400 kHz, bus `AUX_I2C`), consumed by board_services / board_qwiic.
  Both have testpoints.

A project consumes board_aux by wiring `board_services` / `board_qwiic` to the
`AUX_I2C_*` ports and feeding the always-on `STM32_I2C2_*` ports from the
management bus; the `+3V3` / `+3V3_SC` / `GND` rails are shared carrier nets.

## Design

**Manual power gate (U1, SY6280AAC).** A current-limited load switch gates `+3V3`
→ `+3V3_AUX`, matching the bring-up module switches. ILIM is set by R1 = 13k on
ISET: ILIM = 6800/13k ≈ 523 mA, sized above the gated load. The enable is LOCAL
and defaults OFF: DIP switch SW1 (DSHP04, position 1) closes `+3V3` onto
`EN_AUX`, and R2 = 100k holds `EN_AUX` low until a human flips the switch, so the
rail comes up de-energized at power-on. SW1 positions 2–4 are spare (commons
bused to `+3V3`, even pins NC). Keeping the gate self-contained on this sheet
makes the whole block a single add/revert that touches none of the dense
rail-control sheets, and keeps each sheet below the placer's congestion threshold.

**Input reservoir and output bypass.** C1 is 10uF, 0805, LCSC C15850
(CL21A106KAYNNNE, nominal 25 V X5R), between U1.IN and GND. The
[Silergy SY6280/A datasheet](https://www.silergy.com/download/downloadFile?ftype=note&id=4369&type=product),
Rev. 1.0E, page 7, Supply Filter Capacitor, strongly recommends a 10uF ceramic
input capacitor to reduce hot-plug supply droop and warns about short-circuit
input ringing without adequate input capacitance. This is a manufacturer
recommendation, not a stated absolute minimum or evidence that the former
100nF part failed. Nominal capacitance does not guarantee effective capacitance
under DC bias. C1 replaces the former 100nF/0603/C14663; its owner remains
U1.IN, with unchanged connectivity and no new placement-distance threshold.

Output C2 (100nF/0603/C14663) and C3 (10uF/0805/C15850) are unchanged.
The ISET resistor, enable circuit and declared steady-state loads are unchanged;
the larger input reservoir can change charging demand. Regenerate and revalidate
the board and downstream BOM after this hardware change: the larger footprint
has no compaction or clearance waiver, and no board-area improvement is claimed.
PCA9306 topology is unchanged by this correction; its startup/bias/EN review
remains open, and the tests below do not certify transient isolation.

**Status LED.** A red LED on the gated output through R3 = 330R lights when the
AUX rail is enabled, making the manual gate state visible at a glance.

**I2C isolator (U2, PCA9306DCUR).** The board_services peripherals run off the
gated rail but their bus is the always-on `STM32_I2C2`. Tying gated SDA/SCL
straight to that pulled-up bus would back-power the unpowered chips through their
ESD diodes (LAW 0). The PCA9306 bidirectional level/isolation switch bridges the
two domains. The reference asymmetry IS the isolation: VREF1 references `+3V3_SC`
(always-on side — its pull-ups already live on bringup_rails), VREF2 references
the gated `+3V3_AUX` with its own 4k7 pull-ups (R5/R6, required on both sides of
the PCA9306). U2.EN is pulled to `+3V3_AUX` through R4 = 100k, so the switch
OPENS whenever the AUX rail is down — the peripherals are cleanly isolated while
off. 100n bypass on each VREF.

## Parts

| ref | value | lib/part | LCSC |
|-----|-------|----------|------|
| U1  | SY6280AAC | parts: `SY6280AAC` | — |
| U2  | PCA9306DCUR | parts: `PCA9306DCUR` | — |
| SW1 | DSHP04TSGER | parts: `DSHP04TSGER` | — |
| D   | red | `Device:LED` | C2286 |
| C2, C4, C5 | 100n | `Device:C` (0603) | C14663 |
| C1, C3 | 10u | `Device:C` (0805) | C15850 |
| R (ISET) | 13k | `Device:R` | C22797 |
| R (EN pulldown) | 100k | `Device:R` | C25803 |
| R (LED) | 330R | `Device:R` | C23138 |
| R (PCA9306 EN pull-up) | 100k | `Device:R` | C25803 |
| R (×2 AUX bus pull-ups) | 4k7 | `Device:R` | C23162 |

Refdes for the `Device:*` parts are auto-assigned; the netlist topology is the
authority. Three testpoints sit on `+3V3_AUX`, `AUX_I2C_SCL`, `AUX_I2C_SDA`.

## Build & test

The native C++ contracts cover independent frozen pin/reference/NC identities,
live-authoring/derived-circuit parity, C1-C5 values/packages/BOM codes, electrical
rules, power declarations, part ratings, pin/footprint coverage, compiled
ownership requirements, and passive SPICE identities:

- `native/tests/board_aux_c1_contracts.cpp` (REPO CATALOG REPO arguments).
- `native/tests/carrier_surface_requirements_contracts.cpp`.
- `native/tests/carrier_spice_identity_contracts.cpp`.

The C1 contract rejects the former C1 value/package/code and unrelated pin swaps,
reference replacement, missing NC declarations and changes to C2-C5 values.
These are focused structural checks, not active-device transient simulations or
full-board acceptance. The C1 contract is registered in CMake/CTest; changed
boards still require regeneration and validation without footprint waivers.
