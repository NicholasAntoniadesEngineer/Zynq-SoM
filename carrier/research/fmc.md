# Research dossier: fmc (VITA 57.1 FMC LPC, REDUCED carrier subset)

Date: 2026-06-11. Scope: FMC mezzanine site on the carrier — LPC vs HPC
decision from a FULL remaining-PL-pin audit, honest populated subset,
VADJ rail per PLAN round 2 (fixed 2.5 V local LDO), connector live-search
(JLCPCB parts API, 2026-06-11), VITA 57 rail budgets.

---

## 0. LPC vs HPC decision — driven by the remaining-pin audit

### Full PL ledger (som_interface.json vs every subsystem, audited 2026-06-11)

| Bank | Total IOs (connector) | Claimed | By whom | Free | VCCO |
|------|----------------------|---------|---------|------|------|
| 13 | 43 (J2) | 28 | pmod 16 (L2-L5,L7-L10), user_io 8 (25,L6_P,L24_P/N,L15/19/21/22_P), lcd touch 4 (CTP I2C/RST/INT) | 15 | 3.3 V |
| 33 | 39 (J2:29 + J3:10) | 30 | hdmi_tx 12 (8 TMDS + CEC/DDC/HPD), hdmi_rx 10 (8 TMDS + 5V_DET + CEC), camera ctl 4 (SCL/SDA/EN/LED), bringup PL_LED0-3 4 | 9 | 3.3 V |
| 34 | 34 (J3) | 30 | lcd (24 RGB + 5 sync/ctl + BL_PWM) | 4 | 3.3 V |
| 35 | 40 (J3:30 + J1:10) | 10 | camera 6 (L10, L13_MRCC, L15_DQS) + 4 LP-RX reserve (L16, L18) | 30 | **2.5 V** (camera dossier risk 1) |

Notes: hdmi_tx/hdmi_rx/lcd port deferrals (`expect=`) don't name IO pins
yet; their counts are signal counts from the subsystem netlists, all 3.3 V
class. pmod/user_io bind `IO_*_13` names verbatim (grep-verified). The four
LP-RX pins stay reserved per the camera dossier (risk 4) — NOT spent here.

### Consequence
- **HPC is out**: 400-pin connector, 80 LA pairs; we have nowhere near that.
- **VADJ = 2.5 V (PLAN round 2 locked) makes bank 35 the ONLY legal LA
  bank** — banks 13/33/34 are 3.3 V. Camera already forces +VCCO_35 = 2.5 V,
  so FMC LA on bank 35 is voltage-consistent by construction (VADJ ==
  VCCO_35 == 2.5 V, one rail name: +2V5_VADJ serves both — see section 3).
- Free bank-35 inventory: J3-side 20 pins = 9 full pairs + the L19 pair
  (L19_N is VREF-capable; usable as IO since LVDS_25/LVCMOS25 need no
  external VREF); J1-side 10 pins = L1/L4/L5 pairs + the L6 pair (L6_N is
  VREF-capable) + 2 singles (IO_0_35, IO_L2_N_35 — left free, FMC LA pins
  are pairs).
- **Honest scope: REDUCED FMC-LPC — 12 LA pairs (LA00-LA11) + both
  M2C clocks populated; LA12-LA33, DP0, GBTCLK0 unpopulated (author NC).**
  14 usable pairs exist; 12 go to LA so the 2 best clock-capable pairs can
  serve CLK0/CLK1_M2C.

## 1. Populated pin map (drives fmc.py and the future .xdc)

The full 160-pin LPC pin->signal table is committed MACHINE-PARSED at
`carrier/research/fmc_lpc_pinmap.json` (extracted 2026-06-11 from the
fmchub VITA 57.1 appendix table by a deterministic HTML-table parser —
no hand-typing; spot-checked against the ZedBoard LPC schematic
conventions). 61 GND positions. fmc.py loads this JSON.

| FMC signal | LPC pins | carrier port | SoM net (verbatim) | J pins |
|------------|----------|--------------|--------------------|--------|
| CLK0_M2C   | H4/H5   | FMC_CLK0_M2C_P/N | IO_L12_MRCC_P/N_35 | J3.14/16 |
| CLK1_M2C   | G2/G3   | FMC_CLK1_M2C_P/N | IO_L11_SRCC_P/N_35 | J3.8/10 |
| LA00_CC    | G6/G7   | FMC_LA00_CC_P/N  | IO_L14_SRCC_P/N_35 | J3.22/20 |
| LA01_CC    | D8/D9   | FMC_LA01_CC_P/N  | IO_L21_DQS_P/N_35  | J3.24/26 |
| LA02       | H7/H8   | FMC_LA02_P/N     | IO_L17_P/N_35      | J3.37/35 |
| LA03       | G9/G10  | FMC_LA03_P/N     | IO_L20_P/N_35      | J3.34/32 |
| LA04       | H10/H11 | FMC_LA04_P/N     | IO_L22_P/N_35      | J3.42/44 |
| LA05       | D11/D12 | FMC_LA05_P/N     | IO_L23_P/N_35      | J3.47/45 |
| LA06       | C10/C11 | FMC_LA06_P/N     | IO_L24_P/N_35      | J3.51/49 |
| LA07       | H13/H14 | FMC_LA07_P/N     | IO_L19_P_35 / IO_L19_N_VREF_35 | J3.50/52 |
| LA08       | G12/G13 | FMC_LA08_P/N     | IO_L1_P/N_35       | J1.74/92 |
| LA09       | D14/D15 | FMC_LA09_P/N     | IO_L4_P/N_35       | J1.80/84 |
| LA10       | C14/C15 | FMC_LA10_P/N     | IO_L5_P/N_35       | J1.90/88 |
| LA11       | H16/H17 | FMC_LA11_P/N     | IO_L6_P_35 / IO_L6_VREF_N_35 | J1.78/76 |

Port names are FUNCTIONAL (hdmi-sheet pattern) because the linker reads
pair polarity from name suffixes and `IO_*_P_35` is not suffix-inferable;
the IO binding above is THE contract for the P3 linker function map + the
round-4 .xdc generator. Pairs typed `diff_pair` 100R (JLC04161H-7628).

**Documented deviations (rev A):**
1. **LA01_CC is NOT clock-capable** here (L21 is a DQS pair; on 7-series
   only MRCC/SRCC reach clock buffers). Mezzanines needing both LA00_CC and
   LA01_CC as clocks must use CLK0/CLK1_M2C instead.
2. LA07_N and LA11_N land on VREF-capable pins — fine for LVDS_25/
   LVCMOS25 (no external VREF), but bank 35 must never switch to a
   VREF-needing standard.
3. LA08-LA11 route to J1 (the power/STM32 connector) — electrically plain
   bank-35 IOs; length-matching across two mezzanine connectors is the
   layout cost of the last 4 pairs.
4. DP0 (C2/C3/C6/C7), GBTCLK0 (D4/D5): no MGT on Zynq-7020 HR carrier — NC.
5. VREF_A_M2C (H1): unused (no VREF standards) — NC.

## 2. Connector (live JLCPCB API, 2026-06-11) — NOT a ghost

| Part | LCSC | Role | Stock | Price @1 | Lib |
|------|------|------|------:|---------:|-----|
| **Samtec ASP-134603-01** (SEAF-40-06.5 based, ".050 PITCH SOCKET ARRAY", rows 3/4/7/8 = LPC) | **C2836665** | **CARRIER socket — our part** | **282** | $17.75 | Extended |
| Samtec ASP-134604-01 (SEAM-40 based ".050 PITCH TERMINAL ARRAY") | C2830435 | MEZZANINE plug — do NOT order for the carrier | 78 | $14.46 | Extended |

Identity verified from the Samtec drawings served by LCSC (ASP-134603-01 =
SOCKET assembly built on SEAF-40-06.5-10-A, "FILL ROWS 3,4,7,8 ONLY";
ASP-134604-01 = TERMINAL assembly on SEAM-40-03.5-10-A, "VITA 57
CONNECTOR"). ASP-134603-01 is the ZedBoard's FMC LPC carrier connector —
precedent-proven side selection. SEARAY contact rating 2.7 A/pin.

**CAD note (pipeline)**: LCSC's EasyEDA model stores the symbol as 4
SUBPARTS (rows C/D/G/H); `schgen part add` does not traverse subparts and
failed with "EasyEDA symbol has no pins". parts/ASP-134603-01/ was
generated with the documented `--from-json` offline mode after flattening
the subparts' pin shapes into the main shape list VERBATIM (no pin
hand-typing; provenance note embedded in the cached .easyeda.json; pad set
== pin set == c1..h40 verified). 3D model fetch is skipped in offline mode
— regenerate when part_gen learns subparts (flagged to the schgen owner).
**Stock risk**: 282 units, Extended, $17.75 — order-early line item;
preflight re-check before any board run.

## 3. VADJ rail: +2V5_VADJ (fixed 2.5 V local LDO, PLAN round 2)

Pick (live-verified): **TI TLV75725PDBVR** (LCSC C2872563, stock 613,
Extended, $0.20) — 1 A LDO, fixed 2.5 V, SOT-23-5 (DBV), Vin <= 5.5 V.
Pinout verified from the TI TLV757P datasheet (DBV: 1=IN 2=GND 3=EN 4=NC
5=OUT — the same map as the KiCad `Regulator_Linear:AP2204K-1.5` drawing,
the power.py precedent). Caps >= 1 uF effective in/out required.

- Fed from **+3V3** (not +5V: keeps dissipation at (3.3-2.5)*I).
- Dropout: 750 mV max @ 1 A vs 800 mV headroom — thin at 1 A, comfortable
  at <= 0.5 A (~<400 mV typ).
- **Thermal truth (the real limit)**: DBV RthJA = 231 C/W. Pd = 0.8 V * I.
  At Ta = 50 C, Tj <= 125 C -> Pd <= 0.32 W -> **I(VADJ) <= ~0.4 A
  continuous** (1 A short peaks OK). This is the honest rev-A VADJ budget.
- More-current alternates if a mezzanine demands it: TLV75725PDRVR
  (SON+pad, RthJA 100 C/W -> ~0.9 A; LCSC C507271 stock only 16 — ghost
  risk) or a 2.5 V buck cell on a later power.py rev.
- +VCCO_35 (camera dossier risk 1) is THIS rail: one 2.5 V LDO serves the
  FMC VADJ pins and the SoM's bank-35 VCCO feed — single rail name
  +2V5_VADJ in the netlists; the J3 sheet's VCCO_35 binding follows at
  wave-3 regeneration (rail-map entry).
- EN strapped to +3V3 (always on with the 3V3 stage; no bringup cell —
  the 9th gate cell was declined to keep the bringup sheet as-built;
  rail-by-rail bring-up still works because +3V3 itself is DIP-gated).

## 4. Rail budgets vs VITA 57.1 (LPC)

| Rail | LPC pins | VITA nominal | Carrier provision (rev A) |
|------|----------|--------------|---------------------------|
| VADJ | G39, H40 | up to 4 A | **0.4 A continuous** (LDO thermal, section 3) — loud constraint for mezzanine selection |
| 3P3V | C39, D36, D38, D40 | up to 3 A | **1.0 A allocation** from the carrier's 3 A +3V3 buck (shared with the whole board — power-tree budget gate, PLAN round 4, enforces) |
| 12P0V | C35, C37 | up to 1 A | **NOT PROVIDED — author NC.** The carrier has no 12 V rail (PLAN round 2 rail tree). DEVIATION: 12 V-requiring mezzanines unsupported rev A |
| 3P3VAUX | D32 | 20 mA | +3V3 (ungated rail; "aux" semantics hold whenever EN_3V3 is up) |
| VREF_A_M2C | H1 | reference | NC (unused) |

## 5. Service signals

- **SCL/SDA (C30/C31)**: STM32_I2C2 shared bus (FUSB302 + TCA9535 + INA3221
  precedent; pull-ups live ONCE on bringup_rails) — ports STM32_I2C2_SCL/
  SDA verbatim. Mezzanine IPMI EEPROM joins the SC's I2C census.
- **GA0/GA1 (C34/D35)**: tied to GND -> mezzanine EEPROM at I2C address
  offset 0 (0x50 family) — no conflict with the SC map (0x20/0x22/0x40/
  0x41) or camera 0x10 (different bus).
- **PRSNT_M2C_L (H2)**: 10k pull-up to +3V3, port FMC_PRSNT_N -> one of
  the 9 spare bank-33 IOs (expect deferral, P3 linker).
- **PG_C2M (D1)**: 10k pull-up to +2V5_VADJ — asserts exactly when VADJ is
  live (2.5 V is a valid CMOS-high for the mezzanine's 3.3 V-aux logic).
  Simplification vs full "all rails good" logic: documented; the bring-up
  manual orders EN_3V3 before any FMC use anyway.
- **JTAG (D29-D34)**: no carrier JTAG chain to the mezzanine on rev A —
  VITA-required bypass TDI->TDO wired at the connector; TCK 10k to GND,
  TRST_L 10k to GND (TAP held in reset), TMS 10k to +3V3. All 10k =
  C25804 (Basic, 3.1M stock live).

## 6. Risks / open items

1. Connector stock 282 + $17.75 Extended — the single long-lead line item;
   re-verify at preflight, order early.
2. +2V5_VADJ powers bank-35 VCCO too: the wave-3 J3/J1 sheet regeneration
   must add the +VCCO_35 -> +2V5_VADJ rail-map entry (shared flag with the
   camera dossier risk 1).
3. The 0.4 A VADJ budget must end up in the round-4 power-tree gate AND
   the bring-up manual (mezzanine qualification step).
4. part_gen subparts gap (section 2 CAD note) — schgen owner; regen the
   folder online afterward for the 3D model.
5. PG_C2M simplification (section 5) — revisit if a mezzanine reads it
   strictly per VITA timing (tie to a real power-good tree then).

Sources: fmchub.github.io VITA 57.1 appendix (LPC pin table,
machine-parsed -> fmc_lpc_pinmap.json); Samtec drawings 10172241-equiv for
ASP-134603-01/-134604-01 (via LCSC datasheet links, socket/terminal + row
fill confirmed); TI TLV757P datasheet (pinout, dropout, RthJA); JLCPCB
selectSmtComponentList API (stock/prices, 2026-06-11); ZedBoard FMC LPC
precedent (ASP-134603-01 carrier socket); carrier/som_interface.json +
subsystem netlists (pin ledger); carrier/PLAN.md rounds 2-4;
carrier/research/camera_csi.md (+VCCO_35).
