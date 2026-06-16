# hdmi_rx_term — HDMI-RX TMDS sink termination (carrier-local, SI-HDMIRX-TERM / DEF-6)

A **carrier-local** schgen subsystem: the standard 50 Ω-to-AVCC TMDS source
termination for the HDMI-RX sink, on its own sheet. It binds the `HDMI_RX_*`
ports `hdmi_rx.py` exports (which merge with the FPGA bank-33 pins at board
assembly) and rides the carrier `+3V3` rail directly — board-specific, so no
abstract-interface / bind contract.

## Package contents

| file | role |
|------|------|
| `hdmi_rx_term.py`      | the NETLIST — `circuit()`, carrier nets |
| `hdmi_rx_term.cir`     | SPICE subckt — the 8× 49.9 Ω terminations + AVCC bypass, TMDS lines + AVCC/GND as subckt pins |
| `test_hdmi_rx_term.py` | LOCAL electrical-correctness test (offline; model completeness + the 8× 49.9 Ω-to-AVCC invariant + bypass) |
| `README.md`            | this file |

## Purpose (why this sheet exists)

An HDMI/DVI sink on a Zynq-7000 **HR** I/O bank does **not** self-terminate
TMDS_33: the 7-series HR banks have no on-die TMDS termination, and `DIFF_TERM`
is HP-bank / 2.5 V-only. The receiver MUST therefore present the standard
**50 Ω-to-AVCC** source termination on every single-ended line — **2× 49.9 Ω per
pair to a 3.3 V AVCC node, 8 resistors total** for the three data lanes + clock.
Without this network HDMI RX simply does not work.

It was carried for several rounds as a docstring-only "MANDATORY layout note"
because the resistors belong at the **receiver (FPGA-bank) end**, not on the
connector sheet, and the connector-sheet placer could not anchor an off-sheet
AVCC trunk. **DEF-6** promotes it to a real, netlisted, gate-checked, BOM-counted
network on its own sheet, placed physically next to the bank at layout.

## The 8× 49.9 Ω sink termination

Each of the 8 single-ended TMDS-RX lines gets **one 49.9 Ω 1% resistor to AVCC**:

| ref | TMDS line (port) | termination |
|-----|------------------|-------------|
| R1 | `HDMI_RX_D2_P`  | 49.9R → +3V3 (AVCC) |
| R2 | `HDMI_RX_D2_N`  | 49.9R → +3V3 |
| R3 | `HDMI_RX_D1_P`  | 49.9R → +3V3 |
| R4 | `HDMI_RX_D1_N`  | 49.9R → +3V3 |
| R5 | `HDMI_RX_D0_P`  | 49.9R → +3V3 |
| R6 | `HDMI_RX_D0_N`  | 49.9R → +3V3 |
| R7 | `HDMI_RX_CLK_P` | 49.9R → +3V3 |
| R8 | `HDMI_RX_CLK_N` | 49.9R → +3V3 |

Each port is emitted `c.port(net, "Rn.1", expect="...bank 33 receiver end")` and
merges with the bank-33 pin at link; `Rn.2` ties to `+3V3` (AVCC).

## Parts

| ref | value | part / footprint | LCSC | role |
|-----|-------|------------------|------|------|
| R1-R8 | 49.9R | `Device:R` / R_0603 | C114625 | TMDS sink terminations (YAGEO RC0603FR-0749R9L, 1%) |
| C1 | 100n | `Device:C` / C0603 | C14663 | AVCC HF bypass (50 V X7R) |
| C2 | 1u   | `Device:C` / C0603 | C15849 | AVCC charge reservoir (50 V X5R) |

## Interface (carrier nets)

| net | class | meaning |
|-----|-------|---------|
| `+3V3` | POWER | AVCC = VCCO_33 = +3V3; termination pull + bank-local bypass |
| `GND` | GROUND | bypass cap return |
| `HDMI_RX_{D2,D1,D0,CLK}_{P,N}` | PORT | the 8 single-ended TMDS-RX lines (merge with bank-33) |

## Power-tree budget

- `+3V3` 64 mA: 8× TMDS sink termination, each driven-low line sinks ~8 mA
  through its 49.9 Ω to the source's current-steering output (worst case).

## Notes

- **AVCC = +3V3**: bank 33's VCCO **is** +3V3 (the carrier VCCO_33 rail), so
  terminating to +3V3 tracks the bank I/O supply exactly — the correct TMDS_33
  termination voltage. AVCC is bypassed locally with 100 nF + 1 µF near the bank
  (DEF-G). On this IC-less sheet there is no IC body to hang a decoupling cluster
  off, so the caps anchor as rail-decoupling columns.
- A series ferrite to isolate a dedicated AVCC island from +3V3 is a populate
  option at layout (0 Ω / ferrite in the +3V3 → AVCC trace); it is intentionally
  **not** a distinct netlist node, to keep the termination referenced to the
  proven +3V3 / VCCO_33 rail with no extra single-sourced part.
- Termination R: 49.9 Ω 1% 0603 — low DC error keeps the TMDS common-mode
  centred.

## Local test

`test_hdmi_rx_term.py` runs the subsystem-LOCAL slices offline (model
completeness, the `design_rules` DECAP/EP slice, the 8× 49.9 Ω-to-AVCC census,
the AVCC bypass, the `.cir` ↔ netlist passive match). Cross-board gates stay
aggregated by `schgen board`.

```bash
PYTHONPATH=. python3 -m pytest carrier/subsystems/hdmi_rx_term/test_hdmi_rx_term.py -q
```
