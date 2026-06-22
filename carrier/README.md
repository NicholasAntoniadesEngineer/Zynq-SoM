# carrier — the generated carrier board

Open `Zynq_Carrier.kicad_pro` in KiCad (9+). EVERYTHING here except
`subsystems/*.py`, the research dossiers and `HISTORY.md` is generated —
regenerate in place with `PYTHONPATH=. python -m schgen board`.

## Architecture (the locked decisions)

The carrier hosts a Zynq-7000 SoM over the J1/J2/J3 mezzanine. The full
decision log with rationale is archived in [`HISTORY.md`](../docs/HISTORY.md); the
still-true essentials:

- **Power input is USB-C PD only**, 20 V / 3 A via the FUSB302B, behind a
  TPS26631 eFuse with soft-start (controlled inrush + inlet OVP/OCP). No
  barrel jack.
- **The SoM is a 4.2–5 V module — it must NEVER see the 20 V rail** (P0, the
  most important electrical decision). An **always-on `+5V_SOM` buck**
  (its own `power_som` sheet) feeds the SoM's J1 VIN pins; always-on because
  PD negotiation is circular (the system controller must boot first).
- **Carrier bucks win over the SoM's exported rails** — the SoM's +3V3/+1V8
  on J1 are isolated (NC / TP-only); carrier rails are +5V, +3V3, +1V8, plus
  per-module **gated rails** (+5V_USB, +3V3_SD, the HDMI/LCD/CAM/PMOD/AUX
  rails) sourced by bring-up load switches.
- **Bring-up is staged with switches**: a DIP switch AND a system-controller
  GPIO override drive every regulator/module enable; per-rail power-good LEDs;
  rails come up one at a time. New board-services HW (ID-EEPROM, RTC, QWIIC,
  watchdog) sits behind the same gated `+3V3_AUX` rail and a PCA9306 I2C
  isolator (so the gated bus can never back-power the always-on management I2C).
- **microSD carries a mandatory 1.8 V ↔ 3.3 V level translator** (TXS02612):
  the SoM exposes SDIO at 1.8 V, but SD cards init at 3.3 V.
- **Stackup is JLCPCB 4-layer JLC04161H-7628**; its impedance geometry drives
  the exported layout constraints (90 Ω USB, 100 Ω TMDS/LVDS/MIPI). The user
  owns the PCB outline + placement — the floorplan kit is a suggestion.

## The subsystem / adapter pattern

A board sheet is one Python netlist under `subsystems/` — **the only
hand-written layer**. There are two flavours:

- **Thin adapters over the reusable library.** A portable subsystem lives in
  the project-agnostic top-level [`subsystems/`](../subsystems/README.md)
  library with ABSTRACT port/rail names; the carrier consumes it with a tiny
  adapter that declares ONE module-level `META` dict and forwards it —
  `return _lib.circuit(META)`. `META["bind"]` renames the abstract nets to the
  carrier's real net names (order-preserving, so the emitted sheet is
  byte-identical to a hand-written one); `expects` / `buses` / `notes` carry
  the project-specific linker deferrals, bus names and house-style prose. The
  contract is `schgen/core/subsystem.py` (`Meta`); a typo'd top-level key is a
  hard `CircuitError`. 17 subsystems are migrated this way (usb_pd, usbc_otg,
  uart_bridge, usb_jtag, ethernet, hdmi_tx, hdmi_rx, lcd, microsd, camera, pmod,
  pmod_expansion, pd_input, power, rj45_connector, usb_uart_connector,
  usb_jtag_connector) — see [`subsystems/README.md`](../subsystems/README.md).
- **Carrier-specific glue stays local.** Sheets that only make sense for this
  board — the J1/J2/J3 connector sheets, the bring-up + power + power-monitor
  sheets, the board-services HW, the carrier connectors — are authored directly
  under `subsystems/` as full netlists. See
  [`subsystems/README.md`](subsystems/README.md) for the authoring guide.

Either way the rule is the same: **the .py is the NETLIST, never geometry.**
No coordinates, no wire plans, no text positions; a purity gate AST-scans every
subsystem and fails the build if it defines `placer` or imports a geometry API.
All placement is derived from circuit topology by `schgen/place.py`.

- `subsystems/` — the authored netlists (adapters + local glue), the only
  hand-written layer; see `subsystems/README.md`.
- `Zynq_Carrier.kicad_sch` + `schematic/` — the root sheet + sub-sheets
  (hierarchy mode, board-unique references), committed.
- `renders/` — one PNG per sheet, committed and reviewable on GitHub;
  `golden.json` holds perceptual hashes — drift warns, `schgen board
  --bless` accepts intentional changes.
- `reports/` — per-sheet ERC, gate verdicts, link report, board netlist
  gate: the proof travels with the design.
- `manufacturing/` — `bom_jlc.csv` + JLC04161H-7628 layout constraints.
- `fpga/` — `Zynq_Carrier_pins.xdc`, GENERATED Vivado pin constraints
  (`schgen xdc`): every carrier port on a Zynq PL ball through J2/J3,
  ball map live-extracted from the SoM project (never hand-typed),
  cross-checked against `som_interface.json` (stale contract = build
  FAIL), IOSTANDARD from the PLAN VCCO rail map.
- `som_interface.json` — the SoM↔carrier J1/J2/J3 contract, extracted
  programmatically (`schgen som-interface`), never hand-edited.
- `nets.py` — the GENERATED cross-sheet net-name contract
  (`schgen nets`).
- `HISTORY.md` — the **archived** decision log (the former `PLAN.md` +
  `OVERNIGHT_PLAN.md` + `MORNING_REPORT.md`): every locked decision and
  autonomous-run record, kept for the WHY.
- `research/` — the per-subsystem engineering dossiers (datasheet-grounded,
  hand-written): [`bringup_power_gating.md`](research/bringup_power_gating.md),
  [`camera_csi.md`](research/camera_csi.md),
  [`debug_boot_pmod.md`](research/debug_boot_pmod.md), [`fmc.md`](research/fmc.md),
  [`lcd_backlight.md`](research/lcd_backlight.md), [`power_mon.md`](research/power_mon.md),
  [`thermal_bucks.md`](research/thermal_bucks.md) (the TPS54302 buck Tj review
  item), [`usb_jtag_pmod_expansion.md`](research/usb_jtag_pmod_expansion.md),
  [`user_io.md`](research/user_io.md), [`wave3_function_map.md`](research/wave3_function_map.md).
- `docs/` — the design-documentation packet:
  [`DESIGN_SPEC.md`](docs/DESIGN_SPEC.md) (theory of operation: mezzanine
  interface, power architecture + sequencing, every subsystem),
  [`COMPLIANCE.md`](docs/COMPLIANCE.md) (per-interface checklists: HDMI,
  Gigabit Ethernet, USB 2.0, MIPI CSI-2, USB-PD, SoM bank-35 IO header),
  [`BRINGUP.md`](docs/BRINGUP.md), [`TEST_PLAN.md`](docs/TEST_PLAN.md),
  [`FLOORPLAN.md`](docs/FLOORPLAN.md), and the generated diagrams
  `block_diagram.svg` / `power_tree.svg` / `power_sequence.svg`.

## Build + gate discipline

There is **no CI** — instead every local `schgen build <sheet>` /
`schgen board` runs the full gate stack and exits non-zero on any failure, so
nothing un-gated ever gets committed. The committed `reports/` are the proof.
The gates (never edited to pass — LAW 4; strengthening one is the work,
loosening it is forbidden):

- **PURITY** — the subsystem source is netlist-only (no `placer`, no geometry
  import); AST-scanned before execution.
- **MODEL COMPLETENESS** — every pin is netted or explicitly `c.nc()`'d; every
  input is driven.
- **NETLIST** — KiCad's own extracted netlist == the declared netlist, pin for
  pin (the unfakeable electrical proof — catches shorts, opens, single-pin
  nets, NC-cheats, name drift).
- **ERC** — kicad-cli ERC, zero errors.
- **VISUAL** — zero overlap, zero crossings, fits the page (no exemptions).
- **CC short/open** — an independent net-blind union-find over the emitted
  geometry, a 2nd oracle that agrees with the netlist gate pin-for-pin.
- **BOARD GATE + LINK** — every linked net merges correctly across sheets;
  typed-port contract resolved (diff pairs, I2C, sd_bus levels, `expect=`
  deferrals).
- **POWER-TREE / TEST-POINT / THERMAL / DESIGN-RULE / SPICE** — per-regulator
  headroom, a probe per rail/bus, per-device Tj, decoupling/pull-up/strap
  completeness, and divider/feedback/ramp setpoints.

`schgen selftest` mutation-tests the gates themselves (it injects one defect
per class — pin swap, deleted wire, relabel, stray NC, foreign-net junction
short — and proves a gate kills each) and builds twice for byte-determinism
(across PYTHONHASHSEED). Reusable subsystem packages also carry an offline
local `test_<name>.py`; cross-board gates stay aggregated at board level.

The working rhythm: build → read the four verdicts → **open the render PNG and
inspect it like a PCB reviewer** (the render is the deliverable) → commit per
verified unit. Heavy/parallel work runs in isolated git worktrees harvested
sequentially; deterministic output means a regen on the merged state produces
zero artifact diff. The full process contract is
[`../WORKING_GUIDELINES.txt`](../docs/WORKING_GUIDELINES.txt).

<!-- schgen:gallery -->
<!-- GENERATED by `schgen gallery` — edits between these markers are overwritten -->
## Generated 3D board views

The placed board rendered from 8 angles by `schgen board` (kicad-cli, the real component 3D models) — regenerated and committed every build, just like the sheets below.

|   |   |   |   |
|---|---|---|---|
| [<img src="renders/3d_persp.png" width="200" alt="Perspective (front)">](renders/3d_persp.png)<br>**Perspective (front)** | [<img src="renders/3d_persp_rear.png" width="200" alt="Perspective (rear)">](renders/3d_persp_rear.png)<br>**Perspective (rear)** | [<img src="renders/3d_top.png" width="200" alt="Top">](renders/3d_top.png)<br>**Top** | [<img src="renders/3d_bottom.png" width="200" alt="Bottom">](renders/3d_bottom.png)<br>**Bottom** |
| [<img src="renders/3d_front.png" width="200" alt="Front edge">](renders/3d_front.png)<br>**Front edge** | [<img src="renders/3d_back.png" width="200" alt="Back edge">](renders/3d_back.png)<br>**Back edge** | [<img src="renders/3d_left.png" width="200" alt="Left edge">](renders/3d_left.png)<br>**Left edge** | [<img src="renders/3d_right.png" width="200" alt="Right edge">](renders/3d_right.png)<br>**Right edge** |

## Generated schematics

Block diagram and all 37 carrier sheets, regenerated by `schgen board` —
every PNG below passed the netlist, ERC and visual gates.

<img src="../docs/block_diagram.svg" alt="Generated block diagram" width="900">

|   |   |   |
|---|---|---|
| [<img src="renders/board_aux.png" width="220" alt="board_aux">](renders/board_aux.png)<br>**board_aux** | [<img src="renders/board_qwiic.png" width="220" alt="board_qwiic">](renders/board_qwiic.png)<br>**board_qwiic** | [<img src="renders/board_services.png" width="220" alt="board_services">](renders/board_services.png)<br>**board_services** |
| [<img src="renders/bringup_en.png" width="220" alt="bringup_en">](renders/bringup_en.png)<br>**bringup_en** | [<img src="renders/bringup_en_modules.png" width="220" alt="bringup_en_modules">](renders/bringup_en_modules.png)<br>**bringup_en_modules** | [<img src="renders/bringup_modules.png" width="220" alt="bringup_modules">](renders/bringup_modules.png)<br>**bringup_modules** |
| [<img src="renders/bringup_rails.png" width="220" alt="bringup_rails">](renders/bringup_rails.png)<br>**bringup_rails** | [<img src="renders/camera.png" width="220" alt="camera">](renders/camera.png)<br>**camera** | [<img src="renders/debug_boot.png" width="220" alt="debug_boot">](renders/debug_boot.png)<br>**debug_boot** |
| [<img src="renders/ethernet.png" width="220" alt="ethernet">](renders/ethernet.png)<br>**ethernet** | [<img src="renders/fmc.png" width="220" alt="fmc">](renders/fmc.png)<br>**fmc** | [<img src="renders/hdmi_rx.png" width="220" alt="hdmi_rx">](renders/hdmi_rx.png)<br>**hdmi_rx** |
| [<img src="renders/hdmi_rx_term.png" width="220" alt="hdmi_rx_term">](renders/hdmi_rx_term.png)<br>**hdmi_rx_term** | [<img src="renders/hdmi_tx.png" width="220" alt="hdmi_tx">](renders/hdmi_tx.png)<br>**hdmi_tx** | [<img src="renders/lcd.png" width="220" alt="lcd">](renders/lcd.png)<br>**lcd** |
| [<img src="renders/mechanical.png" width="220" alt="mechanical">](renders/mechanical.png)<br>**mechanical** | [<img src="renders/microsd.png" width="220" alt="microsd">](renders/microsd.png)<br>**microsd** | [<img src="renders/motor_pwm.png" width="220" alt="motor_pwm">](renders/motor_pwm.png)<br>**motor_pwm** |
| [<img src="renders/motor_sense.png" width="220" alt="motor_sense">](renders/motor_sense.png)<br>**motor_sense** | [<img src="renders/pd_input.png" width="220" alt="pd_input">](renders/pd_input.png)<br>**pd_input** | [<img src="renders/pmod.png" width="220" alt="pmod">](renders/pmod.png)<br>**pmod** |
| [<img src="renders/pmod_expansion.png" width="220" alt="pmod_expansion">](renders/pmod_expansion.png)<br>**pmod_expansion** | [<img src="renders/power.png" width="220" alt="power">](renders/power.png)<br>**power** | [<img src="renders/power_mon.png" width="220" alt="power_mon">](renders/power_mon.png)<br>**power_mon** |
| [<img src="renders/power_som.png" width="220" alt="power_som">](renders/power_som.png)<br>**power_som** | [<img src="renders/rj45_connector.png" width="220" alt="rj45_connector">](renders/rj45_connector.png)<br>**rj45_connector** | [<img src="renders/som_decoupling.png" width="220" alt="som_decoupling">](renders/som_decoupling.png)<br>**som_decoupling** |
| [<img src="renders/som_j1.png" width="220" alt="som_j1">](renders/som_j1.png)<br>**som_j1** | [<img src="renders/som_j2.png" width="220" alt="som_j2">](renders/som_j2.png)<br>**som_j2** | [<img src="renders/som_j3.png" width="220" alt="som_j3">](renders/som_j3.png)<br>**som_j3** |
| [<img src="renders/uart_bridge.png" width="220" alt="uart_bridge">](renders/uart_bridge.png)<br>**uart_bridge** | [<img src="renders/usb_jtag.png" width="220" alt="usb_jtag">](renders/usb_jtag.png)<br>**usb_jtag** | [<img src="renders/usb_jtag_connector.png" width="220" alt="usb_jtag_connector">](renders/usb_jtag_connector.png)<br>**usb_jtag_connector** |
| [<img src="renders/usb_pd.png" width="220" alt="usb_pd">](renders/usb_pd.png)<br>**usb_pd** | [<img src="renders/usb_uart_connector.png" width="220" alt="usb_uart_connector">](renders/usb_uart_connector.png)<br>**usb_uart_connector** | [<img src="renders/usbc_otg.png" width="220" alt="usbc_otg">](renders/usbc_otg.png)<br>**usbc_otg** |
| [<img src="renders/user_io.png" width="220" alt="user_io">](renders/user_io.png)<br>**user_io** |   |   |

| sheet | description |
|---|---|
| [board_aux](renders/board_aux.png) | Board services: gated +3V3_AUX rail + PCA9306 I2C isolator |
| [board_qwiic](renders/board_qwiic.png) | QWIIC / STEMMA-QT expansion connector + USBLC6 ESD array |
| [board_services](renders/board_services.png) | Board services: ID-EEPROM(MAC) + RTC + watchdog + QWIIC on gated +3V3_AUX |
| [bringup_en](renders/bringup_en.png) | Bring-up EN cells: 3x SN74LVC1G08 rail DIP-AND-override |
| [bringup_en_modules](renders/bringup_en_modules.png) | Bring-up EN cells: 11x SN74LVC1G08 module DIP-AND-override |
| [bringup_modules](renders/bringup_modules.png) | Bring-up module gates: 10x SY6280 + status/user LEDs |
| [bringup_rails](renders/bringup_rails.png) | Bring-up controls: rail/module DIPs + TCA9535 + buttons |
| [camera](renders/camera.png) | RPi camera port: 2-lane MIPI CSI-2 (15P FFC) |
| [debug_boot](renders/debug_boot.png) | JTAG + SWD headers, boot-request DIP, reset |
| [ethernet](renders/ethernet.png) | Ethernet: HX5008NL magnetics + Bob-Smith |
| [fmc](renders/fmc.png) | SoM bank-35 IO breakout (2x20 2.54mm header, VADJ 2.5V) |
| [hdmi_rx](renders/hdmi_rx.png) | HDMI RX: HDMI-A sink + EDID EEPROM |
| [hdmi_rx_term](renders/hdmi_rx_term.png) | HDMI-RX TMDS sink termination (8x49.9R to AVCC=+3V3) |
| [hdmi_tx](renders/hdmi_tx.png) | HDMI TX: TPD12S016 + HDMI-A receptacle (source) |
| [lcd](renders/lcd.png) | 40-pin TTL RGB LCD + SY7201 backlight boost |
| [mechanical](renders/mechanical.png) | Mechanical: M3 mounting holes + chassis-GND bond + fiducials |
| [microsd](renders/microsd.png) | microSD slot (1.8V SoM <-> 3.3V card, TXS02612) |
| [motor_pwm](renders/motor_pwm.png) | 8-ch PWM/ESC output buffer (5V, PL-isolating) |
| [motor_sense](renders/motor_sense.png) | ESC motor-rail telemetry: INA3221 + 10mR shunt (I2C 0x42) |
| [pd_input](renders/pd_input.png) | Power inlet: USB-C PD 20V/3A + TPS26631 eFuse |
| [pmod](renders/pmod.png) | 2x Pmod host ports (bank 13, 200R series, gated 3V3) |
| [pmod_expansion](renders/pmod_expansion.png) | Pmod expansion port (2x6, bank 13, low-cap ESD, manual-gated 3V3) |
| [power](renders/power.png) | Power: +VIN->+5V->+3V3 bucks + +1V8 LDO, PG LEDs |
| [power_mon](renders/power_mon.png) | Rail telemetry: 2x INA3221 + shunts (I2C 0x40/41) |
| [power_som](renders/power_som.png) | Power: +VIN -> +5V_SOM always-on buck (SoM VIN, P0 fix) |
| [rj45_connector](renders/rj45_connector.png) | RJ45 8P8C jack (plain, ext. magnetics) |
| [som_decoupling](renders/som_decoupling.png) | SoM power-entry decoupling under the DF40 mezzanine |
| [som_j1](renders/som_j1.png) | SoM J1: power / USB / STM32 / JTAG / SDIO / ETH MDI |
| [som_j2](renders/som_j2.png) | SoM J2: FPGA bank 13/33 IO + VCCO rails |
| [som_j3](renders/som_j3.png) | SoM J3: FPGA bank 33/34/35 IO + VCCO rails |
| [uart_bridge](renders/uart_bridge.png) | UART bridge: CP2102N USB-UART |
| [usb_jtag](renders/usb_jtag.png) | USB-JTAG/UART debug bridge: CH347T, self-powered + isolated |
| [usb_jtag_connector](renders/usb_jtag_connector.png) | USB-C UFP debug port -> CH347T (VBUS + protected USB pair) |
| [usb_pd](renders/usb_pd.png) | USB-PD: FUSB302B Type-C controller |
| [usb_uart_connector](renders/usb_uart_connector.png) | USB-C UFP console port -> CP2102N |
| [usbc_otg](renders/usbc_otg.png) | USB 2.0 HS OTG port (Type-C, host) |
| [user_io](renders/user_io.png) | User IO: 4 LEDs (gated rail) + 4 buttons, bank 13 |
<!-- /schgen:gallery -->
