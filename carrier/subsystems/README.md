# carrier/subsystems — the carrier design layer

This directory is the only hand-written layer of the carrier board. Everything
else (placement, routing, the KiCad schematic, the PCB, the renders) is
generated. Here you author the **electrical design**: one Python netlist per
schematic sheet, and nothing else.

A netlist is **netlist-only** — it declares parts and nets and ports. It carries
no coordinates, no wire plans, no text positions. The placement engine derives
all geometry from the netlist's topology. This is enforced (see [Purity](#purity)
below), not a convention.

## Two kinds of carrier sheet

Every name in this directory is exactly one of two kinds. The kind is mechanical:
a sheet is an **adapter** if and only if a reusable library package exists at
`../../subsystems/<name>/`; otherwise it is a carrier **local**. The two kinds
have different on-disk shapes, and the gate below proves each one matches.

### Adapter — a thin bind over the reusable library

When the design is portable, its circuit lives once in the project-agnostic
library at [`../../subsystems/<name>/`](../../subsystems/README.md) with abstract
net names. The library package already owns the README, the SPICE model, and the
tests, so the carrier side must not duplicate them. An adapter is therefore a
**flat pair**, not a folder:

```
carrier/subsystems/<name>.py        the bind (circuit() + META)
carrier/subsystems/test_<name>.py   the local bind guard
```

The `.py` declares one module-level `META` dict and forwards it:

```python
from subsystems.ethernet import ethernet as _lib
from schgen.core.model import Circuit

META = {
    "bind":    {"MDI0_P": "ETH_PHY_MDI0_P", "MDI0_N": "ETH_PHY_MDI0_N", ...},
    "expects": {"MX0_P": "rj45_connector (wave 2)", ...},
}

def circuit() -> Circuit:
    return _lib.circuit(META)
```

`META["bind"]` maps each abstract library net to this carrier's real net name,
so the emitted sheet matches a hand-written one. `META["expects"]` records
deferrals — ports that bind on another sheet — so a standalone link reports them
as awaiting that sheet instead of a silent open. The contract is
`schgen.core.subsystem.Meta`; an unknown top-level key is a hard error.

Current adapters: `camera`, `ethernet`, `hdmi_rx`, `hdmi_tx`, `lcd`, `microsd`,
`pd_input`, `pmod`, `pmod_expansion`, `rj45_connector`, `uart_bridge`,
`usb_jtag`, `usb_jtag_connector`, `usb_pd`, `usb_uart_connector`, `usbc_otg`.

### Local — carrier-specific glue authored from `parts/`

When a sheet only makes sense for this board, there is no library to point at.
It is authored here directly, composed from the generated `parts/` folders, and
kept as a self-contained **foldered package** with the same four-artifact parity
the library uses:

```
carrier/subsystems/<name>/<name>.py        the netlist
carrier/subsystems/<name>/__init__.py      re-exports circuit()
carrier/subsystems/<name>/README.md        purpose / interface / parts
carrier/subsystems/<name>/test_<name>.py   the local correctness test
carrier/subsystems/<name>/<name>.cir       the SPICE passive network
```

The locals cover the things unique to this carrier:

- **Mezzanine** — `som_j1`, `som_j2`, `som_j3`: the three DF40 SoM connectors.
  Their pinout is generated from `carrier/som_interface.json`, not hand-typed.
- **Power** — `power_som` (always-on +VIN→+5V_SOM buck feeding the SoM),
  `power_mon` (INA3221 rail telemetry), `som_decoupling` (power-entry decoupling
  under the mezzanine).
- **Bring-up** — `bringup_rails`, `bringup_en`, `bringup_en_modules`,
  `bringup_modules`: the DIP-switch / STM32-override gate cells, per-module power
  gates, and status LEDs.
- **Board services** — `board_aux` (gated +3V3_AUX rail), `board_services`
  (board-management peripherals on that rail), `debug_boot` (JTAG/SWD headers,
  boot-request DIP, reset).
- **Carrier connectors and IO** — `fmc`, `board_qwiic`, `user_io`, `mechanical`
  (mounting holes + chassis bond), `motor_pwm`, `motor_sense`, `hdmi_rx_term`.

## Purity

A subsystem `.py` is netlist-only, enforced by an AST scan of the source before
the module is even imported. The build fails if the source:

- defines or binds a name `placer` (manual placement is banned — the engine
  derives all geometry from topology), or
- imports any geometry / placement API.

The runtime is checked too: a module that exposes a `placer` attribute fails.
Because the scan is on the source, a broken geometry import is still rejected.

## The structure gate

`schgen/verify/carrier_structure.py` is a hard gate (it fails the board). For
every subsystem it determines the kind — adapter iff `../../subsystems/<name>/`
exists, else local — and proves:

- the on-disk shape the kind requires is present (an adapter is the flat pair and
  has **no** leftover folder; a local is the foldered four-artifact package),
- `circuit()` is importable and runs without raising, and
- an adapter additionally exposes a `META` dict.

Run it standalone:

```bash
python -m schgen carrier-check
```

The generic library packages under `../../subsystems/` are policed by the mirror
gate `schgen/verify/subsystem_structure.py`.

## Adding a sheet

There is no registration list. A sheet is discovered purely by its file: every
non-test `.py` module and every folder here is a subsystem. Expose a top-level
`def circuit() -> Circuit:` and name the circuit to match
(`Circuit("<name>", "…")`); the circuit name becomes the sheet and render name.

- A new **adapter**: scaffold the portable circuit into the library
  (`schgen subsystem <name>`), then add the flat `<name>.py` bind plus
  `test_<name>.py` here.
- A new **local**: create the `<name>/` folder with all four artifacts and
  compose the netlist from `parts/`.

Build one sheet (all gates) or the whole board:

```bash
PYTHONPATH=. python -m schgen build <name>
PYTHONPATH=. python -m schgen board
```
