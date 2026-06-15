# pmod — 2x Digilent-standard Pmod host ports (reusable subsystem)

A project-agnostic, self-contained schgen subsystem: **two** plain
Digilent-standard **Pmod** host ports, each a 2x6 right-angle FEMALE 2.54 mm
socket (**CONNFLY DS1024-2x6R2**, the spec-exact part; BOOMELE **C36191**
straight female is the committed stock fallback). Every IO carries the
Digilent-standard **200R series** protection resistor and each port's VCC pins
get a **100n + 10u** local bypass. It declares its interface as **abstract**
port + rail names and knows nothing about any board; a consuming project supplies
a **bind map** (`abstract -> real net`) to drop it onto real nets. (The richer
`pmod_expansion` cell is a separate subsystem — this is the plain connector.)

## Package contents

| file | role |
|------|------|
| `pmod.py`      | the NETLIST — `circuit(meta=None)`, abstract ports/rails |
| `pmod.cir`     | SPICE subckt — the passive network (16x 200R + per-port bypass) with the abstract ports as subckt pins |
| `test_pmod.py` | LOCAL electrical-correctness test (offline, runs the board gate slices on just this subsystem) |
| `README.md`    | this file |

The **DS1024-2x6R2** socket is **referenced, never vendored**: the
zigzag-numbered connector symbol + footprint come from the global `parts/`
library via `use_part`. The 200R series resistors and bypass caps are inline
passives.

## The abstract interface (the reuse contract)

A consuming project binds these names. Rails classify as POWER/GROUND by name
(the `+` prefix + `GND`), and the per-IO host signals as PORT, exactly as real
board nets do, so a standalone build and a bound build share net classes.

### Rails (POWER / GROUND)

| abstract | class | meaning / constraint |
|----------|-------|----------------------|
| `+VCC_PMOD` | POWER  | the Pmod-module VCC rail (3.3 V class). Feeds both ports' VCC pins (socket positions 6/12) with a 100n + 10u local bypass per port. Typically a bring-up-gated module rail (the Pmod spec budgets ~100 mA per attached module). |
| `GND`       | GROUND | ground (socket positions 5/11 of each port). |

### Ports (PORT)

| abstract | type | meaning |
|----------|------|---------|
| `PMOD0_SIG1..8` | single | the 8 host-side IO signals for port 0 (socket `J1`). Each enters through a 200R series resistor onto the socket IO pin. |
| `PMOD1_SIG1..8` | single | the 8 host-side IO signals for port 1 (socket `J2`). Same 200R protection. |

The 200R-resistor → socket-pin span is a **private internal SIGNAL net**
(`PMOD{n}_IO{m}`) and is **never** externally bound.

### Parts (from the global `parts/` lib + inline passives)

| ref | value | lib / part | LCSC |
|-----|-------|-----------|------|
| J1, J2 | DS1024-2x6R2 | `parts/DS1024-2x6R2/` (zigzag-numbered 2x6 socket) | (fallback C36191) |
| R1..R16 | 200R | `Device:R` (Digilent IO protection, one per IO) | C8218 |
| C1, C3 | 100n | `Device:C` (per-port VCC bypass) | C14663 |
| C2, C4 | 10u  | `Device:C` (per-port VCC bulk)   | C15850 |

## Consuming it from a project

A project supplies a thin adapter declaring ONE standard `META` dict (the
adapter contract, `schgen.core.subsystem.Meta`) and forwards it:

```python
from subsystems.pmod import pmod

META = {
    # abstract subsystem net -> your real board net
    "bind": {
        "+VCC_PMOD": "+3V3_PMOD", "GND": "GND",
        "PMOD0_SIG1": "MY_BANK_A0", "PMOD0_SIG2": "MY_BANK_A1", ...,
        "PMOD1_SIG1": "MY_BANK_B0", ...,
    },
    # optional: tell the linker which of your sheets binds the deferred signals
    "expects": {"PMOD0_SIG1": "my_connector", ...},
    # optional house-style override (keep your derived artifacts byte-stable)
    "notes": {"draws": "2x Pmod module budget ~100 mA each"},  # power-tree note
}

def circuit():
    return pmod.circuit(META)
```

The standard `META` keys (`bind` / `expects` / `buses` / `notes`) are universal
across every reusable subsystem — a typo'd top-level key is a hard
`CircuitError`, never silently dropped. `bind` renames every external **in
place, order-preserving** (POWER/GROUND/PORT only — a SIGNAL net is private
wiring and is never rebound; a SIGNAL key or a collision is a hard
`CircuitError`). Because the rename preserves net insertion order, parts, refs
and port-type payloads, **binding to the exact names a hand-written sheet used
yields a byte-identical emitted sheet.** The carrier adapter is
`carrier/subsystems/pmod.py`.

## Design notes (datasheet + spec)

- **Pmod pin numbering is row-major, NOT the 2x6 zigzag.** Per the Digilent Pmod
  spec each socket is `top row 1-6, bottom row 7-12; 1-4 = IO1-4, 5 = GND,
  6 = VCC, 7-10 = IO5-8, 11 = GND, 12 = VCC`. The generated DS1024-2x6R2
  footprint is **zigzag-numbered** (odd pads one row, even pads the other,
  vertical column pairs `(2k-1, 2k)`), so `PAD` maps each Pmod logical position
  `p` onto a connector pad: top-row `p -> 2p-1`, bottom-row `p -> 2(p-6)`. Verify
  odd-row = top row against the DS1024 datasheet drawing at layout.
- **200R series on every IO (Digilent standard).** Each of the 16 IOs gets a
  200R series resistor (C8218, Basic) between the host signal and the socket pin
  — current-limit / edge-soften the user-facing module interface.
- **Per-port VCC bypass.** Each port's VCC pins (socket positions 6/12) carry a
  100n + 10u local bypass; the Pmod spec budgets ~100 mA per attached module, so
  two ports draw ~200 mA worst case on `+VCC_PMOD`.
- **Gated module rail (typical).** `+VCC_PMOD` is usually a bring-up-gated
  module rail (it can be hot-swapped / powered down independently). It is a plain
  POWER rail to this subsystem; the gating belongs to the consuming project's
  power tree, not here.

## Local test vs board gates

`test_pmod.py` runs the **subsystem-local** slices offline: declared abstract
interface (rails/ports present with the right net class, every connector pin
netted-or-NC), the 200R-per-IO and per-port bypass network, part-rating
coverage, the SPICE-subckt ↔ netlist passive match, and the bind contract.
**Cross-board** gates stay aggregated at board level and are *not* duplicated
here: the full power-tree headroom, the link / port-driver graph, board ERC, and
the board netlist merge — all run by `schgen board`.

```bash
PYTHONPATH=. python3 -m pytest subsystems/pmod/test_pmod.py -q
```
