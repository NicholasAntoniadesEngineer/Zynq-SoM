# power — multi-rail regulator tree (buck → buck → LDO, power-good LEDs)

`power` is the Zynq-7000 SoM carrier's main regulator tree: a three-stage chain
that turns the regulator-tree input (`+VIN`, a post-shunt 20 V-class PD rail) into
the board's +5V, +3V3 and +1V8 rails, each with an enable port and a power-good
indicator. It is the carrier's largest subsystem and is written as a
project-agnostic, self-contained schgen package: it declares its interface as
abstract port/rail names and a consuming board binds them to real nets.

## Interface

`power.circuit(meta)` builds the netlist with abstract names. A consuming project
passes one standard `Meta` dict (`schgen.core.subsystem.Meta`); `meta=None` keeps
the abstract names so `test_power.py` runs offline. Keys read:

- `bind` — `{abstract_net: board_net}`, rebinds every externally-visible rail and
  port in place, order-preserving (binding to the names a hand sheet used yields a
  byte-identical sheet). Only POWER/GROUND/PORT nets are bindable; SIGNAL nets are
  private wiring and rebinding one is a hard error.
- `expects` — `{enable_port: deferral}`, attaches a linker deferral to an enable
  port (a project's rail-enable cells bind these on another sheet).
- `notes` — `{"draws_5v"|"draws_3v3"|"draws_1v8": prose}`, overrides the
  power-tree draw-note text.

### Rails (POWER / GROUND)

Each regulator exposes **two** external rails — a reg-side output node and the
board rail the loads see — so a project's series current-monitor can sit on a
shunt between them and measure consumer draw. The reg-side cluster (inductor node,
output bulk, FB sense, PG LED, BIAS tie) stays on `+VOUT_x_REG`; the loads sit on
`+VOUT_x`. A project with a monitor bridges `+VOUT_x_REG → +VOUT_x` through a
shunt; one without binds both abstract names to the same real rail. Which side a
consumer sits on is part of the contract: the +3V3 buck's input caps sit on
`+VOUT_5V` and the LDO's input cap on `+VOUT_3V3`, because each is a consumer of
the upstream rail and must be measured by that rail's shunt.

| abstract | class | meaning |
|----------|-------|---------|
| `+VIN`          | POWER  | regulator-tree input; drives the +5V buck VIN1/VIN2 + input bypass/bulk. Worst case 21 V (20 V PD +5%). |
| `+VOUT_5V_REG`  | POWER  | +5V buck reg-side output (inductor node, 3×22 µF bulk, FB sense, BIAS tie, PG LED). |
| `+VOUT_5V`      | POWER  | board +5V rail; feeds the +3V3 buck input. |
| `+VOUT_3V3_REG` | POWER  | +3V3 buck reg-side output (2×22 µF bulk, FB sense, PG LED). |
| `+VOUT_3V3`     | POWER  | board +3V3 rail; feeds the +1V8 LDO input and the +1V8 PG-LED anode. |
| `+VOUT_1V8_REG` | POWER  | +1V8 LDO reg-side output (1 µF output cap). |
| `+VOUT_1V8`     | POWER  | board +1V8 rail the loads see. |
| `GND`           | GROUND | ground; also the LM61460 heat path (PGND1/PGND2/AGND on the GND pour). |

### Ports (PORT)

| abstract | meaning |
|----------|---------|
| `EN_VOUT_5V`  | +5V buck enable (EN/SYNC, pin 7). |
| `EN_VOUT_3V3` | +3V3 buck enable. |
| `EN_VOUT_1V8` | +1V8 LDO enable. |

Two pins are explicit no-connects: `U1.5`/`U2.5` (PGOOD, the unused open-drain
status output — the rail-up LEDs are the indicators) and `U3.4` (the LDO NC pin).

### Internal SIGNAL nets (private, never bound)

`SW_5V0`, `BOOT_5V0`, `FB_5V0`, `CFF_5V0`, `BIAS_5V0`, `U1_VCC`, `RT_5V0`,
`PG_5V0` (+5V buck); `SW_3V3`, `BOOT_3V3`, `FB_3V3`, `CFF_3V3`, `BIAS_3V3`,
`U2_VCC`, `RT_3V3`, `PG_3V3` (+3V3 buck); `PG_1V8_G`/`PG_1V8_D`/`PG_1V8_K` (+1V8
PG-sense FET gate/drain/LED-cathode). These are the regulators' feedback/switching
wiring; `bind()` rejects them.

## Design

- **+5V buck = LM61460 (U1), 6 A synchronous.** Carries the heaviest converter
  load (2.95 A @ 5 V). The TI LM61460 (3–42 V, 6 A, peak-current-mode, VQFN-HR) is
  chosen for ~2× current margin and a Vin op-max (36 V) that covers the 21 V `+VIN`
  worst case. FB divider 40.2k/10k at Vref 1.0 V → 5.02 V. fSW = 600 kHz set by
  RT = 22k; 10 µH inductor (well above the ~1.67 µH stability minimum, so no
  subharmonic oscillation); peak inductor current 3.27 A < the 4 A Isat.
- **+3V3 buck = LM61460 (U2), 6 A synchronous.** Carries the second-heaviest load
  (2.745 A @ 3.3 V: FMC + gated peripherals + the VADJ LDO), giving 44 % current
  headroom. FB divider 23.2k/10k at Vref 1.0 V → 3.32 V, worst case centred in the
  ±3 % window. Same fSW (600 kHz, RT = 22k), 10 µH, and idioms as U1; peak inductor
  current 2.84 A < 4.1 A Isat.
- **Buck heat path is GND.** The VQFN-HR has no center exposed pad; the
  die-attach heat path is the PGND1/PGND2 (and AGND) power-ground pads plus the SW
  pad, all netted to GND so the exposed-pad-equivalent is netlist-verifiable. On a
  4-layer pour the datasheet gives RthJA ≈ 25 °C/W; the thermal gate credits a
  conservative pour-aware 30 °C/W, and both bucks pass on real margin with no
  waiver (U1 Tj ≈ 128 °C, U2 ≈ 98 °C, against a 140 °C guard).
- **Buck input caps.** Per the LM61460 datasheet, each VIN/PGND pair gets a 50 V
  X7R 100 nF HF cap immediately adjacent, plus bulk ceramic: U1 uses 2×10 µF/1206
  (50 V-class for the 21 V rail), U2 uses 2×22 µF.
- **BIAS tied to VOUT.** Both bucks tie BIAS to their output through a 10 Ω series
  resistor (top of the datasheet 1–10 Ω band, max noise filtering) plus a 1 µF
  bypass, so the internal LDO draws from VOUT rather than VIN — saving
  I_LDO·(VIN−VOUT). BIAS max rating (16 V) covers both outputs.
- **BOOT.** A 100 nF CBOOT cap from SW to BOOT; RBOOT is shorted to CBOOT (a 0 Ω
  wire, same node) for the fastest SW edge and lowest high-side loss.
- **FB feedforward.** Each buck bridges its FB-top resistor with a 22 pF C0G CFF
  in series with a 1k RFF damping resistor (`+VOUT_x_REG → CFF → RFF → FB`),
  improving phase margin / transient response with the all-ceramic output caps.
  Both outputs (5.0 V, 3.3 V) are < 14 V and have their ESR zero above 200 kHz, so
  feedforward is applicable.
- **+1V8 LDO = AP2112K (U3).** Drops +3V3 → +1V8 with 1 µF in / 1 µF out. Drawn
  with the `AP2204K-1.5` library symbol (same SOT-23-5 pinout).
- **Power-good LEDs.** +5V and +3V3 light a red LED directly off the reg-side
  rail. +1V8 cannot (red Vf ≈ 2.0 V > 1.8 V), so an AO3400A (Q1, Vgs(th) ≤ 1.45 V)
  senses the +1V8 rail through a 1k gate-stop with a 100k pulldown — presenting
  Vgs ≈ 1.78 V, a solid margin over Vth — and sinks a 330R + LED chain from
  `+VOUT_3V3`, which is necessarily up before +1V8 exists.
- **Test points.** TP1–TP4 probe `+VOUT_5V`, `+VOUT_3V3`, `+VOUT_1V8` and `GND`
  at their source sheet for the coverage gate.

## Parts

| ref | value | lib / part | LCSC |
|-----|-------|-----------|------|
| U1 | LM61460AANRJRR | `parts/LM61460AANRJRR` (faithful dossier symbol) | C2864505 |
| U2 | LM61460AANRJRR | `parts/LM61460AANRJRR` (faithful dossier symbol) | C2864505 |
| U3 | AP2112K-1.8 | `Regulator_Linear:AP2204K-1.5` / SOT-23-5 | C176944 |
| Q1 | AO3400A | `Transistor_FET:Q_NMOS_GSD` / SOT-23 | C20917 |
| L1, L2 | 10uH | `SWPA8040S100MT` | C37429 |
| C1, C25, C7, C29 | 100n | `Device:C` (buck VIN HF bypass, 50 V X7R) | C14663 |
| C2, C3 | 10u | `Device:C` (+5V buck input bulk, 1206) | C13585 |
| C5, C6, C26 | 22u | `Device:C` (+5V buck output bulk, 0805) | C45783 |
| C8, C30, C10, C11 | 22u | `Device:C` (+3V3 buck input/output bulk, 0805) | C45783 |
| C4, C9 | 100n | `Device:C` (BOOT/CBOOT caps) | C14663 |
| C24, C31 | 1u | `Device:C` (VCC int-LDO bypass) | C15849 |
| C28, C32 | 1u | `Device:C` (BIAS bypass) | C15849 |
| C27, C23 | 22p | `Device:C` (FB feedforward CFF, C0G) | C1653 |
| C12, C13 | 1u | `Device:C` (LDO input / output) | C15849 |
| R1 | 40.2k | `Device:R` (+5V FB top → 5.02 V) | C12447 |
| R2, R5 | 10k | `Device:R` (FB bottom) | C25804 |
| R4 | 23.2k | `Device:R` (+3V3 FB top → 3.32 V) | C23346 |
| R10, R14 | 22k | `Device:R` (RT, fSW = 600 kHz) | C31850 |
| R11, R13 | 10R | `Device:R` (BIAS series) | C22859 |
| R3, R12, R15, R7 | 1k | `Device:R` (PG-LED / FB RFF / +1V8 gate-stop) | C21190 |
| R6, R9 | 330R | `Device:R` (+3V3 / +1V8 PG-LED) | C23138 |
| R8 | 100k | `Device:R` (+1V8 PG-sense gate pulldown) | C25803 |
| D1, D2, D3 | red | `Device:LED` (rail-present indicators) | C2286 |
| TP1–TP4 | — | `Connector:TestPoint` (rail / GND probes) | — |

## Build & test

`test_power.py` runs the subsystem-local slices offline: abstract interface, the
faithful LM61460 dossier symbol, model completeness, the buck GND heat path,
decoupling completeness, the FB-divider ratios, the reg-side/rail-side split,
internal-SIGNAL preservation, part-rating + cap-derate coverage, the SPICE-subckt
↔ netlist passive match, and the bind contract.

```bash
PYTHONPATH=. python3 -m pytest subsystems/power/test_power.py -q
```
