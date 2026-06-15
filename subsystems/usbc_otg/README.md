# usbc_otg — USB 2.0 HS OTG port (USB-C receptacle, host-capable) reusable subsystem

A project-agnostic, self-contained schgen subsystem: a **USB Type-C receptacle**
(TYPE-C-31-M-12) wired as a host-capable USB 2.0 High-Speed **OTG port** — a
**TPS2051C** current-limited power switch sources VBUS, a **USBLC6-2SC6** ESD
array protects the data pair, 56k CC Rp resistors advertise default-USB host
power, and a 1k strap pulls the OTG ID low for the host role. It declares its
interface as **abstract** port + rail names and knows nothing about any board; a
consuming project supplies a **bind map** (`abstract -> real net`) to drop it
onto real nets.

## Package contents

| file | role |
|------|------|
| `usbc_otg.py`      | the NETLIST — `circuit(meta=None)`, abstract ports/rails |
| `usbc_otg.cir`     | SPICE subckt — the passive network with the abstract ports as subckt pins |
| `test_usbc_otg.py` | LOCAL electrical-correctness test (offline, runs the board gate slices on just this subsystem) |
| `README.md`        | this file |

Active parts are **referenced, never vendored**: the TYPE-C-31-M-12, TPS2051CDBVR
and USBLC6-2SC6 symbols/footprints/LCSC come from the global `parts/` lib via
`use_part()`, connected by pin **name** (`J2.VBUS` nets both stacked VBUS pads,
exactly like the symbol).

## The abstract interface (the reuse contract)

A consuming project binds these names. Rails classify as POWER/GROUND by name (a
leading `+` = POWER; `GND` / `CHASSIS_GND` = GROUND), exactly as real board rails
do, so a standalone build and a bound build share net classes.

### Rails (POWER / GROUND)

| abstract | class | meaning / constraint |
|----------|-------|----------------------|
| `+VBUS_SUPPLY` | POWER  | host VBUS supply feeding the TPS2051C switch IN — the rail the port **sources** onto the cable, current-limited (a 0.5 A-class budget). Typically a gated module rail. |
| `+VDD_LOGIC`   | POWER  | logic-domain rail (3.3 V class) for the open-drain FLT# pull-up — chosen so FLT# stays within the downstream reader's IO abs-max **and** readable even when `+VBUS_SUPPLY` is gated OFF. |
| `GND`          | GROUND | ground. |
| `CHASSIS_GND`  | GROUND | receptacle shell / shield bond (chassis earth). |

### Ports (PORT)

| abstract | type | meaning |
|----------|------|---------|
| `USB_DP`, `USB_DM` | usb_hs_pair (90 ohm diff) | USB 2.0 HS data pair to the system PHY, behind the USBLC6-2SC6 ESD array. |
| `VBUS`             | single | the connector VBUS the port sources/senses (TPS2051 OUT + the receptacle VBUS pads; also the CC Rp reference and the ESD VBUS pin). |
| `VBUS_EN`          | single | active-high enable for the VBUS power switch (held OFF by a 100k pulldown until the host drives it high). |
| `FLT_N`            | single | open-drain over-current fault flag from the power switch. |
| `USB_ID`           | single | OTG ID, strapped low through 1k = **host** role for this port. |

SBU1/SBU2 are unused on a USB-2.0-only port → both are explicit author
no-connects on the receptacle (`J2`).

### Parts (from the global `parts/` lib + inline passives)

| ref | value | lib / part | LCSC |
|-----|-------|-----------|------|
| J2 | TYPE-C-31-M-12 | `parts/TYPE-C-31-M-12/` (USB-C receptacle) | C165948 |
| U1 | TPS2051CDBVR   | `parts/TPS2051CDBVR/` (current-limited power switch) | C129581 |
| U2 | USBLC6-2SC6    | `parts/USBLC6-2SC6/` (USB ESD array) | C7519 |
| C1 | 100n | `Device:C` (TPS2051 IN bypass) | C14663 |
| C2 | 22u  | `Device:C` (VBUS bulk, 0805 25V) | C45783 |
| R1, R2 | 56k | `Device:R` (CC host-advertising Rp) | C23206 |
| R3 | 100k | `Device:R` (FLT# pull-up) | C25803 |
| R4 | 1k   | `Device:R` (OTG-ID host strap) | C21190 |
| R5 | 100k | `Device:R` (EN default-OFF pulldown) | C25803 |
| TP1 | VBUS_EN | `Connector:TestPoint` (EN probe) | — |

## Consuming it from a project

A project supplies a thin adapter declaring ONE standard `META` dict (the adapter
contract, `schgen.core.subsystem.Meta`) and forwards it:

```python
from subsystems.usbc_otg import usbc_otg

META = {
    # abstract subsystem net -> your real board net
    "bind": {
        "+VBUS_SUPPLY": "+5V_USB", "+VDD_LOGIC": "+3V3_SC",
        "GND": "GND", "CHASSIS_GND": "CHASSIS_GND",
        "USB_DP": "USB_D+", "USB_DM": "USB_D-",
        "VBUS": "USB_VBUS", "VBUS_EN": "VBUS_OUT_EN",
        "FLT_N": "USBOTG_FLT_N", "USB_ID": "USB_ID",
    },
    # optional: tell the linker which of your sheets will bind a deferred port
    "expects": {"VBUS_EN": "som_j1 (GPIO function map)",
                "USB_ID":  "som_j1 (GPIO function map)",
                "FLT_N":   "bringup (TCA9535 expander port P14)"},
    # optional house-style overrides (keep your derived artifacts byte-stable)
    "notes": {"draws_vbus": "downstream USB device budget, ...",
              "draws_flt":  "USBOTG_FLT# 100k pull-up (G4 re-rail)"},
}

def circuit():
    return usbc_otg.circuit(META)
```

The four standard `META` keys (`bind` / `expects` / `buses` / `notes`) are
universal across every reusable subsystem — a typo'd top-level key is a hard
`CircuitError`, never silently dropped. `bind` renames every external **in place,
order-preserving** (POWER/GROUND/PORT only — a SIGNAL net is private wiring and
is never rebound; a SIGNAL key or a collision is a hard `CircuitError`). Because
the rename preserves net insertion order, parts, refs, NCs and port-type
payloads, **binding to the exact names a hand-written sheet used yields a
byte-identical emitted sheet.** The carrier adapter is
`carrier/subsystems/usbc_otg.py`.

### A note on the diff-pair complement

The USB 2.0 HS pair is typed `c.port_type("USB_DP", kind="usb_hs_pair",
pair_with="USB_DM")`. `Circuit.bind()` renames net + port-type **keys** in place
but does not rewrite the `pair_with` **string** inside the PortType payload, so
this subsystem re-points the complement through the same bind map **after**
`Meta.finish()` (see `_rebind_pair_with`). That keeps the library
project-agnostic (it knows only the bind map, never a carrier name) while the
board SI gate — which harvests pairs as `frozenset({net.name, pt.pair_with})` and
joins them to the project's `si_spec.json` — sees the **project** pair
(`{USB_D+, USB_D-}`), not a stale abstract one. Standalone (no bind) the
complement stays abstract.

## Design notes (datasheet + role contract)

- **VBUS is sourced, not consumed.** This is an OTG **host** port: the TPS2051C
  switches `+VBUS_SUPPLY` onto the cable VBUS, current-limited (0.5 A class). The
  EN is **active-high with a 100k pulldown** so the port stays OFF at power-on
  until the host explicitly decides the OTG role and drives `VBUS_EN` high —
  without it EN floats and the port could back-feed 5 V on the bus.
- **FLT# pull-up rail (abs-max).** TPS2051C FLT# is open-drain; its 100k pull-up
  sits on `+VDD_LOGIC` (a 3.3 V-class logic rail), **not** `+VBUS_SUPPLY`. That
  keeps the flag within a downstream reader's IO abs-max (e.g. an I2C expander at
  VCC+0.5) and readable even with the VBUS supply gated OFF (the flag is valid
  low when the port is unpowered).
- **CC host advertising.** Two 56k Rp from the sourced VBUS to CC1/CC2 advertise
  **default USB** host current per USB Type-C. The CC nets are subsystem-internal
  (terminated at the receptacle); they are not exposed ports.
- **OTG ID = host.** `USB_ID` is strapped low through 1k = host role for this
  port (a dual-role / device port lives elsewhere on the board).
- **ESD on the data pair.** The USBLC6-2SC6 passes the pair through (1<->6,
  3<->4) with TVS clamps to VBUS/GND; the connector-side stubs are internal
  SIGNAL nets, the PHY-side pair is the exposed `USB_DP`/`USB_DM` 90 ohm
  differential port.

## Local test vs board gates

`test_usbc_otg.py` runs the **subsystem-local** slices offline: declared abstract
interface, model completeness (every pin netted-or-NC), decoupling completeness
(design_rules DECAP/EP/STRAP), part-rating coverage + per-rail cap derating, the
SPICE-subckt ↔ netlist passive match, and the bind contract (including the
diff-pair-complement re-point). **Cross-board** gates stay aggregated at board
level and are *not* duplicated here: the EN/FLT linker graph, the full power-tree
headroom, the SI spec join, board ERC and the board netlist merge — all run by
`schgen board`.

```bash
PYTHONPATH=. python3 -m pytest subsystems/usbc_otg/test_usbc_otg.py -q
```
