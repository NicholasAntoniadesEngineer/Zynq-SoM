# hdmi_tx — HDMI source port (TPD12S016 + HDMI Type-A receptacle)

This subsystem is the HDMI **source** front-end for the Zynq-7000 SoM carrier: a
TI **TPD12S016** level-shift / ESD-clamp / +5V load-switch device driving a
**HDMI Type-A receptacle** (SOFNG HDMI-019S). The host TMDS lines flow through
the TPD's clamps to the connector, while DDC/CEC/HPD pass through its level
shifters between the controller-side V_CCA domain and the cable's 5 V. It is a
project-agnostic, reusable subsystem: it declares its interface as abstract port
and rail names and knows nothing about any consuming board.

## Interface

A consuming project supplies a single standard `META` dict
(`schgen.core.subsystem.Meta`) and forwards it to `circuit(meta)`. With
`meta=None` the abstract names are kept so `test_hdmi_tx.py` runs offline.

**Rails** (classified POWER/GROUND by name; leading `+` = POWER):

| abstract | class | meaning |
|----------|-------|---------|
| `+VDD_IO`     | POWER  | TPD V_CCA, controller side (3.3 V class). Decoupled 100n + 10u bulk. |
| `+5V`         | POWER  | TPD V_CC5V, cable side — the load-switch input. Decoupled 100n. |
| `GND`         | GROUND | TPD GND pins + receptacle TMDS shields / DDC ground. |
| `CHASSIS_GND` | GROUND | the four HDMI shell legs; star-bonded to `GND` by the consuming board. |

**Ports** (the V_CCA-domain host side that crosses the sheet boundary to the SoC):

| abstract | type | meaning |
|----------|------|---------|
| `TMDS_D2/D1/D0/CLK_P/N` | tmds_pair | the 4 host-side TMDS differential pairs; each flows through a TPD clamp pad to the receptacle (one net per lane). |
| `CEC`                | single | host-side CEC; level-shifted to the cable inside the TPD. |
| `DDC_SCL`, `DDC_SDA` | i2c (bus `HDMI_TX_DDC`, 100 kHz) | host-side HDMI DDC bus. |
| `HPD`                | single | host-side hot-plug-detect; level-shifted from the cable's 5 V. |

Connector-side (B-side) lanes (`HDMI_TX_CON_*`, `HDMI_TX_CON_5V0`) and the
always-on straps (`HDMI_TX_LS_OE`, `HDMI_TX_CT_HPD`) are private SIGNAL wiring,
never part of the contract and never bound.

```python
from subsystems.hdmi_tx import hdmi_tx

META = {
    "bind": {
        "+VDD_IO": "+3V3_HDMI_TX", "+5V": "+5V_HDMI_TX",
        "GND": "GND", "CHASSIS_GND": "CHASSIS_GND",
        "TMDS_D2_P": "MY_TMDS_2_P", "TMDS_D2_N": "MY_TMDS_2_N",
        # ... D1 / D0 / CLK ...
        "CEC": "MY_CEC", "DDC_SCL": "MY_SCL", "DDC_SDA": "MY_SDA",
        "HPD": "MY_HPD",
    },
    # optional: tell the linker which sheet binds a deferred port
    # (the P line of each TMDS pair carries the pair's deferral)
    "expects": {"TMDS_D2_P": "my_connector", "DDC_SCL": "my_connector"},
    # optional house-style overrides
    "buses": {"ddc": "MY_DDC_BUS"},
    "notes": {"draws_vcca": "...", "draws_5v": "..."},
}

def circuit():
    return hdmi_tx.circuit(META)
```

`bind` renames every external net in place, order-preserving (POWER/GROUND/PORT
only); a SIGNAL key, a collision, or a typo'd top-level key is a hard
`CircuitError`. The carrier adapter is `carrier/subsystems/hdmi_tx.py`.

## Design

Reference circuit: TI TPD12S016 (SLLSE96F) Figure 15, "HDMI source using one
GPIO", with `CT_HPD` and `LS_OE` strapped HIGH.

- **Part selection.** The TPD12S016 (U1) integrates the three things an HDMI
  source needs at the connector: ESD clamps on the 8 TMDS lines, bidirectional
  level shifters for DDC/CEC/HPD (V_CCA ↔ cable 5 V), and a current-limited +5V
  load switch (55 mA limit, DS 7.3.10) sourcing the cable. J1 is the HDMI
  Type-A receptacle.
- **Flow-through TMDS.** Each of the 8 TMDS lines is **one net** running
  source → TPD clamp pad → receptacle. The faithful TPD symbol carries each
  clamp as its own A/B pin number (DS pin map 15..23); the port joins the A pin
  and the receptacle pin so there is exactly one net per lane. The four pairs
  are typed `tmds_pair` for SI-constraint pairing.
- **Level-shifted control.** CEC/DDC/HPD pass through the TPD level shifters:
  the A-side nets are the abstract V_CCA-domain ports; the B-side nets
  (`HDMI_TX_CON_*`) run at the cable's 5 V to the receptacle.
- **Integrated DDC pull-ups.** DDC/CEC/HPD pull-ups are integrated in the
  TPD12S016 (DS 7.3.9/7.3.15) — no external resistors, and no EDID EEPROM (a
  source reads the sink's EDID). The subsystem waives the I2C-pull-up design
  rule on `DDC_SCL`/`DDC_SDA` for this reason.
- **Always-on straps.** `LS_OE` and `CT_HPD` are each pulled HIGH via 10k to
  V_CCA (DS Fig 15 / 8.2.1) so the level shifters and the +5V load switch are
  always enabled.
- **Cable +5V.** The integrated current-limited switch drives receptacle pin 18
  from `+5V`; 100n HF + 1u bulk at the connector per HDMI 1.4 Sec 4.2.7.
- **Rails / decoupling.** +VDD_IO (V_CCA) and +5V (V_CC5V) each carry 100n per
  DS Fig 15; +VDD_IO additionally carries a 10u bulk. A consuming board may gate
  either rail upstream.
- **Grounds.** TPD GND pins and the receptacle TMDS shields / DDC ground tie to
  `GND`; the four shell legs go to `CHASSIS_GND`, star-bonded to `GND` by the
  consuming board. Pin 14 (HEC/Utility) is reserved → author no-connect
  (HDMI 1.4: N.C. on non-HEAC devices).

## Parts

| ref | value | lib / part | LCSC |
|-----|-------|-----------|------|
| U1 | TPD12S016PWR | `parts/TPD12S016PWR/` | C201665 |
| J1 | HDMI-019S    | `parts/HDMI-019S/`    | C111617 |
| C1 | 100n | `Device:C` (V_CCA decoupling) | C14663 |
| C2 | 100n | `Device:C` (V_CC5V decoupling) | C14663 |
| C3 | 100n | `Device:C` (cable +5V HF bypass) | C14663 |
| C4 | 1u   | `Device:C` (cable +5V bulk) | C15849 |
| C5 | 10u  | `Device:C` (V_CCA bulk, 0805) | C15850 |
| R1 | 10k  | `Device:R` (LS_OE strap) | C25804 |
| R2 | 10k  | `Device:R` (CT_HPD strap) | C25804 |

## Build & test

`test_hdmi_tx.py` runs the subsystem-local slices offline: the abstract
interface and port types, model completeness (every pin netted-or-NC),
decoupling/strap completeness, part-rating coverage, the SPICE-subckt ↔ netlist
passive match, and the bind contract. Cross-board gates (link graph, power-tree
headroom, ERC, netlist merge) run at board level via `schgen board`.

```bash
PYTHONPATH=. python3 -m pytest subsystems/hdmi_tx/test_hdmi_tx.py -q
```
