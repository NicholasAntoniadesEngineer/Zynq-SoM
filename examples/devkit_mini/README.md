# devkit_mini — a second consumer of the `subsystems/` library

`devkit_mini` is a small, hypothetical baseboard whose purpose is to be a second,
independent consumer of the project-agnostic `subsystems/` library — alongside the
real `carrier/`. It imports the same library packages the carrier imports and binds
them to a deliberately different set of project net names. The only project-specific
code is the per-subsystem `META` dict in `devkit_mini.py`; the library files under
`subsystems/<name>/` are unchanged. If the subsystem abstraction holds, the same
`circuit()` builds onto two different boards with no library edits.

This is not a manufacturable board: it has no SoM, no power tree, and no connector
glue sheets. It is a portability proof — the four library subsystems compose into a
believable mini devkit under a fresh net-name binding, and the gates pass on the
composed result.

## Structure

| path | role |
|------|------|
| `devkit_mini.py` | the consumer: one thin adapter per subsystem (import the library module, declare a `META` dict, forward it to `circuit(META)`), plus `subsystem_circuits()` returning all bound `Circuit`s and `PROJECT` / `SHARED_RAILS` declarations |
| `__init__.py` | re-exports `PROJECT`, `subsystem_circuits`, and the four `*_circuit()` builders |
| `test_devkit_mini.py` | offline reuse proof (no kicad-cli, no network) |
| `schematic/<name>.kicad_sch` | per-subsystem schematics emitted by the build |
| `renders/<name>.png` | per-sheet PNG renders emitted by the build |
| `reports/` | gate outputs: `cc_gate.txt`, `board_gate.txt`, `board.erc.rpt` |
| `devkit_mini.kicad_pro`, `devkit_mini.kicad_prl`, `devkit_mini.kicad_sch` | the openable KiCad hierarchy project (root + per-sheet schematics) |

## The four reused subsystems

`devkit_mini.py` binds four library packages, in this order (`PROJECT`):

| `subsystems/<name>/` | function | key parts |
|----------------------|----------|-----------|
| `usb_pd` | FUSB302B USB Type-C / PD sink PHY | FUSB302BMPX |
| `usbc_otg` | USB 2.0 HS host port (Type-C) | TYPE-C receptacle, TPS2051C power switch, USBLC6-2SC6 ESD |
| `microsd` | TXS02612 level-translated microSD slot | TXS02612, microSD socket, TPD6E001 ESD |
| `uart_bridge` | CP2102N USB-UART console bridge | CP2102N-A02-GQFN24R |

Each adapter is the same shape as `carrier/subsystems/<name>.py`: import the library
module, declare one module-level `META` (`bind` / `expects` / `buses` / `notes`, the
`schgen.core.subsystem.Meta` contract), and return `_lib.circuit(META)`.

## Net-naming convention (distinct from the carrier)

The devkit chooses its own project net names so the re-bind is genuine rather than a
copy of the carrier's map. The devkit's host is treated as a hypothetical FPGA SoC,
which is why the host-side names read `+1V8_FPGA` and `FPGA_UART0_*`.

### Rails

| library abstract | devkit net | carrier net | meaning |
|------------------|-----------|-------------|---------|
| `+VDD_LOGIC` (usb_pd, usbc_otg) | `+3V3_MINI` | `+3V3_SC` | shared 3.3 V logic rail |
| `+VDD_IO` (uart_bridge) | `+3V3_MINI` | `+3V3` | same shared rail |
| `+VDD_CARD` (microsd) | `+3V3_MINI` | `+3V3_SD` | same shared rail (carrier keeps a dedicated SD rail) |
| `+VDD_HOST` (microsd) | `+1V8_FPGA` | `+1V8` | SDIO host-signalling level |
| `+VBUS_SUPPLY` (usbc_otg) | `+5V_DEV` | `+5V_USB` | 5 V sourced onto the OTG cable |
| `+VBUS_SENSE` (usb_pd) | `+VBUS_RAW` | `+VBUS_IN` | raw receptacle VBUS the PD PHY senses |
| `GND`, `CHASSIS_GND` | `GND`, `CHASSIS_GND` | identity | the nets every board agrees on |

The defining choice: the carrier spreads its 3.3 V-class supplies over three rails
(`+3V3_SC`, `+3V3`, `+3V3_SD`), while the devkit collapses them onto one `+3V3_MINI`
rail shared by all four subsystems. That shared rail, together with `GND`, is the
cross-subsystem composition the test and the board netlist gate verify (`+3V3_MINI`
spans 4 sheets / 26 pins; `GND` spans 4 sheets / 37 pins).

### Buses and signal groups

| library abstract | devkit name | carrier name |
|------------------|-------------|--------------|
| I2C bus (`buses["i2c"]`) | `MINI_I2C0` | `STM32_I2C2` |
| `CC1` / `CC2` | `PD_CC1` / `PD_CC2` | `STM32_USB_CC1/2` |
| `SD_CLK/CMD/D0..D3` | `SD0_CLK/CMD/DAT0..3` | `SDIO_*` |
| `UART_TXD/RXD/RTS_N/CTS_N` | `FPGA_UART0_*` (post-crossover) | `ZYNQ_PS_UART0_*` |
| USB data / VBUS | `USB2_HOST_*` / `USB2_UART_*` | `USB_D+/-`, `USB_UART_*` |

The bridge↔host UART null-modem crossover (bridge `TXD` → host `RXD`, bridge `RTS_N`
→ host `CTS_N`, and vice versa) lives in the devkit's bind map, exactly as it lives
in the carrier's. Host-side wiring is a consumer decision, not part of the library.

## Build it

```sh
python -m schgen devkit          # add --no-render to skip the PNGs
```

`schgen devkit` (`schgen/generate/devkit.py`) builds the four bound library
subsystems with the same generic machinery the carrier uses —
`place.place_and_route`, `output.emit.emit`, `generate.board.build_board`,
`verify.cc_gate`, and `output.render.render_sheet_to_png` — without copying any
carrier code. The carrier-specific steps (SoM DF40 contract, `sheet_index.json`,
carrier-structure gate, SoM-centered floorplan) do not apply because the devkit has
no SoM.

It writes:

- `schematic/<name>.kicad_sch` — one schematic per subsystem,
- the `devkit_mini.kicad_pro` hierarchy root that opens them together,
- `renders/<name>.png` — per-sheet renders (best-effort; skipped with `--no-render`),
- `reports/cc_gate.txt` and `reports/board_gate.txt` — the gate results.

The build passes only if every gate passes:

- the board netlist gate (`build_board`) confirms every linked net merges across
  sheets — the shared `+3V3_MINI` and `GND` rails span all four sheets, root ERC is
  clean;
- the geometry-only connected-components gate (`cc_gate`) confirms 0 shorts and 0
  opens across the composed board (each sheet's declared nets agree with its emitted
  geometry components).

## Test it

```sh
PYTHONPATH=. python3 -m pytest examples/devkit_mini/test_devkit_mini.py -q
```

`test_devkit_mini.py` runs offline and asserts, parametrized over all four
subsystems unless noted:

1. each library subsystem builds under the devkit `META` with no library edit;
2. every external net is a devkit name — no abstract interface name leaks (except
   identity-bound `GND`/`CHASSIS_GND`), and no carrier name appears (a real re-bind);
3. binding is a pure rename: bound rails still classify POWER/GROUND, bound ports
   still classify PORT;
4. the bind contract holds — it rejects an unknown name, a private SIGNAL net, a
   collision of two externals onto one net, and a typo'd top-level `META` key;
5. local gate slices pass on each bound circuit — `design_rules` DECAP/EP/STRAP,
   `part_rules`, and model completeness (every pin netted or NC); the DECAP rule is
   confirmed non-trivial at the project aggregate (`checked["decap"] >= 1`);
6. the bind is byte-stable — same parts, refs, and no-connects, and the net
   insertion order is preserved versus the standalone abstract build, so each power
   draw budget follows its renamed rail;
7. composition — `+3V3_MINI` and `GND` are the same net (same name, same class)
   across all four subsystems, and the only externals shared between subsystems are
   those two declared shared rails (no accidental private-signal clash);
8. library unchanged — binding the same `usb_pd.circuit()` to the carrier's names
   versus the devkit's names yields the carrier versus devkit net sets from one
   untouched source; the two sets overlap only on `GND`, and the part topology is
   identical;
9. the four bound subsystems place, route, and compose into one board with 0 shorts
   / 0 opens (`cc_gate`).
