# devkit_mini — a second consumer that proves the subsystems port unchanged

`devkit_mini` is a small, **hypothetical** baseboard built for one purpose: to be a
**SECOND, independent consumer** of the project-agnostic `subsystems/` library
alongside the real `carrier/`, and thereby **prove the reusable-subsystem
architecture**. It imports the same library packages the carrier does and binds them
to a **deliberately different** set of project net names — so the only thing that
changes between the two boards is each subsystem's project-specific `META` dict. **The
library files (`subsystems/<name>/`) are byte-for-byte unchanged.** If the abstraction
is real, the same `circuit()` drops onto two different boards with zero library edits.

> This is not a manufacturable board — there is no carrier glue, no SoM, no power tree.
> It is a focused proof of *portability*: the subsystems compose into a believable mini
> devkit under a fresh binding, and the gate slices pass on each bound cell.

## Package contents

| file | role |
|------|------|
| `devkit_mini.py`      | the consumer — one thin adapter per subsystem (import lib + declare `META` + forward), plus `subsystem_circuits()` returning all bound Circuits |
| `test_devkit_mini.py` | end-to-end REUSE proof, offline (no kicad-cli): build, re-bind, gate slices, composition, carrier-vs-devkit divergence |
| `README.md`           | this file |

## Subsystems reused (the bill of subsystems)

Four library packages compose into the mini board — a USB-C PD sink, a USB 2.0 host
port, a level-translated microSD slot, and a USB-UART console:

| `subsystems/<name>/` | what it is | key parts |
|----------------------|-----------|-----------|
| `usb_pd`      | FUSB302B USB Type-C / PD sink PHY        | FUSB302BMPX |
| `usbc_otg`    | USB 2.0 HS host port (Type-C)            | TYPE-C-31-M-12, TPS2051C, USBLC6-2SC6 |
| `microsd`     | TXS02612 level-translated microSD slot   | TXS02612, TF-01A, TPD6E001 |
| `uart_bridge` | CP2102N USB-UART console bridge          | CP2102N-A02-GQFN24R |

Each is consumed exactly as in `carrier/subsystems/<name>.py`: `import` the library
module, declare ONE module-level `META` (`bind` / `expects` / `buses` / `notes`, the
`schgen.core.subsystem.Meta` contract), and return `_lib.circuit(META)`.

## The devkit net-naming convention (DIFFERENT from the carrier)

This is the heart of the proof — the devkit picks its **own** project net names so the
re-bind is genuine, not a copy of the carrier's map. The devkit's "host" is a
hypothetical **FPGA SoC** (hence `+1V8_FPGA` / `FPGA_UART0_*`), distinct from the
carrier's STM32 system-controller + Zynq PS naming.

### Rails

| library abstract | **devkit net** | carrier net | note |
|------------------|----------------|-------------|------|
| `+VDD_LOGIC` (usb_pd, usbc_otg) | **`+3V3_MINI`** | `+3V3_SC` | the **shared** 3.3 V logic rail |
| `+VDD_IO` (uart_bridge)         | **`+3V3_MINI`** | `+3V3`    | same shared rail |
| `+VDD_CARD` (microsd)           | **`+3V3_MINI`** | `+3V3_SD` | same shared rail (carrier kept a dedicated SD rail) |
| `+VDD_HOST` (microsd)           | **`+1V8_FPGA`** | `+1V8`    | SDIO host-signalling level |
| `+VBUS_SUPPLY` (usbc_otg)       | **`+5V_DEV`**   | `+5V_USB` | sourced onto the cable |
| `+VBUS_SENSE` (usb_pd)          | **`+VBUS_RAW`** | `+VBUS_IN`| raw receptacle VBUS the PHY senses |
| `GND` / `CHASSIS_GND`           | `GND` / `CHASSIS_GND` | (identity) | the one net all boards agree on |

The single biggest difference: the carrier spreads its 3.3 V-class supplies over three
rails (`+3V3_SC`, `+3V3`, `+3V3_SD`); the devkit deliberately collapses them onto ONE
**`+3V3_MINI`** rail shared by all four subsystems. That shared rail (plus `GND`) is the
**cross-subsystem composition** the test asserts.

### Buses / signal groups

| library abstract | **devkit name** | carrier name |
|------------------|-----------------|--------------|
| I2C bus (`buses["i2c"]`)  | **`MINI_I2C0`**   | `STM32_I2C2` |
| `CC1` / `CC2`             | **`PD_CC1/2`**    | `STM32_USB_CC1/2` |
| `SD_CLK/CMD/D0..D3`       | **`SD0_CLK/CMD/DAT0..3`** | `SDIO_CLK/CMD/D0..3` |
| `UART_TXD/RXD/RTS_N/CTS_N`| **`FPGA_UART0_*`** (post-crossover) | `ZYNQ_PS_UART0_*` |
| USB data / VBUS           | **`USB2_HOST_*` / `USB2_UART_*`** | `USB_D+/-`, `USB_UART_*` |

The bridge↔host UART **null-modem crossover** (bridge TXD → host RXD, etc.) lives in the
devkit's bind map, exactly as it lives in the carrier's — proving host-side wiring is a
**consumer** decision, not baked into the library.

## What the test proves (`test_devkit_mini.py`, offline)

Per subsystem (parametrized over all four):

1. **Builds under the devkit bind** — the library `circuit()` builds with only the
   devkit `META` supplied; no library edit.
2. **Real names present, no leaks** — every external is a devkit net name; no abstract
   interface name survives a non-identity bind, and **no carrier net name** appears (a
   real re-bind, not a copy).
3. **Net classes preserved** — bound rails still classify POWER/GROUND, bound ports
   still classify PORT (the chosen names keep the class, e.g. the `+` prefix).
4. **Bind contract honored** — rejects an unknown name, a private SIGNAL net, and a
   collision (two externals onto one net = a LAW-0 short); a typo'd top-level `META` key
   is a hard error.
5. **Local gate slices pass** — `design_rules` DECAP/EP/STRAP, `part_rules`, and model
   completeness (every pin netted-or-NC) on each bound circuit.
6. **Byte-stable rename** — same parts/refs/NCs and net **insertion order** vs the
   standalone abstract build; every draw budget follows its renamed rail.

Across the project:

7. **Cross-subsystem composition** — `+3V3_MINI` and `GND` are the **same net** (same
   name, same class) across all four bound subsystems; the only externals shared between
   subsystems are the declared shared rails (no accidental private-signal clash).
8. **Library unchanged** — binding the **same** `usb_pd.circuit()` to the carrier's names
   vs the devkit's names yields the carrier vs devkit net sets respectively, from one
   untouched library file. The two boards' external sets diverge on everything except the
   universally-shared `GND`, while the topology (parts/refs) is identical.

Run it:

```sh
PYTHONPATH=. python3 -m pytest examples/devkit_mini/test_devkit_mini.py -q
```

## Build it

```
python -m schgen devkit          # -> examples/devkit_mini/{schematic,renders,reports}/ + devkit_mini.kicad_pro
```

This builds the four bound library subsystems into real KiCad output the same way
the carrier is built (reusing `schgen.generate.board.build_board` + the place /
emit / netlist / cc machinery — no carrier code copied, the carrier is untouched).
The board netlist gate proves every net merges across sheets and the geometry-only
`cc_gate` proves 0 shorts / 0 opens (LAW 0). The shared rails confirm the
composition — e.g. `+3V3_MINI` and `GND` span all four subsystem sheets, the same
library packages re-bound to THIS board's net names.
