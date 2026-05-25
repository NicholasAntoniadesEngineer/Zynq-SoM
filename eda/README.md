# zynq_eda — Programmatic KiCad schematic generator

Generates production-grade KiCad 9.0 `.kicad_sch` projects for the Zynq-SoM
carrier (today) and other Zynq-family boards (future). Driven by Python; the
output is pristine, ERC-clean, BOM-ready KiCad — no manual layout pass needed
after generation.

## Install

From `eda/`:

```bash
make install        # editable install + hidden-flag fix
make install-dev    # + pytest, ruff
make test
```

The `Makefile` wraps `pip install -e . --config-settings editable_mode=compat`
and strips the macOS `UF_HIDDEN` flag that hatchling sets on its `.pth` file
(Python 3.13+ silently refuses to load hidden `.pth` files).

## Run

```bash
python -m zynq_eda --board carrier --output boards/carrier
python -m zynq_eda --board carrier --audit-only          # Stage 0: completeness check
python -m zynq_eda --board carrier --only power          # build a single block
python -m zynq_eda --board carrier --skip-erc            # skip kicad-cli ERC
```

## Package layout

```
src/zynq_eda/
  core/         # board-agnostic infrastructure (model, layout, route, rules, emit, validate)
  catalog/      # shared component catalog (parts, refcircuits, datasheets, symbols)
  projects/     # per-board project definitions (carrier, som)
```

See the top-level repo `README.md` for the full architecture and roadmap.
