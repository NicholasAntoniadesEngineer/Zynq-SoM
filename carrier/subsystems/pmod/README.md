# pmod — carrier ADAPTER for the reusable 2x Digilent-Pmod host-port subsystem

The carrier-specific GLUE for two plain Digilent-standard Pmod HOST ports (each a
2x6 right-angle female 2.54 mm socket, LVCMOS33). This is a **THIN ADAPTER**: the
portable circuit (netlist + SPICE + local test) lives ONCE in the project-agnostic
library package and this folder only BINDS it to the Zynq carrier's real net names
via the standard `META` contract.

> Library subsystem (the authoritative netlist + Digilent Pmod spec notes):
> [`../../../subsystems/pmod/README.md`](../../../subsystems/pmod/README.md)

## Package contents

| file | role |
|------|------|
| `pmod.py`       | the ADAPTER — `from subsystems.pmod import pmod as _lib`, the `META` bind contract, `circuit()` returns `_lib.circuit(META)` |
| `__init__.py`   | re-exports `circuit`, `META` |
| `pmod.cir`      | THIN carrier subckt — the carrier external nets as pins, instantiating the library `subsystems/pmod/pmod.cir` |
| `test_pmod.py`  | bind-parity guard — adapter nets == `_lib.circuit(META)` nets, carrier names present, no abstract leak |
| `README.md`     | this file |

## The carrier bind (`META`)

The adapter binds the library's abstract interface to the carrier's REAL net
names (the 16 J2 bank-13 host signals come VERBATIM from
`carrier/som_interface.json`); full rationale is in the `pmod.py` docstring.
Summary:

| library abstract net | carrier net | why |
|----------------------|-------------|-----|
| `+VCC_PMOD`     | `+3V3_PMOD` | bring-up-gated module rail (SY6280 #7) |
| `GND`           | `GND`       | identity |
| `PMOD0_SIG1..8` | `IO_L2_P_13 … IO_L5_N_13` | 4 bank-13 LVDS-capable J2 pairs |
| `PMOD1_SIG1..8` | `IO_L7_P_13 … IO_L10_N_13` | 4 more bank-13 J2 pairs |

`META["expects"]` declares the linker deferral for all 16 host signals (they bind
on the generated J2 connector sheet); `META["notes"]` restores the carrier's
power-tree draw prose (~100 mA per module). NOTE the SoM-symbol quirk
`IO_L5P_13` (no underscore before P) — do not "fix" it.

Because the adapter is a pure rename of the library circuit, the emitted
`carrier/schematic/pmod.kicad_sch` and its golden render are **byte-identical** to
the pre-folding flat adapter.

## Local test

```bash
PYTHONPATH=. python3 -m pytest carrier/subsystems/pmod/test_pmod.py -q
```

The library's full electrical correctness (200R IO protection / VCC bypass /
ratings / SPICE) is proven by `subsystems/pmod/test_pmod.py`; the board-level
gates (power tree, ERC, link/port-driver graph, netlist merge) stay aggregated by
`schgen board`.
