# P7a ETHERNET WAVE — Ring-0 RATIFICATION REQUEST

**Thread:** P7a ethernet (Opus, Ring-2), worktree `.claude/worktrees/p7-ethernet`, base `35cc213`.
**Status:** items 2–4 (template + wiring + red→green) delivered & verified; this request covers the two INTENT EDITS that require Ring-0 ratification before they land in `carrier/floorplan.json`.

There are **TWO** intent edits below. Edit **B (ethernet exclusive pull)** is *spec-pre-sanctioned* by the T1 D-1 ledger rule and is REQUIRED for the ethernet wave to go green without a seat-consistency advisory flag — I have included it in the delivered ethernet wave (it is a `pull` on ethernet's existing `near`, no edge-list change, exactly the usb_pd precedent). Edit **A (corridor clear)** is a NEW edge/anchor move and is delivered as a *proposal only* — I did NOT apply it; the ethernet wave is complete and green WITHOUT it.

---

## RE-VERIFICATION FINDING (LAW: re-verify audit findings) — the F7 squatter is `power_mon`, not `motor_pwm`

The task brief (item 1) names the corridor squatter as *"motor_pwm's ICs (U21001/U21002-class, sheet 21)"*. I re-measured the **live** board (`carrier/Zynq_Carrier.kicad_pcb` @ base `35cc213`, board hash `cbdb25a7…`) before acting. The finding as stated does not hold on the current board; the corrected finding is:

| Claim in brief | Live-board truth (re-verified) |
|---|---|
| motor_pwm ICs squat in the ethernet corridor | **motor_pwm is already on the W edge** (bbox `27.3,119.2 → 47.4,137.7`; its ICs U36001/U36003 at x≈30–36, hard against its own W-edge PWM header). It is NOT in the corridor. |
| The squatters are U21001/U21002, sheet 21 | U21001/U21002 exist and DO squat the corridor — but they are **`power_mon`** (the 2×INA3221 rail-telemetry sheet, `interior.side=E`), **not motor_pwm**. sheet-21 refdes now map to power_mon. |

**Corridor measured (live):**
- `ethernet` zone bbox `137.8,59.0 → 151.3,78.5` (E interior, `near: rj45_connector`).
- `rj45_connector` bbox `142.0,52.6 → 194.6,73.5` (E edge, mating face off-board +X).
- **`power_mon` bbox `137.7,64.1 → 158.0,86.1`** — overlaps the ethernet zone in X, and its ICs **U21001 @ (153.5,65.6)** and **U21002 @ (153.5,71.1)** sit in the ethernet↔rj45 line-side corridor (x∈[151.3, 194] between ethernet's media edge and the jack), exactly the F1/F7 defect, just on the correct sheet.
- Other corridor-region parts (motor_sense D37001/U37002; usb_uart/usb_jtag passives) are edge/adjacent-zone spill, low-severity, NOT the primary squatter.

So the corridor-clear intent is about **relocating `power_mon`**, whose electrical home is beside its flow-downstream `power_som` / the SoM power (it monitors +VIN/+5V/+3V3/+1V8 rails), NOT in the ethernet analog line side. This *strengthens* the original intent: moving power_mon toward power_som both clears the ethernet moat AND shortens the `power_mon→power_som` flow (47.19mm today).

---

## INTENT EDIT A — corridor clear (power_mon) — **PROPOSED, NOT APPLIED, awaiting ratification**

**What:** re-anchor `power_mon` off the raw E side and toward its downstream `power_som` (board interior / SE-center), so its INA3221 pair vacates the ethernet↔rj45 corridor.

**Exact JSON diff** (`carrier/floorplan.json`, `interior.power_mon`):

```json
// BEFORE
"power_mon": { "side": "E" },
// AFTER (option A1 — near its flow-downstream; connectors unchanged, no edge-list move)
"power_mon": { "near": "power_som" },
```

Rationale for `near: power_som` over a raw side flip:
- power_mon's only external flow term is `flow: [power_mon, power_som]`; `near` seats it at power_som's x/y (the first-fit-nearest-anchor lever, `floorplan.py:807`), which is SE-center — clear of the NE ethernet corridor.
- It is an anchor change only (no edge-list edit → no connector re-seat, unlike D9), so blast radius is bounded to power_mon's own zone + second-order L4 re-slides.
- It shortens `power_mon→power_som` flow (a free composition win) instead of degrading it.

**Why this needs ratification (not auto-applied):** it is a NEW floorplan intent (changes where a shipped subsystem seats), i.e. the `--allow-intent` class per T1 §5 law 4 / P8 precedent — never a tuning edit. It also touches the E-band packing (fmc/power/bringup neighbours), so it must go through the banded-monotone acceptance + full `schgen board` + render verdict on the rebuilt board. I have NOT run that accept loop (the edit is un-applied); Ring-0 should either ratify (then I apply + gate + render + report deltas) or supply the preferred target.

**Acceptance I will run once ratified:** all gates green on the rebuilt board; `A' ≤ 25,670`; power_mon→power_som flow no-worse; ethernet corridor visibly clear in the t1↔rj45 crop; near_max/far ethernet terms stay green; build-twice byte-identical; ledger entry.

**Blocked-work note:** per the task, items 2–4 do NOT depend on Edit A and are delivered complete + green. If Ring-0 declines/defers Edit A, the ethernet wave still stands: the corridor squatter is a *composition* concern (power_mon's pose), not an ethernet-zone or wiring defect, and the ethernet near_max/far terms are green regardless of where power_mon sits (they measure ethernet↔rj45 and ethernet↔power, not ethernet↔power_mon).

---

## INTENT EDIT B — ethernet exclusive pull (D-1 ledger rule) — **APPLIED in the delivered wave** (ratify to keep)

**What:** add an exclusive `pull` to ethernet's existing `{"near":"rj45_connector"}`, mirroring the usb_pd P3 precedent, so the D-1 seat-consistency advisory stays green when ethernet is wired.

**Exact JSON diff** (`carrier/floorplan.json`, `interior.ethernet`):

```json
// BEFORE
"ethernet": { "near": "rj45_connector" },
// AFTER
"ethernet": {
  "near": "rj45_connector",
  "pull": {
    "to": "rj45_connector",
    "weight": 60.0,
    "face": "inboard",
    "exclusive": true,
    "basis": "D11 near_max edge-gap <=20mm proxy for Pulse v7 p.1 <=25mm part-to-part (T1 P7a, ethernet wave): magnetics seat at the RJ45 jack. Migrated per D-1 seat-consistency rule when ethernet joins _WIRED_SHEETS — same mechanism as usb_pd's pd_input pull."
  }
}
```

**Why this is spec-pre-sanctioned (D-1):** T1 §0 decision D-1 states verbatim *"Ethernet's seat at its wave is therefore a reviewed one-line spec diff, not silent behavior."* The D-1 seat-consistency advisory (`compose_repair._seat_consistency`) flags *any WIRED near_max term whose subject is an interior block anchored `{"near":<edge block>}` without an exclusive pull*. Once ethernet is in `_WIRED_SHEETS`, its near_max→rj45 term meets that precondition exactly (ethernet is interior, rj45_connector is an E-edge block), so the advisory WOULD flag ethernet without this pull. The pull is the sanctioned migration of the seat from packing-luck to the validated knob.

**weight=60.0, face=inboard, exclusive=true** match the usb_pd exemplar (`interior.usb_pd.pull`) 1:1; the loader invariants (`_validate_pull`) pass (near==pull.to==rj45_connector, rj45_connector on an edge list, basis non-empty).

**Verified effect (delivered board):** ethernet near_max→rj45 stays `0.00mm gap / <=20mm` GREEN; seat-consistency advisory clean; board byte-identical to the no-pull ethernet wave (the pull reproduces the seat the `near` already produced — ethernet's zone already abuts rj45 at 0.00mm; the pull makes that seat *authored* rather than incidental).

---

## INTENT EDIT C — area escalation: +0.66% board growth (datasheet-forced) — **needs Ring-0 area judgment**

**What:** wiring ethernet grows the board **170×151 = 25,670mm² → 170×152 = 25,840mm² (+170mm², +0.66%)**, exceeding the P0 ledger area cap (`cumulative_area_cap_mm2 = 25,670`).

**Why it is forced (not a search artifact — proven):** I pinned the outline to a fixed `170×151` and rebuilt; the packer FAILS with *"the REAL 2-sided packed blocks do not fit the fixed outline 170x151"*. The datasheet-faithful ethernet zone is intrinsically larger than the size-sorted legacy shelf-pack it replaces:
- legacy (size-sorted) ethernet zone: **14.3 × 20.66 ≈ 295mm²**
- template (datasheet Bob-Smith at MCT pins + C5 barrier + media-facing turn): **25.51 × 21.75 ≈ 555mm²**

The +260mm² zone is real copper the datasheet layout requires (each channel's 75R‖1n at its own centre tap, all on the media side facing the jack). Per the "never redraw/bend a part to fit the tool" law I did NOT compress it. I also verified the growth is **independent of Edit A** (moving power_mon to `near:power_som` still yields 170×152) — so it cannot be recovered by the corridor clear either.

**Escalation basis (spec §5 law 4 / A3):** *"a `--allow-intent` edit failing ONLY `A' ≤ A` is reported with measured growth and deferred to the orchestrator's ~+5% wave judgment — never silently vetoed."* +0.66% is far inside the spec's per-wave ~+5% allowance. The wave BUYS: ethernet contract violations **23 → 0** (Bob-Smith at MCT pins, media row faces the jack — the F1 fix), and the flow terms improve (power→power_som 63.12→39.16mm, usb_pd→power 110.37→112.42mm). Every hard gate is green at 170×152 (DRC 0, RATSNEST, PLACEMENT CONTRACT 32/0, PLACEMENT FLOW 3-contract, COMPOSITION hard-RED 0, RETURN STITCH 29/29, THERMAL 0-over-limit).

**Requested:** ratify the +0.66% as the ethernet wave's area cost (I will re-base the ledger `cumulative_area_cap_mm2` to 25,840 with this basis on your go), OR direct a recovery avenue (P10 `_rotate_zone_90` is the spec's designated area-recovery unit; it is out of this wave's scope).

---

## SUMMARY FOR RING-0

- **Ratify B** (already applied, spec-pre-sanctioned by D-1): keeps the delivered ethernet wave's seat authored + the ledger advisory green.
- **Ratify or redirect A** (proposed, un-applied): the corridor squatter is `power_mon`, not motor_pwm; move it toward power_som. I will run the full accept loop + render verdict on your go.
- **Ratify or redirect C** (delivered board is at +0.66%): datasheet-forced board growth to 170×152; a `--allow-intent`-class area judgment, not a defect. All gates green; growth proven un-recoverable within this wave.
