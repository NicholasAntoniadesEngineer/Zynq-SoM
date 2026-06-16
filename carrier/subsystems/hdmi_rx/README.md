# hdmi_rx — carrier ADAPTER for the reusable HDMI-A sink subsystem

THIN ADAPTER. The portable circuit lives in the project-agnostic library
[`subsystems/hdmi_rx/`](../../../subsystems/hdmi_rx/README.md) (netlist + README
+ SPICE + local test). This package is the carrier-specific GLUE: it imports the
library subsystem and BINDS its abstract ports/rails to the carrier's REAL net
names via a `META` contract, returning the bound `Circuit`. The board build
discovers it exactly as the flat layout did (`circuit()` exposed via
`__init__`), and the binding reproduces the EXACT net names the hand-written
sheet used, so the emitted `carrier/schematic/hdmi_rx.kicad_sch` and its golden
render stay byte-identical.

J1 draws the FAITHFUL `parts/HDMI-019S/` dossier symbol (the "0 hand-built
symbols" migration is COMPLETE — the old `schgen:HDMI_A_RX` hand symbol is gone
and `symbol_law.PENDING_MIGRATION` is empty). Binding does not touch `lib_id`.

## Package contents (4-artifact parity with the generic library)

| file | role |
|------|------|
| `hdmi_rx.py`      | the THIN ADAPTER — `META` (bind/expects/notes) + `circuit()` returning `_lib.circuit(META)` |
| `__init__.py`     | re-exports `circuit, META` so discovery + the bind test import the package |
| `hdmi_rx.cir`     | thin SPICE subckt — the CARRIER external nets as subckt pins, pointing at the library `.cir` for the real passive network |
| `test_hdmi_rx.py` | byte-identical-BIND guard — adapter nets == `_lib.circuit(META)` nets; carrier names appear; no abstract leak |
| `README.md`       | this file |

## The carrier bind (generic subsystem + META)

The generic subsystem's abstract INTERFACE is mapped to the carrier nets by
`META["bind"]`:

| abstract net | carrier net | role |
|--------------|-------------|------|
| `+VDD_LOGIC` | `+3V3_HDMI_RX` | gated module rail; only the CEC 27k pull-up sits here (EEPROM + EDID WC# are cable-5V-fed) |
| `GND`        | `GND`          | identity (TMDS shields + DDC/CEC ground + EEPROM ground + ESD GND pads) |
| `CHASSIS_GND`| `CHASSIS_GND`  | identity (four HDMI shell legs; star-bonded to GND elsewhere) |
| `TMDS_RX_D2/D1/D0/CLK_P/N` | `HDMI_RX_D2/D1/D0/CLK_P/N` | four RX TMDS pairs, DC-coupled connector -> Zynq HR bank 33 |
| `HDMI_5V_DET`| `HDMI_RX_5V_DET` | cable-5V presence detect (10k/15k divider, LVCMOS33-safe) |
| `CEC`        | `HDMI_RX_CEC`  | 3V3-domain CEC with the spec 27k pull-up to `+3V3_HDMI_RX` |

The DDC I2C (`HDMI_RX_SDA/SCL`), HPD assert (`HDMI_RX_HPD`) and the cable-5V
quasi-rail (`HDMI_RX_5V`) stay PRIVATE SIGNAL wiring inside the library (they
run connector<->EEPROM<->ESD on this sheet), so they are NOT in the bind
contract and keep their library names (identical to the carrier).

`META["expects"]` declares the J2/J3-deferred ports (TMDS + 5V-det + CEC bind on
the generated J2/J3 sheets, som_conn_gen wave-3 FPGA bank function map).
`META["notes"]` cites the carrier's house-style power-tree draw wording. The
TMDS sink termination (2x49.9R/pair to AVCC) lives at the FPGA-bank end, NOT this
sheet (SI-HDMIRX-TERM).

The full per-net rationale lives in the adapter module docstring
(`hdmi_rx.py`); the device + passive network is documented in the library
README at [`../../../subsystems/hdmi_rx/README.md`](../../../subsystems/hdmi_rx/README.md).

## Local test

```bash
PYTHONPATH=. python3 -m pytest carrier/subsystems/hdmi_rx/test_hdmi_rx.py -q
```

The board-level gates (full power tree, board ERC, the cross-sheet link/port-
driver graph, the golden renders) stay aggregated by `schgen board`.
