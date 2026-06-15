# microsd — TXS02612 microSD-slot subsystem (reusable subsystem)

A project-agnostic, self-contained schgen subsystem: a microSD push-push slot
wired to a standard 3.3 V SD card, fed through a TI **TXS02612** auto-direction
SDIO level translator so a lower-voltage host can talk to the fixed-3.3 V card.
Card-side anti-float pulls, a **TPD6E001** 6-channel ESD array across the
user-facing card lines, and a card-detect report complete the cell. It declares
its interface as **abstract** port + rail names and knows nothing about any
board; a consuming project supplies a **bind map** (`abstract -> real net`) to
drop it onto real nets. See `subsystems/usb_pd/` for the worked exemplar of the
`subsystems/<name>/` library layout.

## Package contents

| file | role |
|------|------|
| `microsd.py`      | the NETLIST — `circuit(meta=None)`, abstract ports/rails |
| `microsd.cir`     | SPICE subckt — the passive (bypass) network with the abstract rails as subckt pins |
| `test_microsd.py` | LOCAL electrical-correctness test (offline, runs the board gate slices on just this subsystem) |
| `README.md`       | this file |

Active parts are **referenced, never vendored**: the TXS02612RTWR / TF-01A /
TPD6E001RSER symbols/footprints/LCSC come from the global `parts/` library.

## The abstract interface (the reuse contract)

A consuming project binds these names. Rails classify as POWER/GROUND by name
(the `+` prefix + `GND`), exactly as real board rails do, so a standalone build
and a bound build share net classes.

### Rails (POWER / GROUND)

The TXS02612 is a voltage-level translator with **two distinct supply rails** —
one per side — so a project binds each independently.

| abstract | class | meaning / constraint |
|----------|-------|----------------------|
| `+VDD_HOST` | POWER  | TXS02612 **VCCA** — the host-side reference (the host signalling voltage; abstract host level `HOST_LEVEL_V` = 1.8 V). uA-class draw. |
| `+VDD_CARD` | POWER  | TXS02612 **VCCB(0/1)** — the card-side rail. Also feeds slot VDD, every card-line pull-up, the TPD6E001 ESD-array VCC and the bulk cap. Fixed 3.3 V class (SD-1). |
| `GND`       | GROUND | ground. |

### Ports (PORT)

| abstract | type | meaning |
|----------|------|---------|
| `SD_CLK`, `SD_CMD`, `SD_D0`..`SD_D3` | sd_bus @ `HOST_LEVEL_V` | the SD bus on the **host (A) side** of the translator. The card-side twins are PRIVATE internal SIGNAL nets (`SD_CARD_*`) and are never externally bound. |
| `CD_N` | single | card-detect: the slot switch closes to GND, pulled up (10k), reported to the host. Active-low presence. |

The unused TXS02612 port B1 (six lanes) and the two TPD6E001 NC pads are
explicit author no-connects.

### Parts (from the global `parts/` lib + inline passives)

| ref | value | lib / part | LCSC |
|-----|-------|-----------|------|
| U1 | TXS02612RTWR | `parts/TXS02612RTWR/` | (from parts) |
| J1 | TF-01A (push-push slot) | `parts/TF-01A/` | (from parts) |
| U2 | TPD6E001RSER (6-ch ESD) | `parts/TPD6E001RSER/` | (from parts) |
| R1..R5 | 100k | `Device:R` (card-line anti-float pull, SD-2) | C25803 |
| R6 | 10k | `Device:R` (card-detect pull) | C25804 |
| C1 | 100n | `Device:C` (VCCA host bypass) | C14663 |
| C2 | 100n | `Device:C` (VCCB card bypass) | C14663 |
| C3 | 22u  | `Device:C` (VCCB card bulk)   | C45783 |
| C4 | 100n | `Device:C` (TPD6E001 VCC bypass) | C14663 |

## Consuming it from a project

A project supplies a thin adapter declaring ONE standard `META` dict (the
adapter contract, `schgen.core.subsystem.Meta`) and forwards it:

```python
from subsystems.microsd import microsd

META = {
    # abstract subsystem net -> your real board net
    "bind": {
        "+VDD_HOST": "+1V8", "+VDD_CARD": "+3V3_SD", "GND": "GND",
        "SD_CLK": "SDIO_CLK", "SD_CMD": "SDIO_CMD",
        "SD_D0": "SDIO_D0", "SD_D1": "SDIO_D1",
        "SD_D2": "SDIO_D2", "SD_D3": "SDIO_D3",
        "CD_N": "SD_CARD_DETECT",
    },
    # optional: tell the linker which of your sheets binds a deferred port
    "expects": {"CD_N": "my_connector"},
    # optional house-style overrides (keep your derived artifacts byte-stable)
    "notes": {"draws_card": "...", "draws_host": "..."},
}

def circuit():
    return microsd.circuit(META)
```

The four standard `META` keys (`bind` / `expects` / `buses` / `notes`) are
universal across every reusable subsystem — a typo'd top-level key is a hard
`CircuitError`, never silently dropped. `bind` renames every external **in
place, order-preserving** (POWER/GROUND/PORT only — a SIGNAL net is private
wiring and is never rebound; a SIGNAL key or a collision is a hard
`CircuitError`). Because the rename preserves net insertion order, parts, refs,
NCs and port-type payloads, **binding to the exact names a hand-written sheet
used yields a byte-identical emitted sheet.** The carrier adapter is
`carrier/subsystems/microsd.py`.

## Design notes (datasheet + bring-up contract)

- **Two supply domains.** The TXS02612 is an auto-direction level translator:
  VCCA references the host side (`+VDD_HOST`), VCCB(0/1) the card side
  (`+VDD_CARD`). Port A talks to the host bus; port B0 talks to the card. SEL is
  strapped low (to GND) to select port B0; port B1 is unused (six explicit NCs).
- **Card-side pull value (SD-2).** R1..R5 sit on the TXS02612's active B0
  one-shot outputs, which already hold an internal pull-up (4 kohm high / 40 kohm
  low; TI SCEA054A fig.1). A 10k external pull parallels the internal 40k while
  driving low, lifting VOL and softening edges — SCEA054A Table 1 measures VOL
  29 mV (no pull) -> 169 mV (~10k) -> 38 mV (100k); the guidance is ">50 kohm
  beneficial". So R1..R5 are **100k** (kept inside TI's >50k band, VOL within
  ~9 mV of the no-pull baseline). R6 (card-detect, NOT a TXS output) stays 10k.
- **Fixed 3.3 V card rail (SD-1).** The card side is wired at a fixed 3.3 V-class
  rail, with no 1.8 V card-rail switch, so this slot supports only DEFAULT-speed
  and HIGH-SPEED SD modes (3.3 V signalling); **UHS-I** (SDR50/SDR104/DDR50),
  which mandates a 1.8 V signalling voltage switch (S18), is **not** available. A
  host SDIO controller MUST keep voltage-switching disabled — do not request S18
  (CMD11 / 1.8 V switch): the card rail is permanently 3.3 V, so a host that
  switched to 1.8 V would lose the card.
- **ESD clamp reference (SD-1).** The TPD6E001 VCC sets its clamp reference; a
  floating VCC gives the worst-case clamp on the user-facing card lines (TI
  SLLS546). It is biased to the card-side rail `+VDD_CARD` and bypassed locally.

## Local test vs board gates

`test_microsd.py` runs the **subsystem-local** slices offline: declared abstract
interface (host ports external, card-side twins private SIGNAL), model
completeness (every pin netted-or-NC), decoupling completeness (design_rules
DECAP/EP/STRAP), part-rating coverage + per-rail cap derating, the SPICE-subckt
to netlist passive match, and the bind/meta contract. **Cross-board** gates stay
aggregated at board level and are *not* duplicated here: the link / port-driver
graph (CD_N binds on the J1 sheet), the full power-tree headroom, board ERC, and
the board netlist merge — all run by `schgen board`.

```bash
PYTHONPATH=. python3 -m pytest subsystems/microsd/test_microsd.py -q
```
