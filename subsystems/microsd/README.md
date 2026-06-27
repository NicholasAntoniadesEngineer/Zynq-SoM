# microsd — microSD slot behind a TXS02612 SDIO level translator

A project-agnostic, reusable schgen subsystem: a microSD push-push slot wired to
a standard 3.3 V SD card, fed through a TI TXS02612 auto-direction SDIO level
translator so a lower-voltage host can talk to the fixed-3.3 V card. On the
Zynq-7000 SoM carrier it provides the boot/removable-storage slot, bridging the
host SDIO bus to the card and clamping the user-facing card lines with a
TPD6E001 6-channel ESD array. It declares its interface as abstract port and
rail names and knows nothing about any board; a consuming project supplies a
bind map to drop it onto real nets.

## Interface

The externally-visible nets a consuming project binds. Rails classify as
POWER/GROUND by name (the `+` prefix and `GND`) so a standalone build and a
bound build share net classes.

### Rails (POWER / GROUND)

The TXS02612 is a voltage-level translator with two distinct supply rails — one
per side — so a project binds each independently.

| abstract | class | meaning / constraint |
|----------|-------|----------------------|
| `+VDD_HOST` | POWER  | TXS02612 **VCCA**, the host-side reference (host signalling level; abstract `HOST_LEVEL_V` = 1.8 V). uA-class draw. |
| `+VDD_CARD` | POWER  | TXS02612 **VCCB0/VCCB1**, the card-side rail. Also feeds slot VDD, every card-line pull-up, the TPD6E001 ESD-array VCC and the bulk cap. Fixed 3.3 V class (see Design). |
| `GND`       | GROUND | ground. |

### Ports (PORT)

| abstract | type | meaning |
|----------|------|---------|
| `SD_CLK`, `SD_CMD`, `SD_D0`..`SD_D3` | `sd_bus` @ `HOST_LEVEL_V` | the SD bus on the **host (A) side** of the translator. The card-side twins are private internal SIGNAL nets (`SD_CARD_*`) and are never externally bound. |
| `CD_N` | port | card-detect: the slot switch closes to GND, pulled up (R6 10k), reported to the host. Active-low presence. |

The unused TXS02612 port B1 (six lanes) and the two TPD6E001 NC pads are
explicit author no-connects.

### Binding contract

A project supplies one standard `META` dict (`schgen.core.subsystem.Meta`) and
forwards it to `circuit(meta)`. `bind` rebinds every externally-visible net
in place, order-preserving (POWER/GROUND/PORT only; SIGNAL nets are private and
never rebound). With `meta=None` the subsystem keeps its abstract names so the
local test runs offline.

```python
from subsystems.microsd import microsd

META = {
    "bind": {
        "+VDD_HOST": "+1V8", "+VDD_CARD": "+3V3_SD", "GND": "GND",
        "SD_CLK": "SDIO_CLK", "SD_CMD": "SDIO_CMD",
        "SD_D0": "SDIO_D0", "SD_D1": "SDIO_D1",
        "SD_D2": "SDIO_D2", "SD_D3": "SDIO_D3",
        "CD_N": "SD_CARD_DETECT",
    },
    # optional: which sheet binds a deferred port
    "expects": {"CD_N": "my_connector"},
    # optional house-style power-tree draw notes
    "notes": {"draws_card": "...", "draws_host": "..."},
}

def circuit():
    return microsd.circuit(META)
```

The carrier adapter is `carrier/subsystems/microsd.py`.

## Design

- **Two supply domains.** The TXS02612 is an auto-direction level translator:
  VCCA references the host side (`+VDD_HOST`), VCCB0/VCCB1 the card side
  (`+VDD_CARD`). Port A talks to the host bus; port B0 talks to the card. SEL is
  strapped low (to GND) to select port B0; port B1 is unused (six explicit NCs).
  EP, both TXS GND pins, and the slot VSS/GND pads tie to GND.

- **Card-side pull value (SD-2).** R1..R5 (the CMD and D0..D3 lanes) sit on the
  TXS02612's active B0 one-shot outputs, which already hold an internal pull-up
  (4 kohm driving high / 40 kohm driving low; TI SCEA054A fig.1). An external
  pull parallels the internal 40 kohm while the output drives low, lifting VOL
  and softening edges — SCEA054A Table 1 measures VOL 29 mV (no pull) →
  169 mV (~10k) → 38 mV (100k), with guidance ">50 kohm beneficial". So R1..R5
  are **100k**: a visible SD-spec anti-float pull kept inside TI's >50k band
  (VOL within ~9 mV of the no-pull baseline). R6 (card-detect, not on a TXS
  output) is 10k.

- **Fixed 3.3 V card rail (SD-1).** The card side is wired at a fixed 3.3 V-class
  rail with no 1.8 V card-rail switch, so the slot supports only DEFAULT-speed
  and HIGH-SPEED SD modes (3.3 V signalling). UHS-I (SDR50/SDR104/DDR50), which
  mandates a 1.8 V signalling voltage switch (S18), is **not** available. A host
  SDIO controller MUST keep voltage-switching disabled — do not request S18
  (CMD11 / 1.8 V switch): the card rail is permanently 3.3 V, so a host that
  switched to 1.8 V would lose the card.

- **ESD clamp reference (SD-1).** The TPD6E001 clamps the six user-facing card
  lines (CLK, CMD, D0..D3) via its IO1..IO6 channels. Its VCC sets the clamp
  reference; a floating VCC gives the worst-case clamp (TI SLLS546), so VCC is
  biased to the card-side rail `+VDD_CARD` and bypassed locally. NC pads 4/9 are
  explicit no-connects.

- **Decoupling and bulk.** VCCA carries a local 100n bypass (C1). The card rail
  carries a 100n bypass (C2) plus a 22u bulk cap (C3) sized for ~200 mA SD write
  bursts; the TPD6E001 VCC carries its own 100n bypass (C4). Power-tree budget:
  `+VDD_CARD` ~250 mA (write burst + pulls + VCCB), `+VDD_HOST` ~5 mA (uA-class
  VCCA, budgeted). SD CMD and CLK carry test points on the host (A) side.

## Parts

| ref | value | lib / part | LCSC |
|-----|-------|-----------|------|
| U1 | TXS02612RTWR | `TXS02612RTWR` (parts lib) | (from parts) |
| J1 | TF-01A (push-push slot) | `TF-01A` (parts lib) | (from parts) |
| U2 | TPD6E001RSER (6-ch ESD) | `TPD6E001RSER` (parts lib) | (from parts) |
| R1..R5 | 100k | `Device:R` | C25803 |
| R6 | 10k | `Device:R` | C25804 |
| C1 | 100n | `Device:C` (VCCA host bypass) | C14663 |
| C2 | 100n | `Device:C` (card-rail bypass) | C14663 |
| C3 | 22u  | `Device:C` (card-rail bulk)   | C45783 |
| C4 | 100n | `Device:C` (TPD6E001 VCC bypass) | C14663 |

## Build & test

`test_microsd.py` runs the subsystem-local correctness slices offline (abstract
interface, model/decoupling completeness, part-rating + cap derating, SPICE
subckt match, bind/meta contract). Cross-board gates stay aggregated at board
level.

```bash
PYTHONPATH=. python3 -m pytest subsystems/microsd/test_microsd.py -q
```
