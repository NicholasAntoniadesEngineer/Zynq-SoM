# Why two-sided placement isn't shrinking the board — model analysis

Measured on master 5f8c7d6 (carrier 185x166 = 30,710 mm²).

## The board is neither area-bound nor wire-bound

- Component courtyards total **6,062 mm²**; the derivation's own area floor is
  130x120 = **15,600 mm²**. The board is **30,710 mm²** — nearly double the floor.
- Estimated cross-airwire **15,505 / 17,349 budget = 89.4 %** — not binding.

So the outline is set by ONE thing: how the block RECTANGLES pack. Any principle
that frees packing area shrinks the board; anything else is noise.

## DEFECT 1 — punch is applied to whole blocks, not to what pierces

`_Occupancy.add()` defaults to `OCC_PUNCH` (both surfaces). Interior blocks pass
`_side_mask(b.side)` (floorplan.py:2695/2715/2721/2728), but:

- **edge blocks** are added with NO mask (floorplan.py:2493) -> PUNCH
- **the SoM keepout** is added with NO mask (floorplan.py:2481) -> PUNCH

| falsely punched | mm² | % of a surface |
|---|---|---|
| 15 edge blocks | 8,548 | 27.8 % |
| SoM + 7 mm halo | 3,584 | 11.7 % |
| **total** | **12,132** | **39.5 %** |

(The 4 corner mounting-hole keepouts, 676 mm², punch CORRECTLY — holes pierce.)

Only through-hole PADS pierce copper. A USB-C receptacle's shell, its SMD
support parts and the empty area of its zone do not block bottom copper.
`_zone_components` ALREADY computes per-THT-part PUNCH boxes for interior
zones — the machinery exists, it is simply not applied to edge blocks.

## DEFECT 2 — the SoM bottom is treated as keepout, and it is the best real estate

LAW 6 (amended 2026-07-09): the SoM's TOP face is full keepout; **the bottom face
is free** — `som_decoupling` already places 18 caps there via a separate grid path.
But the lattice reserves the whole SoM rect on BOTH faces, so no interior block may
use it. That region is the single largest contiguous free area on the board AND the
closest area to J1/J2/J3 — i.e. the placement with the SHORTEST possible airwires
to the module. The model forbids exactly the placement that would win most.

## Consequence (explains every measurement so far)

With ~40 % of the bottom falsely blocked — specifically the perimeter and the
centre — a block opted to the bottom cannot sit under an edge zone or under the
SoM. It is pushed into the contested interior, where it disturbs top-side packing
instead of relieving it. That is why every bottom opt-in emitted a BIGGER board
(rails 188x164, power_mon 185x175, usb_pd 185x169) while the estimator predicted
wins: est −145 mm for bringup_rails vs +420 mm on the emitted board.

## Fix principles (wave 11)

1. **Punch only what pierces.** Edge-block main rect carries its own side's mask;
   its THT pads emit PUNCH boxes via the existing `_zone_components` path. Same
   for any other whole-rect punch reservation.
2. **SoM: OCC_TOP only.** Its bottom carries the real `som_decoupling` cap boxes
   plus the DF40 escape-corridor bands as punch — not a blanket rect.
3. **Re-measure the est/emission gap AFTER 1+2.** The gap is plausibly a symptom
   of forcing bottom blocks into contested space; if it survives, close it by
   modelling emission-time disruption, and only then can the ordinary-net via cost
   fall toward its true near-zero value (user decree 2026-07-30: vias are cheap
   except on impedance-controlled nets).

Nothing here softens a gate: every punch removed must be replaced by the exact
geometry that genuinely pierces, and DRC/D13/escape gates judge the emitted board.
