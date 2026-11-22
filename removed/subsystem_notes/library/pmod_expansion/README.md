# pmod_expansion — manual-gated Digilent Pmod expansion port (reusable subsystem)

A project-agnostic, self-contained schgen subsystem providing one Digilent-standard
Pmod port (2x6, 2.54 mm, 3.3 V): 8 IO + 2x VCC + 2x GND on a right-angle
**DS1024-2x6R2** socket at the board edge. On the Zynq-7000 SoM carrier it breaks
out free host PL GPIO to an external Pmod peripheral, fed by a manually-gated,
current-limited 3.3 V rail and protected by a low-capacitance TVS clamp on every
cable-facing IO. It declares its interface as abstract port/rail names and knows
nothing about any board; a consuming project supplies a bind map to land it on
real nets.

## Interface

A consuming project supplies one standard `META` dict (`schgen.core.subsystem.Meta`)
and forwards it to `circuit(meta)`. Rails classify as POWER/GROUND by name (a
leading `+` = POWER, `GND` = GROUND), so a standalone build and a bound build share
net classes; `bind` renames externals in place, order-preserving, so binding to a
hand-sheet's names yields a byte-identical sheet.

### Rails (POWER / GROUND)

| abstract | class | meaning |
|----------|-------|---------|
| `+VDD_PMOD` | POWER  | the input rail the SY6280 load switch gates (3.3 V class). |
| `+VSW_PMOD` | POWER  | the switched / gated output rail provided to the Pmod peripheral (= `U1.OUT`). Dark at power-up until the manual enable is flipped, so a peripheral cannot be back-fed from this port. The status LED and the Pmod power-pin bypass/bulk sit on this rail. |
| `GND`       | GROUND | ground. |

### Ports (PORT)

| abstract | meaning |
|----------|---------|
| `PMOD_IO1` … `PMOD_IO8` | the eight Digilent Pmod IO — plain LVCMOS33 GPIO bound to the host's free GPIO pins. Each lands on the socket pad alongside its own GND-referenced TPD4E1U06 ESD clamp channel. |

### Internal SIGNAL nets (private — never bindable)

| net | role |
|-----|------|
| `EN_PMODX`      | the SY6280 enable; SW1 pos 1 closes `+VDD_PMOD` onto it, a 100k pulldown holds it OFF at power-up. |
| `BS_ISET_PMODX` | the SY6280 ILIM-set node (13k → 6800/13k ≈ 523 mA). |
| `BS_PG_PMODX`   | the status-LED cathode node (lit = port enabled). |

### Bind example

```python
from subsystems.pmod_expansion import pmod_expansion

META = {
    "bind": {
        "+VDD_PMOD": "+3V3", "+VSW_PMOD": "+3V3_PMODX", "GND": "GND",
        "PMOD_IO1": "MY_IO1", "PMOD_IO2": "MY_IO2",  # … through PMOD_IO8
    },
    # optional: tell the linker which sheet binds a deferred port
    "expects": {"PMOD_IO1": "my_connector"},
    # optional house-style override (keep the power-tree note byte-stable)
    "notes": {"draws_pmod": "1x Pmod module budget ~100 mA + status LED"},
}

def circuit():
    return pmod_expansion.circuit(META)
```

The standard `META` keys (`bind` / `expects` / `notes`) are universal across
reusable subsystems; an unknown top-level key, a SIGNAL-net bind, or a bind
collision is a hard `CircuitError`. The carrier adapter is
`carrier/subsystems/pmod_expansion.py`.

## Design

- **Manual power gate (default-OFF).** U1 (SY6280AAC current-limited load switch)
  gates `+VDD_PMOD` → `+VSW_PMOD`. Its enable `EN_PMODX` is local: SW1 (DSHP04TSGER
  DIP, position 1) closes `+VDD_PMOD` onto the enable, and a 100k pulldown holds it
  low until a human flips the switch. So the port is dark at power-up, and a
  peripheral whose own 3.3 V is down cannot be back-fed from this port. SW1
  positions 2–4 are spare (commons bused to `+VDD_PMOD`, even pins NC).
- **Current limit.** ILIM = 6800 / R(ISET) = 6800 / 13k ≈ **523 mA**, comfortably
  above the Digilent ~100 mA/module budget while still limiting a fault.
- **Status LED.** A red LED + 330R from `+VSW_PMOD` to `BS_PG_PMODX` shows the
  gated output enabled at a glance (≈3.9 mA on the switched rail).
- **Datasheet bypass.** The SY6280 IN carries 100n HF + a local 10u bulk (the
  datasheet strongly recommends a 10 µF from VIN to GND, since without local input
  bulk an output short rings the input). OUT carries a local 100n HF; its 10u bulk
  is met by the Pmod power-pin bulk on `+VSW_PMOD` (= `U1.OUT`, same net).
- **Cable-facing ESD (shunt).** The port mates an external cable, so each of the 8
  IO carries a low-capacitance TPD4E1U06 clamp — a pure GND-referenced shunt, never
  in series with the signal. Two TPD4E1U06DBVR arrays (4 channels each, U2 for IO
  1–4 and U3 for IO 5–8) cover the 8 IO; pin 2 = GND, pin 5 = NC. The 5.5 V working
  voltage / IEC 61000-4-2 ±8 kV rating references 3.3 V LVCMOS safely, and the
  0.8 pF junction does not slow LVCMOS33 edges.
- **Optional 200R series damping (DNP).** Some Pmod hosts add ~200R per IO for
  short-circuit / ringing protection. This is a documented DNP stuffing option (not
  populated): the ESD clamp is the primary protection and the eight IO are plain
  LVCMOS33 GPIO. If LP/strobe ringing appears at bring-up, stuff an 0603 200R
  (C8218) in series between the host GPIO pin and the socket pad on each IO.
- **Pmod pin numbering.** Row-major (Digilent spec): top row 1-6 = IO1-4, GND, VCC;
  bottom row 7-12 = IO5-8, GND, VCC. The DS1024-2x6R2 footprint is zigzag-numbered
  (odd pads one row, even pads the other), so `PAD` maps logical Pmod positions onto
  connector pads.

## Parts

| ref | value | lib / part | LCSC |
|-----|-------|-----------|------|
| U1     | SY6280AAC   | `parts/SY6280AAC/` (current-limited load switch) | — |
| SW1    | DSHP04TSGER | `parts/DSHP04TSGER/` (manual enable DIP) | — |
| J1     | DS1024-2x6R2 | `parts/DS1024-2x6R2/` (2x6 Pmod socket) | — |
| U2, U3 | TPD4E1U06   | `parts/TPD4E1U06DBVR/` (low-cap 4ch ESD array) | C124691 |
| R (ISET) | 13k   | `Device:R` | C22797 |
| R (EN pulldown) | 100k | `Device:R` | C25803 |
| R (LED set) | 330R | `Device:R` | C23138 |
| D (status) | red | `Device:LED` (KT-0603R) | C2286 |
| C (IN bypass) | 100n | `Device:C` | C14663 |
| C (IN bulk)   | 10u  | `Device:C` | C15850 |
| C (OUT bypass) | 100n | `Device:C` | C14663 |
| C (Pmod pwr bypass) | 100n | `Device:C` | C14663 |
| C (Pmod pwr bulk)   | 10u  | `Device:C` | C15850 |

Active parts (U1, SW1, J1, U2/U3) are referenced via `use_part()` from the global
`parts/` lib; passives are inline `Device:*` with the LCSC codes above. R/C/D refs
are auto-assigned in declaration order.

## Build & test

`test_pmod_expansion.py` runs the subsystem-local slices offline: declared abstract
interface, model completeness (every pin netted-or-NC), decoupling / load-switch
bypass completeness, two-array ESD clamp coverage, part-rating + per-rail cap
derating, the SPICE-subckt ↔ netlist passive match, and the bind contract.
Cross-board gates (the `PMOD_IO*` link/port-driver graph, full power-tree headroom,
board ERC, the board netlist merge) run by `schgen board`.

```bash
PYTHONPATH=. python3 -m pytest subsystems/pmod_expansion/test_pmod_expansion.py -q
```
