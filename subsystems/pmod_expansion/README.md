# pmod_expansion — manual-gated Digilent Pmod expansion port (reusable subsystem)

A project-agnostic, self-contained schgen subsystem: one **Digilent-standard
Pmod** (2x6, 2.54 mm, 3.3 V) breakout — 8 IO + 2x VCC + 2x GND on a right-angle
**DS1024-2x6R2** socket — fed by a **SY6280AAC** current-limited load switch so
the port's 3.3 V is **manually gated** (a powered-down peripheral can never be
back-fed), with a low-capacitance **TPD4E1U06** TVS clamp on every cable-facing
IO. It declares its interface as **abstract** port + rail names and knows nothing
about any board; a consuming project supplies a **bind map**
(`abstract -> real net`) to drop it onto real nets.

## Package contents

| file | role |
|------|------|
| `pmod_expansion.py`      | the NETLIST — `circuit(meta=None)`, abstract ports/rails |
| `pmod_expansion.cir`     | SPICE subckt — the passive network with the abstract ports as subckt pins |
| `test_pmod_expansion.py` | LOCAL electrical-correctness test (offline, runs the board gate slices on just this subsystem) |
| `README.md`              | this file |

Active parts are **referenced, never vendored**: the SY6280AAC, DSHP04TSGER,
DS1024-2x6R2 and TPD4E1U06DBVR symbols/footprints/LCSC come from the global
`parts/` lib via `use_part()`. (The two ESD arrays carry the display value
`TPD4E1U06`.)

## The abstract interface (the reuse contract)

A consuming project binds these names. Rails classify as POWER/GROUND by name (a
leading `+` = POWER; `GND` = GROUND), exactly as real board rails do, so a
standalone build and a bound build share net classes.

### Rails (POWER / GROUND)

| abstract | class | meaning / constraint |
|----------|-------|----------------------|
| `+VDD_PMOD` | POWER  | the input rail the SY6280 load switch gates (3.3 V class). |
| `+VSW_PMOD` | POWER  | the **switched / gated** output rail the port provides to the Pmod peripheral (= `U1.OUT`). Dark at power-up until the manual enable is flipped, so a peripheral cannot be back-fed from this port. The status LED + the Pmod power-pin bypass/bulk sit on this rail. |
| `GND`       | GROUND | ground. |

### Ports (PORT)

| abstract | type | meaning |
|----------|------|---------|
| `PMOD_IO1` … `PMOD_IO8` | single | the eight Digilent Pmod IO — plain LVCMOS33 GPIO bound to the host's free GPIO pins. Each lands on the socket pad alongside its own GND-referenced **TPD4E1U06** ESD clamp channel (a pure shunt, never in series). |

### Internal SIGNAL nets (private — never bindable)

| net | role |
|-----|------|
| `EN_PMODX`      | the SY6280 enable — DSHP04 pos 1 closes `+VDD_PMOD` onto it; a 100k pulldown holds it OFF at power-up. |
| `BS_ISET_PMODX` | the SY6280 ILIM-set node (13k → 6800/13k ≈ 523 mA). |
| `BS_PG_PMODX`   | the status-LED cathode node (lit = port enabled). |

### Parts (from the global `parts/` lib + inline passives)

| ref | value | lib / part | LCSC |
|-----|-------|-----------|------|
| U1 | SY6280AAC | `parts/SY6280AAC/` (load switch) | — |
| SW1 | DSHP04TSGER | `parts/DSHP04TSGER/` (manual enable DIP) | — |
| J1 | DS1024-2x6R2 | `parts/DS1024-2x6R2/` (2x6 Pmod socket) | — |
| U2, U3 | TPD4E1U06 | `parts/TPD4E1U06DBVR/` (low-cap ESD array, 4ch) | C124691 |
| R1 | 13k  | `Device:R` (ILIM set) | C22797 |
| R2 | 100k | `Device:R` (EN pulldown) | C25803 |
| R3 | 330R | `Device:R` (status-LED set) | C23138 |
| D1 | red  | `Device:LED` (status LED) | C2286 |
| C1 | 100n | `Device:C` (SY6280 IN bypass) | C14663 |
| C2 | 10u  | `Device:C` (SY6280 IN bulk)   | C15850 |
| C3 | 100n | `Device:C` (switched-rail OUT bypass) | C14663 |
| C4 | 100n | `Device:C` (Pmod power-pin bypass) | C14663 |
| C5 | 10u  | `Device:C` (Pmod power-pin bulk)   | C15850 |

## Consuming it from a project

A project supplies a thin adapter declaring ONE standard `META` dict (the
adapter contract, `schgen.core.subsystem.Meta`) and forwards it:

```python
from subsystems.pmod_expansion import pmod_expansion

META = {
    # abstract subsystem net -> your real board net
    "bind": {
        "+VDD_PMOD": "+3V3", "+VSW_PMOD": "+3V3_PMODX", "GND": "GND",
        "PMOD_IO1": "MY_IO1", "PMOD_IO2": "MY_IO2", ...,
    },
    # optional: tell the linker which of your sheets will bind a deferred port
    "expects": {"PMOD_IO1": "my_connector", ...},
    # optional house-style override (keep your power-tree note byte-stable)
    "notes": {"draws_pmod": "1x Pmod module budget ~100 mA + status LED"},
}

def circuit():
    return pmod_expansion.circuit(META)
```

The four standard `META` keys (`bind` / `expects` / `buses` / `notes`) are
universal across every reusable subsystem — a typo'd top-level key is a hard
`CircuitError`, never silently dropped. `bind` renames every external **in
place, order-preserving** (POWER/GROUND/PORT only — a SIGNAL net is private
wiring and is never rebound; a SIGNAL key or a collision is a hard
`CircuitError`). Because the rename preserves net insertion order, parts, refs,
NCs, port-type payloads and the testpoint value, **binding to the exact names a
hand-written sheet used yields a byte-identical emitted sheet.** The carrier
adapter is `carrier/subsystems/pmod_expansion.py`.

## Design notes

- **Manual power gate (default-OFF).** The SY6280's enable is **local** and
  defaults OFF: SW1 (DSHP04, position 1) closes `+VDD_PMOD` onto `EN_PMODX` and
  a 100k pulldown holds it low until a human flips the switch. So the port is
  dark at power-up, and a peripheral whose own 3.3 V is down cannot be back-fed
  from this port. A status LED on `+VSW_PMOD` shows enable at a glance.
- **Current limit.** ILIM = 6800 / R(ISET) = 6800 / 13k ≈ **523 mA**, comfortably
  above the Digilent ~100 mA/module budget while still current-limiting a fault.
- **Datasheet bypass.** The SY6280 IN carries 100n + a local 10u bulk (the
  datasheet strongly recommends a 10 µF from VIN to GND). The OUT-side 10u bulk
  is met by the Pmod power-pin bulk on `+VSW_PMOD` (= `U1.OUT`, same net).
- **Cable-facing ESD (LAW-0 shunt).** Each of the 8 IO carries a low-capacitance
  TPD4E1U06 clamp (0.8 pF, C124691) — a **pure GND-referenced shunt**, NEVER in
  series with the signal. Two TPD4E1U06 (4 channels each) cover the 8 IO; the
  5.5 V working voltage / IEC 61000-4-2 ±8 kV rating references 3.3 V LVCMOS
  safely, and the 0.8 pF junction does not slow LVCMOS33 edges.
- **Optional 200R series damping (DNP).** Some Pmod hosts add ~200R per IO for
  short-circuit / ringing protection. That is a documented **DNP stuffing
  option** (not populated): the ESD clamp is the primary protection. If LP/strobe
  ringing appears at bring-up, stuff an 0603 200R (C8218 Basic) in series between
  the host GPIO pin and the socket pad on each IO.
- **Pmod pin numbering.** Row-major (Digilent spec): top row 1-6 = IO1-4, GND,
  VCC; bottom row 7-12 = IO5-8, GND, VCC. The DS1024-2x6R2 footprint is
  zigzag-numbered (odd pads one row, even pads the other), so `PAD` maps logical
  Pmod positions onto connector pads.

## Local test vs board gates

`test_pmod_expansion.py` runs the **subsystem-local** slices offline: declared
abstract interface, model completeness (every pin netted-or-NC), decoupling /
load-switch bypass completeness, the two-array ESD clamp coverage, part-rating
coverage + per-rail cap derating, the SPICE-subckt ↔ netlist passive match, and
the bind contract. **Cross-board** gates stay aggregated at board level and are
*not* duplicated here: the `PMOD_IO*` link / port-driver graph (the IO bind on
the generated SoM connector sheet), the full power-tree headroom, board ERC and
the board netlist merge — all run by `schgen board`.

```bash
PYTHONPATH=. python3 -m pytest subsystems/pmod_expansion/test_pmod_expansion.py -q
```
