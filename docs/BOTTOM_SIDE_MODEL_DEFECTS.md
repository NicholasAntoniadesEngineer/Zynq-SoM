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

## Fix principles (wave 11) — BOTH LANDED

1. **Punch only what pierces.** Edge-block main rect carries its own side's mask;
   its THT pads emit PUNCH boxes via the existing `_zone_components` path. Same
   for any other whole-rect punch reservation.
2. **SoM: OCC_TOP only.** Its bottom carries the real `som_decoupling` cap boxes
   plus the DF40 escape-corridor bands as punch — not a blanket rect.

Nothing there softens a gate: every punch removed was replaced by the exact
geometry that genuinely pierces, and DRC/D13/escape gates judge the emitted board.
Wave-11 released **8,155.8 mm² = 27.0 %** of the bottom surface. The board did
not move.

## DEFECT 3 was WRONG — wave-12 measurement (supersedes it)

Waves 10 and 11 blamed an **est/emission gap**: the sizing estimator was said to
predict bottom-side wins the emitted board then lost. Wave-12 measured that
claim at every stage boundary and it is **REFUTED**.

- The estimator is a near-CONSTANT upper bound: **+315.0 / +315.0 / +321.7 /
  +314.9 mm (2.06 % ± 0.03 %)** over the emitted cross on four conservative
  plans, +199.9 on the freed plan. Its ranking matched the emitted ranking
  **4 out of 4** times.
- **No post-floorplan mover destroys a predicted win.** Per stage, l4_pull +
  edge_seat + breathe + refit_facing + reorder are a NET **improvement** of
  −171.9 / −170.9 / −171.5 / −76.6 mm on the four plans. `edge_seat` is already
  replicated inside `_cross_estimator`.
- Wave-11's "+1,217 mm at unchanged area" was a **comparison-frame artefact**:
  with `power_mon` eligible the conservative plan is 185x164 / est 15,643.8 /
  emitted 15,328.9 and the freed plan is 185x163 / est 16,736.0 / emitted
  16,536.1. The guard's key is `(area, est_cross)` with area strictly first, so
  it bought 185 mm² for +1,207 mm — as instructed, and the estimator predicted
  that cost correctly (+1,092 mm).

## The REAL model defect — the board is 100 % PACK-bound in BOTH dimensions

Of **2,868 candidate outlines** the sizing search tried, **14 packed and the
LAW-5 airwire budget rejected NONE**. Airwire has never sized this board.

- **W = 185 is a proven geometric floor.** Every candidate below 185 — 2,186 of
  them, 100 % — is rejected by the EDGE-RUN FIT guard, never reaching the
  interior packer. The S-edge run
  (`hdmi_tx` 17.155 + 20.0 cable + `hdmi_rx` 23.965 + 20.0 cable + `pmod` 41.765
  + 0.700 + `pmod_expansion` 39.435, plus 1.750 end reach and 2 x `EDGE_MARGIN`,
  less the 0.1 `run_overflow_tol` credit) needs **184.669 mm**; the best of all
  24 orderings needs **184.269 mm** and still misses the 184 mm grid point. No
  edge block owns a narrower shape variant (LAW-6 pins mating direction, so only
  same-span mirrors are registered), and a side flip cannot compress a perimeter
  run — the released bottom area is *interior surface*, the binder is *perimeter
  length*.
- **H = 163 is set by `power`**, the largest interior block (53.21 x 23.93) and
  the LAST one placed, because the pack order is `(priority, −connectivity,
  −area, name)` and a power stage has the lowest cross-subsystem connectivity.
  `power` is **provably top-pinned** (user-facing `D20001-3`, `TP20001-4`), as
  are `usb_jtag`, `power_som`, `uart_bridge` (face-up parts) and `fmc`,
  `debug_boot` (seated connectors). The block that sets the height is the one
  block that can never use the freed bottom surface.

**That is why 8,156 mm² of released bottom bought nothing.** The bottom-opt-in
ladder is exhausted: every interior block has now been measured, and every
remaining one refuses the bottom face LOUDLY with a declared reason.

The one measured lever that does move the board is the interior pack ORDER:
area-first (first-fit-decreasing) emits **185x160 = 29,600 mm² (−1.84 %)** at
**+9.0 % cross-airwire**, taking LAW-5 utilisation from 89.1 % to 98.0 %. That
is an area-vs-airwire trade at the wall and is a USER decision, not an engine
one — measured, quantified, and deliberately not landed.
