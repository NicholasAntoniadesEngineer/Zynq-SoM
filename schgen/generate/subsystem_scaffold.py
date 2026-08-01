from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SUBSYSTEMS_DIR = REPO_ROOT / "subsystems"


def _py(name: str) -> str:
    return f'''"""{name} — <one-line purpose> (reusable subsystem).

PROJECT-AGNOSTIC. Declares its interface as ABSTRACT port + rail names and knows
nothing about any board; a project consumes it via the standard meta contract
(schgen.core.subsystem) — circuit(meta) with meta["bind"] = {{abstract: real}}.
See subsystems/usb_pd/ for the worked exemplar.
"""

from __future__ import annotations

from schgen.core.model import Circuit
from schgen.core.subsystem import Meta

# ---- the abstract interface (the REUSE contract) ------------------------------
# Externally-visible net names a consuming project binds. Rails classify as
# POWER/GROUND by name (a leading '+' = POWER; 'GND' = GROUND); ports are
# declared with c.port(...).
RAILS = ("+VDD", "GND")
PORTS = ()                       # e.g. ("MY_SIGNAL",)
INTERFACE = RAILS + PORTS

# Default house-style metadata a project may override via meta["buses"]/["notes"]:
#   DRAWS_NOTE = "<part> <current> (datasheet)"   # meta["notes"]["draws"]
#   I2C_BUS = "{name.upper()}_I2C"                 # meta["buses"]["i2c"]


def circuit(meta: "Meta | dict | None" = None) -> Circuit:
    """Build the {name} netlist with ABSTRACT names. ``meta`` is the standard
    subsystem adapter dict (schgen.core.subsystem): meta["bind"] rebinds the
    externally-visible nets to a project's real names, meta["expects"] adds
    per-port linker deferrals, meta["buses"]/meta["notes"] restore house style.
    Standalone (meta=None) keeps the abstract names for the local test."""
    meta = Meta(meta)
    c = Circuit("{name}", "<title>")

    # active from the global parts/<MPN>/ lib (referenced, never vendored):
    #   c.use_part("MPN_IN_PARTS_DIR", ref="U1")
    # c.net("+VDD", "U1.VDD")
    # c.decouple("U1.VDD", "100n")
    # c.net("GND", "U1.GND")
    # c.port("MY_SIGNAL", "U1.OUT", **meta.expect_kw("MY_SIGNAL"))
    raise NotImplementedError("fill in the {name} netlist")

    return meta.finish(c)        # noqa: F841 — applies meta["bind"], returns c
'''


def _init(name: str) -> str:
    return (f'"""{name} reusable subsystem."""\n\n'
            f"from subsystems.{name}.{name} import circuit, INTERFACE, "
            f"RAILS, PORTS\n\n"
            f'__all__ = ["circuit", "INTERFACE", "RAILS", "PORTS"]\n')


def _readme(name: str) -> str:
    return f"""# {name} — <one-line purpose> (reusable subsystem)

A project-agnostic, self-contained schgen subsystem. Declares its interface as
**abstract** port + rail names; a project supplies a **bind map**
(`abstract -> real net`). See `subsystems/usb_pd/README.md` for the worked
exemplar.

## Package contents

| file | role |
|------|------|
| `{name}.py`      | the NETLIST — `circuit(meta=None)`, abstract ports/rails |
| `{name}.cir`     | SPICE subckt — passive network with abstract ports as subckt pins |
| `test_{name}.py` | LOCAL electrical-correctness test (offline) |
| `README.md`      | this file |

Active parts are **referenced** from the global `parts/<MPN>/` lib, never
vendored.

## The abstract interface (the reuse contract)

### Rails (POWER / GROUND)

| abstract | class | meaning / constraint |
|----------|-------|----------------------|
| `+VDD` | POWER | <supply> |
| `GND`  | GROUND | ground |

### Ports (PORT)

| abstract | type | meaning |
|----------|------|---------|
| `MY_SIGNAL` | single | <what it is> |

## Consuming it from a project

A project supplies a thin adapter declaring ONE standard `META` dict (see
`schgen.core.subsystem`):

```python
from subsystems.{name} import {name}

META = {{
    "bind": {{"+VDD": "+3V3", "GND": "GND", "MY_SIGNAL": "BOARD_NET"}},
    # "expects": {{"MY_SIGNAL": "bound on the <X> sheet"}},
    # "buses":   {{"i2c": "BOARD_I2C"}},
    # "notes":   {{"draws": "<house-style power-tree note>"}},
}}

def circuit():
    return {name}.circuit(META)
```

## Design notes

- <datasheet / dossier notes>

## Local test

```bash
PYTHONPATH=. python3 -m pytest subsystems/{name}/test_{name}.py -q
```
"""


def _cir(name: str) -> str:
    return f"""* {name}.cir — SPICE subckt for the {name} subsystem.
*
* PROJECT-AGNOSTIC: the subckt pins are the subsystem's ABSTRACT interface, NOT
* any board net. Values mirror {name}.py one-for-one (parse_si compatible).
*
* Port order: VDD GND   (GND last by convention; add the rest)

.subckt {name} VDD GND
* <passives mirroring the netlist, e.g.:>
* C1 VDD GND 100n
.ends {name}

.end
"""


def _test(name: str) -> str:
    return f'''"""LOCAL electrical-correctness test for the {name} reusable subsystem.

Runs the SUBSYSTEM-LOCAL slices of the board verify gates on JUST this
subsystem's circuit, standalone and offline. See subsystems/usb_pd/test_usb_pd.py
for the worked exemplar. Cross-board gates (link, full power tree, board ERC,
board netlist merge) stay aggregated at board level — do NOT duplicate them here.
"""

from __future__ import annotations

import types

import pytest

from schgen.core.model import Circuit, CircuitError, NetClass
from schgen.core.symbols import Library
from schgen.verify import design_rules

import subsystems.{name}.{name} as {name}


def _sheet(c: Circuit):
    return types.SimpleNamespace(name=c.name, circuit=c)


@pytest.mark.skip(reason="scaffold stub — implement once {name}.py is filled in")
def test_interface_is_abstract():
    c = {name}.circuit()
    externals = {{n.name for n in c.nets.values()
                 if n.net_class is not NetClass.SIGNAL}}
    assert externals == set({name}.INTERFACE), externals


@pytest.mark.skip(reason="scaffold stub — implement once {name}.py is filled in")
def test_decoupling_complete():
    c = {name}.circuit()
    r = design_rules.check([_sheet(c)], Library())
    assert not (r.decap or r.ep or r.strap), r.findings


@pytest.mark.skip(reason="scaffold stub — implement once {name}.py is filled in")
def test_bind_rejects_unknown_name():
    c = {name}.circuit()
    with pytest.raises(CircuitError):
        c.bind({{"NOT_A_PORT": "X"}})
'''


WRITERS = {
    "{name}.py": _py,
    "__init__.py": _init,
    "README.md": _readme,
    "{name}.cir": _cir,
    "test_{name}.py": _test,
}


def scaffold(name: str, *, force: bool = False) -> Path:
    if not name.isidentifier():
        raise SystemExit(f"subsystem name {name!r} must be a valid Python "
                         f"identifier")
    pkg = SUBSYSTEMS_DIR / name
    if pkg.exists() and not force:
        raise SystemExit(f"subsystems/{name}/ already exists — edit it in place "
                         f"(pass --force to overwrite the skeleton)")
    pkg.mkdir(parents=True, exist_ok=True)
    for template, writer in WRITERS.items():
        fname = template.replace("{name}", name)
        (pkg / fname).write_text(writer(name))
    return pkg


def cmd(args) -> int:
    pkg = scaffold(args.name, force=getattr(args, "force", False))
    files = ", ".join(sorted(p.name for p in pkg.iterdir()))
    print(f"scaffolded subsystems/{args.name}/ ({files})")
    print(f"next: fill in {args.name}.py's circuit(), then run\n"
          f"  PYTHONPATH=. python3 -m pytest subsystems/{args.name}/"
          f"test_{args.name}.py -q\n"
          f"  PYTHONPATH=. python3 -m schgen subsystem-check")
    return 0
