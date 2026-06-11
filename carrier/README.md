# carrier — the generated carrier board

Open `Zynq_Carrier.kicad_pro` in KiCad (9+). EVERYTHING here except
`subsystems/*.py`, `PLAN.md` and the research dossiers is generated —
regenerate in place with `PYTHONPATH=. python -m schgen board`.

- `subsystems/` — the authored netlists (the only hand-written layer);
  see `subsystems/README.md` for the authoring guide.
- `Zynq_Carrier.kicad_sch` + `schematic/` — the root sheet + sub-sheets
  (hierarchy mode, board-unique references), committed.
- `renders/` — one PNG per sheet, committed and reviewable on GitHub;
  `golden.json` holds perceptual hashes — drift warns, `schgen board
  --bless` accepts intentional changes.
- `reports/` — per-sheet ERC, gate verdicts, link report, board netlist
  gate: the proof travels with the design.
- `manufacturing/` — `bom_jlc.csv` + JLC04161H-7628 layout constraints.
- `fpga/` — `Zynq_Carrier_pins.xdc`, GENERATED Vivado pin constraints
  (`schgen xdc`): every carrier port on a Zynq PL ball through J2/J3,
  ball map live-extracted from the SoM project (never hand-typed),
  cross-checked against `som_interface.json` (stale contract = build
  FAIL), IOSTANDARD from the PLAN VCCO rail map.
- `som_interface.json` — the SoM↔carrier J1/J2/J3 contract, extracted
  programmatically (`schgen som-interface`), never hand-edited.
- `nets.py` — the GENERATED cross-sheet net-name contract
  (`schgen nets`).
- `PLAN.md` — the locked decisions; `research/` — per-subsystem dossiers.
