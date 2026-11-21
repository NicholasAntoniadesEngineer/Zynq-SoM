# pl_expansion origin

## 1. What it was and who used it

The library subsystem `pl_expansion`: a 2x20 header carrying 32 spare bank-34 module pins with a current-limited 3.3 V pin pair (SY6280). Only `motor_carrier` used it.

## 2. Files moved

| original path | archive path | git hash-object |
|---|---|---|
| `subsystems/pl_expansion/subsystem.json` | `removed/pl_expansion/source/subsystem.json` | `ca8b73410e2d3f0abf34d878e0870ec6d928fc33` |
| `subsystems/component_basis.json:297-299` (PL_EXPANSION_ISET, PL_EXPANSION_IN_BYPASS, PL_EXPANSION_OUT) | `removed/pl_expansion/fragments/component_basis.json.L297-299.txt` | `95be92906322a481dfcfca48a355a112016c7199` |

Its README and .cir are already in `removed/subsystem_notes/library/pl_expansion/`. Also removed from `motor_carrier`: the sheet in `board.json`, its three `component_basis.json` uses and sheet entry, the S-edge floorplan entry, the `wired_sheets` entry, and the `board_scope_only` name in `subsystems/component_basis.json`. The 32 bank-34 module pins it bound now keep the module's own names as one-pad port nets, the convention for unused module pins (`native/src/project_authoring.cpp`).

## 3. Source commit

`3255981b2c4122daf2ad7c1390d4d46bbd046d00` (the last commit with the files at their original paths).

## 4. Why it was removed

The owner, on the first renders of the motor-control carrier: "We also don't need random headers on our motor controlelr board".

## 5. Bringing it back

`git mv` the source file back to `subsystems/pl_expansion/subsystem.json`, restore the three declarations at their recorded lines, add the name back to `board_scope_only`, and add the sheet, its bindings (see the board.json of the source commit), basis uses, floorplan and `wired_sheets` entries back to a board.
