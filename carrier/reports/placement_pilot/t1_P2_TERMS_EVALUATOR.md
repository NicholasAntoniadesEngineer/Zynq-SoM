# T1 P2 — term index + exact evaluator + advisory ledger (evidence)

Delivered units (all uncommitted, for Ring-0 merge review):
- `schgen/generate/floorplan_compose.py` — Term/TermIndex (`build_term_index`,
  both contract roots, dedupe keep-min-bound + OR-enforced, fail-loud unknown
  kinds incl. `region_void`), `zone_local_metrics` (full emit rounding chain),
  `evaluate_terms` (argument-pure exact evaluator), `measure_terms` +
  `compose_report` (emitted-model gate-kernel truth), `emit_mobile_sheets`
  (same-run exactness expectation), `cross_airwires_by_pair` +
  `channel_demand_mm` (D13 channel demand, Ring-0 injection),
  spec-§4 constants with basis strings.
- `schgen/generate/compose_repair.py` — `measure_ledger` (real gates +
  None-filtered discover injection + LAW-5 + check_all + D13 hotspots +
  advisory floors as repair TRIGGERS + D-1 seat-consistency advisory);
  driver-only ledger writers (compose_ledger.json/.md — a plain board build
  never writes them).
- Gate additions (all additive; summary text proven byte-identical):
  `placement_flow_gate.FlowTerm` + `.terms`, `ratsnest_gate.dispersion_by_sheet`.
- Build wiring: `emit.generate` computes `floorplan_composition` (advisory
  report, D-5: never a gate); `__main__` writes
  `carrier/reports/floorplan_composition.txt` beside the flow-gate block.
- Tests: `test_floorplan_compose.py` (hermetic dedupe / fail-loud / enforced
  mirroring / None-filter / FlowTerm channel / dispersion map / channel
  thresholds / D-1 advisory tracking-spec; board-scale exactness + no-snap
  red half + 0.7mm mutation twin, env-gated `SCHGEN_BOARD_TESTS=1`).

## The decisive P2 measurement — exactness residual vector (live)

Instrument: build_plan poses + zone_local_metrics vs the emitted model's own
gate kernels (scratch `t1_p2_exactness.py`; full vector in the session log).

- **usb_pd: residual 0.000000 (exact)** — the all-top template sheet; the
  rounding-chain replication (gridify + round-4 + gate rounding) is proven
  (the naive no-snap prediction diverges > 1e-6 — the red half).
- **motor_pwm: 0.000000 (exact)** — no L4 movers, no snapped connector.
- **EVERY other sheet is L4/snap-mobile** — mm-to-tens-of-mm residuals
  (power 2.3mm centroid / 23mm bbox; pd_input 10.8mm; power_som 23mm;
  rj45 21mm; ethernet 1.8mm). **SPEC CORRECTION (stale-scalar law): the
  spec's P2 claim "exactness <= 1e-6 for power" is REFUTED — power carries
  L4-mobile bottom leftovers.** Consequences:
  1. The exactness test derives its expected-exact set from the SAME-RUN
     model (`emit_mobile_sheets`) — never a static sheet list.
  2. The P5 exemption set must be pinned from live discovery as
     {pd_input, power, power_som} (usb_pd vacuous) — NOT the spec's
     "{pd_input, power_som}" figure.
  3. Until P5, the only 1e-6-assertable terms are between exact sheets;
     the usb_pd<->pd_input near_max prediction is proven one-sided
     conservative (L4 can only CLOSE that gap; pred 1.92 vs meas 0.00).
- far power<->ethernet.line_side residual 3.26mm <= FAR_L4_GUARD 14.0 (the
  spec's measured guard figure, re-confirmed conservative).

## D13 channel demand (constants + basis)

`CHANNEL_FLOOR_MM = 2.0` (judgment:2.0 — D13 floor "2x 0.1/0.1mm lanes +
1.0mm clearance" ~= 1.4mm, rounded up one lane-pair), `CHANNEL_PER_NET_MM =
0.2` (one 0.1/0.1 lane per exiting net), `CHANNEL_MIN_NETS = 6` (P0 pair
table: hotspots 7-24 airwires, tail <= 5). Fold-in as HARD legalizer terms
happens at P6; P2 lands the demand instrument + report table.

## Motor RED archive (A2 evidence)

`near_max motor_sense<->motor_pwm`: regenerated 68.65mm gap > 20 — RED
(advisory), archived in ledger.jsonl (P0 entry) and in
`floorplan_composition.txt` (this phase). Threshold-relative only; the value
is never pinned (doc :759 records 132mm centroid-era — both are >20 RED).

## Byte-identity scoping (§3 manifest note)

`manifest.json` gains exactly one new hashed line for
`reports/floorplan_composition.txt` (reports/*.txt glob). All other
artifacts byte-identical — proven at the phase gate below.

## Phase gate (results appended)

- ruff green; fast suite green; hermetic P2 tests green.
- Board-scale exactness suite: see `t1_p2_board_tests.txt`.
- Full `schgen board` x2: byte-identity + determinism — see
  `t1_p2_board_hashes.txt`.
