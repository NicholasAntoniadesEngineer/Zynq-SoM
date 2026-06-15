# Carrier BOM — Sourcing Risk + Cost Assessment

Live JLCPCB/LCSC sourcing review of every distinct BOM part: stock, library
class (Basic vs Extended), unit price, second-source availability, and risk.
Data source: the JLCPCB parts API (`jlcpcb.com/.../selectSmtComponentList`,
the same endpoint `schgen preflight` and the parts browser use) + LCSC product
pages, queried live. Scope: `carrier/manufacturing/bom_jlc.csv`.

This report is the primary deliverable. One safe drop-in swap was APPLIED
(C1591 -> C14663, the 100 nF high-runner); all other findings are
RECOMMENDATIONS ONLY because no clean drop-in exists (footprint / pin-map /
class would change, or the value has no JLC-Basic equivalent).

## Summary

| Metric | Value |
|--------|------:|
| Distinct parts (post-swap) | 94 |
| Basic | 30 |
| Extended | 64 |
| Extended that are Preferred (feeder-fee EXEMPT) | 2 (C25750, C7562) |
| Extended that incur a feeder fee | 62 |
| Est. Extended feeder-loading fee (62 x $3) | $186 one-time |
| Est. unit-parts cost / board (qty>=100 price tier) | ~$51 |
| Parts with <5,000 stock | 15 |
| Parts with <300 stock (procurement-critical) | 6 |

JLCPCB charges a one-time **$3 feeder-loading fee per unique Extended part**
(Basic and Preferred are exempt); this is on top of the base assembly setup
($25/side). Reducing the Extended *line count* is what reduces this fee — the
per-unit price of the swapped passives is already sub-cent and not the driver.

### Where the cost actually is

The $51/board parts cost is dominated by a handful of parts, NOT the Extended
line count: the Samtec FMC connector **C2836665 (ASP-134603-01) at $14.85 ea**
is ~29% of the board BOM by itself, followed by CH347T ($2.19), TPS26631
($3.50), RV-3028 RTC ($1.51), CP2102N ($1.37), LM61460 buck ($1.13), the two
INA3221 ($1.04 ea). These are function-defining single-source ICs/connectors —
none has a cheaper drop-in.

## Applied swap (verified clean drop-in)

| # | Net effect | Old LCSC | New LCSC | Proof |
|---|-----------|----------|----------|-------|
| 1 | 100 nF 0603 decoupling (83 placements) consolidated onto one Basic line | **C1591** (Samsung CL10B104KB8NNNC, Extended, 2.08 M stock) | **C14663** (YAGEO CC0603KRX7R9BB104, **Basic**, 17.8 M stock) | IDENTICAL spec: 100 nF / 50 V / X7R / +-10% / 0603. Same `Capacitor_SMD:C_0603_1608Metric` footprint, same `Device:C` symbol -> netlist & render byte-identical. `ratings.py` already carries C14663 with identical ratings (v_max 50 V, X7R, 125 C). Removes 1 Extended feeder fee (-$3) + cheaper unit ($0.0094 vs $0.0114) + de-risks stock 8.5x. |

The board already used C14663 for 12 of its 100 nF positions (Basic) while 71
others used the Extended C1591 — pure duplication of an identical part. The
swap merges both into a single 83-piece Basic line. This is the single biggest
feeder-fee + stock-risk win available, and the ONLY clean Basic drop-in on the
whole board.

Gate evidence (post-swap): `schgen part-rules` PASS (132 checks, 0 findings);
`schgen board` PASS (33 sheets, golden renders 33/33 match, DRC 0 errors);
`scripts/check.sh` PASS (selftest 59/59 mutants, m1_rc, pytest 219). No render
changed (LCSC is a `(hide yes)` property -> not drawn).

## Recommendations (REPORT-ONLY — not applied)

None of these are clean drop-ins (footprint, pin-map, MPN identity, or class
would change), so applying them blindly would risk the netlist (LAW 0). They
are flagged for the owner to evaluate against the real footprint/datasheet.

### A. Procurement-critical low stock (<300) — single-sourced, NO clean alternate

| Part | LCSC | Stock | Risk & note |
|------|------|------:|-------------|
| HX5008NLT ethernet magnetics | C962544 | **10** | Highest risk on the board. The exact SOIC-24W (7.5x15.4 mm) part is nearly out. Nearest in stock: HX5008NLTP-CND (C47575004, 418) and HX5008FNLT (C968751, 354) — **different packages** (SMD-24P 15.1x13.2 / SOP-24-13.2 mm); HanRun HY602401/HY602403 are 24-pin 350 uH equivalents but again a different footprint. ANY swap needs a footprint + pinout re-verify against the magnetics drawing. **Do not ship without confirming this line can be filled** — consider buying ahead or designing in a second footprint. |
| DS1024-2x6R2 Pmod connector | C49284652 | **45** | qty 3 needed; only listing for this exact 2x6 2.54 mm part. Generic 2x6 2.54 mm headers exist but with different mechanicals/footprint. Buy-ahead or qualify a generic 2.54 mm 2x6 header footprint. |
| TLV75725PDYDR (FMC LDO) | C35209004 | 133 | Same-die SOT-23-5 variants are far better stocked (TLV75725PDBVR-MS C54539936 = 3,000) but a **different footprint** than the PDYDR thermal-pad part. The WSON same-package PDRVR (C507271) is worse (16). Re-verify footprint before any move. |
| TPS26631PWPR (eFuse) | C2866319 | 177 | TPS26631PWPT (C2832195, 205) is the SAME HTSSOP-20 package (tape vs reel suffix) — a genuine same-footprint alternate, but only marginally more stock. The RGER/RGET VQFN variants are a different footprint. |
| TPD6E001RSER (uSD ESD) | C1973318 | 191 | RSFR variant (C1975428, 204) is QFN-12 4x4 — different footprint. No same-footprint alternate with more stock. |
| KH-5224-8P8C-D (RJ45) | C2828085 | 239 | KH-5224-8P8C (C2683357, 5,365) is the same family but the **non "-D"** variant (harpoon vs plain contact / mount); verify footprint + retention before swapping. |
| SFW15R-1STE1LF (camera FFC) | C3168538 | 274 | The "-2STE" variant is top-contact vs this part's bottom-contact — not interchangeable. Exact part is the best available. |
| ASP-134603-01 (Samtec FMC) | C2836665 | 282 | $14.85 ea, single-source, no equivalent. Cost + stock concentration risk; primary mitigation is buy-ahead. |

### B. Data-integrity finding (NOT a cost swap — fix recommended)

**C25750 (power:R1, "40.2k" FB-top resistor) currently resolves on LCSC to a
120 kohm 0402 part** (`0402WGF1203TCE`, Uni-Royal), not a 40.2 kohm 0603. The
project's own comment/ratings call it "40.2k 0603" — the LCSC code is
stale/reassigned. This is a live mismatch: the BOM ships R1 as a 0402 120 k in
a 0603 land if ordered as-is, which breaks the +5 V feedback divider
(40.2k/10k -> 5.02 V). Recommend reassigning to a correct **40.2 kohm 0603 1%**
part, e.g. **C12447** (UniOhm 0603WAF4022T5E, 40.2 kohm 75 V 0603, Extended,
42,541 stock). NOT applied here: power:R1 is a value-bearing FB resistor, so the
owner should confirm the value/footprint intent before the change (it is a
judgement call, not a like-for-like sourcing swap).

### C. Higher-stock same-chip alternates (optional, all still Extended)

These would NOT reduce the feeder-fee count (still Extended) and most differ in
footprint, so they are only worth noting as supply-chain backups:

- **FUSB302BMPX (C132291, 5,390)**: "Fusb302mpx" (C442699, 9,976) is a same-package
  WFQFN-14 listing with ~2x stock but a different/relabelled MPN string — do NOT
  silently swap a USB-PD PHY on MPN ambiguity. FUSB302B01MPX (C488155, 2,675) is
  a genuine TI variant if a true second source is needed.
- **AP2112K-1.8 (C176944, 4,261)**: AP2112K-1.8TRG1(MS) (C22365428, 1,988) and the
  TPAP2112K clone exist but in SOT-23-5 vs this part's SOT-25 listing — verify
  footprint.

## Extended-BY-NECESSITY (do NOT churn)

Every remaining Extended part below has NO JLC-Basic equivalent — confirmed by
searching the JLC Basic library for the same value/function:

- **Precise E96 resistors** (49.9R, 5.49k, 22.1k, 47.5k, 68.1k, 1.5R, 40.2k):
  JLC's Basic library is essentially E24/E12; these precise values are Extended
  everywhere. C0G/precision caps (75p, 200p), 2.2u 0805, 10u 1210 X7R likewise.
- **Green LED (C12624), blue LED (C2288)**: no Basic green/blue 0603 LED in JLC
  (only red C2286 + white C2290 are Basic). qty 1 each — negligible.
- **Single AND-gate SN74LVC1G08 (C7666, x14)**, **SY6280AAC load switch (x12)**,
  **USBLC6-2SC6 ESD (x6)**: searched — no Basic option for any. The x14/x12
  feeder fees are unavoidable.
- All function-defining ICs/connectors: FUSB302, INA3221, CH347T, CP2102N,
  LM61460, TPS54302, TPS26631, TLV75725, TXS02612, PCA9306, TCA9535, TPS3823,
  RV-3028, M24C02(Pref), 24AA025E48, the TPD-series HDMI/USB ESD arrays, the
  HDMI/USB-C/FMC/DF40/RJ45/microSD/Qwiic connectors, the SWPA inductors, the
  RLM current-sense shunts, SS34/SMBJ22A/MMSZ5231B diodes, the 8 MHz crystal.
  These are correct, intentional, single-purpose parts; swapping any for "Basic"
  is not possible without changing the design.

## Notes / honest uncertainty

- Stock and price are a **live snapshot** from the JLCPCB assembly parts API at
  review time; both move daily. The <300-stock figures (esp. HX5008NLT = 10) are
  the volatile ones — re-run `schgen preflight ethernet` (and the other low-stock
  subsystems) immediately before ordering to confirm fillability.
- Prices are the qty>=100 tier `productPrice` (USD), pre-fee; the est.
  ~$51/board excludes the $186 feeder fee, base setup, and PCB fab.
- `carrier/manufacturing/preflight_report.txt` is an older `schgen preflight`
  dump and still lists C1591 as Extended; re-run `schgen preflight` to refresh
  it (it is not a gate and is not auto-regenerated by `schgen board`).

## Full part table

| LCSC | Value/Part | Qty | Class | Stock | $@100 | Risk |
|------|-----------|----:|-------|------:|------:|------|
| C10214 | SMBJ22A | 1 | Extended | 4,499 | 0.0572 | low-stock,Ext-fee |
| C106794 | TPD4E02B04DQAR | 2 | Extended | 39,513 | 0.2668 | Ext-fee |
| C111617 | HDMI-019S | 2 | Extended | 21,513 | 0.2389 | Ext-fee |
| C113796 | 200p | 2 | Extended | 193,322 | 0.0061 | Ext-fee |
| C114625 | 49.9R | 8 | Extended | 514,243 | 0.0019 | Ext-fee |
| C124691 | TPD4E1U06 | 2 | Extended | 9,152 | 0.2520 | Ext-fee |
| C125847 | 2.2u | 1 | Extended | 219,872 | 0.0562 | Ext-fee |
| C12624 | green | 1 | Extended | 223,204 | 0.0121 | Ext-fee |
| C129581 | TPS2051CDBVR | 1 | Extended | 9,444 | 0.2841 | Ext-fee |
| C129895 | 24AA025E48T-I/OT | 1 | Extended | 1,898 | 0.4809 | low-stock,Ext-fee |
| C130204 | TCA9535PWR | 1 | Extended | 12,468 | 0.7601 | Ext-fee |
| C132291 | FUSB302BMPX | 1 | Extended | 5,390 | 0.5552 | Ext-fee |
| C13585 | 10u | 4 | Basic | 2,271,490 | 0.1098 | - |
| C138714 | TPD4E05U06DQAR | 1 | Extended | 123,691 | 0.0667 | Ext-fee |
| C140276 | TXS02612RTWR | 1 | Extended | 24,256 | 0.4325 | Ext-fee |
| C14663 | 100n | 83 | Basic | 17,789,417 | 0.0094 | - |
| C15849 | 1u | 8 | Basic | 6,067,353 | 0.0109 | - |
| C15850 | 10u | 15 | Basic | 3,807,459 | 0.0801 | - |
| C1622 | 47n | 1 | Basic | 386,253 | 0.0087 | - |
| C1653 | 22p | 3 | Basic | 1,017,753 | 0.0057 | - |
| C165948 | TYPE-C-31-M-12 | 4 | Extended | 183,957 | 0.1456 | Ext-fee |
| C176944 | AP2112K-1.8 | 1 | Extended | 4,261 | 0.1438 | low-stock,Ext-fee |
| C181255 | INA3221AIRGVR | 2 | Extended | 2,402 | 1.0377 | low-stock,Ext-fee |
| C188070 | 10mR | 3 | Extended | 86,218 | 0.0291 | Ext-fee |
| C188263 | 5.49k | 1 | Extended | 5,046 | 0.0012 | Ext-fee |
| C1973318 | TPD6E001RSER | 1 | Extended | 191 | 0.2663 | CRIT-stock,Ext-fee |
| C201665 | TPD12S016PWR | 1 | Extended | 4,321 | 0.5761 | low-stock,Ext-fee |
| C20917 | AO3400A | 1 | Basic | 734,155 | 0.0677 | - |
| C21190 | 1k | 15 | Basic | 11,514,436 | 0.0017 | - |
| C22399620 | 75p | 2 | Extended | 8,020 | 0.0046 | Ext-fee |
| C22769 | 1.5R | 1 | Extended | 16,790 | 0.0026 | Ext-fee |
| C22775 | 100R | 4 | Basic | 8,506,585 | 0.0023 | - |
| C22797 | 13k | 8 | Basic | 825,167 | 0.0014 | - |
| C22809 | 15k | 1 | Basic | 1,417,382 | 0.0017 | - |
| C22859 | 10R | 1 | Basic | 3,512,682 | 0.0019 | - |
| C2286 | red | 17 | Basic | 7,784,105 | 0.0072 | - |
| C2288 | blue | 1 | Extended | 253,360 | 0.0102 | Ext-fee |
| C2290 | white | 1 | Basic | 2,458,337 | 0.0121 | - |
| C22967 | 27k | 1 | Basic | 884,481 | 0.0016 | - |
| C23061 | 47k5 | 1 | Extended | 88,351 | 0.0020 | Ext-fee |
| C23138 | 330R | 13 | Basic | 1,356,678 | 0.0016 | - |
| C23162 | 4k7 | 10 | Basic | 9,621,528 | 0.0018 | - |
| C23186 | 5.1k | 5 | Basic | 4,487,140 | 0.0018 | - |
| C23206 | 56k | 2 | Basic | 277,056 | 0.0020 | - |
| C23212 | 6.8k | 4 | Basic | 547,133 | 0.0018 | - |
| C23345 | 22R | 1 | Basic | 3,004,295 | 0.0017 | - |
| C240854 | 878311420 | 1 | Extended | 5,986 | 0.9860 | Ext-fee |
| C25750 | 40.2k | 1 | Extended (Pref) | 5,361 | 0.0008 | - |
| C25803 | 100k | 47 | Basic | 9,126,040 | 0.0016 | - |
| C25804 | 10k | 29 | Basic | 1,474,892 | 0.0014 | - |
| C25961 | 22k1 | 1 | Extended | 47,588 | 0.0018 | Ext-fee |
| C262572 | AFC07-S40FCA-00 | 1 | Extended | 9,849 | 0.1750 | Ext-fee |
| C2828085 | KH-5224-8P8C-D | 1 | Extended | 239 | 0.3034 | CRIT-stock,Ext-fee |
| C2836665 | ASP-134603-01 | 1 | Extended | 282 | 14.8495 | CRIT-stock,Ext-fee |
| C2864505 | LM61460AANRJRR | 1 | Extended | 3,761 | 1.1313 | low-stock,Ext-fee |
| C2866319 | TPS26631PWPR | 1 | Extended | 177 | 3.4954 | CRIT-stock,Ext-fee |
| C3019759 | RV-3028-C7-32.768kHz-1ppm-TA-QC | 1 | Extended | 15,313 | 1.5073 | Ext-fee |
| C311983 | TPS54302DDCR | 2 | Extended | 24,635 | 0.2670 | Ext-fee |
| C3168538 | SFW15R-1STE1LF | 1 | Extended | 274 | 0.3567 | CRIT-stock,Ext-fee |
| C31850 | 22k | 2 | Basic | 1,957,638 | 0.0014 | - |
| C318884 | USER | 8 | Basic | 1,809,053 | 0.0196 | - |
| C3293144 | DSHP04TSGER | 6 | Extended | 31,731 | 0.4390 | Ext-fee |
| C3293147 | DSHP08TSGER | 1 | Extended | 35,268 | 0.4938 | Ext-fee |
| C33196 | PCA9306DCUR | 1 | Extended | 8,586 | 0.2631 | Ext-fee |
| C35209004 | TLV75725PDYDR | 1 | Extended | 133 | 0.2211 | CRIT-stock,Ext-fee |
| C37429 | 10uH | 3 | Extended | 6,052 | 0.1206 | Ext-fee |
| C38117 | 10uH | 1 | Extended | 95,893 | 0.0751 | Ext-fee |
| C393094 | 20mR | 1 | Extended | 50,088 | 0.0373 | Ext-fee |
| C42372555 | HX_JN1.27-2x5 | 1 | Extended | 10,774 | 0.1767 | Ext-fee |
| C4275 | 75R | 4 | Basic | 789,363 | 0.0020 | - |
| C45783 | 22u | 10 | Basic | 2,327,650 | 0.0949 | - |
| C49284652 | DS1024-2x6R2 | 3 | Extended | 45 | 0.1085 | CRIT-stock,Ext-fee |
| C51118 | AP2112K-3.3TRG1 | 1 | Extended | 87,465 | 0.1235 | Ext-fee |
| C5122332 | CH347T | 1 | Extended | 1,953 | 2.1947 | low-stock,Ext-fee |
| C5365933 | KH-CR1220-2 | 1 | Extended | 24,491 | 0.1479 | Ext-fee |
| C55136 | SY6280AAC | 12 | Extended | 195,549 | 0.0773 | Ext-fee |
| C57131 | 8MHz | 1 | Extended | 32,856 | 0.2540 | Ext-fee |
| C596319 | 10u | 1 | Extended | 12,539 | 0.2942 | Ext-fee |
| C597931 | DF40C-100DS-0.4V(51) | 3 | Extended | 15,946 | 0.7520 | Ext-fee |
| C7430446 | ZX-SH1.0-4PWT | 1 | Extended | 192,078 | 0.0554 | Ext-fee |
| C7519 | USBLC6-2SC6 | 6 | Extended | 37,666 | 0.1180 | Ext-fee |
| C7562 | M24C02-WMN6TP | 1 | Extended (Pref) | 64,251 | 0.1316 | - |
| C7661 | SN74LVC125ADR | 1 | Extended | 7,330 | 0.2179 | Ext-fee |
| C7666 | SN74LVC1G08 | 14 | Extended | 252,347 | 0.0404 | Ext-fee |
| C7719 | TPS3823-33DBVR | 1 | Extended | 65,580 | 0.1924 | Ext-fee |
| C82173 | SY7201ABC | 1 | Extended | 16,042 | 0.2595 | Ext-fee |
| C8218 | 200R | 16 | Basic | 3,353,920 | 0.0015 | - |
| C844583 | 68.1k | 1 | Extended | 10,869 | 0.0063 | Ext-fee |
| C85181 | MMSZ5231B | 1 | Extended | 180,887 | 0.0162 | Ext-fee |
| C8678 | SS34 | 1 | Basic | 3,895,728 | 0.0301 | - |
| C91145 | TF-01A | 1 | Extended | 116,137 | 0.1517 | Ext-fee |
| C9196 | 1n | 5 | Basic | 1,280,731 | 0.0362 | - |
| C962544 | HX5008NLT | 1 | Extended | 10 | 1.0054 | CRIT-stock,Ext-fee |
| C969151 | CP2102N-A02 | 1 | Extended | 22,419 | 1.3717 | Ext-fee |
