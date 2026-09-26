# Floorplan precision provenance

Captured privately on 2026-09-26 against repository commit
`0ea2dab55d1869230fdd508aa9a3e1108ede06f9`, before the six floorplan extractions.
No existing fixture was rewritten.

`legacy_output.txt` records devkit_mini, carrier and devkit_mini_single;
`fixed_legacy.txt` records devkit_mini with a 100 by 100 mm fixed outline.
These contain all 83 policy declarations, typed plan values at binary64
round-trip precision, decision values/inputs/text, ledger bytes, exported
specification and all prior counters by owner. Fresh captures compiled the
original owned sources from the commit, linked against a private copy of the
pre-extraction core. They also matched the recovered prior captures byte for
byte. The test codec removes only the six explicitly named additions.

`additive_counts.json` was captured with only `precision_ops.cpp` compiled
with `-finstrument-functions -fno-inline`. The observer counts real function
entries independently of the production counters, and assertions compare
both before accepting a capture. It covers automatic/fixed sizing, both
reservation passes, rejected free-plan work, and single-sided placement.
Zero engagements are absent, not fabricated.

`floorplan_precision_contracts.cpp` additionally checks decimal halfway
neighbors, signed zero and IEEE binary64 results; exact registry identity and
arity; numeric versus string/bool display calls; rejected ledger operations;
overflow before an unbooked operation; concurrent invocation ownership;
pre-existing accounting imported once across restore; receipt replay; and
pure ledger replay/serialization with no new scalar calls or counts.

Capture driver and build logs are retained with the private handoff in
`/private/tmp/schgen-floorplan-exact6.peFrNv`. The parent owns full native
suite integration after releasing the source freeze.
