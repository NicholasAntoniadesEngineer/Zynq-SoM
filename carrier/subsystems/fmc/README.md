# fmc — SoM bank-35 IO breakout on a generic 2.54 mm header

A carrier-local schgen subsystem that breaks out the SoM bank-35 LVDS IO
(14 differential pairs: CLK0/CLK1_M2C plus LA00–LA11) onto a generic 2×20
0.1″ / 2.54 mm pin header, together with a local 2.5 V VADJ rail. It is a
cheap, universally-wireable IO breakout — no specific FMC mezzanine card is
required.

## Interface

This is a carrier-LOCAL subsystem: it drives the carrier power/ground nets
directly, and exposes the 14 IO pairs as typed diff-pair ports for binding.

- Header `J1` exposes each of the 14 pairs as typed `diff_pair` ports
  (`<stem>_P` / `<stem>_N`, 100 Ω, paired). The functional stems
  (`FMC_CLK0_M2C`, `FMC_CLK1_M2C`, `FMC_LA00_CC`, `FMC_LA01_CC`,
  `FMC_LA02`…`FMC_LA11`) match the SoM-side names, so the SoM binding
  (`som_conn_gen` FUNCTION_MAP), the XDC pin constraints and the SI diff-pair
  constraints — which reference the SoM bank-35 pins, not this connector —
  merge against these names. Each pair expects the `som_j3/j1` bank-35 pin map.
- Carrier nets driven: `+3V3` (input rail), `+2V5_VADJ` (generated VADJ rail,
  also offered on the header), `GND`.
- `+2V5_VADJ` carries a `testpoint()` so the locally-generated rail is probeable.

## Design

Header. `J1` is a stock KiCad 2×20 0.1″ part
(`Connector_Generic:Conn_02x20_Odd_Even` +
`Connector_PinHeader_2.54mm:PinHeader_2x20_P2.54mm_Vertical`, with KiCad's own
3D model). It is intentionally generic; the integrator picks the exact orderable
header, so its LCSC is left open in the BOM.

Pinout. P sits on the odd pin and N on the even pin of each physical row so a
pair is side-by-side; a GND row falls every ~3 pairs for return-current
locality; `+3V3` and `+2V5_VADJ` are on row 1 so an add-on can be powered and
level-referenced from the header:

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

Diff pairs. Each of the 14 pairs is typed `diff_pair` at 100 Ω: the SoM→header
PCB trace is impedance-controlled. The 0.1″ header pads themselves are not
controlled-impedance — that is the nature of a generic breakout.

VADJ rail. `+2V5_VADJ` is generated locally by the TLV75725PDYDR fixed 2.5 V LDO
fed from `+3V3`. This rail is the bank-35 VCCO reference for both the LA pairs
broken out here and the camera CSI pairs, so the IO sits at the correct 2.5 V
LVDS level; it is also offered on the header (pin 2) so an add-on references the
same level. The TLV75725 is a 1 A LDO and the DYD package carries an exposed
thermal pad. EN (`U1.3`) is strapped to `+3V3` (enabled on); `U1.4` (NC) is left
unconnected; the EP pad (`U1.6`) is netted to GND — a real, gate-checkable
ground, not a layout-only pour bond. Pin map: 1=IN, 2=GND, 3=EN, 4=NC, 5=OUT,
6=EP. Bypass: `C1` 10 µF bulk + `C2` 100 nF on `+3V3`, `C3` 1 µF at the LDO
input, `C4` 10 µF at the LDO output, `C5` 100 nF at the header on `+2V5_VADJ`.

Power budget. `+3V3` draws a 0.500 A header allowance for an add-on. `+2V5_VADJ`
budgets 0.350 A: the TLV75725 DYD 0.40 A envelope less the ~0.05 A real bank-35
VCCO load (the LVDS_25 drivers across the LA and camera CSI pairs). The figures
are conservative header-allowance bookkeeping, not a thermal ceiling.

## Parts

| ref | value | lib / part | LCSC |
|-----|-------|------------|------|
| J1 | Header_2x20_2.54mm | `Connector_Generic:Conn_02x20_Odd_Even` / `PinHeader_2x20_P2.54mm_Vertical` | open |
| U1 | TLV75725PDYDR | `use_part` TLV75725PDYDR (DYD thermal-pad LDO) | via part lib |
| C1 | 10u | `Device:C` / C_0805 | C15850 |
| C2 | 100n | `Device:C` / C_0603 | C14663 |
| C3 | 1u | `Device:C` / C_0603 | C15849 |
| C4 | 10u | `Device:C` / C_0805 | C15850 |
| C5 | 100n | `Device:C` / C_0603 | C14663 |

## Build & test

`test_fmc.py` checks model completeness, the header pinout, the VADJ LDO and its
EP-to-GND tie, and the 14 LA/CLK diff pairs.

```bash
PYTHONPATH=. python3 -m pytest carrier/subsystems/fmc/test_fmc.py -q
```
