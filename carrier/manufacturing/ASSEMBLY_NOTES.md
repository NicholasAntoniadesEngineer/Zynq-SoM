# Carrier assembly + fab requirements (DFM)

Mechanical / fab-art requirements the netlist + BOM + CPL do not carry. Hand
this to the layout engineer and the assembly house with the generated
`bom_jlc.csv` and (when emitted) the CPL. Suggested positions are for a
~120 × 100 mm board (the floorplan target, `carrier/docs/FLOORPLAN.svg`);
finalise against the real outline.

## Fiducials (REQUIRED for fine-pitch pick-and-place)

The board carries fine-pitch / no-lead parts (FMC SEAF mezzanine, HDMI, microSD,
FFC tails, QFN/SON/HTSSOP regulators + the FUSB302 WQFN). These need optical
fiducials or the assembler cannot register the stencil and the fine-pitch
placements.

- **3 global fiducials**, one per board corner in an L (not symmetric), so the
  machine can resolve rotation. Each = 1.0 mm bare copper dot + 2.0 mm
  solder-mask opening, ≥ 5 mm from any board edge, no copper/silk inside the
  mask ring.
- **Local (per-part) fiducials**: a pair diagonally across the **FMC connector**
  (the densest, most rotation-sensitive part) and one at each **QFN/SON** EP
  part (FUSB302, INA3221, TPS26631, TPD12S016). Same 1 mm/2 mm geometry.

## Tooling / mounting holes

- **4 × M3 mounting holes**, board corners, 6 mm keep-out, plated + tied to
  `CHASSIS_GND` (see the chassis bond below) — they double as the assembly
  tooling holes.
- If the assembler needs dedicated tooling holes, add **2 × 2.5 mm
  non-plated** on a diagonal.

## Chassis-ground star bond (DOC-3 — REQUIRED, layout-domain)

`GND` and `CHASSIS_GND` are deliberately **distinct nets** (the netlist keeps
them apart; collapsing them in the schematic would force the topology). They
MUST be joined at the PCB by a **single-point star stitch** — ONE location, so
chassis/shield return current cannot flow through signal ground:

- Place the bond **at the Ethernet RJ45 / HDMI shield entry** (where chassis
  current enters), as a 0 Ω / net-tie footprint or a deliberate copper stitch
  (a small via field is fine) joining `GND` ↔ `CHASSIS_GND` at that one point.
- Everywhere else the two pours stay isolated. Do NOT add a second bond.
- The Ethernet Bob-Smith termination (`ethernet.py`, 2 kV caps) returns to
  `CHASSIS_GND`; the microSD/HDMI/USB shields likewise. Confirm each shield net
  lands on `CHASSIS_GND`, not `GND`, before the star bond.

## Solder-paste / stencil

- Exposed/thermal pads (every QFN/SON EP + large connector tabs) already carry a
  **windowed paste grid (~60 %)** in the generated footprints (DEF-2) — do NOT
  override to 100 % coverage; it floats/tombstones the part.
- Standard 0.12 mm stainless stencil; reduce the EP apertures further only if
  the assembler's DFM report asks.

## Silkscreen requirements

- **`FMC: REDUCED LPC`** label next to the FMC connector — the carrier wires
  only LA00–11 + CLK0/1 of the LPC pinout (deliberate scope, `fmc.py`); the
  silk warns an integrator not to expect a full LPC.
- Pin-1 / polarity marks on every IC, diode (TVS/Schottky/zener), LED, and the
  electrolytic/tantalum bulk caps.
- Connector keying / orientation arrows on the FFC tails (LCD, camera) and the
  microSD.
- Board name + revision + the `+VIN` max-voltage caution (20 V PD) near the
  USB-C inlet.

## Panelisation

- Recommend a **2 × 1 or 2 × 2 panel** with 5 mm rails (fiducials + tooling on
  the rails) and mouse-bite or V-score breakaways. The fine-pitch parts argue
  for V-score over mouse-bite near board edges to avoid flex-cracking.

> NOTE: this is a static requirements sheet. A future generator
> (`schgen` floorplan extension) can emit the actual fiducial / tooling-hole
> coordinates once the board outline is frozen — the floorplan already derives
> the outline + per-block courtyards.
