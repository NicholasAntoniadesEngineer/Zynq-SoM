# Scripts

This  folder contains:
- A python script to add die lengths to the Xilinx SoC footprint
- A python script to calculate SoM pcb track propagation delays
- A Kicad plugin to create a carrier pcb template
- A bash script to generate carrier connector symbols

## Requirements
python pandas



## `footprint_add_die_lengths.py`

This script adds die lengths to the Zynq SoC `<footprint_name>.kicad_mod` footprint.

Xilinx provides Die-to-Package delay data by specifying **max** and **min** delay values (in *ps*). Unluckly, Kicad footprints can only store die-length values (in *mm*).

Equivalent Die-length values are calculated as the average Die-to-Package delay multiplied by the microstrip propagation speed (approximated to 1/6 *mm/ps* for common FR4 boards).

$$ \frac{T_{D,max} + T_{D,min}}{2}\cdot V_{p*}$$

Where:
- $V_{p*}$ = miscrostrip propagation speed (hardcoded to 1/6 *mm/ps*)
- $T_{D}$ = Die-to-Package delay (*ps*)

### Usage
Run in terminal 
```bash
python footprint_add_die_lengths.py xc7z020clg484_delays.csv CLG484_XIL.kicad_mod
```
The resulting footprint is saved as `<footprint_name>_with_die_lengths.kicad_mod`

## `calculate_track_delays.py`
This script calculates propagation delays/skews for the following signal groups:
- DDR CMD/ADDR Bus
- DDR Data lanes
- Boot flash QSPI 
- eMMC SDIO 
- ETH RMGII TX
- ETH RMGII RX
- USB ULPI

Delays are calculated as 

$$ \frac{DL}{V_{p*}} + \sum_{layers} \frac{TL_{\,layer}}{V_{p,layer}}$$

Where:
- $DL$ = Package Die-Length [*mm*] (stored in footprint)
- $V_{p*}$ = 1/6 *mm/ps* (used during Die-Length calculation see [footprint_add_die_lengths](#footprint_add_die_lengthspy))
- $TL_{\,layer}$ = signal trace length for that specific layer [*mm*]
- $V_{p,layer}$ = signal propagation speed for that specific layer and signal type (differential or single-ended) [*mm/ps*]

>[!NOTE]
>- Outer layer Propagation speeds (microstrip) are lower compared to inner layers (stripline).
>- Propagation speed can vary between differential and single-ended signals

Via delays are not considered in the calculations. 

### Usage
1. With pcbnew create a Net Inspector Report named `tracklengths.csv` and save it inside `/scripts` subfolder
![](../pictures/create_net_report.png)

2. Run in terminal:
```bash
python calculate_track_delays.py tracklengths.csv
```
Results are printed out in terminal.

## `create_carrier_template_plugin.py` 

This script generates a `.kicad_pcb` template used as a starting point for carrier board designs.

It places footprints for
- mating connectors (with die-lengths*)
- standoffs
- testing probes

![](../pictures/carrier_template.png)

### Usage
This script needs to be executed inside pcbnew Python scripting console by running:
```python
import os
exec(open(os.path.expandvars("${KIPRJMOD}/scripts/create_carrier_template_plugin.py")).read())
```
The `.kicad_pcb` template file can be found inside the `carrier_template` folder, together with the `.csv` files that will be used by [symbol_creation.bash](#symbol_creationbash) to create the SoM carrier connector symbols.

## `symbol_creation.bash`

This bash script uses the previously generated `.csv` files to create a  symbol library (`.lib`) containing the SoM carrier  connector symbols.
### Usage
Run in terminal:
```bash
source symbol_creation.bash
```
The library file is saved as `symbol_Zynq_SoM.lib` (Kicad < V6.0). Conversion to the newer `.kicad_sym` format can be done during import by clicking the "Migrate Library" button inside Symbol Library Manager.

![](../pictures/SoM_carrier_symbols.png)

## `create_carrier_template_schematic.py`

This script generates a complete, validated KiCad 9.0 schematic for the carrier evaluation board.  It is the top-level entry point for the `scripts/carrier/` Python package which produces a "kitchen-sink" carrier exposing every SoM peripheral (USB-C x2, RJ45 Gigabit Ethernet with discrete magnetics, microSD, HDMI TX + RX, LVDS LCD, MIPI camera, FMC-LPC, 4x PMODs, XADC SMA, MRCC clock SMA, USB-UART bridge, RTC + EEPROM + 6x power monitoring, etc.).

Every supporting component on the carrier (decoupling caps, pull-up resistors, ESD diodes, USB-C CC terminations, LED current limits, etc.) is derived from the IC's manufacturer Typical Application Circuit, encoded as a `ReferenceCircuit` Python spec in `scripts/carrier/refcircuits/<part>.py`.

### Usage

Run after `symbol_creation.bash` so that the connector symbol library exists.

From the repository root:
```bash
python scripts/create_carrier_template_schematic.py
```

The script runs 4 stages with strict validation between them:

1. Generate `io_assignment.csv` mapping every SoM bank pin to its carrier destination (FMC LA pin, HDMI TMDS lane, PMOD bit, etc.)
2. Generate `carrier_BOM.csv` aggregating every LCSC-sourced part with quantities, footprints, datasheet URLs, alternates, and per-board cost
3. Generate `reference_circuits.md` - per-IC datasheet design-intent record for EE review before tape-out
4. Generate `carrier_template.kicad_sch` with all symbols placed and labelled, embedded symbol library, hierarchical-ready structure

A strict validator (`scripts/carrier/rules.py`) implements rule sets A through I (BOM, footprint coherence, schematic best practices, naming, hierarchical structure, IO assignment integrity, file integrity, manufacturing, industry-standards alignment). The validator **does not fail fast** - it collects every violation across the entire generation pass and reports them in a single aggregated report. Output files are written atomically (temp + rename) only if zero strict violations exist.

### Outputs

| File | Purpose |
|---|---|
| `scripts/carrier_template/carrier_template.kicad_sch` | The schematic (~300 KB, ~18k lines) |
| `scripts/carrier_template/carrier_template.kicad_pro` | KiCad project (auto-updated UUID) |
| `scripts/carrier_template/carrier_BOM.csv` | Master BOM (~50 parts, ~$33/board) |
| `scripts/carrier_template/io_assignment.csv` | SoM pin to carrier interface map (300 rows) |
| `scripts/carrier_template/reference_circuits.md` | Per-IC design-intent doc (~17 ICs, ~600 lines) |
| `scripts/carrier_template/validation_report.md` | Last validation report (aggregated rule results) |

### Package layout

```
scripts/carrier/
  core/
    sexpr.py          - tiny S-expression emitter
    parts.py          - BOMPart, ALLOWED_FOOTPRINT_PREFIXES, PACKAGE_TO_FOOTPRINT
    refcircuit.py     - ReferenceCircuit, ExternalPart, StrapPin, LayoutNote
    registry.py       - master BOM-part registry (single source of truth)
    symbols.py        - embedded KiCad symbols for every active part
  refcircuits/
    <part>.py         - one Python spec per IC (FUSB302, USBLC6, TPS2051, ...)
    __init__.py       - registry of all REFCIRCUITS + IC_INSTANCE_COUNT
  rules.py            - validation engine (rule sets A-I + C11-C13)
  sheet_emitter.py    - symbol-to-S-expression rendering
  generator.py        - main schematic emitter
  bom_io.py           - BOM and io_assignment CSV emitters
  gen_refcircuits_doc.py - emits reference_circuits.md
```

### Adding a new IC to the carrier

1. Add the part to `scripts/carrier/core/registry.py` with verified LCSC stock
2. Create `scripts/carrier/refcircuits/<part>.py` encoding the datasheet's Typical Application Circuit
3. Register it in `scripts/carrier/refcircuits/__init__.py` (REFCIRCUITS + IC_INSTANCE_COUNT)
4. Add an entry to `IC_TO_SECTION` in `scripts/carrier/generator.py` choosing the visual section
5. Re-run; the validator will catch any token/footprint/stock issues

### Modifying the IO assignment

`io_assignment.csv` is regenerated on every run from rules in `scripts/carrier/bom_io.py`. Edit the `_classify_destination()` / `_classify_pl_io()` functions there to remap pins.





