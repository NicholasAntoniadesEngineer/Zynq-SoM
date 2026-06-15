# usb_jtag_connector — USB-C UFP receptacle + ESD reusable subsystem

A project-agnostic, self-contained schgen subsystem: a **USB Type-C receptacle**
(TYPE-C-31-M-12) wired as a USB 2.0 **device-role (UFP)** debug port — a
**USBLC6-2SC6** ESD array protects the data pair, 5.1k **Rd** pulldowns on both
CC pins advertise the device role (so the host applies VBUS), and a 10u bulk
bypasses the receptacle VBUS. It declares its interface as **abstract** port +
rail names and knows nothing about any board; a consuming project supplies a
**bind map** (`abstract -> real net`) to drop it onto real nets.

It is the connector half of the usb_jtag debug bridge: a USB-C cable plugged here
supplies the downstream consumer (the CH347T bridge on the carrier) over its own
5 V VBUS + a protected USB 2.0 HS data pair, on its own sheet so neither sheet
gets dense.

## Package contents

| file | role |
|------|------|
| `usb_jtag_connector.py`      | the NETLIST — `circuit(meta=None)`, abstract ports/rails |
| `usb_jtag_connector.cir`     | SPICE subckt — the passive network with the abstract ports as subckt pins |
| `test_usb_jtag_connector.py` | LOCAL electrical-correctness test (offline, runs the board gate slices on just this subsystem) |
| `README.md`                  | this file |

Active parts are **referenced, never vendored**: the TYPE-C-31-M-12 receptacle
and USBLC6-2SC6 ESD array symbols/footprints/LCSC come from the global `parts/`
lib via `use_part()`, connected by pin **name** (`J1.VBUS` nets both stacked VBUS
pads, exactly like the symbol).

## The abstract interface (the reuse contract)

A consuming project binds these names. Rails classify as POWER/GROUND by name (a
leading `+` = POWER; `GND` / `CHASSIS_GND` = GROUND), exactly as real board rails
do, so a standalone build and a bound build share net classes.

### Rails (POWER / GROUND)

| abstract | class | meaning / constraint |
|----------|-------|----------------------|
| `+VBUS`       | POWER  | the receptacle 5 V VBUS (also the USBLC6 VBUS clamp ref). A POWER rail so it merges by **name** onto the downstream consumer's supply input — the port **sinks** this 5 V (the cable host's own supply), it does not source it. |
| `GND`         | GROUND | ground. |
| `CHASSIS_GND` | GROUND | receptacle shell / shield bond (chassis earth). |

### Ports (PORT)

| abstract | type | meaning |
|----------|------|---------|
| `USB_DP`, `USB_DM` | usb_hs_pair (90 ohm diff) | USB 2.0 HS data pair to the downstream consumer, behind the USBLC6-2SC6 ESD array. |

SBU1/SBU2 are unused on a USB-2.0-only debug link → both are explicit author
no-connects on the receptacle (`J1`). The CC lines are subsystem-internal (the
Rd pulldowns terminate them at the receptacle); they are not exposed ports.

### Parts (from the global `parts/` lib + inline passives)

| ref | value | lib / part | LCSC |
|-----|-------|-----------|------|
| J1 | TYPE-C-31-M-12 | `parts/TYPE-C-31-M-12/` (USB-C receptacle) | C165948 |
| U1 | USBLC6-2SC6    | `parts/USBLC6-2SC6/` (USB ESD array) | C7519 |
| C1 | 10u  | `Device:C` (VBUS bulk, 0805) | C15850 |
| R1, R2 | 5.1k | `Device:R` (USB device-role Rd pulldown) | C23186 |
| TP1 | +VBUS | `Connector:TestPoint` (VBUS probe) | — |

## Consuming it from a project

A project supplies a thin adapter declaring ONE standard `META` dict (the adapter
contract, `schgen.core.subsystem.Meta`) and forwards it:

```python
from subsystems.usb_jtag_connector import usb_jtag_connector

META = {
    # abstract subsystem net -> your real board net
    "bind": {
        "+VBUS": "+5V_DBG",
        "GND": "GND",
        "CHASSIS_GND": "CHASSIS_GND",
        "USB_DP": "DBG_USB_DP",
        "USB_DM": "DBG_USB_DM",
    },
    # optional: tell the linker which of your sheets consumes the USB pair
    "expects": {"USB_DP": "usb_jtag (CH347T bridge)"},
}

def circuit():
    return usb_jtag_connector.circuit(META)
```

The four standard `META` keys (`bind` / `expects` / `buses` / `notes`) are
universal across every reusable subsystem — a typo'd top-level key is a hard
`CircuitError`, never silently dropped. `bind` renames every external **in place,
order-preserving** (POWER/GROUND/PORT only — a SIGNAL net is private wiring and
is never rebound; a SIGNAL key or a collision is a hard `CircuitError`). Because
the rename preserves net insertion order, parts, refs, NCs and port-type
payloads, **binding to the exact names a hand-written sheet used yields a
byte-identical emitted sheet.** The carrier adapter is
`carrier/subsystems/usb_jtag_connector.py`.

### A note on the diff-pair complement

The USB 2.0 HS pair is typed `c.port_type("USB_DP", kind="usb_hs_pair",
pair_with="USB_DM")`. `Circuit.bind()` (applied last by `Meta.finish()`) renames
net + port-type **keys** in place **and** re-points the `pair_with` payload
through the same bind map, so the bound pair's two ends agree. That keeps the
library project-agnostic (it knows only the bind map, never a carrier name) while
the board SI gate — which harvests pairs as `frozenset({net.name, pt.pair_with})`
and joins them to the project's `si_spec.json` — sees the **project** pair
(`{DBG_USB_DP, DBG_USB_DM}`), not a stale abstract one. Standalone (no bind) the
complement stays abstract.

The pair's linker deferral (which of the project's sheets **consumes** the pair)
is likewise a project concern: it defaults to the abstract `CONSUMER` string and
is overridden via `expects["USB_DP"]` (it propagates to both ends of the pair).

## Design notes (datasheet + role contract)

- **VBUS is sunk, not sourced.** This is a USB **device (UFP)** port. The 5 V it
  brings in (`+VBUS`) is the cable host's own supply (an external source); the
  consumer's load is declared on the consuming sheet, so this subsystem declares
  **no draw of its own** — only a `TestPoint` probe on the VBUS rail.
- **Device-role CC termination.** Both CC pins carry a **5.1k Rd** pulldown to
  GND (USB Type-C device spec: Rd = 5.1k ±20%, so a 5% Basic part is correct) —
  **not** a host's 56k Rp. That tells the host to apply VBUS. The CC nets are
  subsystem-internal (terminated at the receptacle); they are not exposed ports.
- **USB-2 flip-pair short.** USB 2.0 on a Type-C device shorts the two
  flip-orientation contacts of each data line (DP1=DP2, DN1=DN2) so the cable
  works either way up.
- **ESD on the data pair (no series R).** The USBLC6-2SC6 passes the pair through
  (1<->6, 3<->4) with TVS clamps to VBUS/GND; the connector-side stubs are
  internal SIGNAL nets, the consumer-side pair is the exposed `USB_DP`/`USB_DM`
  90 ohm differential port. The array is a **SHUNT** — it adds **no series
  element** on the data lines, suiting a consumer whose datasheet forbids a
  series R (e.g. the CH347 UD+/UD-). LAW-0 honoured.
- **SBU / shell.** SBU1/SBU2 are unused on a USB-2.0-only link (author
  no-connects); the shell (EH) bonds to `CHASSIS_GND`.

## Local test vs board gates

`test_usb_jtag_connector.py` runs the **subsystem-local** slices offline:
declared abstract interface, model completeness (every pin netted-or-NC),
decoupling completeness (design_rules DECAP/EP/STRAP), part-rating coverage +
per-rail cap derating, the SPICE-subckt ↔ netlist passive match, and the bind
contract (including the diff-pair-complement re-point and the `expects` pair
deferral). **Cross-board** gates stay aggregated at board level and are *not*
duplicated here: the USB-pair linker graph (the pair binds on the consumer
sheet), the full power-tree headroom, the SI spec join, board ERC and the board
netlist merge — all run by `schgen board`.

```bash
PYTHONPATH=. python3 -m pytest subsystems/usb_jtag_connector/test_usb_jtag_connector.py -q
```
