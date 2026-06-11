# parts/ — the component library

One folder per physical component, named by **manufacturer part number**. Every
file in a folder carries the part's name. Everything is **generated** — never
hand-edited (re-run the generator to update):

```
parts/FUSB302BMPX/
  FUSB302BMPX.py            # metadata: MPN, LCSC id, datasheet, pin table (+ rules)
  FUSB302BMPX.kicad_sym     # schematic symbol (schgen's clean on-grid layout)
  FUSB302BMPX.kicad_mod     # footprint — faithful to the JLC physical part
  FUSB302BMPX.step / .wrl   # 3D models
  FUSB302BMPX.easyeda.json  # raw CAD data (provenance + offline regeneration)
```

## Adding a new part from LCSC

1. Find the part on lcsc.com / jlcpcb.com/parts and note its **C-number**
   (prefer JLC *Basic* parts — no assembly setup fee).
2. Generate the folder:
   ```bash
   PYTHONPATH=. python -m schgen part add C132291
   ```
3. Check the result: the symbol must load (the generator enforces the 1.27 mm
   pin grid), the footprint is converted pad-for-pad from the JLC data.
4. Verify availability/price any time:
   ```bash
   PYTHONPATH=. python -m schgen preflight <subsystem>...
   ```
5. Commit the folder.

Offline regeneration (no network, byte-stable):
```bash
PYTHONPATH=. python -m schgen part add C132291 --from-json parts/FUSB302BMPX/FUSB302BMPX.easyeda.json
```

Subsystems consume parts by MPN — see `carrier/subsystems/README.md`.
