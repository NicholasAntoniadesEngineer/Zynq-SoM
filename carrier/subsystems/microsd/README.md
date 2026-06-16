# microsd — carrier ADAPTER for the reusable TXS02612 microSD-slot subsystem

A **thin carrier adapter**. The portable circuit (netlist + SPICE + README +
local test) lives in the project-agnostic library
[`../../../subsystems/microsd/`](../../../subsystems/microsd/README.md). This
package is the carrier-specific **glue**: it imports that library subsystem and
**binds** its abstract ports/rails to the Zynq carrier's real net names, so the
emitted `carrier/schematic/microsd.kicad_sch` and its golden render are
unchanged. The board build discovers it folder-aware exactly as before
(`circuit()` exposed here).

The SoM's `SDIO_*` nets run at 1.8 V and standard SD cards init at 3.3 V, so a
TXS02612 level translator sits between them: port A (1.8 V) = SoM side, port B0
(3.3 V) = card side to the TF-01A push-push slot. DEFAULT/HIGH-SPEED SD only (no
UHS-I S18). The part choice and card-line pulls live in the library README.

## Package contents

| file | role |
|------|------|
| `microsd.py`      | the carrier ADAPTER — `circuit()` + the `META` bind contract (returns `_lib.circuit(META)`) |
| `__init__.py`     | re-exports `circuit`, `META` |
| `microsd.cir`     | thin carrier-BOUND SPICE subckt (pins = carrier nets); passive model lives in `../../../subsystems/microsd/microsd.cir` |
| `test_microsd.py` | offline BIND GUARD — adapter circuit == `lib.circuit(META)`, carrier nets present, no abstract leak |
| `README.md`       | this file |

## The carrier bind (`META`)

`bind` — abstract subsystem net → carrier real net:

| abstract | carrier net | why |
|----------|-------------|-----|
| `+VDD_HOST` | `+1V8`    | TXS02612 VCCA host-side reference (SoM SDIO domain @ 1.8 V) |
| `+VDD_CARD` | `+3V3_SD` | bring-up-gated card rail (SY6280 cell 5) — feeds slot VDD + both VCCB + every card pull + bulk + the TPD6E001 ESD VCC |
| `GND`       | `GND`     | identity |
| `SD_CLK/CMD/D0..D3` | `SDIO_CLK/CMD/D0..D3` | the SoM SDIO contract nets (port A, 1.8 V), verbatim |
| `CD_N`      | `SD_CARD_DETECT` | card-detect reported to the SoM |

`expects` — explicit linker deferral (the port awaits its sheet, never a silent
open):

- `CD_N` → `som_j1_connector` (STM32 GPIO function map)

`notes` — power-tree draw notes (house-style wording, keeps `power_tree.txt`
byte-identical):

- `draws_card`: `SD card write burst ~200 mA + pull-ups + TXS02612 VCCB`
- `draws_host`: `TXS02612 VCCA (SoM-side level)`

## Local test

```bash
PYTHONPATH=. python3 -m pytest carrier/subsystems/microsd/test_microsd.py -q
```

The library's own electrical correctness is proven by
`subsystems/microsd/test_microsd.py`; the board-level gates (power tree, ERC,
link/port-driver graph) stay aggregated by `schgen board`.
