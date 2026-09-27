# Named visual-correction expectations, version 1

These are new expectations, not replacements for the immutable historical
`schematic_place_templates/*.json` fixtures. The original inputs and full
original outputs remain required, unchanged test dependencies.

The three `*_row_clearance_v1.json` files hold complete corrected Engine states.
They were captured from the C++ correction, then independently constrained in
`schematic_place_templates_contracts.cpp`: every historical capacitor row is
rigidly translated down by its zero-based row index times 3.81 mm (three existing
1.27 mm grid cells). Every attached part, ground/supply primitive, reference/value
position, artwork box and wire path must undergo exactly that row translation.
Every x coordinate, identity, net, primitive count, ordering and non-placement
state field remains identical to the original. The production result must match
the complete corrected state exactly, not within a tolerance.

The displacement is geometrically justified from the original fixture boxes:
ground value bottom is 8.636 mm below the capacitor row; the next original bus
is only 6.35 mm below it. One 1.27 mm grid cell of clearance therefore requires
`ceil((8.636 + 1.27 - 6.35) / 1.27) = 3` extra cells per wrap. The oracle does
not call the production wrapping, snapping or extent helpers.

Only the independent old-plus-displacement arithmetic allows floating-point
roundoff (32 machine epsilons); this is not a production geometry tolerance or
a tolerance in the final full-state comparison. Five unrelated mutation classes
per fixture must be rejected (net identity, part x, part y, box edge and wire x).

Each original must demonstrate foreign supply-bus/ground-artwork or ground-text
contact; each corrected state must remove that contact. A one-cap run's bus is
its direct supply pin. Upward supply stubs and their artwork are separate from
the bus-row invariant, and remain subject to ordinary complete-sheet visual
validation and spacing retries. These pre-centering intermediate fixtures are
not themselves an assertion that every primitive is ready for final publication.

Title compatibility uses separately named `worksheet_corrected_v1` expectations
in `schematic_title_correction_fixture.hpp`, used by emitter and hierarchy
contracts. Three literal prescribed title/continuation pairs
reconstruct the original title exactly with a joining space. Only those exact
title lines and the new comment-2 lines are substituted in original file bytes;
all remaining bytes, metadata, UUIDs and geometry must match the originals.
Six unaffected emitter fixtures remain exact historical outputs. The hierarchy
fixtures additionally exercise the mechanical title; all hierarchy/root bytes
outside the three named child title corrections remain under their originals.

No historical fixture is ignored, no old golden is overwritten, and no gate is
disabled. Actual affected-sheet renders, extracted netlist equality, ERC and
normal visual checks remain required integration evidence.
