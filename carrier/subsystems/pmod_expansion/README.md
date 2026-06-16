# pmod_expansion — carrier ADAPTER for the reusable manual-gated Pmod port

The carrier-specific GLUE for a single host-side Pmod expansion port: 8 IO + 2x
VCC(3.3 V) + 2x GND on a right-angle 2x6 socket at the board edge, the 3.3 V it
provides taken from a MANUALLY-GATED rail so a powered-down peripheral is never
back-fed (constraint C1). This is a **THIN ADAPTER**: the portable circuit
(netlist + SPICE + local test) lives ONCE in the project-agnostic library package
and this folder only BINDS it to the Zynq carrier's real net names via the
standard `META` contract.

> Library subsystem (the authoritative netlist + datasheet design notes):
> [`../../../subsystems/pmod_expansion/README.md`](../../../subsystems/pmod_expansion/README.md)

## Package contents

| file | role |
|------|------|
| `pmod_expansion.py`       | the ADAPTER — `from subsystems.pmod_expansion import pmod_expansion as _lib`, the `META` bind contract, `circuit()` returns `_lib.circuit(META)` |
| `__init__.py`             | re-exports `circuit`, `META` |
| `pmod_expansion.cir`      | THIN carrier subckt — the carrier external nets as pins, instantiating the library `subsystems/pmod_expansion/pmod_expansion.cir` |
| `test_pmod_expansion.py`  | bind-parity guard — adapter nets == `_lib.circuit(META)` nets, carrier names present, no abstract leak |
| `README.md`               | this file |

## The carrier bind (`META`)

The adapter binds the library's abstract interface to the carrier's REAL net
names; full rationale (including the SY6280 manual-enable / default-OFF gating
and the free bank-13 PL pins) is in the `pmod_expansion.py` docstring. Summary:

| library abstract net | carrier net | why |
|----------------------|-------------|-----|
| `+VDD_PMOD`     | `+3V3`        | carrier-sourced `+VCCO_13 = +3V3`; SY6280 input |
| `+VSW_PMOD`     | `+3V3_PMODX`  | the MANUALLY-GATED switched output rail (default OFF, C1) |
| `GND`           | `GND`         | identity |
| `PMOD_IO1..8`   | `PMODX_IO1..8`| 8 genuinely-FREE bank-13 PL function nets (J2) |

`META["expects"]` declares the linker deferral for the 8 Pmod IO (they bind on
the generated J2 connector sheet); `META["notes"]` restores the carrier's
power-tree draw prose (~100 mA + status LED).

Because the adapter is a pure rename of the library circuit, the emitted
`carrier/schematic/pmod_expansion.kicad_sch` and its golden render are
**byte-identical** to the pre-folding flat adapter.

## Local test

```bash
PYTHONPATH=. python3 -m pytest carrier/subsystems/pmod_expansion/test_pmod_expansion.py -q
```

The library's full electrical correctness (SY6280 load-switch / ESD / ratings /
SPICE) is proven by `subsystems/pmod_expansion/test_pmod_expansion.py`; the
board-level gates (power tree, ERC, link/port-driver graph, netlist merge) stay
aggregated by `schgen board`.
