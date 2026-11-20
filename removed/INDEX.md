# removed/

Hand-written outputs that were taken out of the schgen tool. Nothing here is deleted: every file was moved with `git mv`, so `git log --follow <archive path>` shows its history.

The owner's ruling: "lets clear out handwritten things completely and we can deal with them later. The tool must be as programmatic as possible and extensive as what that allows".

Each subfolder has an `ORIGIN.md` that records, in order: what the output was and who used it; every file moved (original path, archive path, `git hash-object`); the source commit; what produced it; what it read; why it was removed; what part of it can be generated; what bringing it back would take. The template is `ORIGIN_TEMPLATE.md`.

Rules the tool relies on (enforced by `native_removed_archive_contracts`):

- `removed/board.json` must not exist: a direct child of the repository root holding `board.json` is read as a board folder.
- `removed/project.json` must not exist: a direct child of the repository root holding `project.json` is read as a fallback baseline.
- No `.py`, `.pyc` or `.pyo` file may be placed under `removed/`.
- Never archive under `subsystems/` or `<board>/subsystems/`.

## Subfolders

(none yet; each removal adds its line here)

## Files

(none yet; each removal adds its files here)

## Move commits

(none yet; each removal adds its commit here)
