# pd_input — carrier ADAPTER for the reusable USB-C PD power-inlet subsystem

The carrier-specific GLUE for the USB-C PD power INLET: the Type-C receptacle +
TPS26631 eFuse (OVP / soft-start) + USBLC6 data ESD. This is a **THIN ADAPTER**:
the portable circuit (netlist + SPICE + local test + datasheet design notes)
lives ONCE in the project-agnostic library package and this folder only BINDS it
to the Zynq carrier's real net names via the standard `META` contract.

> Library subsystem (the authoritative netlist + TI SLVSE94G design notes):
> [`../../../subsystems/pd_input/README.md`](../../../subsystems/pd_input/README.md)

## Package contents

| file | role |
|------|------|
| `pd_input.py`       | the ADAPTER — `from subsystems.pd_input import pd_input as _lib`, the `META` bind contract, `circuit()` returns `_lib.circuit(META)` |
| `__init__.py`       | re-exports `circuit`, `META` |
| `pd_input.cir`      | THIN carrier subckt — the carrier external nets as pins, instantiating the library `subsystems/pd_input/pd_input.cir` |
| `test_pd_input.py`  | bind-parity guard — adapter nets == `_lib.circuit(META)` nets, carrier names present, no abstract leak |
| `README.md`         | this file |

## The carrier bind (`META`)

The adapter binds the library's abstract interface to the carrier's REAL net
names; the rationale for each is in the `pd_input.py` module docstring (every
strap value from TI SLVSE94G). Summary:

| library abstract net | carrier net | why |
|----------------------|-------------|-----|
| `+VBUS_CONN`  | `+VBUS_IN`        | raw receptacle VBUS, ahead of the eFuse (TVS + OVP-top) |
| `+VBUS_OUT`   | `+VIN`            | fused board bulk; `power.py` consumes it |
| `+VDD_LOGIC`  | `+3V3_SC`         | always-on SoM logic rail; FLT# pull-up + USBLC6 clamp ref |
| `GND`         | `GND`             | identity |
| `CHASSIS_GND` | `CHASSIS_GND`     | connector-shell earth island (identity) |
| `CC1` / `CC2` | `STM32_USB_CC1/2` | receptacle CC lines -> FUSB302 + STM32 CC-sense |
| `USB_D_P/N`   | `STM32_USB_D_P/N` | FS data pair (post-USBLC6 ESD) |
| `FLT_N`       | `PD_FLT_N`        | eFuse open-drain fault -> bring-up TCA9535 (P15) |

`META["expects"]` declares the linker deferral for `FLT_N` (it binds on the
generated bring-up TCA9535 expander). `pd_input` declares no `draws`/`buses`: it
SOURCES rails rather than budgeting a load, matching the original sheet.

Because the adapter is a pure rename of the library circuit, the emitted
`carrier/schematic/pd_input.kicad_sch` and its golden render are **byte-identical**
to the pre-folding flat adapter.

## Local test

```bash
PYTHONPATH=. python3 -m pytest carrier/subsystems/pd_input/test_pd_input.py -q
```

The library's full electrical correctness (eFuse straps / OVP divider / ESD /
ratings / SPICE) is proven by `subsystems/pd_input/test_pd_input.py`; the
board-level gates (power tree, ERC, link/port-driver graph, netlist merge) stay
aggregated by `schgen board`.
