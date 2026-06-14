# Thermal review: the TPS54302 step-down bucks (REVIEW-FLAGGED)

**Surfaced by:** the per-device thermal Tj gate (`schgen/thermal.py`,
verification P2), 2026-06-14. **Status:** waived in the gate (board stays
green) but **flagged for human review** — this is a genuine layout-critical
thermal margin, not a false positive.

## What the gate found

Running `Tj = Ta + Pd·RθJA` against the regulator tree, with the **conservative**
model (datasheet bare-package 2s2p RθJA + an 0.85 efficiency floor), Ta = 50 °C:

| device | rail | Iout | Pd (model) | RθJA | Tj (model) | limit |
|--------|------|------|-----------|------|-----------|-------|
| power:U1 | +VIN(20 V)→+5V | 2.80 A | 2467 mW | 70.6 | **224 °C** | 140 |
| power:U4 | +VIN(20 V)→+5V_SOM | 2.00 A | 1644 mW | 70.6 | **166 °C** | 140 |
| power:U2 | +5V→+3V3 | 2.42 A | 1412 mW | 70.6 | **150 °C** | 140 |

All three are the **TPS54302DDCR** in **SOT-23-6 (DDC, no exposed pad)**.

## Why it is layout-critical (and why it is waived, not ignored)

The gate's RθJA (70.6 °C/W) is the JEDEC **2s2p bare-package** number. A
no-exposed-pad SOT-23 sinks heat almost entirely through its leads, so the
**effective** RθJA depends heavily on the copper around SW / VIN / PGND:

- TI's recommended power layout (large SW/VIN/PGND pours + a thermal-via field
  under the part, 4-layer) takes the effective RθJA to roughly **45–55 °C/W**.
- The TPS54302 efficiency at these operating points is **~88–91%** (datasheet
  curves), not the 0.85 floor the gate assumes — so the real Pd is lower.

With RθJA ≈ 50 °C/W and η ≈ 0.90, the worst case (U1, +VIN→+5V @ 2.8 A) lands
near **Tj ≈ 115–130 °C** — under the 150 °C max but with **modest margin**.
That is acceptable *only if the PCB layout actually achieves it*, hence the
`c.waive_thermal("U1"/"U2"/"U4", …)` in `power.py` carrying that exact caveat.

## Required follow-up (the actual review item)

1. **Confirm** the effective RθJA at layout time — a quick thermal sim (or a
   bench Tj measurement at bring-up, e.g. IR camera / on-die temp) on U1 first,
   since it is the hottest (20 V → 5 V at the full +5V-rail current).
2. If the layout **cannot** hit ~50 °C/W (tight board, no room for pours/vias),
   **switch to an exposed-pad buck** (a QFN/HSOP regulator with an EP gives
   ~35–40 °C/W and removes the risk) — at least for U1, possibly U4.
3. Consider whether the full **+5V rail current** (≈2.8 A) is real worst-case or
   a sum of non-coincident peaks; a lower steady current relaxes U1 directly.

Until (1) is done the thermal gate keeps these three devices on an explicit
waiver, so any *new* device over Tj — or any load creep that pushes a
non-waived part over — still fails the board.
