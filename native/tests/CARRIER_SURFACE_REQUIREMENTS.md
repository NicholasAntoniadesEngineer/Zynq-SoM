# Carrier surface requirements: board_aux / bringup_rails

Base: `ebcf7c4e4fcffdf6146784fedaa2792a1c81993d`. Circuitry and numerical
thresholds are unchanged. The checker and mandatory pipeline hook are now
integrated with focused CTest coverage. Carrier (37 sheets) and devkit (12 sheets)
passed whole-board mandatory gates with `--no-render` on the integrated hook.
This proves the hard-gate wiring, not qualitative proximity or final rendered
acceptance. Later geometry/search corrections require fresh combined validation.

## Deliberate runtime integration boundary

The two `placement_requirements.json` files are consumed by the new typed runtime
checker in `placement_requirements.hpp/.cpp`, NOT by the old geometric contract
gate. Do not rename them to `placement_contract.json`:
the old engine cannot express their qualitative proximity/ownership rules.
An empty `structures` array would misleadingly appear as an inert-met contract;
a `same_side` entry alone has no members without other structures. Neither is
an acceptable substitute. No numerical maximum or categorical same-side rule is
invented from a datasheet layout illustration. Ownership and switch top-face now
have runtime enforcement through the mandatory `placement_requirements` stage.
Focused hook tests use synthetic geometry and do not prove full-board acceptance.

## Independent requirement evidence

1. [Silergy SY6280/A Rev1.0E, pp.7–8](https://www.silergy.com/download/downloadFile?ftype=note&id=4369&type=product):
   input/output ceramics belong near their respective device pins; output
   capacitance also serves connector transients. Guidance is qualitative, not a
   millimetre limit. The source recommends 10uF input capacitance for hot-plug
   robustness. Current board_aux has C1=100n on IN and C3=10u on OUT: C3 cannot
   discharge that input-side requirement. Assess upstream capacitance and actual
   transients before claiming adequacy; no electrical change is made here.
2. [TI TCA9535 SCPS201F, §7.4.1](https://www.ti.com/lit/ds/symlink/tca9535.pdf):
   local supply capacitors should be close to the device. No numerical separation
   or mandatory component-side restriction is specified. Live construction maps
   U1.VCC/24 to C1.1 on +3V3_SC, with C1.2 grounded. C2–C4 are button capacitors,
   not alternative supply-pin bypass owners.
3. [TI PCA9306 SCPS113O, §8.1.5, §10, §11.1](https://www.ti.com/lit/gpn/PCA9306):
   equal-voltage switch mode exists, so translation-only EN headroom is not proof
   this design is invalid. The published bias/filter network nevertheless differs
   from this circuit (direct gated VREF2, separate 100k EN pull-up, 100n C5).
   C4/C5 ownership records the actual design, not manufacturer certification or
   a claim that C5 is the documented 100pF translation filter. Verify asymmetric
   power-off/ramp behavior separately; no topology is silently corrected here.

Sources read 2026-10-01. Pin numbers independently cross-checked against tracked
part.json and the live C++ builders. No copied PDF or mutable regenerated baseline.

## Actual coverage and mutations

`carrier_surface_requirements_contracts.cpp` invokes both live native factories,
checks every pin/net against immutable circuit IR, and checks six explicitly owned
capacitors against actual rails, grounded terminal, value/type and named owner pin.
It rejects each omitted ownership and missing capacitor return, wrong-rail member,
and C2/C5 exchanged between owners despite identical value and rail.
The test now additionally exercises the production checker for these mutations,
plus catalog pin mismatch, missing actual parts/geometry, actual pad-net corruption
(both name and numeric ID), wrong value in both live circuit and placed model,
and omitted access declarations. Its independent synthetic pad geometry has an
exact 3-4-5 gap at the owned terminal while the other capacitor terminal overlaps
the IC; nearest-any-pad logic would incorrectly return zero and fails this oracle.

Seven switches (board_aux SW1; bringup_rails SW1–SW6) are individually moved to
bottom in an in-memory model. The existing `check_placement_mech` top-face rule
rejects each while all pin-net identities remain unchanged. The synthetic pose
values are mutation stimuli, not layout prescriptions. This does not exercise
the real placer or emitted-board round trip. D1 LED top-face behavior is already
handled by its LED footprint in the existing gate; no new access proof is claimed.

The typed parser rejects malformed/duplicate/unknown structural keys, duplicate
ownership/access entries and any non-null numeric proximity policy. Register one
CTest using `schgen_core`, repository root, and the
owning build's catalog output path (normally `${CMAKE_CURRENT_SOURCE_DIR}/catalog.bin`).
Do not substitute success of this focused test for whole-board acceptance.

## Remaining engine / hardware gaps

- Runtime typed ownership binds owner pin + member pin + return to independent
  compiled declarations and catalog identities, and verifies all live sheet
  pin/net identities in the placed model. Same-rail matching alone is not used
  to infer ownership. Durable requirement revision/provenance hashing remains
  future work; the current declarations are compiled into the build.
- Qualitative near-pin requirements need an explicit reviewed interpretation or
  an engine representation that reports them as unverified. Current proximity
  requires `max_mm` and measures the nearest member pad, not an owned terminal.
- Top-face is an existing owner policy, not a datasheet-derived finger/tool
  clearance. Actuation/access envelopes and surrounding assembly obstacles are
  not expressible; switch usability remains unverified. No unsupported distances.
- Both sheets expose control surfaces rather than off-board cable connectors.
  AUX output also serves board_services/board_qwiic: connector-side bulk placement
  cannot be proved from board_aux's local group alone.

## Runtime pipeline integration contract

1. Add `src/placement_requirements.cpp` to `schgen_core` and register the focused
   test; no geometry engine replacement. For carrier, explicitly require both
   `board_aux` and `bringup_rails` manifests, even if a manifest is absent or a
   placed sheet is missing. Missing file, parse exception or missing live circuit
   is a hard failure, not an empty successful coverage set.
2. Use `carrier_surface_requirement_declaration(sheet)` as the independent
   compiled requirement source. Never construct this argument from the manifest.
   Populate the catalog map with the actual invocation's catalog snapshots for
   the declaration's MPNs. No globals or file loading occurs inside the checker.
3. After `BoardPcbStage` placement is available, call the checker on the actual
   prepared `PcbCheckInput` and the pre-placement live circuit. Supply the trusted
   source-ref to uniquified-ref map and source-net to emitted-net map from current
   validated hierarchy assembly. Do NOT derive these maps from the candidate
   placement or relax checks to accommodate ambiguous local-net naming. Both maps
   must be complete and injective within the sheet. The existing pipeline's PCB
   gate phase in `board_pipeline_pcb.cpp` is the intended final-check location.
4. Publish `summary()` alongside the existing independent electrical/mechanical
   reports. A nonempty `violations` list must fail the new mandatory hard gate.
   `hard_requirements_met()` means only ownership/identity/top-switch constraints
   held; the overall status remains UNVERIFIED when no violations exist. Preserve
   the `unverified` list as unresolved coverage, NEVER convert it into a proximity
   PASS or a movement permission. Existing gates and allowed-movement policy stay
   mandatory and unchanged. If the pipeline only supports Boolean verdicts, keep
   the hard-gate result and unresolved qualitative report separate and explicit.
5. Rerun on every candidate accepted for publication and after side/pose changes;
   never cache a previous model's measurements. Measurements are planar gaps
   between transformed pad bounding boxes for the specified terminals, with side
   labels. They are not path length, via inductance, 3D distance, or a numeric
   design limit. Missing/invalid geometry fails, not a fabricated distance.

The production hook's synthetic integration tests and missing-gate closure tests
pass. No fresh whole-board acceptance or emitted-board round-trip for this new
hook is claimed yet. Research findings above remain findings only; circuitry is
unchanged.
