# power_som — always-on +VIN -> +5V_SOM buck (the SoM VIN supply)

The dedicated step-down converter that feeds the SoM's `VIN` pin. The SoM is a
**4.2-5 V-input** module (its on-module regulators are all 6 V-class), so its
`J1.VIN` cannot bind to the 20 V PD rail. This buck (`U4`) drops
`+VIN_SYS -> +5V_SOM` (5 V class) and `som_conn_gen` binds `J1.VIN -> +5V_SOM`.

This is a **carrier-LOCAL** subsystem: it wires the carrier's real net names
directly (no abstract interface / `META` bind contract). Its maintained authoring
implementation is `native/src/project_authoring_devkit_mini_power_som.cpp`.

## Interface

Carrier-local — there is no abstract port API. The subsystem drives these
carrier nets directly:

| net | direction | role |
|-----|-----------|------|
| `+VIN_SYS` | input | buck INPUT — the **post-RS1** rail (RS1 in `power_mon` sits between the eFuse `+VIN` and all buck inputs), so U4's draw is metered on the `+VIN_SYS` telemetry channel |
| `+5V_SOM`  | output | buck OUTPUT, **always-on**, the SoM VIN supply (`som_conn_gen` binds `J1.VIN` here) + BIAS tie |
| `GND`      | return | return + the LM61460 heat path (PGND1/PGND2/AGND on the GND pour) |

Every other net (`SW_5V_SOM`, `BOOT_5V_SOM`, `FB_5V_SOM`,
`PG_5V_SOM`, `RT_5V_SOM`, `BIAS_5V_SOM`, `CFF_5V_SOM`, `U4_VCC`) is internal to
this stage. Cross-sheet rails merge by name with the `power` subsystem.

## Design

- **Buck (`U4` = LM61460AANRJRR).** TI 3-36 V / 6 A synchronous buck in VQFN-HR
  (RJR "HotRod") — the same part as `power` U1/U2. At the
  +5V_SOM ~2 A load the 6 A rating gives 67% headroom, and its PGND1/PGND2 + SW
  pads contribute to heat removal, but **SW must remain on its switched net,
  never on GND**. Prior estimated junction temperatures are not layout-qualified
  thermal evidence. U4 draws its
  faithful `parts/LM61460AANRJRR/` dossier symbol (pins by number: 1 BIAS,
  2 VCC, 3 AGND, 4 FB, 5 PGOOD, 6 RT, 7 EN/SYNC, 8 VIN1, 9 PGND1, 10 SW,
  11 PGND2, 12 VIN2, 13 RBOOT, 14 CBOOT).

- **Always-on, NO bring-up gate.** `+5V_SOM` must be alive pre-DIP / pre-PD so
  the SoM SC can boot and master the FUSB302 PD negotiation. The PD chain is the
  `FUSB302` (on `+3V3_SC`) + the SoM SC, and `+3V3_SC` is generated ON the SoM
  from its VIN — so gating SoM VIN on a DIP would leave the SC dead, nothing to
  negotiate PD, and 20 V would never arrive (circular). At the 5 V default-USB
  contract the buck runs near 100% duty and passes ~4.7-4.8 V (inside the
  4.2-5 V window); after the 20 V contract it regulates ~4.65 V.

- **PWR-1 — direct VIN enable.** U4.7 now shares `+VIN_SYS` with VIN1/VIN2
  (pins 8/12), the self-start arrangement described in
  [TI SNVSBD5D section 8.3.1](https://www.ti.com/lit/ds/symlink/lm61460.pdf).
  The inherited TPS54302-era R12/D5/C20 network is removed, including its
  external RC delay/filter. No external enable-delay requirement was identified;
  input decoupling and internal UVLO/soft-start are retained. The native check
  proves unique net ownership only, not input-envelope, startup-time or transient
  performance. Those require separate qualification; this is not fabrication
  readiness. No device voltage limit was relaxed.

- **FB divider.** Vref = 1.0 V, so `Vout = 1.0 * (1 + Rtop/Rbot)`. `R14/R15` =
  47.5k/13k -> **4.654 V nom** (WC-corner [4.582, 4.728] V, inside the SoM
  4.2-5.0 V input window). A 22 pF C0G feedforward (`C21`) across the FB top
  plus a 1k series damp (`R19`) shape the loop: `+5V_SOM -> C21 -> R19 -> FB`.

- **Switching node.** `L3` = SWPA8040S100MT 10 uH (Isat 4.1 A) on `SW_5V_SOM`;
  `C17` = 100 nF BOOT cap with RBOOT(13) shorted to CBOOT(14) as one node; `R18`
  = 22k on RT -> fSW ~600 kHz (matches U1/U2).

- **Bias / supply.** BIAS (pin 1) tied to VOUT through `R17` = 10R + `C23` = 1u
  bypass (VOUT 4.65 V > the 3.1 V BIAS-active threshold; BIAS max 16 V); `C22` =
  1u VCC internal-LDO bypass.

- **Input / output filtering.** Per-VIN-pin HF bypass `C14`/`C25` = 100 nF +
  bulk `C15`/`C16` = 10u (50 V class for the 20 V rail) on the input; `C18`/`C19`
  = 22u output bulk.

- **PGOOD.** `U4.5` (PGOOD, open-drain) is an author no-connect; `D4`/`R16`
  (red LED + 1k) on `+5V_SOM` are the board power-good indicator. An un-driven
  open-drain output floats harmlessly.

## Parts

| ref | value | lib/part | LCSC |
|-----|-------|----------|------|
| U4  | LM61460AANRJRR | LM61460AANRJRR | C2864505 |
| L3  | 10uH | Device:L (SWPA8040S100MT) | C37429 |
| C14 | 100n | Device:C | C14663 |
| C25 | 100n | Device:C | C14663 |
| C15 | 10u | Device:C | C13585 |
| C16 | 10u | Device:C | C13585 |
| C22 | 1u | Device:C | C15849 |
| R17 | 10R | Device:R | C22859 |
| C23 | 1u | Device:C | C15849 |
| R18 | 22k | Device:R | C31850 |
| C17 | 100n | Device:C | C14663 |
| C18 | 22u | Device:C | C45783 |
| C19 | 22u | Device:C | C45783 |
| R14 | 47.5k | Device:R | C23061 |
| R15 | 13k | Device:R | C22797 |
| C21 | 22p | Device:C | C1653 |
| R19 | 1k | Device:R | C21190 |
| D4  | red | Device:LED | C2286 |
| R16 | 1k | Device:R | C21190 |

## Build & test

The native commands distinguish circuit completeness from electrical
qualification. The SPICE report labels the direct enable check as netlist
topology, not an analog voltage calculation. Structural or topology PASS alone
does not qualify operating margins or transients.

```bash
native/bin/schgen circuit-check --project devkit_mini power_som
native/bin/schgen spice --project devkit_mini power_som --no-ngspice
ctest --test-dir native/build/fast --output-on-failure -R '^native_(spice|board_pipeline)_contracts$'
```
