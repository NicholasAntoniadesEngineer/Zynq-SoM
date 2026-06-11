# Zynq-SoM

A Zynq-7000 system-on-module + carrier board, with `schgen` — a netlist-first
KiCad schematic generator that produces electrically-proven, hand-drawn-quality
schematics from Python subsystem definitions.

## The three layers

1. **`parts/`** — one folder per physical part, named by MPN, GENERATED from
   LCSC/EasyEDA (`schgen part add C…`): pin table, symbol, footprint, 3D.
   See `parts/README.md`.
2. **`carrier/subsystems/`** — one Python netlist per subsystem, composed
   FROM parts (`use_part`, named pins, the `carrier/nets.py` contract).
   The netlist is the only hand-written layer. See
   `carrier/subsystems/README.md`.
3. **The board** — `schgen` derives ALL geometry from netlist topology,
   proves it (netlist-equivalence + ERC + zero-overlap visual gates) and
   links the sheets into one KiCad project.

Plus `som/` — the hand-authored Zynq SoM KiCad project (open
`som/Zynq_SoM.kicad_pro`, KiCad 9+; its custom libs live in `som/lib/`).
The SoM↔carrier contract `carrier/som_interface.json` is extracted
programmatically (`schgen som-interface`), never hand-edited.

## Generate everything

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install pymupdf pillow          # kicad-cli must be on PATH
PYTHONPATH=. python -m schgen build usb_pd   # one subsystem, all gates
PYTHONPATH=. python -m schgen board          # EVERY sheet + link + project
```

`schgen board` regenerates the committed outputs in place:
`carrier/Zynq_Carrier.kicad_pro` (open it in KiCad), `carrier/schematic/`,
`carrier/renders/` (with golden-snapshot drift detection, `--bless` to
accept), `carrier/reports/`, `carrier/manufacturing/` (JLC BOM + layout
constraints).

Every build fails unless ALL gates pass: **netlist** (KiCad's extracted
netlist == the declared netlist, pin for pin), **ERC** (zero errors),
**visual** (zero overlap, zero crossings, fits the page). The generator's
architecture and gate definitions: `schgen/DESIGN.md`.

## Who watches the watchmen: `schgen selftest`

There is no CI — the gate stack is the only guarantee, so `schgen selftest`
mutation-tests the gates themselves. It builds known-green sheets
(`schgen/tests/m1_rc_sheet.py` + a real carrier sheet), injects one defect
per mutation class — a pin swapped between two nets, EVERY wire segment
deleted in turn, a net label rewritten to another net's name (silent
merge/short), a stray no-connect on a netted pin, a junctioned bridge
between two foreign nets (the LAW-0 short) — and proves at least one gate
kills every mutant. It then builds each sheet twice from scratch and
byte-compares the `.kicad_sch` (uuid identities mapped to ordinals; all
geometry, order and text must match exactly) to prove determinism.
Any surviving mutant or build drift = non-zero exit. Run it after touching
`schgen/` internals:

```bash
PYTHONPATH=. python -m schgen selftest
```

Its first run already paid for itself: a stray-NC mutant survived the old
count-based no-connect check, which is why `schgen/verify/netlist_gate.py`
now audits every `no_connect` POSITIONALLY against the emitted pin map.
