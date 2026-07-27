# Promotion evidence — fast checks vs the visual ground truth (Principle 0)

*Living ledger. A fast (non-visual) check may stand in for a visual check ONLY with
recorded multi-round validation here: it must fire on every injected defect of its class
(zero false-negatives) and stay silent on the clean twin (no false positives). The
full-render + visual inspection before every landing is unconditional and never replaced.*

## The battery
`schgen/tests/test_defect_corpus.py` — synthetic-model defect injection over real
footprints (hermetic, ~1 s). Classes and status:

| Defect class (eye-caught origin) | Gate | Injected fires | Clean silent | Status |
|---|---|---|---|---|
| Off-board part (LAW 5 origin wave-B) | ratsnest_gate | ✓ | ✓ | ARMED |
| Dispersed subsystem cluster (LAW 5) | ratsnest_gate | ✓ | ✓ | ARMED |
| Interior off-board connector (LAW 6 densify disaster) | placement_mech | ✓ | ✓ | ARMED |
| Inward mating face (LAW 6) | placement_mech | ✓ | ✓ | ARMED |
| Part on SoM-TOP keepout (LAW 6 as amended 2026-07-09) | placement_mech | ✓ | ✓ (bottom exempt) | ARMED |
| Control under module (LAW 6) | placement_mech | ✓ | — | ARMED |
| Scattered decoupling (contract origin) | placement_contract | ✓ | ✓ | ARMED |
| Starved fan-out (D13) | fanout_gate | ✓ | ✓ | ARMED |

Covered by their own long-standing suites (ledger pointers, not duplicated):
flow/facing (test_placement_flow_gate), silk overprint (refdes suite, board-file),
DF40 corridor intrusion (return-stitch/escape suites), schematic short/open (netlist
gate + shorts detector, LAW 0), courtyard overlap (kicad-cli DRC).

## Promotion protocol status
No fast check has yet been promoted to REPLACE a visual step. The corpus is the
precondition; promotion additionally requires multi-round comparison against rendered
output on real changes (per docs/AI_PLATFORM_ROADMAP.md Principle 0). Current fast
harnesses (stage-template zone tests, this corpus) operate as inner-loop accelerators
ONLY — every landing still gets the full render + eyes.
