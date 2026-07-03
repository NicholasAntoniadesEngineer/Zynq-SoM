# T1 P3 — pull-knob migration (evidence)

Delivered (uncommitted, for Ring-0 review; code + JSON designed as ONE atomic
unit per the spec):

- `schgen/generate/floorplan.py`:
  - loader accepts interior `{"side","near","pull"}`; `_validate_pull`
    enforces the schema `{to, weight>0, face inboard|center, exclusive,
    basis non-empty}` + invariants (unknown key, unknown target, inboard
    needs an edge-listed target, exclusive needs near==to AND edge-listed —
    the packer's `_anchor` precondition, so an exclusive pull can never
    silently no-op). All errors are `FloorplanSpecError` with the offending
    key named.
  - `Block.pull`; `build_plan` threads the spec entry onto the block.
  - `_anchor`: the `_EDGE_SEAT_BLOCKS` branch replaced by pull semantics —
    exclusive: zone-weight = pull.weight, SoM pull dropped, `face=inboard`
    aims at the pulled edge block's inner face (geometry VERBATIM from the
    old branch); non-exclusive: ONE weighted point joins the accumulation.
  - packing order: exclusive-pull blocks place first (was the
    `_EDGE_SEAT_BLOCKS` test).
  - `_EDGE_SEAT_BLOCKS` / `_EDGE_SEAT_ZONE_W` DELETED (grep-verified: no
    remaining reference outside tests asserting their absence).
  - `export_floorplan_spec` round-trips the knob.
  - `build_plan(spec=None)` additive injection parameter (IM1) threaded to
    `subsystem_zone_geometry` / `_connector_sheet_edges` /
    `_downstream_facing` / `build_model` — default None path reads the file
    exactly as before.
  - loader `source` field no longer crashes on out-of-repo spec paths
    (pre-existing latent defect exposed by the new tmp-path tests).
- `carrier/floorplan.json`: usb_pd KEEPS `"near": "pd_input"` and gains the
  exclusive pull `{to: pd_input, weight: 60.0 (== the deleted
  _EDGE_SEAT_ZONE_W), face: inboard, exclusive: true, basis: "D11 edge-seat
  override, migrated from _EDGE_SEAT_BLOCKS (T1 P3): ..."}` — the reviewed
  one-line intent diff (D-1).
- `schgen/tests/test_floorplan_pull.py` — RED-ON-BEFORE captured against the
  pre-P3 loader (10 failed: the `keys - {"side","near"}` rejection), archived
  at `t1_p3_red_on_before.txt`; now green: parse + every invariant rejection
  + hack-is-gone + carrier-spec-carries-the-pull.
- D-1 seat-consistency advisory (compose_repair `_seat_consistency`) flips
  usb_pd from FLAGGED (near-anchor without pull) to CLEAN — the test computes
  the expectation live from the spec file, so it proved the flag pre-P3 and
  the clean state post-P3 without pinning the migration state.

## Byte-identity proof (the migration MUST NOT move copper)

Phase gate = double `schgen board` after P2+P3 (hashes in
`t1_p23_build1_hashes.txt` / `t1_p23_build2_hashes.txt`, scratch): board
`Zynq_Carrier.kicad_pcb`, `FLOORPLAN.svg`, `FLOORPLAN.md`,
`placement_flow.txt`, `ratsnest.txt` byte-identical to the committed tree
(pcb = 9a375217...); `manifest.json` carries exactly the one expected new
line (`reports/floorplan_composition.txt`) + its hash — the §3 manifest-note
delta. Results appended below by the gate run.

## Gate results (build 1)

- `schgen board` PASS with ALL of P1-P4 code + the migrated JSON.
- `git diff --stat` vs HEAD: ONLY `carrier/manifest.json | 4 ++++` — the
  floorplan_composition.txt entry. Board pcb hash 9a375217... == committed;
  FLOORPLAN.svg/MD, placement_flow.txt, ratsnest.txt and every pre-existing
  report byte-identical (empty git diff). The P3 migration moved NOTHING.
- floorplan_composition.txt (new, advisory): 6 hard terms all green (min
  margin +10.00 = the usb_pd seat), motor near_max archived RED (-48.65),
  D13 hotspot table (6 pairs >= 6 airwires; max demand 6.8mm corridor for
  bringup_en_modules|bringup_rails).
- Build 2 determinism twin: hashes appended in t1_p23_build2_hashes.txt.

## Gate results (build 2 — determinism twin)

Build 2 hashes IDENTICAL to build 1 on every tracked artifact (pcb
9a375217..., FLOORPLAN.svg 57533a49..., FLOORPLAN.md 853cb142...,
placement_flow 0aef7fcf..., ratsnest 7023c3bc..., floorplan_composition
a2b6512e..., manifest fc955ce5...) — cross-process build-twice PROVEN.
P2 + P3 phase gates COMPLETE.
