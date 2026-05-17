"""Format-preservation tests: emit-then-diff against golden fixtures.

Inspired by kicad-sch-api's byte-exact testing approach. Each fixture
is a known-good rendering of a small ``sexpr.py`` primitive (wire,
junction, label, etc.) with all UUIDs normalised to the all-zero UUID
so the test is deterministic.

Together these tests catch:
    - Indentation drift (tab handling)
    - Atom-order changes
    - Missing or extra whitespace / parentheses
    - Float formatting changes (4-significant-digit rendering)
    - Unintended changes to label/junction/wire structure
"""
