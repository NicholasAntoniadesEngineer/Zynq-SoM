# ethernet — HX5008NL 1000BASE-T magnetics + Bob-Smith termination (reusable subsystem)

A project-agnostic, self-contained schgen subsystem: the Pulse **HX5008NL** single-port
1:1 gigabit Ethernet magnetics module with its media-side **Bob-Smith** (IEEE 802.3
§40.7.1) HF termination. It declares its interface as **abstract** port + rail names and
knows nothing about any board; a consuming project supplies a **bind map**
(`abstract -> real net`) to drop it onto real nets. See `subsystems/usb_pd/` for the
worked exemplar and `subsystems/hdmi_tx/` for the diff-pair sibling.

The RJ45 jack is a **separate** subsystem (`rj45_connector`) — this package owns only
the magnetics + Bob-Smith network and exposes the media-side pairs as ports for the jack
to bind.

## Package contents

| file | role |
|------|------|
| `ethernet.py`      | the NETLIST — `circuit(meta=None)`, abstract ports/rails |
| `ethernet.cir`     | SPICE subckt — the 1:1 magnetics + Bob-Smith passive network with the abstract ports as subckt pins |
| `test_ethernet.py` | LOCAL electrical-correctness test (offline, runs the board gate slices on just this subsystem) |
| `README.md`        | this file |

The magnetics part is **referenced, never vendored**: the HX5008NLT symbol / footprint /
LCSC come from the global `parts/HX5008NLT/` dossier (`schgen part add C962544`), verified
pad-for-pad against Pulse datasheet PS-0118.001-D Rev A, Sheet 2.

## The abstract interface (the reuse contract)

A consuming project binds these names. Rails classify as POWER/GROUND by name
(`CHASSIS_GND` = GROUND), exactly as real board rails do, so a standalone build and a
bound build share net classes.

### Rails (GROUND)

| abstract | class | meaning / constraint |
|----------|-------|----------------------|
| `CHASSIS_GND` | GROUND | the chassis-ground **island**, kept separate from any signal GND. The Bob-Smith trunk bypasses to it through the single 1n/2kV barrier cap (C5). Star-bonded to signal ground by the consuming board. |

There is **no** signal `GND` and **no** power rail on this sheet — the magnetics are
passive and self-isolating; the only externally-visible non-port net is the chassis island.

### Ports (PORT — all 100 Ω differential pairs)

| abstract | side | meaning |
|----------|------|---------|
| `MDI0_P/N` … `MDI3_P/N` | **CHIP** (PHY-facing) | the four 1000BASE-T differential pairs that face the SoC/PHY across the sheet boundary. Bind these to the host PHY's MDI lanes. |
| `MX0_P/N` … `MX3_P/N`   | **MEDIA** (RJ45-facing) | the four differential pairs that face the RJ45 jack. Bind these to the `rj45_connector` subsystem (a project's `expects` declares which sheet binds them). |

The 1:1 winding is **in phase** (datasheet): `+` couples to `+`, so `MDIn_P <-> MXn_P`.

### Private internal wiring (SIGNAL — never bound)

`MCT1..MCT4` (the four media-side centre taps) and `BS_COMMON` (the shared Bob-Smith
trunk) are private to this sheet. The four **chip-side** centre taps (HX5008NL pins
1/4/7/10) are explicit no-connects — a voltage-mode PHY self-biases its own transmit
common mode.

### Parts (from the global `parts/` lib + inline passives)

| ref | value | lib / part | LCSC |
|-----|-------|-----------|------|
| T1 | HX5008NLT | `parts/HX5008NLT/` (24-pad 1:1 gigabit magnetics) | C962544 (alt C47575004) |
| R1..R4 | 75R | `Device:R` (Bob-Smith) | C4275 |
| C1..C4 | 1n | `Device:C` 1206 / **2 kV** (Bob-Smith HF) | C9196 |
| C5 | 1n | `Device:C` 1206 / **2 kV** (BS trunk → chassis, the isolation barrier) | C9196 |

All five 1n caps are genuine **2 kV** X7R 1206 parts (IEC 60950/62368 hi-pot); the value
is drawn `1n` for schematic economy.

## Consuming it from a project

A project supplies a thin adapter declaring ONE standard `META` dict (the adapter
contract, `schgen.core.subsystem.Meta`) and forwards it:

```python
from subsystems.ethernet import ethernet

META = {
    # abstract subsystem net -> your real board net
    "bind": {
        "CHASSIS_GND": "CHASSIS_GND",
        # chip-side pairs -> your PHY MDI lanes
        "MDI0_P": "PHY_MDI0_P", "MDI0_N": "PHY_MDI0_N",
        # ... MDI1..MDI3 ...
        # media-side pairs -> the RJ45 jack
        "MX0_P": "LINE_MDI_0_P", "MX0_N": "LINE_MDI_0_N",
        # ... MX1..MX3 ...
    },
    # optional: tell the linker which of your sheets binds the media pairs
    "expects": {"MX0_P": "rj45_connector", "MX1_P": "rj45_connector",
                "MX2_P": "rj45_connector", "MX3_P": "rj45_connector"},
}

def circuit():
    return ethernet.circuit(META)
```

The standard `META` keys (`bind` / `expects` / `buses` / `notes`) are universal across
every reusable subsystem — a typo'd top-level key is a hard `CircuitError`, never silently
dropped. `bind` renames every external **in place, order-preserving** (POWER/GROUND/PORT
only — a SIGNAL net is private wiring and is never rebound; a SIGNAL key or a collision is
a hard `CircuitError`). Because the rename preserves net insertion order, parts, refs, NCs
and port-type payloads (incl. each diff pair's `pair_with` complement), **binding to the
exact names a hand-written sheet used yields a byte-identical emitted sheet.** The carrier
adapter is `carrier/subsystems/ethernet.py`.

`expects` threads a project's linker deferral onto a port via `meta.expect_kw`. Only the
**P** net of each media pair need be named; the reciprocal **N** inherits the deferral
automatically (the diff-pair complement carries the same `expect`). This subsystem has no
power rail to budget and no named bus, so `buses` / `notes` carry no library default.

## Design notes (datasheet + electrical contract)

- **Faithful pinout (LAW 0).** The pin map below is the genuine Pulse HX5008NL 24-pad
  dossier, verified pad-for-pad against the datasheet schematic page. Per channel: chip
  pair `TDn` → abstract `MDIn`, media pair `MXn` → abstract `MXn`, media centre tap `MCTn`
  → Bob-Smith trunk, chip centre tap `TCTn` → no-connect.

  ```
      CHIP / PHY side                MEDIA / RJ45 side
      1  TCT1                        24 MCT1
      2  TD1+   3  TD1-              23 MX1+   22 MX1-
      4  TCT2                        21 MCT2
      5  TD2+   6  TD2-              20 MX2+   19 MX2-
      7  TCT3                        18 MCT3
      8  TD3+   9  TD3-              17 MX3+   16 MX3-
      10 TCT4                        15 MCT4
      11 TD4+  12 TD4-              14 MX4+   13 MX4-
  ```

  *History:* an earlier hand-built symbol invented a numbering that used non-existent pins
  25/26 (a hard OPEN on the 4th gigabit pair) and shorted MX4± to ground — gigabit was
  non-functional. The faithful dossier replaced it; the footprint-pad-coverage gate now
  blocks any symbol pin that has no pad.

- **Bob-Smith termination.** Each media centre tap carries a 75 Ω ∥ 1 nF into the shared
  `BS_COMMON` trunk (IEEE 802.3 §40.7.1 / common-mode HF return), and the trunk bypasses
  to the chassis island through one 1 nF / 2 kV barrier cap (C5). **C5 is the isolation
  barrier** — it is the single element bridging signal and chassis domains, and carries the
  same 2 kV hi-pot rating as the per-tap caps.

- **Chip-side centre taps are no-connects.** A voltage-mode-driver PHY self-biases its own
  transmit common mode, and a typical mezzanine exposes only the MDI pairs (no CT-bias path
  crosses the boundary). The four chip-side taps (pins 1/4/7/10) are explicit author
  no-connects.

- **Chassis ground is its own net.** `CHASSIS_GND` is a separate island, star-bonded to
  signal ground by the consuming board — it is not a signal GND.

## Local test vs board gates

`test_ethernet.py` runs the **subsystem-local** slices offline: declared abstract
interface, the pin-faithful HX5008NL mapping, model completeness (every pin netted-or-NC),
the diff-pair typing, the Bob-Smith network (75R ∥ 1n per tap + the 2 kV barrier cap),
part-rating coverage, the SPICE-subckt ↔ netlist passive match, and the bind contract.
**Cross-board** gates stay aggregated at board level and are *not* duplicated here: the
link / port-driver graph (chip pairs face the PHY sheet, media pairs the RJ45-connector
sheet), the full SI 37-pair constraint set, board ERC, and the board netlist merge — all
run by `schgen board`.

```bash
PYTHONPATH=. python3 -m pytest subsystems/ethernet/test_ethernet.py -q
```
