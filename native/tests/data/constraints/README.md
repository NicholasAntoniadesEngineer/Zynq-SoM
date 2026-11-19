# Layout constraint byte contracts

`projects.json` freezes the committed carrier and devkit CSV/rule outputs before
switching the constraints generator to C++. CSV CRLF endings, ordering, researched
per-net skew citations, stackup geometry and legacy provenance text are preserved.
The runner reads authoritative project IR and SI target data, compares all output
bytes, and requires missing differential-pair research to fail. Synthetic cases
cover CSV quoting, multiline metadata, bus policy, voltage classes and no invented
geometry for unsupported impedance. It never regenerates its own expectations.

Stack-up refresh (2026-11-19): the boards moved to the six-layer JLC06161H-3313
stack-up. The stack-up header, the geometry source text and the differential pair
widths (90 ohm 0.1455 mm, 100 ohm 0.1148 mm) changed in every pair row and rule;
net order, pairing, skew targets and research citations are unchanged.
