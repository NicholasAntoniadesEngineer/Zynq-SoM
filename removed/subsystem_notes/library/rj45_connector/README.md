# rj45_connector — plain 8P8C RJ45 jack with integrated housing LEDs

A project-agnostic, self-contained schgen subsystem: the Kinghelm **KH-5224-8P8C-D**
plain (transformerless) shielded 8P8C RJ45 jack, the line-side connector downstream
of an Ethernet magnetics block. On the Zynq-7000 SoM carrier it is the physical
network jack; the discrete 1000BASE-T magnetics and Bob-Smith termination live in
the sibling `subsystems/ethernet/` package, so the eight contacts take the line-side
MDI pairs straight off the magnetics secondary. It declares its interface as abstract
port + rail names and knows nothing about any board; a consuming project supplies a
bind map to drop it onto real nets.

## Interface

A consuming project supplies one standard `META` dict (`schgen.core.subsystem.Meta`)
and forwards it; `bind` renames every externally-visible net in place, order-preserving,
so binding to the names a hand-written sheet used yields a byte-identical emitted sheet.
With `meta=None` the subsystem keeps its abstract names for the offline local test.

Rails (`+VLED`, `GND`, `CHASSIS_GND`) classify as POWER/GROUND by name. Ports are the
four 100 Ω differential line-side MDI pairs. The two housing-LED anode nodes
(`RJ45_LED_L`, `RJ45_LED_R`) are private SIGNAL wiring and are never part of the contract.

### Rails

| abstract | class | meaning |
|----------|-------|---------|
| `+VLED`       | POWER  | LED indicator supply for the two integrated housing LEDs (330R each, ~4 mA). Should be an always-on rail so the indicator lights regardless of any module enable. |
| `GND`         | GROUND | signal ground; the LED cathodes return here (J1.10, J1.12). |
| `CHASSIS_GND` | GROUND | chassis-ground island for the shell/shield (J1.13). A separate net from signal GND, star-bonded by the consuming board. |

### Ports

| abstract | type | contacts |
|----------|------|----------|
| `RJ45_MDI0_P/N` | diff_pair 100 Ω | BI_DA, T568 contacts 1,2 |
| `RJ45_MDI1_P/N` | diff_pair 100 Ω | BI_DB, T568 contacts 3,6 |
| `RJ45_MDI2_P/N` | diff_pair 100 Ω | BI_DC, T568 contacts 4,5 |
| `RJ45_MDI3_P/N` | diff_pair 100 Ω | BI_DD, T568 contacts 7,8 |

These four line-side pairs are the same pairs the `ethernet` magnetics subsystem
exposes media-side (its `MXn` ports). Binding both subsystems to the same real nets
resolves the magnetics' media-side linker deferral to BOUND on both sheets; a project
attaches that deferral per port via `META["expects"]` (naming only the P net of a pair;
the reciprocal N inherits it).

```python
from subsystems.rj45_connector import rj45_connector

META = {
    "bind": {
        "+VLED": "+3V3", "GND": "GND", "CHASSIS_GND": "CHASSIS_GND",
        "RJ45_MDI0_P": "ETH_LINE_MDI_0_P", "RJ45_MDI0_N": "ETH_LINE_MDI_0_N",
        "RJ45_MDI1_P": "ETH_LINE_MDI_1_P", "RJ45_MDI1_N": "ETH_LINE_MDI_1_N",
        "RJ45_MDI2_P": "ETH_LINE_MDI_2_P", "RJ45_MDI2_N": "ETH_LINE_MDI_2_N",
        "RJ45_MDI3_P": "ETH_LINE_MDI_3_P", "RJ45_MDI3_N": "ETH_LINE_MDI_3_N",
    },
    "notes": {"draws": "RJ45 housing LEDs (2x 330R port-present indicator)"},
}

def circuit():
    return rj45_connector.circuit(META)
```

## Design

- **Plain jack, external magnetics.** The KH-5224-8P8C-D has no transformer: its CAD
  pin table is 13 pins (1–8 = the eight T568 contacts, 9/10 = left LED, 11/12 = right
  LED, 13 = SHELL), where a magjack would expose 16+ winding/centre-tap pins. The jack
  is therefore a transformerless 8P8C and relies on the `ethernet` subsystem for the
  1000BASE-T magnetics and Bob-Smith termination. It is a shielded, through-hole,
  LED jack — the highest-stock plain shielded LED 8P8C in the catalogue.
- **Contact → MDI mapping.** IEEE 802.3 / TIA-568 1000BASE-T order: BI_DA = contacts
  1,2; BI_DB = 3,6; BI_DC = 4,5; BI_DD = 7,8. Each pair is declared a 100 Ω `diff_pair`
  via `port_type`, so the SI gates see the line-side impedance constraint.
- **Housing LEDs as a power-on indicator.** The two LEDs are integrated in the jack
  body (symbol pins LED-x+/LED-x-), so no discrete `Device:LED` is added — placing one
  would put two LEDs in series. Each LED anode is driven steady from `+VLED` through one
  330R series resistor (~(3.3−2.0)/330 ≈ 4 mA), cathode to `GND`. This is an honest
  port-present indication, not a PHY-driven link/activity blink: the passive magnetics
  expose no PHY LED logic on this sheet. The two 330R/anode nodes (`RJ45_LED_L`/`_R`)
  are private SIGNAL wiring.
- **Chassis bond.** The shell/shield (J1.13) ties to `CHASSIS_GND`, a separate net from
  signal GND that the consuming board star-bonds. This shell tie is the only
  `CHASSIS_GND` item on the sheet; M3 corner mounting holes live on the consuming
  board's mechanical sheet, kept out of this jack's per-subsystem ratsnest cluster.
- **Power budget.** The subsystem declares an `+VLED` draw of ~8 mA (two 330R indicator
  LEDs) into the board power tree; a project may override the prose via `META["notes"]["draws"]`.

## Parts

| ref | value | lib / part | LCSC |
|-----|-------|-----------|------|
| J1 | KH-5224-8P8C-D | `parts/KH-5224-8P8C-D/` | C2828085 |
| R1 | 330R | `Device:R` (LED-L series, `R_0603_1608Metric`) | C23138 |
| R2 | 330R | `Device:R` (LED-R series, `R_0603_1608Metric`) | C23138 |

## Build & test

`test_rj45_connector.py` runs the subsystem-local slices offline: the abstract
interface, the T568 contact→MDI mapping, model completeness (every pin netted or NC),
the LED-indicator + chassis-bond topology, the passive-connector design-rule slice,
part-rating coverage, the SPICE-subckt ↔ netlist passive match, and the bind contract.
Cross-board gates (link/port-driver graph, full SI pair set, power-tree headroom, ERC,
netlist merge) run at board level via `schgen board`.

```bash
PYTHONPATH=. python3 -m pytest subsystems/rj45_connector/test_rj45_connector.py -q
```
