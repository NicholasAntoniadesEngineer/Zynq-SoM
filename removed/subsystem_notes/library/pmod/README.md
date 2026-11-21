# pmod — 2x Digilent-standard Pmod host ports (reusable subsystem)

A project-agnostic, self-contained schgen subsystem providing two plain
Digilent-standard Pmod host ports for the Zynq-7000 SoM carrier. Each port is a
2x6 2.54 mm female socket at the board edge with the Digilent-standard 200R
series protection on every IO and a low-capacitance ESD clamp on each FPGA-pin
net. It declares an abstract port/rail interface and knows nothing about any
consuming board; a project binds it onto real nets.

## Interface

The subsystem exposes abstract net names that a consuming project rebinds via the
standard `META` adapter contract (`schgen.core.subsystem.Meta`). Rails classify
as POWER/GROUND by name (`+` prefix, `GND`) and the per-IO host signals as PORT,
so a standalone build and a bound build share net classes.

### Rails (POWER / GROUND)

| abstract | class | meaning |
|----------|-------|---------|
| `+VCC_PMOD` | POWER  | Pmod-module VCC rail (3.3 V class). Feeds both ports' VCC pins (socket positions 6/12) with a 100n + 10u local bypass per port. Typically a bring-up-gated module rail (the Pmod spec budgets ~100 mA per attached module). |
| `GND`       | GROUND | ground (socket positions 5/11 of each port, plus the ESD-array GND pins). |

### Ports (PORT)

| abstract | type | meaning |
|----------|------|---------|
| `PMOD0_SIG1..8` | single | the 8 host-side IO signals for port 0 (socket `J1`). |
| `PMOD1_SIG1..8` | single | the 8 host-side IO signals for port 1 (socket `J2`). |

Each host signal enters a 200R series resistor onto the socket IO pin; the
resistor→pin span is a private internal SIGNAL net (`PMOD{n}_IO{m}`) and is never
externally bound.

### Binding from a project

```python
from subsystems.pmod import pmod

META = {
    "bind": {
        "+VCC_PMOD": "+3V3_PMOD", "GND": "GND",
        "PMOD0_SIG1": "MY_BANK_A0", ..., "PMOD1_SIG8": "MY_BANK_B7",
    },
    "expects": {"PMOD0_SIG1": "my_connector", ...},   # optional linker deferral
    "notes":   {"draws": "2x Pmod module budget ~100 mA each"},  # optional
}

def circuit():
    return pmod.circuit(META)
```

`bind` renames every external net in place, order-preserving (POWER/GROUND/PORT
only — a SIGNAL net is private and never rebound; a SIGNAL key or a name
collision is a hard `CircuitError`). Binding to the exact names a hand-written
sheet used yields a byte-identical emitted sheet. `expects` attaches an explicit
linker deferral per host-signal port (which of the project's sheets binds the
deferred bank signal). The carrier adapter is `carrier/subsystems/pmod.py`.

## Design

**Two plain host ports.** `PORTS_DEF` defines two Digilent-standard Pmod sockets,
`J1`/`PMOD0` and `J2`/`PMOD1`, each carrying 8 IO, GND, and VCC.

**Connector — DS1024-2x6R2.** Each port is a right-angle female 2.54 mm 2x6
socket (CONNFLY DS1024-2x6R2, the spec-exact part). The faithful
zigzag-numbered connector symbol and footprint come from the global `parts/`
library via `use_part` (referenced, never vendored).

**Pin-number mapping (row-major spec → zigzag pads).** The Digilent Pmod spec
numbers each socket row-major: top row 1-6, bottom row 7-12; positions 1-4 =
IO1-4, 5 = GND, 6 = VCC, 7-10 = IO5-8, 11 = GND, 12 = VCC. The DS1024-2x6R2
footprint is zigzag-numbered (odd pads one row, even pads the other, in vertical
column pairs `(2k-1, 2k)`). `PAD` maps each logical position `p` onto a connector
pad: top-row `p → 2p-1`, bottom-row `p → 2(p-6)`. `IO_POS` maps IO index 1-8 onto
logical positions 1-4 and 7-10. Verify odd-row = top row against the DS1024
datasheet drawing at layout.

**200R series on every IO (Digilent standard).** Each of the 16 IOs gets a 200R
series resistor (`R1..R16`, C8218) between the host signal and the socket pin,
current-limiting and edge-softening the user-facing module interface.

**Low-capacitance ESD clamp.** Each port carries two TPD4E1U06 4-channel arrays
(0.8 pF, C124691): `U1`/`U2` on `J1`, `U3`/`U4` on `J2` — one array clamps IO1-4,
the other IO5-8 (`ESD_CH` = channel pins 1/3/6/4, GND = pin 2, NC = pin 5). The
clamp is a GND-referenced shunt that rides the BOUND signal net just inboard of
the 200R resistor — the series resistor limits the strike current into the
clamp+pin while the clamp holds the bank-13 IO at Vclamp. The clamp is never in
series with the signal (LAW-0), and riding the signal net rather than the socket
leg keeps each socket leg a clean 2-pin float chain for the placer.

**Per-port VCC bypass.** Each port's VCC pins (positions 6/12) carry a 100n + 10u
local bypass (`C1`/`C2` for J1, `C3`/`C4` for J2). The Pmod spec budgets ~100 mA
per attached module, so two ports draw ~200 mA worst case on `+VCC_PMOD`; the
power-tree note declares `DRAWS_A = 0.200`.

**Gated module rail.** `+VCC_PMOD` is typically a bring-up-gated module rail (it
can be powered down independently). To this subsystem it is a plain POWER rail;
the gating belongs to the consuming project's power tree.

## Parts

| ref | value | lib / part | LCSC |
|-----|-------|-----------|------|
| J1, J2 | DS1024-2x6R2 | `parts/DS1024-2x6R2/` (zigzag-numbered 2x6 socket) | — (stock fallback C36191) |
| U1–U4 | TPD4E1U06 | `TPD4E1U06DBVR` (4-channel low-cap ESD array) | C124691 |
| R1–R16 | 200R | `Device:R` (Digilent IO protection, one per IO) | C8218 |
| C1, C3 | 100n | `Device:C` (per-port VCC bypass) | C14663 |
| C2, C4 | 10u  | `Device:C` (per-port VCC bulk)   | C15850 |

## Build & test

`test_pmod.py` runs the subsystem-local electrical-correctness slices offline:
declared abstract interface, the 200R-per-IO and ESD-clamp network, per-port
bypass, part-rating coverage, the SPICE-subckt ↔ netlist passive match, and the
bind contract.

```bash
PYTHONPATH=. python3 -m pytest subsystems/pmod/test_pmod.py -q
```
