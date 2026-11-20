# schgen

Generates the Zynq carrier and devkit boards from their C++ circuit definitions:
checked schematics, a placed board, design rules, manufacturing files and renders.
Routing is not done yet.

## Build

```sh
./build
```

Compiles the tool and runs the test suite (about 17 minutes). `./build --no-tests`
only compiles. Needs CMake, Ninja, ccache, a C++17 compiler, KiCad 10 and the
libraries listed in [native/ci/README.md](native/ci/README.md).

## Run

```sh
./run
```

Builds every board listed in `schgen.json` into `out/<board>/`. To build one board,
name it: `./run carrier`. A run ends with `BOARD: PASS` or `BOARD: FAIL`.

## Settings

Every setting lives in [`schgen.json`](schgen.json). Edit the file and run again;
nothing needs recompiling. A misspelt or unknown key stops the run with an error.

| Key | Default | Meaning |
|---|---|---|
| `boards` | `["carrier", "devkit_mini"]` | Boards to build, each a folder in this repository |
| `output` | `"out"` | Folder that receives one sub-folder per board |
| `squeeze` | `true` | Compact the placed board to the smallest outline that passes every rule |
| `arrange` | `true` | Before squeezing, move clusters of parts off sides of the module so those sides can close up; needs `squeeze` |
| `renders` | `true` | Produce the 3D and per-sheet images |
| `labels` | `false` | After the layout is final, seat each part's reference label beside it on its own face and draw the function labels. Parts never move for a label; one with no free seat is hidden and listed in `reports/label_seats.txt` |
| `timing` | `true` | Print how long each stage took |
| `plane_net` | `"GND"` | Net of the reference planes |
| `audit_projections` | `2` | Source audits run side by side (1 or 2) |
| `stackup` | `JLC06161H-3313` per board | Layer build-up, by name from the catalogue below |
| `overmold_parts` | `["HDMI-019S"]` on the carrier | Connectors whose cable overmould needs side clearance |

## Layer build-ups

[`native/stackups.json`](native/stackups.json) lists the fabricator's standard
4, 6, 8 and 10-layer builds. To try another, put its name under `stackup` and run
again. The placed layout carries over between any two builds that have a ground
plane under both faces. To add a build, add an entry to that file.

## Where things are

| Folder | Holds |
|---|---|
| `carrier/`, `devkit_mini/` | Each board's design data and generated outputs |
| `subsystems/`, `parts/` | Shared circuit blocks and part data |
| `native/` | The tool's source and tests |
| `docs/` | Background; start with [docs/OVERVIEW.md](docs/OVERVIEW.md) |

`native/bin/schgen tools` lists the individual commands used for diagnosis.
