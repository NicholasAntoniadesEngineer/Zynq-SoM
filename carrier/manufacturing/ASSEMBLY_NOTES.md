# Carrier assembly + fab requirements (DFM)

Mechanical / fab-art requirements the netlist + BOM do not carry. Hand this to
the layout engineer and the assembly house with the generated `bom_jlc.csv` and
the CPL (`Zynq_Carrier_cpl.csv`, regenerated every `schgen board` by
`kicad-cli pcb export pos`). **Board outline: 178 × 163 mm** (the emitted
`Zynq_Carrier.kicad_pcb`, page frame (25,25)–(203,188); NOT the old ~120 × 100
floorplan target — that number is stale). All positions below are in the board
(page) frame.

## Fiducials — EMITTED (5 on the board; GAP3 closed)

The board carries fine-pitch / no-lead parts (the 0.4 mm-pitch SoM DF40
receptacles J1/J2/J3, HDMI, microSD, FFC tails, QFN/SON/HTSSOP regulators + the
FUSB302 WQFN). These need optical fiducials or the assembler cannot register the
stencil. **Fiducials are now emitted** by the placer as PCB-only fab-art
(`Fiducial:Fiducial_1mm_Mask2mm` = 1.0 mm bare-copper dot + 2.0 mm solder-mask
opening, net-less, no BOM line — see `schgen/generate/pcb/placement.py`
`build_model`). They appear in the CPL (`in_pos_files`) so the P&P registers off
them.

- **3 global fiducials** in an asymmetric **L** (the missing 4th corner lets the
  machine resolve board rotation), on the top (assembly) side, inset 9 mm from
  each corner so they sit clear inside the corner M3 mounting-hole pads:
  - `FID1` (top-left)  = (34, 34)
  - `FID2` (top-right) = (194, 34)
  - `FID3` (bottom-left) = (34, 179)
- **Local pair** flanking the densest 0.4 mm DF40 (the SoM region), seated in the
  dead corners of the SoM body keepout, clear of every DF40 pad + the under-SoM
  decoupling grid:
  - `FID4` = (91, 87.5)   (SoM keepout NW corner)
  - `FID5` = (137, 125.5) (SoM keepout SE corner)

> The FMC site is a generic 2×20 0.1″ header (the VITA 57.1 SEAF/ASP mezzanine
> was removed per user request 2026-06-18) — it is NOT a fine-pitch no-lead part
> and needs no local fiducial.

## Tooling / mounting holes

- **4 × M3 mounting holes** (H1–H4), EMITTED at the board corners inset 5 mm:
  (30.48, 30.48), (198.12, 30.48), (198.12, 182.88), (30.48, 182.88); 6 mm
  keep-out, plated + tied to `CHASSIS_GND` (see the chassis bond below) — they
  double as the assembly tooling holes. The 3 global fiducials sit inset just
  inside these (9 mm), clear of the M3 pads.
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

- **`SoM bank-35 IO`** label next to the 2×20 breakout header — it carries the
  SoM bank-35 LA00–11 + CLK0/1 pairs + 2.5 V VADJ (`fmc.py`); the silk makes
  clear it is a generic IO breakout, not a seatable FMC mezzanine.
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

## Double-sided SMT — RATIFIED process decision

The board is a **two-sided SMT assembly**: of 569 placed footprints, **313 sit on
the bottom (B.Cu)** — the per-subsystem decoupling / small passives and the
under-SoM power-entry bypass grid live on the bottom to pull cross-airwire and to
keep the top routable (LAW 5/6). This is a **deliberate, ratified** process choice,
NOT an accident of packing:

- The assembler must run **two reflow passes** (bottom first, then top, or
  top-first with bottom on adhesive) — quote accordingly. Every bottom part is a
  small, mirror-symmetric, non-polarized passive (the placer's 2-side classifier
  forbids bottom-side polarized/active parts), so a swapped-pad mirror is
  electrically identical (verified) — no bottom part is orientation-sensitive.
- All connectors, ICs, regulators, the SoM DF40 receptacles, mounting holes and
  the fiducials are **top-side** (259 footprints) — the P&P registers off the
  top fiducials for the fine-pitch pass.
- If the assembler prefers a single-sided build, set `two_side=False` in the PCB
  step (everything moves to the top) — the board grows and routability drops, so
  the two-sided default stands unless the quote says otherwise.

> NOTE: fiducial + mounting-hole coordinates ARE now emitted (above) and land
> deterministically from `schgen board` (the placer fixes them; re-runs are
> byte-identical). This sheet stays the home for the requirements the netlist/BOM
> cannot carry (chassis bond, silk, panelisation, hand-insert consumables).

## Board-services block (board_aux / board_services / board_qwiic)

The manually-gated +3V3_AUX block adds parts that need explicit assembly care:

- **BT1 — ML1220 RECHARGEABLE coin cell (KH-CR1220-2 holder).** The SMD *holder*
  is reflow-placeable (manual feeder load); the **cell is a hand-insert
  consumable** fitted AFTER reflow. **Polarity: the cell `+` face goes toward
  pad 1** (`V_RTC_BAT`); pad 2 is GND. The footprint marks polarity on
  `Cmts.User` only — **add a silk `+` next to pad 1 at layout** (or mark it on
  the assembly drawing) so the cell is not inserted reversed.
- **RTC cell is RECHARGEABLE (ML1220, Mn-Li).** Fit an **ML1220** (charges to
  ~3.1 V from the 3.3 V supply); the SC firmware ENABLES the RV-3028 trickle
  charger so it stays topped up. Do **NOT** fit a primary CR1220 (it would be
  charged → vent risk) or a LIR1220 Li-ion (its 4.2 V charge target exceeds the
  3.3 V supply). See the firmware contract for the charger config.
- **SW1 — board_aux DSHP04 DIP (AUX power enable).** Only **position 1** is
  used (`+3V3_AUX` enable); it defaults **OFF** (open). Mark the silk so pos-1 =
  "AUX EN" is unambiguous; positions 2-4 are spare/no-connect.
- **J1 (QWIIC, board_qwiic) pad order.** Pads 1..4 = GND / +3V3 / SDA / SCL
  (looking into the receptacle). **Verify pad-1 location against the footprint
  silk before fab** — a swapped power pad damages external QWIIC modules.
