# rj45_connector — plain 8P8C RJ45 jack (reusable subsystem)

A project-agnostic, self-contained schgen subsystem: the Kinghelm
**KH-5224-8P8C-D** plain (transformerless) shielded 8P8C RJ45 jack with integrated
housing LEDs, the line-side connector **downstream of an Ethernet magnetics
block** (the discrete 1000BASE-T magnetics + Bob-Smith termination live in the
sibling `subsystems/ethernet/` package). It declares its interface as **abstract**
port + rail names and knows nothing about any board; a consuming project supplies
a **bind map** (`abstract -> real net`) to drop it onto real nets.

## Package contents

| file | role |
|------|------|
| `rj45_connector.py`      | the NETLIST — `circuit(meta=None)`, abstract ports/rails |
| `rj45_connector.cir`     | SPICE subckt — the passive network (the two 330R LED series resistors) with the abstract ports as subckt pins |
| `test_rj45_connector.py` | LOCAL electrical-correctness test (offline) |
| `README.md`      | this file |

The jack is **referenced, never vendored**: the KH-5224-8P8C-D symbol/footprint/
LCSC come from the global `parts/KH-5224-8P8C-D/`.

## The abstract interface (the reuse contract)

A consuming project binds these names. Rails classify as POWER/GROUND by name
(the `+` prefix + `GND`/`CHASSIS_GND`), exactly as real board rails do, so a
standalone build and a bound build share net classes.

### Rails (POWER / GROUND)

| abstract | class | meaning / constraint |
|----------|-------|----------------------|
| `+VLED`       | POWER  | LED indicator supply for the two integrated housing LEDs (330R each, ~4 mA). Should be an **always-on** rail so the port-present indicator lights regardless of any module enable. |
| `GND`         | GROUND | signal ground (the LED cathodes return here). |
| `CHASSIS_GND` | GROUND | chassis-ground island for the shell/shield (J1.13) + the four M3 corner mounting holes. A **separate** net from signal GND — the consuming board star-bonds it. |

### Ports (PORT)

| abstract | type | meaning |
|----------|------|---------|
| `RJ45_MDI0_P/N` | diff_pair 100 Ω | line-side pair BI_DA, T568 contacts 1,2 |
| `RJ45_MDI1_P/N` | diff_pair 100 Ω | line-side pair BI_DB, T568 contacts 3,6 |
| `RJ45_MDI2_P/N` | diff_pair 100 Ω | line-side pair BI_DC, T568 contacts 4,5 |
| `RJ45_MDI3_P/N` | diff_pair 100 Ω | line-side pair BI_DD, T568 contacts 7,8 |

The four line-side MDI pairs are the same pairs the `ethernet` magnetics
subsystem exposes **media-side** (its `MXn` ports). Binding both subsystems to
the same real nets resolves the magnetics' media-side linker deferral to BOUND on
both sheets.

The two housing-LED anode nodes (`RJ45_LED_L`, `RJ45_LED_R`) are **private SIGNAL
wiring** (the 330R → integrated-LED-anode node) and are never part of the
contract — there is **no discrete LED part**, the diode lives inside the
connector body.

### Parts (from the global `parts/` lib + inline passives)

| ref | value | lib / part | LCSC |
|-----|-------|-----------|------|
| J1 | KH-5224-8P8C-D | `parts/KH-5224-8P8C-D/` | C2828085 |
| R1 | 330R | `Device:R` (LED-L series) | C23138 |
| R2 | 330R | `Device:R` (LED-R series) | C23138 |
| H1..H4 | MountingHole_M3 | `Mechanical:MountingHole_Pad` (chassis bond, BOM-excluded) | — |

## Consuming it from a project

A project supplies a thin adapter declaring ONE standard `META` dict (the adapter
contract, `schgen.core.subsystem.Meta`) and forwards it:

```python
from subsystems.rj45_connector import rj45_connector

META = {
    # abstract subsystem net -> your real board net
    "bind": {
        "+VLED": "+3V3", "GND": "GND", "CHASSIS_GND": "CHASSIS_GND",
        "RJ45_MDI0_P": "ETH_LINE_MDI_0_P", "RJ45_MDI0_N": "ETH_LINE_MDI_0_N",
        "RJ45_MDI1_P": "ETH_LINE_MDI_1_P", "RJ45_MDI1_N": "ETH_LINE_MDI_1_N",
        "RJ45_MDI2_P": "ETH_LINE_MDI_2_P", "RJ45_MDI2_N": "ETH_LINE_MDI_2_N",
        "RJ45_MDI3_P": "ETH_LINE_MDI_3_P", "RJ45_MDI3_N": "ETH_LINE_MDI_3_N",
    },
    # optional house-style override (keep your power-tree note byte-stable)
    "notes": {"draws": "RJ45 housing LEDs (2x 330R port-present indicator)"},
}

def circuit():
    return rj45_connector.circuit(META)
```

The four standard `META` keys (`bind` / `expects` / `buses` / `notes`) are
universal across every reusable subsystem — a typo'd top-level key is a hard
`CircuitError`, never silently dropped. `bind` renames every external **in place,
order-preserving** (POWER/GROUND/PORT only — a SIGNAL net is private wiring and is
never rebound; a SIGNAL key or a collision is a hard `CircuitError`). Because the
rename preserves net insertion order, parts, refs, NCs and port-type payloads,
**binding to the exact names a hand-written sheet used yields a byte-identical
emitted sheet.** The carrier adapter is `carrier/subsystems/rj45_connector.py`.

## Design notes (datasheet + dossier)

- **Plain jack, external magnetics.** The KH-5224-8P8C-D has **no transformer**
  (the EasyEDA pin table is 13 pins: 8 contacts + 4 LED + shell — a magjack would
  expose 16+ winding/centre-tap pins). The 1000BASE-T magnetics + Bob-Smith
  termination live in `subsystems/ethernet/`; the line-side MDI pairs come
  straight off the magnetics secondary onto the eight contacts.
- **Contact → MDI order.** IEEE 802.3 / TIA-568 1000BASE-T: BI_DA = 1,2; BI_DB =
  3,6; BI_DC = 4,5; BI_DD = 7,8. Each pair is a 100 Ω `diff_pair`.
- **Housing LEDs are a power-on indicator, not link/act.** The two LEDs are
  **integrated** in the jack (symbol pins LED-x+/LED-x-). They are driven steady
  off `+VLED` through one 330R each (~(3.3−2.0)/330 ≈ 4 mA) — a port-present
  indication, **not** a PHY-driven link/activity blink (the passive magnetics
  expose no PHY LED logic on this sheet). No discrete `Device:LED` is added (that
  would put two LEDs in series).
- **Chassis bond.** The shell/shield (J1.13) and four plated M3 corner mounting
  holes bond to `CHASSIS_GND`, a separate net from signal GND, star-bonded by the
  consuming board. All `CHASSIS_GND` fab-art is co-located on this sheet.

## Local test vs board gates

`test_rj45_connector.py` runs the **subsystem-local** slices offline: the declared
abstract interface, the faithful T568 contact→MDI mapping, model completeness
(every pin netted-or-NC), the LED-indicator + chassis-bond topology, the
design-rule slice (no decap/EP/strap on a passive connector), part-rating
coverage, the SPICE-subckt ↔ netlist passive match, and the bind contract.
**Cross-board** gates stay aggregated at board level (not duplicated here): the
link / port-driver graph (the line-side pairs face the ethernet magnetics sheet),
the full SI pair set, the full power-tree headroom, board ERC, and the board
netlist merge — all run by `schgen board`.

```bash
PYTHONPATH=. python3 -m pytest subsystems/rj45_connector/test_rj45_connector.py -q
```
