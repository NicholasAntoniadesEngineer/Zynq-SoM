# Independent Python provenance captures

These bytes were captured before deleting any retained Python constructor body.
They are never read by production code. Do not regenerate them to repair a gate.

* `python_basis.json`: original `_legacy_circuit` executions. A temporary in-memory
  `str` subclass tagged each value returned by `Registry.register`; a
  `Circuit.part` wrapper recorded declaration identity before transport stripped
  the subclass. This captured 214 component/policy declarations, 416 registered
  physical component uses, and 46 typed-port policy uses. Two additional recorded
  numeric strings are Molex catalog identities, not physical magnitudes.
  The 17 library and 49 project sheet manifest came from the already-independent
  authoring fixtures. No C++ source was examined to infer these expectations.
* `python_copper.json`: original Python `analyze` and `report` for the carrier,
  devkit, and no-board cases. The copper contracts use the existing immutable
  `../pcb_emit/{carrier,devkit_mini}.kicad_pcb` bytes rather than generated boards.
  Only diagnostic `where` locations and the report introduction intentionally
  change: structured native metadata replaces Python source anchors.
* `python_copper_cases.json`: ten independently evaluated Python evidence
  scenarios, exercising missing copper, partial/full thermal evidence, chassis
  and Bob-Smith islands, isolation voids with/without a plane, and SoM fanout.

The native registry stores reviewed engineering declarations and obligations,
not frozen output circuits. The live auditor compares every actual component
and targeted port against those declarations. Native contracts mutate every
obligation and every declaration, remove sheets, add uncovered passives, and
mutate policy/connectivity to prove failures are real.
