# Bottom-side placement — wave-9 design

## The right abstraction

NOT two floorplans. One floorplan where SIDE is a per-block degree of freedom:

- The two surfaces share one outline, one edge-connector perimeter, one SoM region,
  and every PUNCH-THROUGH: THT pads block the far side locally, escape/stitch vias
  need both-side landing room, corridors are per-side bands, mounting holes pierce.
  Two independent floorplans are each blind to the other's penetrations; one
  allocator with a top layer + bottom layer + shared punch layer models the truth.
- The ATOM of side assignment is the BLOCK, never the part: contract structures
  (hot loops, terminations) are same-side by datasheet; a zone's existing internal
  top/bot split (`top_off`/`bot_off`) stays intra-block.

## Why the engine is closer than it looks

- Gates are already side-aware: D13 crowding skips opposite-side neighbors; DRC is
  per-layer; corridor eviction is already B.Cu-aware; the SoM bottom face is already
  populated (som_decoupling). The gap is ONLY the block allocator: today a block's
  rectangle claims both surfaces implicitly.
- Wave-4 multi-shape is the natural carrier: a bottom placement is just MORE SHAPE
  VARIANTS — the mirrored (X-flipped) re-pack of the same zone, tagged side=bottom.
  The greedy deterministic chooser, chosen-shape plumbing, estimator-judges-chosen-
  geometry, and P6 legalizer machinery all extend rather than fork.

## Plan

- P1 INFRASTRUCTURE (byte-identity-safe landing): `_Occupancy` becomes two layers +
  punch layer; `Block.side`; `place_near` searches (x, y, side) over each block's
  variant set; bottom variants = mirrored `_pack_one_zone` re-packs; estimator adds
  a per-crossing VIA COST term for nets spanning sides; emission flips sides.
  Eligibility defaults to top-only — with zero blocks opted in, the board must be
  byte-identical (the control that lands the machinery inert).
- P2 ELIGIBILITY (data, not code): floorplan.json per-block `"side": "top" |
  "bottom" | "either"`. Hard rules derived, not asserted: connectors/switches/LEDs/
  displays are user-facing = top; height-capped by the enclosure standoff budget
  (USER DATA NEEDED); second-reflow mass rule (heavy parts top) as a new DFM gate —
  an extension, no existing gate softened. First candidates: faceless blocks —
  hdmi_rx_term, board_services, uart_bridge-class networks, bulk/termination groups.
  Each opt-in lands as a measured A/B (area, airwire, via count).
- P3 HARVEST: the sizing search re-derives the outline as interior demand drops
  toward max(top, bottom) instead of their sum. Edge runs (99mm of 183 today) do
  not bind, so the interior win is real board shrink.

## User decisions (RESOLVED 2026-07-29)

1. Bottom-side height: NO LIMIT.
2. Bottom-eligible: everything EXCEPT connectors, probes/testpoints, LEDs,
   switches (ethernet family, power supply, etc. all eligible). Policy: blocks
   with seated connectors stay top-pinned; TP/LED/SW PARTS carry a face=top
   constraint the zone packer honors inside a bottom-assigned block's variant
   (the internal two-side split flips roles, so a bottom block can still
   present its user-facing parts on the board-top face).
3. Double-sided assembly already paid for — cost accepted.
4. Battery holder (ML1220 coin cell) explicitly bottom-eligible (user 2026-07-29)
   — service access on standoffs, not user-facing.

Sequencing: P1 starts after the wave-8 engine unit lands (same files).

## P2 measured (2026-07-30)

- Side choice is EST-DRIVEN inside the pack search (`_pick_sided`): when a
  block's fitting variants span both faces, the per-face finalists are judged
  by the sizing estimator restricted to that sheet's nets (cross-airwire +
  registered `est_via_cost`) on the partial board — strict 1e-6 win or the
  distance incumbent stays; distance still judges within a face. Zero opt-ins
  means the judge cannot fire (byte-identity control held on both projects).
- Achiral-safe opt-in frontier (unified convention — no chiral IC emission
  yet): hdmi_rx_term + user_io only; 16 interior blocks excluded (ICs, diodes,
  unproven multi-pad inductors or magnetics on the would-be-B.Cu primary;
  conn-class jumpers; MH-only mechanical). Both measured NEUTRAL at 185x166:
  hdmi_rx_term's bottom variant est +48..+65 mm (via cost, no cross win —
  63/63 judgements keep top, including the P1 distance tie at 0.403);
  user_io's variant is vacuous (all 8 parts face-top, primary empty) and the
  judge RESCUED it from 36 distance-preferred bottom placements (up to
  +245 mm worse cross). Boards byte-identical, so the opt-ins are reported,
  not landed (user acceptance rule: measured wins only).
- P3 outline harvest therefore waits on the chirality debt (embed-level local
  mirror + kernel updates for IC-bearing blocks) before interior demand can
  approach max(top, bottom) instead of the sum.

## Chirality PAID (wave-9, 2026-07-30)

- KiCad-EXACT mirrored emission is live: `schgen/generate/pcb/mirror.py`
  materialises each footprint's pcbnew-LEFT_RIGHT-flip twin (stored local
  y -> -y, local angles -> -a; instance rotation t -> (180 - t) % 360; layers
  still flipped by `embed._flip_to_bottom`; `(model ...)` untouched) as a
  real .kicad_mod under `.mirrored_fp/` (gitignored derived cache, outside
  parts/ so the model3d census never sees it). A mirrored instance is an
  instance WHOSE mod_path IS the mirrored document, so every geometry kernel
  (`_pad_boxes`/`_rot_pad_bbox`/`_footprint_bbox`/`_inst_pad_geom`/
  `_mod_pads`/escape/silk/D13/contract/ratsnest) stays side-blind with zero
  mirror branches.
- GROUND TRUTH pinned against pcbnew 10.0.2 itself: a 32-footprint fixture
  (SOT-23-5, QFN24 with rot-90 oval pads, FUSB302 MLP, HX5008 TH magnetics;
  rots 0/37/90/270, both sides) emitted by `embed._embed_footprint` matched
  KiCad's own `FOOTPRINT::Flip` objects pad-for-pad at 0.0 nm (584 pads:
  position, orientation, layer set, shape, size, drill), side-blind loader
  formula residual 0.5 nm, `kicad-cli pcb drc` 0 violations. Placed-pattern
  identity: `R_cw(180 - t) . M_y == M_x . R_cw(t)`.
- Bottom shape variants now carry the TRUE mirror (`_mirror_pack`): primary
  pack = mirrored documents at origin (zw - ox, oy), rotation
  (180 - t) % 360 (`ZoneShape.mirror`); secondary pack (face-top parts,
  presents F.Cu) keeps plain top emission with box-preserving mirrored
  origins. `apply_chosen_shapes` rebinds resolvable/bbox_of to the mirrored
  documents (`ZoneGeom.mirror_refs` -> `FootprintInst.mirror`); the
  estimator, D13 shape reach, occupancy comps, zone metrics and the contract
  re-measure all judge the mirrored geometry. The achiral-swap convention
  remains ONLY for the 2-side classifier population (pushed passives +
  som_decoupling, byte-pinned boards) and its entry guard now scopes to
  inst.mirror=False; mirrored parts of ANY footprint class are legal on
  B.Cu (face-top TP/LED/SW still forced to present top; seated-connector /
  conn-class / no-zone hard raises unchanged).
