# hdmi_tx — carrier ADAPTER for the reusable TPD12S016 HDMI-source subsystem

THIN ADAPTER. The portable circuit lives in the project-agnostic library
[`subsystems/hdmi_tx/`](../../../subsystems/hdmi_tx/README.md) (netlist + README
+ SPICE + local test). This package is the carrier-specific GLUE: it imports the
library subsystem and BINDS its abstract ports/rails to the carrier's REAL net
names via a `META` contract, returning the bound `Circuit`. The board build
discovers it exactly as the flat layout did (`circuit()` exposed via
`__init__`), and the binding reproduces the EXACT net names the hand-written
sheet used, so the emitted `carrier/schematic/hdmi_tx.kicad_sch` and its golden
render stay byte-identical.

## Package contents (4-artifact parity with the generic library)

| file | role |
|------|------|
| `hdmi_tx.py`      | the THIN ADAPTER — `META` (bind/expects) + `circuit()` returning `_lib.circuit(META)` |
| `__init__.py`     | re-exports `circuit, META` so discovery + the bind test import the package |
| `hdmi_tx.cir`     | thin SPICE subckt — the CARRIER external nets as subckt pins, pointing at the library `.cir` for the real passive network |
| `test_hdmi_tx.py` | byte-identical-BIND guard — adapter nets == `_lib.circuit(META)` nets; carrier names appear; no abstract leak |
| `README.md`       | this file |

## The carrier bind (generic subsystem + META)

The generic subsystem's abstract INTERFACE is mapped to the carrier nets by
`META["bind"]`:

| abstract net | carrier net | role |
|--------------|-------------|------|
| `+VDD_IO`  | `+3V3_HDMI_TX` | V_CCA controller-side rail (gated module rail; SY6280 load switch on `bringup_power_gating`) |
| `+5V`      | `+5V_HDMI_TX`  | V_CC5V load-switch INPUT, cable side (gated module rail) |
| `GND`      | `GND`          | identity |
| `CHASSIS_GND` | `CHASSIS_GND` | identity (four HDMI shell legs to the chassis island) |
| `TMDS_D2/1/0/CLK_P/N` | `ZYNQ_HDMI_TX_TMDS_2/1/0/CLK_P/N` | 8 differential TMDS lines from the Zynq PL |
| `CEC`      | `ZYNQ_HDMI_TX_CEC` | A-side CEC to the Zynq PL |
| `DDC_SCL`  | `ZYNQ_HDMI_TX_SCL` | HDMI DDC (I2C); pull-ups INTEGRATED in the TPD (library waives them) |
| `DDC_SDA`  | `ZYNQ_HDMI_TX_SDA` | HDMI DDC (I2C) |
| `HPD`      | `ZYNQ_HDMI_TX_HPD` | A-side hot-plug-detect to the Zynq PL |

`META["expects"]` declares the J2-deferred ports (the eight TMDS lines + the four
control lines bind on the generated J2 sheet, som_conn_gen wave-3 PL
FUNCTION_MAP). Buses/notes are left at the library defaults (they already equal
the carrier's house-style HDMI_TX_DDC bus name + power-tree draw notes), so the
carrier's derived artifacts stay byte-identical without an override.

The full per-net rationale lives in the adapter module docstring
(`hdmi_tx.py`); the device + passive network is documented in the library
README at [`../../../subsystems/hdmi_tx/README.md`](../../../subsystems/hdmi_tx/README.md).

## Local test

```bash
PYTHONPATH=. python3 -m pytest carrier/subsystems/hdmi_tx/test_hdmi_tx.py -q
```

The board-level gates (full power tree, board ERC, the cross-sheet link/port-
driver graph, the golden renders) stay aggregated by `schgen board`.
