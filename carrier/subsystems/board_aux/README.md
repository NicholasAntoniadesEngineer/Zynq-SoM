# board_aux — the manually-gated +3V3_AUX rail + its PCA9306 I2C isolator

The INFRASTRUCTURE half of the board-services block: it makes the gated
`+3V3_AUX` rail and bridges the always-on management I2C onto the gated segment.
The peripherals it feeds live on `board_services`; the QWIIC connector that
re-exports the rail + bus lives on `board_qwiic`. This is a **carrier-LOCAL**
subsystem (real carrier net names wired directly — no abstract-interface `META`
bind contract). It is kept on its own sheet so neither sheet is dense enough to
defeat the placer's rail-stub router.

## Package contents

| file | role |
|------|------|
| `board_aux.py`      | the NETLIST — `circuit()` returning the carrier `Circuit` |
| `board_aux.cir`     | SPICE subckt — the passive network (gate IN/OUT bypass, ILIM-set, EN pulldown, status LED divider, PCA9306 VREF bypass + EN/bus pull-ups) with the external nets as subckt pins |
| `test_board_aux.py` | LOCAL electrical-correctness test (offline: model completeness + decap/strap slice + ratings + SPICE-passive match + the gate/isolation invariants) |
| `README.md`         | this file |

## Parts

| ref | part | MPN / lib | LCSC | role |
|-----|------|-----------|------|------|
| U1  | load switch | `SY6280AAC` | C (parts lib) | gates `+3V3` → `+3V3_AUX`; ILIM = 6800/13k ≈ 523 mA |
| U2  | I2C isolator | `PCA9306DCUR` | C (parts lib) | bidirectional level/isolation switch, STM32_I2C2 ↔ AUX_I2C |
| SW1 | DIP switch | `DSHP04TSGER` | C (parts lib) | manual enable (pos 1 closes +3V3 → EN_AUX); pos 2–4 spare |
| D1  | LED | `Device:LED` red | C2286 | gated-rail status LED (lit = AUX enabled) |
| C1–C4 | 100n | `Device:C` | C14663 | U1.IN, U1.OUT, U2.VREF1, U2.VREF2 bypass |
| R1  | 13k  | `Device:R` | C22797 | SY6280 ISET (ILIM ≈ 523 mA) |
| R2  | 100k | `Device:R` | C25803 | EN_AUX pulldown (default-OFF at power-up) |
| R3  | 330R | `Device:R` | C23138 | status LED series resistor |
| R4  | 100k | `Device:R` | C25803 | PCA9306 EN pull-up to +3V3_AUX |
| R5,R6 | 4k7 | `Device:R` | C23162 | AUX-bus SDA/SCL pull-ups to +3V3_AUX |
| TP1–TP3 | testpoint | — | — | probes on +3V3_AUX / AUX_I2C_SCL / AUX_I2C_SDA |

(Refs above are illustrative of the auto-assigned order; the netlist is the
authority — the local test keys on net topology, not refdes.)

## The I2C bus and isolation

The board_services peripherals run off the GATED rail but their bus is the
always-on `STM32_I2C2` management bus. Tying gated SDA/SCL straight to that
pulled-up bus would back-power the unpowered chips through their ESD diodes
(LAW 0). U2 (PCA9306) bridges the two domains:

- **side 1** references `+3V3_SC` (the always-on bus; its pull-ups already live
  on `bringup_rails`) — ports `STM32_I2C2_SCL` / `STM32_I2C2_SDA`.
- **side 2** references `+3V3_AUX` with its OWN 4k7 pull-ups (R5/R6) — ports
  `AUX_I2C_SCL` / `AUX_I2C_SDA`, published for `board_services` / `board_qwiic`.
- **EN** is pulled to `+3V3_AUX`, so the switch OPENS (isolated) whenever the AUX
  rail is down — the peripherals are cleanly cut off when off.

Both i2c port pairs are typed (scl/sda, 400 kHz): bus `STM32_I2C2` on side 1,
bus `AUX_I2C` on side 2.

## Notes (the gate + the isolation reference split)

- **Power gate (C1: "a manual power enable like the previous").** U1 gates
  `+3V3` → `+3V3_AUX` exactly like the ten bring-up module switches, but its
  enable is LOCAL and defaults OFF: SW1 (pos 1) closes `+3V3` onto `EN_AUX` and
  the 100k pulldown holds `EN_AUX` low until a human flips the switch. Keeping
  the gate self-contained here makes the whole block one add / one revert,
  touching none of the dense rail-control sheets.
- **Isolation reference split (LAW 0).** The PCA9306's two VREF pins reference
  the two different rails — that asymmetry IS the isolation; the local test
  asserts VREF1 = +3V3_SC and VREF2 = +3V3_AUX and that EN is pulled to the
  gated rail.
- **Status + probes.** A red LED on the gated output makes the enable state
  visible at a glance; three testpoints expose the rail and the isolated bus.
- This sheet's own `+3V3_AUX` load (status LED + the two 4k7 pulls) is declared
  for the power tree; the peripherals declare theirs on `board_services`.

## Local test

```bash
PYTHONPATH=. python3 -m pytest carrier/subsystems/board_aux/test_board_aux.py -q
```

Board-level gates (full power-tree headroom, board ERC, the cross-sheet link /
port-driver graph) stay aggregated by `schgen board`.
