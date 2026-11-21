# usb_jtag_connector — USB-C UFP debug receptacle + ESD

A project-agnostic, reusable schgen subsystem: a USB Type-C receptacle
(TYPE-C-31-M-12) wired as a USB 2.0 device-role (UFP) debug port. A USBLC6-2SC6
ESD array protects the data pair, 5.1k Rd pulldowns on both CC pins advertise the
device role so the host applies VBUS, and a 10u bulk cap bypasses the receptacle
VBUS. It is the connector half of the usb_jtag debug bridge on the Zynq-7000 SoM
carrier: a USB-C cable plugged here supplies the downstream CH347T bridge over its
own 5 V VBUS and a protected USB 2.0 HS data pair, on its own sheet so neither the
connector nor the consumer sheet gets dense.

The subsystem declares its interface as abstract port + rail names and knows
nothing about any board; a consuming project supplies a `bind` map
(`abstract -> real net`) to drop it onto real carrier nets.

## Interface

A consuming project supplies one standard `META` dict (the adapter contract,
`schgen.core.subsystem.Meta`) and forwards it to `circuit()`. Rails classify as
POWER/GROUND by name (a leading `+` = POWER; `GND` / `CHASSIS_GND` = GROUND), so a
standalone build and a bound build share net classes.

### Rails (POWER / GROUND)

| abstract | class | meaning / constraint |
|----------|-------|----------------------|
| `+VBUS`       | POWER  | receptacle 5 V VBUS, also the USBLC6 VBUS clamp ref. A POWER rail so it merges by name onto the downstream consumer's supply input. The port sinks this 5 V (the cable host's own supply); it does not source it. |
| `GND`         | GROUND | ground. |
| `CHASSIS_GND` | GROUND | receptacle shell / shield bond (chassis earth). |

### Ports (PORT)

| abstract | type | meaning |
|----------|------|---------|
| `USB_DP`, `USB_DM` | usb_hs_pair (90 ohm diff) | USB 2.0 HS data pair to the downstream consumer, behind the USBLC6-2SC6 ESD array. |

SBU1/SBU2 are unused on a USB-2.0-only debug link and are explicit author
no-connects on `J1`. The CC nets are subsystem-internal (the Rd pulldowns
terminate them at the receptacle); they are not exposed ports.

### Binding from a project

```python
from subsystems.usb_jtag_connector import usb_jtag_connector

META = {
    "bind": {
        "+VBUS": "+5V_DBG",
        "GND": "GND",
        "CHASSIS_GND": "CHASSIS_GND",
        "USB_DP": "DBG_USB_DP",
        "USB_DM": "DBG_USB_DM",
    },
    # optional: tell the linker which sheet consumes the USB pair
    "expects": {"USB_DP": "usb_jtag (CH347T bridge)"},
}

def circuit():
    return usb_jtag_connector.circuit(META)
```

`bind` renames every external net in place, order-preserving (POWER/GROUND/PORT
only — a SIGNAL net is private wiring and is never rebound; a SIGNAL key or a
collision is a hard `CircuitError`). The rename preserves net insertion order,
parts, refs, NCs and port-type payloads, so the emitted sheet depends only on the
chosen names. The carrier adapter is `carrier/subsystems/usb_jtag_connector.py`.
With `meta=None` the abstract names are kept so the local test runs offline.

The USB 2.0 HS pair is typed `port_type("USB_DP", kind="usb_hs_pair",
pair_with="USB_DM")`. `Circuit.bind()` (applied last by `Meta.finish()`) renames
the net and port-type keys in place and re-points the `pair_with` payload through
the same bind map, so the bound pair's two ends agree and the board SI gate sees
the project pair (`{DBG_USB_DP, DBG_USB_DM}`). The pair's linker deferral (which
sheet consumes the pair) defaults to the abstract `CONSUMER` string and is
overridden via `expects["USB_DP"]`.

## Design

- **Device-role (UFP) Type-C.** Both CC pins carry a 5.1k Rd pulldown to GND (USB
  Type-C device spec: Rd = 5.1k ±20%, so a 5% part is correct) — not a host's 56k
  Rp. This advertises a device and tells the host to apply VBUS.
- **VBUS is sunk, not sourced.** The 5 V brought in on `+VBUS` is the cable host's
  own supply (an external source); the consumer's load is declared on the consuming
  sheet, so this subsystem declares no draw of its own — only a `TestPoint` probe
  on the VBUS rail. A 10u 0805 bulk cap bypasses VBUS at the receptacle.
- **USB-2 flip-pair short.** USB 2.0 on a Type-C device shorts the two
  flip-orientation contacts of each data line (DP1=DP2, DN1=DN2) so the cable works
  in either orientation.
- **ESD on the data pair, no series element.** The port mates an external cable, so
  the data pair runs through a USBLC6-2SC6 low-capacitance array in the 1↔6 / 3↔4
  pass-through idiom: connector-side DP/DM on U1.1/U1.3, the protected pair (to the
  consumer) on U1.6/U1.4, the VBUS clamp ref on U1.5 (≤5.25 V), GND on U1.2. The
  USBLC6 is a SHUNT array, so it adds no series element on the data lines — only the
  ~3.5 pF clamp tap, suiting a consumer whose datasheet forbids a series R on the
  data lines (e.g. the CH347 UD+/UD-). LAW-0 honoured.
- **Shell / unused.** The shell (EH, all four pads) bonds to `CHASSIS_GND`; both
  stacked GND pads go to `GND`; SBU1/SBU2 are author no-connects.

Active parts are referenced, never vendored: the TYPE-C-31-M-12 receptacle and
USBLC6-2SC6 array come from the global `parts/` lib via `use_part()`, connected by
pin name (`J1.VBUS` nets both stacked VBUS pads, exactly like the symbol).

## Parts

| ref | value | lib / part | LCSC |
|-----|-------|-----------|------|
| J1     | TYPE-C-31-M-12 | `parts/TYPE-C-31-M-12/` (USB-C receptacle) | C165948 |
| U1     | USBLC6-2SC6    | `parts/USBLC6-2SC6/` (USB ESD array)       | C7519   |
| C1     | 10u            | `Device:C` (VBUS bulk, 0805)               | C15850  |
| R1, R2 | 5.1k           | `Device:R` (USB device-role Rd pulldown, 0603) | C23186 |
| TP1    | +VBUS          | `Connector:TestPoint` (VBUS probe)         | —       |

## Build & test

`test_usb_jtag_connector.py` runs the subsystem-local slices offline: declared
abstract interface, model completeness (every pin netted-or-NC), decoupling
completeness, part-rating + per-rail cap derating, the SPICE-subckt ↔ netlist
passive match, and the bind contract (diff-pair-complement re-point and the
`expects` pair deferral). Cross-board gates (the USB-pair linker graph, full
power-tree headroom, SI spec join, board ERC and the netlist merge) run at board
level via `schgen board`, not here.

```bash
PYTHONPATH=. python3 -m pytest subsystems/usb_jtag_connector/test_usb_jtag_connector.py -q
```
