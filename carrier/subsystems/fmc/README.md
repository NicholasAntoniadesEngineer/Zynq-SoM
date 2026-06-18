# fmc — SoM bank-35 IO breakout on a generic 2.54 mm header (carrier-local)

A **carrier-local** schgen subsystem: it breaks out the SoM **bank-35** LVDS IO
(14 differential pairs) plus a local 2.5 V **VADJ** rail onto a generic **2×20
0.1″ / 2.54 mm pin header**, and rides the carrier rails directly.

> **History (2026-06-18, user request).** This site WAS a VITA 57.1 **FMC LPC**
> mezzanine connector (Samtec ASP-134603-01). The proprietary FMC connector was
> replaced with a generic 2×20 2.54 mm header so the same SoM bank-35 IO is
> broken out to a cheap, universally-wireable header — **no specific FMC
> mezzanine card required**. The 14 pairs keep their functional names, so the SoM
> binding (FUNCTION_MAP), XDC and SI constraints — which reference the SoM side,
> not this connector — are unchanged. The FMC-mezzanine management (GA straps,
> PRSNT/PG presence, JTAG bypass, mezzanine EEPROM, the 400-pin VITA grid) is
> gone with the connector.

## Package contents

| file | role |
|------|------|
| `fmc.py`       | the NETLIST — `circuit()`, carrier nets; the 2×20 header pinout + the VADJ LDO |
| `fmc.cir`      | SPICE subckt — the +3V3 bypass + VADJ LDO in/out caps (rails as subckt pins) |
| `test_fmc.py`  | LOCAL electrical-correctness test (offline; model completeness + header pinout + VADJ LDO + 14 LA/CLK diff pairs + EP-to-GND) |
| `README.md`    | this file |

## Header pinout (Conn_02x20, 2.54 mm)

P on the odd pin / N on the even pin of each physical row (pair sits side-by-side);
a GND row every ~3 pairs for return-current locality; power on row 1.

| pin | net | pin | net |
|----:|-----|----:|-----|
| 1 | `+3V3` | 2 | `+2V5_VADJ` |
| 3 | `FMC_CLK0_M2C_P` | 4 | `FMC_CLK0_M2C_N` |
| 5 | `FMC_CLK1_M2C_P` | 6 | `FMC_CLK1_M2C_N` |
| 7 | `GND` | 8 | `GND` |
| 9 | `FMC_LA00_CC_P` | 10 | `FMC_LA00_CC_N` |
| 11 | `FMC_LA01_CC_P` | 12 | `FMC_LA01_CC_N` |
| 13 | `FMC_LA02_P` | 14 | `FMC_LA02_N` |
| 15 | `GND` | 16 | `GND` |
| 17 | `FMC_LA03_P` | 18 | `FMC_LA03_N` |
| 19 | `FMC_LA04_P` | 20 | `FMC_LA04_N` |
| 21 | `FMC_LA05_P` | 22 | `FMC_LA05_N` |
| 23 | `GND` | 24 | `GND` |
| 25 | `FMC_LA06_P` | 26 | `FMC_LA06_N` |
| 27 | `FMC_LA07_P` | 28 | `FMC_LA07_N` |
| 29 | `FMC_LA08_P` | 30 | `FMC_LA08_N` |
| 31 | `GND` | 32 | `GND` |
| 33 | `FMC_LA09_P` | 34 | `FMC_LA09_N` |
| 35 | `FMC_LA10_P` | 36 | `FMC_LA10_N` |
| 37 | `FMC_LA11_P` | 38 | `FMC_LA11_N` |
| 39 | `GND` | 40 | `GND` |

Pairs are typed `diff_pair` 100 Ω (the SoM→header PCB trace is still
impedance-controlled; the 0.1″ header pads themselves are not — the nature of a
generic breakout). The SoM binding for each pair is the dossier section-1
contract (bank-35 IO_*).

## Parts

| ref | value | part / footprint | LCSC | role |
|-----|-------|------------------|------|------|
| J1 | 2×20 header | `Connector_Generic:Conn_02x20_Odd_Even` / `PinHeader_2x20_P2.54mm_Vertical` | *(open)* | generic 2.54 mm IO-breakout header (stock KiCad part + 3D; integrator picks the exact orderable header) |
| U1 | (VADJ LDO) | `TLV75725PDYDR` (use_part, DYD thermal-pad) | C35209004 | fixed 2.5 V LDO, EP=pin 6 netted to GND |
| C1 | 10u  | `Device:C` / C0805 | C15850 | +3V3 bulk |
| C2 | 100n | `Device:C` / C0603 | C14663 | +3V3 HF bypass |
| C3 | 1u   | `Device:C` / C0603 | C15849 | VADJ LDO input |
| C4 | 10u  | `Device:C` / C0805 | C15850 | VADJ LDO output |
| C5 | 100n | `Device:C` / C0603 | C14663 | VADJ at-header bypass |

## VADJ rail (retained)

`+2V5_VADJ` from the **TLV75725PDYDR** (fixed 2.5 V LDO) fed by `+3V3`. It is the
bank-35 VCCO reference for BOTH these LA pairs AND the camera CSI pairs, and is
offered on the header (pin 2) so the broken-out IO sits at the correct 2.5 V
level. EN strapped on; EP pad (footprint pad 6) netted to GND (DEF-E) — a real,
gate-checkable ground. Pin map 1=IN 2=GND 3=EN 4=NC 5=OUT 6=EP. The rail carries
a `testpoint()`.

**PWR-3 thermal (SBVS322C):** the DYD thermal-pad variant (RthJA ~92.5 °C/W
EP-to-GND) keeps Tj ~80 °C @ Ta=50 °C at the budget — a comfortable margin.

## Power-tree budget

- `+3V3` 0.500 A: a generic-breakout add-on allowance (was a 1.0 A FMC mezzanine).
- `+2V5_VADJ` 0.350 A: TLV75725 DYD 0.40 A thermal envelope less ~0.05 A bank-35
  VCCO (LVDS_25 drivers: 12 bank-35 LA pairs + 3 camera CSI pairs).

## Notes

- **Generic header**: the header is a stock KiCad part (symbol + footprint + 3D),
  faithful and not hand-built. The exact orderable 2×20 0.1″ header (and its LCSC)
  is the integrator's choice — left open in the BOM.
- **Freed SoM pin**: the former FMC presence-detect pin (IO_L6_P_33, J2.89) is no
  longer mapped (`som_conn_gen.py`) and is now a verbatim spare bank-33 PL IO.
- **Silkscreen**: label the site as a SoM bank-35 IO breakout (LA00-11 + CLK0/1 +
  2.5 V VADJ) so it is clear it is not a seatable FMC mezzanine.

## Local test

```bash
PYTHONPATH=. python3 -m pytest carrier/subsystems/fmc/test_fmc.py -q
```
