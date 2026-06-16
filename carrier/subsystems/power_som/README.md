# power_som — always-on +VIN -> +5V_SOM buck (the SoM VIN supply, P0 fix)

The single dedicated step-down converter that feeds the SoM's `VIN` pin. The SoM
is a **4.2-5 V-input** module (its on-module regulators are all 6 V-class), so
binding its `J1.VIN` straight to the 20 V PD rail would destroy it at the first PD
contract (**P0**, user-signed-off 2026-06-12). This buck (`U4`) drops
`+VIN -> +5V_SOM` (5 V class) and `som_conn_gen` rebinds `J1.VIN -> +5V_SOM`.

This is a **carrier-LOCAL** subsystem: it is folded into the `<name>/<name>.py`
package layout (same 4-artifact parity as the generic `subsystems/<name>/`
library) but wires the carrier's REAL net names directly — no abstract interface
/ `META` bind contract.

It was **split out of `power.py`** for sheet density (the multi-converter power
sheet overflowed one A3 page). `+5V_SOM` is the cleanly-separable unit: only the
`+VIN_SYS` / `+5V_SOM` / `GND` rails cross to `power.py` (they merge by name
across sheets); every signal net (`EN_5V_SOM` / `SW_5V_SOM` / `BOOT_5V_SOM` /
`FB_5V_SOM` / `PG_5V_SOM` / `RT_5V_SOM` / `BIAS_5V_SOM` / `CFF_5V_SOM` / `U4_VCC`)
is internal.

## Package contents

| file | role |
|------|------|
| `power_som.py`      | the NETLIST — `circuit()` returning the carrier `Circuit` |
| `power_som.cir`     | SPICE subckt — the LM61460 buck passive network (input/output bulk, BOOT, BIAS/VCC bypass, FB divider + feedforward) with the carrier externals as subckt pins |
| `test_power_som.py` | LOCAL electrical-correctness test (offline: model completeness + decap/EP slice + ratings + FB-divider invariant + LM61460 heat path + SPICE-passive match) |
| `README.md`         | this file |

## Parts (live-verified on JLCPCB)

| ref | part | LCSC | role |
|-----|------|------|------|
| U4  | `LM61460AANRJRR` | C2864505 | TI 3-42 V / **6 A** synchronous buck, VQFN-HR (RJR "HotRod") — the SAME EP-equivalent part as `power.py` U1/U2 |
| L3  | `SWPA8040S100MT` 10 uH | C37429 | buck inductor (Isat 4.1 A) |
| R12 | 10k | C25804 | EN-clamp series (`+VIN_SYS -> EN`) |
| D5  | `MMSZ5231B` 5.1 V zener | C85181 | EN-clamp shunt (`EN -> GND`) |
| C20 | 100n | C14663 | EN bypass |
| R14 / R15 | 47.5k / 13k | C23061 / C22797 | **FB divider -> 4.654 V nom** (WC [4.582, 4.728] V, inside the SoM 4.2-5.0 V window) |
| C21 / R19 | 22p / 1k | C1653 / C21190 | FB feedforward (CFF) + RFF damp |
| R17 / C23 | 10R / 1u | C22859 / C15849 | BIAS series + bypass (BIAS tied to VOUT) |
| C22 | 1u | C15849 | VCC internal-LDO bypass |
| R18 | 22k | C31850 | RT (fSW = 600 kHz) |
| C17 | 100n | C14663 | BOOT (CBOOT) cap (RBOOT shorted to CBOOT) |
| C14 / C25 | 100n | C14663 | per-VIN-pin HF input bypass |
| C15 / C16 | 10u | C13585 | input bulk |
| C18 / C19 | 22u | C45783 | output bulk |
| D4 / R16 | red LED / 1k | C2286 / C21190 | power-good indicator |

## Rails

| net | role |
|-----|------|
| `+VIN_SYS` | buck INPUT — the **post-RS1** rail (RS1 in `power_mon` sits between the eFuse `+VIN` and all buck inputs), so U4's draw is counted on the `+VIN_SYS` telemetry channel |
| `+5V_SOM`  | buck OUTPUT, **always-on**, the SoM VIN supply (`som_conn_gen` binds `J1.VIN` here) + BIAS tie |
| `GND`      | return + the LM61460 heat path (PGND1/PGND2/AGND on the GND pour) |

## Notes (datasheet + bring-up contract)

- **Always-on, NO bring-up gate (P0).** `+5V_SOM` must be alive pre-DIP / pre-PD
  so the SoM SC can boot and master the FUSB302 PD negotiation. The PD chain is
  `FUSB302` (on `+3V3_SC`) + the SoM SC, and `+3V3_SC` is generated ON the SoM
  from its VIN — so if SoM VIN waited for a DIP the SC would be dead, nobody would
  negotiate PD, and 20 V would never arrive (circular). At the 5 V default-USB
  contract the buck runs near 100 % duty and passes ~4.7-4.8 V; after the 20 V
  contract it regulates ~4.65 V (PWR-5 divider). Alive pre-DIP by design, like
  `+3V3_SC`.
- **PWR-1 — EN clamp.** The always-on EN strap must enable the buck at the 4.75 V
  default-USB contract AND never exceed the EN rec-max at the 21 V contract. A
  plain divider can't do both, so `R12` (10k series `+VIN_SYS -> EN`) + `D5`
  (5.1 V zener `EN -> GND`) + `C20` (100n bypass): at low VIN the zener is off and
  EN ~= VIN (sure enable); at high VIN the zener clamps EN to ~5.0 V. EN stays
  inside [~1.3, 5.5] V across 4.75-21 V. The schgen spice gate re-derives EN from
  the netlist (finding the EN/SYNC pin by name) and FAILS if EN ever leaves
  [1.5, 5.5] V — PWR-1 can never silently regress.
- **U4 thermal (2026-06-16, NO WAIVER).** U4 WAS a TPS54302 (SOT-23-6, no EP, 3 A)
  whose HONEST datasheet RthJA put `Tj` over the 125 C rec-max at the +5V_SOM
  2.004 A load — masked by a fabricated 70.6 C/W + a 140 C guard + an author
  waiver. `thermal.py` is re-based to the datasheet figures and U4 is RESELECTED
  to the LM61460 EP buck: at the gate's pour-aware 30 C/W, `Tj` ~99 C << the
  140 C guard. U4 draws its FAITHFUL `parts/LM61460AANRJRR/` dossier symbol (no
  `lib_id` override, the "0 hand-built symbols" idiom).
- **PGOOD unused.** `U4.5` (PGOOD, open-drain) is an author no-connect — `D4` is
  the board PG indicator; an un-driven open-drain output floats harmlessly.

## Local test

```bash
PYTHONPATH=. python3 -m pytest carrier/subsystems/power_som/test_power_som.py -q
```

The board-level gates (full power tree, the EN spice/clamp check, the thermal
join, board ERC, the netlist merge) stay aggregated by `schgen board`.
