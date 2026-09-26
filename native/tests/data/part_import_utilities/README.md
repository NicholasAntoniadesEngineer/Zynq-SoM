# Independent part-import utility reference

`python.json` was captured from the unmodified legacy `schgen/partlib/part_gen.py`
before its adapter replacement on 2026-09-26. The recorded source SHA-256 is in
the fixture. Pin grouping, normalization, exposed-pad numbering, symbol geometry,
safe names, and EP/polarity graphics were computed by the original Python
functions. Symbol serialization and text measurement explicitly used the retained
Python reference functions, not native converter output.

This supplements (does not replace or regenerate) the 62 original responses in
`../part_gen/`, each with three independently captured model variants. Existing
OBJ-to-WRL cases are reused from `../render_models/reference.json`.

The gzip bytes were generated once from the stored UTF-8 plaintext using the
Python standard-library gzip encoder with `mtime=0`. Native contracts replay
those exact bytes through a real child process before decompression, without
network access. Other HTTP failures use explicit injected transport responses.

`SHA256SUMS` covers this reference and all 62 earlier part-conversion references;
paths are relative to `native/tests/data`. Tests must not rewrite these fixtures.
