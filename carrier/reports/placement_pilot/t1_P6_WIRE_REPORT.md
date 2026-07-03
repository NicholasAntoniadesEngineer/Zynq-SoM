# T1 P6-wire — PHASE REPORT (Opus successor, 2026-07-03)

**Base:** 9f77031 (T1 merge unit P0-P6core). **Worktree:**
`.claude/worktrees/t1-continue`. **Status:** P6-wire VERIFIED COMPLETE,
uncommitted (fleet protocol). **P7 NOT started.**

---

## 1. What the partial was, and what I found

The predecessor threaded the P6-core legalizer (`floorplan_compose.legalize_
compact`) into `_attempt_pack`'s four call sites in `floorplan.py`, then died
mid-verification after a power loss. The worktree held a **stale, buggy board**:
its reports showed `power_som` MOVED (flow power->power_som 63.12 -> 45.33mm,
facing 1.7deg -> 14.7deg degraded, power_som caps dropped out of T2 escape
corridors). That is exactly the regression the movable rule exists to prevent —
a guarded, un-templated sheet being compacted, which re-rolls its L4 bottom
slide and (at P7's rebase) parks its caps in the buck thermal-via field.

The CODE on disk, however, already carried the fix the predecessor's
`t1_P6_WIRE.md` documents:

```
movable_names = sorted(parts_ & inames & set(_exempt))   # _exempt from
                                                          # wired_term_participants()
```

with `_exempt = {pd_input, power, usb_pd}` and `power_som` GUARDED. So the stale
BOARD was the pre-fix artifact; the SOURCE was correct. A clean rebuild reverts
the board to baseline. **This was the core suspect-file finding: the code was
finished and right; only the on-disk board/reports were stale.**

## 2. Diff-read: complete vs half-done

- **Source diff = `floorplan.py` ONLY** (105 insertions), matching spec §3 item
  1 verbatim: `Plan.composition` field; once-per-build TermIndex + zone-local
  metrics + D13 channel-demand map (proxy = EXCLUSIVE 2-sheet nets) + T2 escape
  corridors, computed after the zg import; `compose` threaded into all four
  `_attempt_pack` calls; `compact=True` only at the fixed-outline call + final
  re-pack; the LEGALIZE(+COMPACT) tail block. No `placement.py` change — its
  `som_core_rect` / L4-exemption were already merged on 9f77031. Nothing in the
  wiring was half-done.
- Every symbol the wiring depends on resolves (`legalize_compact` signature,
  `LegalizeVar`, `build_term_index`, `zone_local_metrics`, `escape_corridors`,
  `som_core_rect`, `wired_term_participants`, `Term.target`).

## 3. Measured before -> after (9f77031 baseline -> P6-wire accept)

| Scalar | Baseline (9f77031) | P6-wire | Verdict |
|---|---|---|---|
| pcb `Zynq_Carrier.kicad_pcb` sha | `ea3260e7…` | `ea3260e7…` | **byte-identical** |
| Board area | 25,670 mm² (170x151) | 25,670 mm² | A3 ok (<= 25,670) |
| usb_pd->power flow | 113.27/123.3 (margin **10.03**) | 113.27/123.3 (10.03) | A1: >= 10.0 floor, binding window named |
| power->power_som flow | 63.12 mm | 63.12 mm | unchanged (power_som fixed) |
| facing power->power_som | 1.7 deg | 1.7 deg | unchanged |
| usb_pd<->pd_input near_max | 1.92 mm | 1.92 mm | A4 ok (<= 8 = bound-GUARD) |
| LAW-5 cross | 13,567.4/15,862 | 13,567.4 | A5 ok, unchanged |
| RETURN STITCH (T2) | 29/29, worst 1.777 | 29/29, worst 1.777 | coexistence ok |
| THERMAL over-limit | 0 | 0 | ok |
| Composition report sha | `dc4aa02c…` | `dc4aa02c…` | byte-identical |
| `power` block pose (floorplan frame) | x=145.00 | x=**144.98** | 0.02 mm compaction pull |

Every emitted-board gate report is **byte-identical to baseline** — the
strongest banded no-worsen possible (no scalar moved). The ONLY delta is the
0.02mm floorplan-frame pull on `power` (+ FLOORPLAN.md/svg + the manifest lines
that hash them). It rounds away at emit (GRID=1.27) -> byte-identical board.

## 4. Acceptance bar (spec P6 / t1_P6_WIRE.md)

- **Timing (<= +10s):** A/B in one process, warm caches, median of 3 build_plan
  runs — BASELINE (compose off, L0 path) 105.15s vs WIRED 106.49s -> **+1.33s**.
- **Build-twice byte-identity:** pcb/manifest/composition IDENTICAL x2.
- **Banded no-worsen vs 9f77031:** every gate report byte-identical; all gates
  PASS; no term left GREEN; no term lost margin.
- **A1 verdict:** margin 10.03mm, above the 10.0 floor; the legalizer runs (log
  = "compacted…", "accept: all hard terms green") and pulls `power` toward
  `power_som`, but the **E-band separations bind** (fmc/power_mon/bringup + board
  wall) so the move is 0.02mm of quantization slack. Real unlock deferred to P7
  (power_som DOF).
- **ruff green; full fast suite 591 passed / 5 skipped;** targeted suites green.

## 5. Judgment calls (flagged)

1. **Stale artifact revert, not a code change.** I rebuilt rather than reverting
   the board by hand; the corrected code produces the baseline board. I did NOT
   touch the movable rule — it was already correct. (If the intent had been to
   let power_som move at P6, that would contradict the spec's P5b partition and
   the predecessor's own gate-caught regression; I kept power_som guarded.)
2. **P6-wire is a no-op on the EMITTED board at today's DOF.** This is
   spec-sanctioned (A1 alternative: "binding window named"), NOT a failure. The
   legalizer genuinely executes and compacts; the emitted board is byte-
   identical because the only movable that CAN move (`power`) is separation-
   clamped to sub-grid slack. The value P6-wire delivers is the by-construction
   machinery + the proven A1 binding-window verdict that scopes the P7 unlock —
   not a board change this phase.
3. **Timing A/B is heavier here** (build_plan ~105s vs the predecessor's ~67s)
   — different machine/load. The DELTA is what the spec bounds; +1.33s is
   comfortably within +10s. The full end-to-end build ran ~7:19 twice.
4. **Mystery untracked file** `carrier/schematic/mechanical.uniqcheck.kicad_sch`
   in the opening snapshot was a `board.py` transient (schematic uniqueness
   check), caught mid-build; clean rebuilds removed it. Not part of the delta.
5. **3d_*.png drift** is raytracer raster nondeterminism (pcb is byte-identical);
   not a P6-wire effect.

## 6. Renders (carrier/reports/placement_pilot/t1_p6w_*)

`t1_p6w_board_{top,bottom}.png` (whole, 8 px/mm), `t1_p6w_power_zone_{top,
bottom}.png`, `t1_p6w_usbpd_seat_top.png` (30 px/mm crops), `t1_p6w_floorplan.
png` (composition frame). All read clean: SoM centered, connectors edge-flush,
both LM61460 buck stages + FUSB302 network intact, buck thermal-via fields
present, zero overlaps, zero off-board parts. Matches P5's renders (byte-
identical board); the composition effect is the sub-pixel 0.02mm `power` pull.

## 7. Files

- Source: `schgen/generate/floorplan.py` (the P6-wire threading — only source
  change).
- Evidence: `carrier/reports/placement_pilot/t1_P6_WIRE.md` (gate results
  appended), `t1_p6w_*.png`, this report.
- Working-tree deltas vs 9f77031: floorplan.py; FLOORPLAN.md/svg + manifest.json
  (0.02mm pull); compose_ledger + ledger.jsonl (advisory); 3d renders (raster
  noise). **Board pcb + all gate reports byte-identical to base.**
