# Zynq-SoM

A Zynq-7000 system-on-module + carrier board, with `schgen` — a netlist-first
KiCad schematic generator that produces electrically-proven, hand-drawn-quality
schematics from Python subsystem definitions.

## Repo layout

- `som/` — the hand-authored Zynq SoM KiCad project (open `Zynq_SoM.kicad_pro`,
  KiCad 9+). 512Mb DDR3L, 8Gb eMMC, 16Mb boot flash, GbE PHY, USB 2.0 HS OTG,
  STM32 system controller (USB FS + PD), IMU. Exposes J1/J2/J3 mezzanine
  connectors (PS MIO, 48 PL diff pairs, 56 PL single-ended).
- `carrier/` — the carrier board design: one Python file per subsystem in
  `carrier/subsystems/` (the netlist IS the spec, with LCSC part numbers for
  JLCPCB assembly); generated sheets/renders/BOM in `carrier/out/`.
- `schgen/` — the generator tool. Netlist-first: the emitted schematic is
  PROVEN equivalent to the declared netlist via KiCad's own extraction
  (`kicad-cli`), ERC-clean, and zero-overlap/zero-crossing by construction.
  See `schgen/DESIGN.md` for the architecture and the three immutable gates.
- `shared/` — KiCad assets shared between SoM and carrier (symbols,
  footprints, 3D models).
- `legacy/` — the previous generator (`zynq_eda`) and its generated carrier,
  kept as the pinout/reference source of truth. Not maintained.
- `tools/`, `docs/`, `scripts/` — utilities, block diagrams, references.

## Building a carrier subsystem

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install pymupdf            # renderer dependency (kicad-cli must be on PATH)
PYTHONPATH=. python -m schgen build usb_pd        # one subsystem
PYTHONPATH=. python -m schgen bom usb_pd uart_bridge ethernet   # JLC BOM csv
```

`build` fails (non-zero exit) unless ALL gates pass:
1. **Netlist gate** — KiCad's extracted netlist == the declared netlist,
   pin-for-pin (shorts, opens, and No-Connect cheats are structural failures).
2. **ERC gate** — `kicad-cli sch erc` zero errors.
3. **Visual gate** — zero overlap of anything, zero wire crossings.

Every build also renders a PNG (`carrier/out/<name>.png`) for human review.
