# hdmi_rx_term — HDMI-RX TMDS sink termination

A carrier-local schgen subsystem providing the standard 50 Ω-to-AVCC TMDS sink
termination for the HDMI-RX receiver on the Zynq-7000 SoM carrier. A 7-series HR
I/O bank does not self-terminate TMDS_33, so the receiver presents an external
49.9 Ω termination to a 3.3 V AVCC node on every single-ended TMDS line. The
network lives on its own sheet and is placed physically next to FPGA bank 33 at
layout.

## Interface

This is a carrier-local subsystem (no abstract-interface / bind contract); it
drives carrier nets directly.

| net | class | meaning |
|-----|-------|---------|
| `HDMI_RX_{D2,D1,D0,CLK}_{P,N}` | PORT | the 8 single-ended TMDS-RX lines; each is emitted as `c.port(net, "Rn.1", expect=...bank 33 receiver end)` and merges with the bank-33 pin at link |
| `+3V3` | POWER | AVCC = VCCO_33 = +3V3; the node every line terminates to, plus bank-local bypass |
| `GND` | GROUND | bypass cap return |

Power-tree budget: `+3V3` draws 0.064 A — 8 TMDS sink terminations, each
driven-low line sinking ~8 mA through its 49.9 Ω to the source's current-steering
output (worst case).

## Design

- **External termination is mandatory.** The 7-series HR banks have no on-die
  TMDS termination, and `DIFF_TERM` is HP-bank / 2.5 V-only. The HDMI/DVI sink
  must therefore present the standard 50 Ω-to-AVCC source termination on every
  single-ended line: 2× 49.9 Ω per pair, 8 resistors total across the three data
  lanes plus clock. Without this network HDMI RX does not work.

- **8× 49.9 Ω 1% to AVCC.** Each of the 8 TMDS-RX lines (`HDMI_RX_D2/D1/D0/CLK`
  × P/N) gets one 49.9 Ω 1% 0603 resistor (R1–R8) from the line to the AVCC node.
  The 1% tolerance keeps DC error low so the TMDS common-mode stays centred.

- **AVCC = +3V3.** Bank 33's VCCO is +3V3 (the carrier VCCO_33 rail), so
  terminating to +3V3 tracks the bank I/O supply exactly — the correct TMDS_33
  termination voltage. AVCC is not a distinct netlist node: keeping the
  termination referenced to the proven +3V3 / VCCO_33 rail avoids an extra
  single-sourced part. A series ferrite to isolate a dedicated AVCC island is a
  populate option at layout (fit a 0 Ω / ferrite in the +3V3 → AVCC trace).

- **Bank-local AVCC bypass.** 100 nF HF (C1) + 1 µF reservoir (C2) from +3V3 to
  GND, placed in the termination island next to bank 33 to absorb the ~64 mA load
  swing against AVCC. On this IC-less sheet there is no IC body for a decoupling
  cluster, so the caps anchor as rail-decoupling columns (place.py
  `_rail_decoupling_columns`): rail symbol on top, cap stacked down to a GND foot.

## Parts

| ref | value | lib/part | footprint | LCSC |
|-----|-------|----------|-----------|------|
| R1–R8 | 49.9R | `Device:R` | R_0603_1608Metric | C114625 |
| C1 | 100n | `Device:C` | C_0603_1608Metric | C14663 |
| C2 | 1u | `Device:C` | C_0603_1608Metric | C15849 |

R1–R8 map to the TMDS lines in order: D2_P, D2_N, D1_P, D1_N, D0_P, D0_N, CLK_P,
CLK_N. Termination R is YAGEO RC0603FR-0749R9L (49.9 Ω 1%); C1 is 50 V X7R, C2 is
50 V X5R.

## Build & test

`test_hdmi_rx_term.py` runs the subsystem-local slices offline: model
completeness, the 8× 49.9 Ω-to-AVCC census, the AVCC bypass, and the `.cir` ↔
netlist passive match.

```bash
PYTHONPATH=. python3 -m pytest carrier/subsystems/hdmi_rx_term/test_hdmi_rx_term.py -q
```
