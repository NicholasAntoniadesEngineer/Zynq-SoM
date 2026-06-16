# fmc — VITA 57.1 FMC LPC mezzanine site, REDUCED subset (carrier-local)

A **carrier-local** schgen subsystem: a reduced VITA 57.1 **FMC LPC** mezzanine
site with a local 2.5 V **VADJ** LDO. It loads its connector pinout from the
machine-parsed `carrier/research/fmc_lpc_pinmap.json`, exports functional
pair-suffixed ports bound to the SoM bank-35 IOs, and rides the carrier rails
directly — board-specific, so no abstract-interface / bind contract.

## Package contents

| file | role |
|------|------|
| `fmc.py`       | the NETLIST — `circuit()`, carrier nets; loads `../../research/fmc_lpc_pinmap.json` (note: `parents[2]` = carrier in the folded package layout) |
| `fmc.cir`      | SPICE subckt — the VADJ LDO output network + service-strap pull-ups + connector bypass, rails/VADJ/3P3V as subckt pins |
| `test_fmc.py`  | LOCAL electrical-correctness test (offline; model completeness + VADJ LDO + LA/CLK diff pairs + GND census + service straps + EP-to-GND) |
| `README.md`    | this file |

## Purpose / honest scope

A FULL remaining-PL-pin audit (dossier `carrier/research/fmc.md`) settles the
LPC-vs-HPC decision: **HPC is out** (400-pin, 80 LA pairs — nowhere near
available), and **VADJ = 2.5 V (PLAN round 2 locked) makes bank 35 the ONLY legal
LA bank** (13/33/34 are 3.3 V). Honest scope: **REDUCED FMC-LPC — LA00-LA11
(12 pairs) + both M2C clocks populated**; LA12-LA33, DP0, GBTCLK0, VREF_A_M2C,
12P0V are **author NCs** (documented deviations: LA01_CC is not clock-capable, no
MGT on the Zynq-7020 HR carrier, and the carrier has **no 12 V rail**).

## Banks / pins (the populated map)

12 LA pairs + 2 M2C clocks, on true MRCC/SRCC pairs where required. Pairs are
typed `diff_pair` 100 Ω. The IO binding is the dossier section-1 contract.

| FMC signal | carrier port | SoM net (verbatim) | J pins |
|------------|--------------|--------------------|--------|
| CLK0_M2C | `FMC_CLK0_M2C_P/N` | IO_L12_MRCC_P/N_35 | J3.14/16 |
| CLK1_M2C | `FMC_CLK1_M2C_P/N` | IO_L11_SRCC_P/N_35 | J3.8/10 |
| LA00_CC  | `FMC_LA00_CC_P/N`  | IO_L14_SRCC_P/N_35 | J3.22/20 |
| LA01_CC  | `FMC_LA01_CC_P/N`  | IO_L21_DQS_P/N_35  | J3.24/26 |
| LA02     | `FMC_LA02_P/N`     | IO_L17_P/N_35      | J3.37/35 |
| LA03     | `FMC_LA03_P/N`     | IO_L20_P/N_35      | J3.34/32 |
| LA04     | `FMC_LA04_P/N`     | IO_L22_P/N_35      | J3.42/44 |
| LA05     | `FMC_LA05_P/N`     | IO_L23_P/N_35      | J3.47/45 |
| LA06     | `FMC_LA06_P/N`     | IO_L24_P/N_35      | J3.51/49 |
| LA07     | `FMC_LA07_P/N`     | IO_L19_P_35 / IO_L19_N_VREF_35 | J3.50/52 |
| LA08     | `FMC_LA08_P/N`     | IO_L1_P/N_35       | J1.74/92 |
| LA09     | `FMC_LA09_P/N`     | IO_L4_P/N_35       | J1.80/84 |
| LA10     | `FMC_LA10_P/N`     | IO_L5_P/N_35       | J1.90/88 |
| LA11     | `FMC_LA11_P/N`     | IO_L6_P_35 / IO_L6_VREF_N_35 | J1.78/76 |

The pin → signal map is machine-parsed from
`carrier/research/fmc_lpc_pinmap.json` (160 LPC positions, **61 GND** — asserted
before binding; VADJ = G39/H40; 3P3V = C39/D36/D38/D40). Port names are
FUNCTIONAL (hdmi pattern) so the linker infers pair polarity from suffixes.

## Parts

| ref | value | part / footprint | LCSC | role |
|-----|-------|------------------|------|------|
| J1 | (FMC) | `ASP-134603-01` (use_part) | C2836665 | Samtec SEAF-based LPC **socket** (carrier side; the ZedBoard's part) |
| U1 | (VADJ LDO) | `TLV75725PDYDR` (use_part, DYD thermal-pad) | C35209004 | fixed 2.5 V LDO, EP=pin 6 netted to GND |
| R1 | 10k | `Device:R` / R_0603 | C25804 | PRSNT_M2C_L pull-up (→ +3V3) |
| R2 | 10k | `Device:R` / R_0603 | C25804 | PG_C2M pull-up (→ +2V5_VADJ) |
| R3 | 10k | `Device:R` / R_0603 | C25804 | FMC TCK held low (→ GND) |
| R4 | 10k | `Device:R` / R_0603 | C25804 | FMC TRST_L held low (→ GND) |
| R5 | 10k | `Device:R` / R_0603 | C25804 | FMC TMS held high (→ +3V3) |
| C1 | 10u  | `Device:C` / C0805 | C15850 | 3P3V connector bulk |
| C2 | 100n | `Device:C` / C0603 | C14663 | 3P3V connector HF |
| C3 | 1u   | `Device:C` / C0603 | C15849 | VADJ LDO input |
| C4 | 10u  | `Device:C` / C0805 | C15850 | VADJ LDO output |
| C5 | 100n | `Device:C` / C0603 | C14663 | VADJ at connector |

## VADJ rail

`+2V5_VADJ` from the **TLV75725PDYDR** (fixed 2.5 V LDO) fed by `+3V3` — the SAME
voltage bank 35 runs at (`+VCCO_35`), so LA levels are consistent by
construction (one rail name serves FMC VADJ and the bank-35 VCCO feed). EN is
strapped on (always-on with the +3V3 stage). The EP pad (footprint pad 6) is
netted to GND in the schematic (DEF-E) — a real, gate-checkable ground bond.
Pin map 1=IN 2=GND 3=EN 4=NC 5=OUT 6=EP. The rail carries a `testpoint()`.

**PWR-3 thermal swap (SBVS322C):** the former DBV (SOT-23-5, RthJA ~231 °C/W) had
no margin at the 0.4 A / ~0.8 V-drop budget (Pd ~0.32 W → Tj ~125 °C @ Ta=50 °C).
The DYD thermal-pad variant (RthJA ~92.5 °C/W EP-to-GND) lifts the same 0.32 W
only ~30 °C → Tj ~80 °C — a comfortable continuous limit.

## Service signals

- **I2C**: `STM32_I2C2_SCL/SDA` on the shared SC bus (pull-ups live ONCE on
  `bringup_rails`). GA0/GA1 tied to GND → mezzanine EEPROM at 0x50.
- **PRSNT_M2C_L** → `FMC_PRSNT_N`, 10k pull-up to +3V3 (bank-33 spare, deferral).
- **PG_C2M** → `FMC_PG_C2M`, 10k pull-up to +2V5_VADJ (asserts when VADJ is live).
- **JTAG**: bypass TDI→TDO (`FMC_JTAG_BYPASS`); TCK/TRST_L held low, TMS held
  high (TAP in reset) — `FMC_TCK`/`FMC_TRST_L`/`FMC_TMS`, all 10k.

## Power-tree budget

- `+3V3` 1.000 A: FMC 3P3V + 3P3VAUX mezzanine allocation (from the +3V3 buck).
- `+2V5_VADJ` 0.350 A: TLV75725 DYD 0.40 A thermal envelope less ~0.05 A bank-35
  VCCO (LVDS_25 drivers: 12 FMC LA + 3 camera CSI pairs).

## Notes

- **SILKSCREEN INTENT (reduced-LPC)**: although the connector is a full
  LPC-mechanical SEAF socket, this is a REDUCED LPC site (only LA00-LA11 +
  CLK0/CLK1_M2C populated). The PCB silkscreen MUST be labelled to that effect
  (e.g. "FMC LPC (REDUCED) — LA00-LA11, no 12V") so an integrator does not seat a
  mezzanine assuming a full LA bus, a 12 V supply, or the GTP GBTCLK/DP lanes. A
  fab-art/silkscreen requirement, not a netlist change.
- **Connector side**: `ASP-134603-01` is the carrier-side **socket** (the
  mezzanine-side `ASP-134604-01` is the wrong side). Long-lead Extended line item
  — preflight re-check before any board run.
- **Folded-package path note**: `fmc.py` reads the pinmap via
  `Path(__file__).resolve().parents[2] / "research" / ...` — in the foldered
  `carrier/subsystems/fmc/fmc.py` layout, `parents[2]` is `carrier/` (the flat
  layout used `parents[1]`). The emitted netlist is byte-identical.

## Local test

`test_fmc.py` runs the subsystem-LOCAL slices offline (model completeness, the
VADJ LDO presence + EP-to-GND, the 14 LA/CLK diff pairs, the GND census, the
service-strap pulls, the `design_rules` DECAP/EP/STRAP slice, the `.cir` ↔
netlist passive match). Cross-board gates (full link / power-tree headroom / board
ERC) stay aggregated by `schgen board`.

```bash
PYTHONPATH=. python3 -m pytest carrier/subsystems/fmc/test_fmc.py -q
```
