# Four-sheet legacy example references

Captured on 2026-09-26, before implementing any native example factory. These
are `examples/devkit_mini`, not the distinct twelve-sheet `devkit_mini` project.

Each record contains the original wrapper's exact metadata, reusable-library
interface/rail/port declarations, default library IR, bound example IR, and one
independent alternate metadata/IR case. The existing reusable-library authoring
implementation had already been migrated and validated; capture invoked the
unchanged Python example wrapper and `Circuit.to_ir`, never the new example C++
factory. The older independent library-constructor oracles remain under
`../authoring/`. Production C++ reads none of these files.

Alternate cases systematically rename non-ground bindings and change note,
expectation and bus parameters. They prove live parameter transport, while native
mutation tests independently check unknown/private/colliding binds, actual symbol
completeness, design/part rules, and freshly placed/routed CC geometry.

Source hashes at capture:

```
d188e3d6de221cc25791a00c1094634a5fa4330b0cf4d6f30a32efd1d3f336ca  examples/devkit_mini/devkit_mini.py
8f88cf58f0e0184c8900d1dc941a2c19f8aae3220e82542face454546c31f5d7  examples/devkit_mini/test_devkit_mini.py
82c626455465c71c6cc61906c9329ef0d7944316e4270c4999c27b5c144a2727  schgen/generate/devkit.py
```

No render, schematic, board or report baseline was regenerated. Freeze these
bytes; do not regenerate expectations to accommodate native differences.
