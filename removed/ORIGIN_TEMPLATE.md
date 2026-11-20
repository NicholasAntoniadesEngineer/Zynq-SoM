# <subfolder> origin

Copy this file to `removed/<subfolder>/ORIGIN.md` and fill the eight items in this order.

1. What the output was, in two sentences, and who used it: which role of reader, and which other pipeline step read it (with `file:line`).
2. Every file moved, as a table: original path, archive path, `git hash-object` value; for a fragment, the original file and line range.
3. The source commit: the hash of the last commit in which the files were at their original paths (the parent of the move commit). The move commit's own hash is added to `INDEX.md` by the next commit.
4. What produced it: the pipeline step and gate name, the function and call site, the command-line command, and the build-file lines that compiled it.
5. What it read: sheets by name, parts recognised, nets by name, typed numbers, each with the original `file:line`.
6. Why it was removed, quoting the owner: "lets clear out handwritten things completely and we can deal with them later. The tool must be as programmatic as possible and extensive as what that allows", and the specific reason (which share was typed).
7. What part of it can be generated, under which task, and which facts that needs.
8. What bringing it back would take: the files to move back, the build-file and pipeline lines to restore (quoted as removed), the tests, and what has changed since that it depends on.

Folder layout: `source/` whole generator files; `tests/` tests and fixtures that existed only for the output; `outputs/<board>/` the last committed generated copy at its relative path; `fragments/` text cut out of a file that stays, one file per fragment named `<original file name>.L<first>-<last>.txt` holding the exact removed lines.
