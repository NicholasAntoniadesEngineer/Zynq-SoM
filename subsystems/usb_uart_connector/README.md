# usb_uart_connector — USB-C UFP (device) receptacle + ESD reusable subsystem

A project-agnostic, self-contained schgen subsystem: a **USB Type-C receptacle**
(TYPE-C-31-M-12) wired as a USB 2.0 **device-role (UFP)** port that supplies a
downstream USB-UART bridge over a **USBLC6-2SC6**-protected data pair. Two 5.1k
**Rd** pulldowns advertise the device role on CC1/CC2, the receptacle VBUS is
brought out with a 10u bulk to a peer bridge's VBUS-sense, and the data pair is
ESD-protected. It declares its interface as **abstract** port + rail names and
knows nothing about any board; a consuming project supplies a **bind map**
(`abstract -> real net`) to drop it onto real nets.

## Package contents

| file | role |
|------|------|
| `usb_uart_connector.py`      | the NETLIST — `circuit(meta=None)`, abstract ports/rails |
| `usb_uart_connector.cir`     | SPICE subckt — the passive network with the abstract ports as subckt pins |
| `test_usb_uart_connector.py` | LOCAL electrical-correctness test (offline, runs the board gate slices on just this subsystem) |
| `README.md`                  | this file |

Active parts are **referenced, never vendored**: the TYPE-C-31-M-12 and
USBLC6-2SC6 symbols/footprints/LCSC come from the global `parts/` lib via
`use_part()`, connected by pin **name** (`J1.VBUS` nets both stacked VBUS pads,
exactly like the symbol).

## The abstract interface (the reuse contract)

A consuming project binds these names. Grounds classify by name (`GND` /
`CHASSIS_GND` = GROUND); the ports are declared with `c.port(...)`.

### Rails (GROUND)

| abstract | class | meaning / constraint |
|----------|-------|----------------------|
| `GND`         | GROUND | ground — receptacle GND pads, ESD GND ref, CC Rd returns, VBUS bulk return. |
| `CHASSIS_GND` | GROUND | receptacle shell / shield bond (chassis earth). |

### Ports (PORT)

| abstract | type | meaning |
|----------|------|---------|
| `VBUS`             | single | the receptacle 5 V VBUS the port presents to a downstream bridge's VBUS-sense (also the ESD array VBUS clamp ref + the 10u bulk). A **PORT, not a sourced rail** — this is a UFP/device port: it **sinks**, it does not source VBUS. |
| `USB_DP`, `USB_DM` | usb_hs_pair (90 ohm diff) | USB 2.0 HS data pair, behind the USBLC6-2SC6 ESD array, to the bridge's USB data pins. |

SBU1/SBU2 are unused on a USB-2.0-only console → both are explicit author
no-connects on the receptacle (`J1`).

### Parts (from the global `parts/` lib + inline passives)

| ref | value | lib / part | LCSC |
|-----|-------|-----------|------|
| J1 | TYPE-C-31-M-12 | `parts/TYPE-C-31-M-12/` (USB-C receptacle) | C165948 |
| U1 | USBLC6-2SC6    | `parts/USBLC6-2SC6/` (USB ESD array) | C7519 |
| C1 | 10u  | `Device:C` (VBUS bulk, 0805 25V) | C15850 |
| R1, R2 | 5.1k | `Device:R` (CC device-role Rd pulldown) | C23186 |

## Consuming it from a project

A project supplies a thin adapter declaring ONE standard `META` dict (the adapter
contract, `schgen.core.subsystem.Meta`) and forwards it:

```python
from subsystems.usb_uart_connector import usb_uart_connector

META = {
    # abstract subsystem net -> your real board net
    "bind": {
        "GND": "GND", "CHASSIS_GND": "CHASSIS_GND",
        "VBUS": "USB_UART_VBUS",
        "USB_DP": "USB_UART_DP", "USB_DM": "USB_UART_DM",
    },
    # optional: tell the linker which of your sheets binds a deferred port
    # (here the peer USB-UART bridge sheet binds the three USB nets)
    "expects": {"VBUS":   "uart_bridge (USB-UART side)",
                "USB_DP": "uart_bridge (USB-UART side)",
                "USB_DM": "uart_bridge (USB-UART side)"},
}

def circuit():
    return usb_uart_connector.circuit(META)
```

The four standard `META` keys (`bind` / `expects` / `buses` / `notes`) are
universal across every reusable subsystem — a typo'd top-level key is a hard
`CircuitError`, never silently dropped. `bind` renames every external **in place,
order-preserving** (POWER/GROUND/PORT only — a SIGNAL net is private wiring and
is never rebound; a SIGNAL key or a collision is a hard `CircuitError`). Because
the rename preserves net insertion order, parts, refs, NCs and port-type
payloads, **binding to the exact names a hand-written sheet used yields a
byte-identical emitted sheet.** The carrier adapter is
`carrier/subsystems/usb_uart_connector.py`.

### A note on the peer pair

This connector is one half of a USB-UART link: its `VBUS` / `USB_DP` / `USB_DM`
ports are **the exact net names** a peer bridge subsystem (e.g. the carrier's
`uart_bridge`) binds for its USB side, so the two sheets join those nets at link
time. The adapter declares the peer sheet as the `expects` deferral, so a
standalone link reports the three USB nets as *awaiting the bridge sheet* rather
than as silent opens.

### A note on the diff-pair complement

The USB 2.0 HS pair is typed `c.port_type("USB_DP", kind="usb_hs_pair",
pair_with="USB_DM")`. `Circuit.bind()` renames the net + port-type **keys** in
place **and** re-points the `pair_with` **payload** through the same map, so a
board build that binds the pair to the project nets sees the **project** pair
(`{USB_UART_DP, USB_UART_DM}`) in the SI gate — which harvests pairs as
`frozenset({net.name, pt.pair_with})` and joins them to `si_spec.json`.
Standalone (no bind) the complement stays abstract (`{USB_DP, USB_DM}`).

## Design notes (datasheet + role contract)

- **VBUS is sensed, not sourced.** This is a USB **device (UFP)** port: it draws
  power from the host's VBUS. `VBUS` is exposed as a PORT (not a sourced rail) so
  a downstream bridge can sense cable-attach through its own self-powered
  divider; a 10u bulk/bypass on the receptacle VBUS (USB-C UFP `Cbus`) is the
  only passive on it here.
- **Device-role CC (Rd, not Rp).** Two **5.1k Rd** pulldowns to GND on CC1/CC2 =
  USB **device/UFP** role. The source's Rp + our Rd form the attach divider that
  tells the source to apply VBUS — **not** a host port's 56k Rp. One Rd per CC
  pin per the USB Type-C spec (5.1k +/-20%, so a 5% Basic part is correct). The
  CC nets are subsystem-internal (terminated at the Rd); they are not ports.
- **USB 2.0 flip pairs.** USB 2.0 on a Type-C device shorts the two
  flip-orientation contacts of each data line (DP1=DP2, DN1=DN2) so the cable
  works either way up; each shorted pair then passes through the ESD array.
- **ESD on the data pair.** The USBLC6-2SC6 passes the pair through (1<->6,
  3<->4) with TVS clamps to VBUS/GND; the connector-side stubs are internal
  SIGNAL nets, the protected pair is the exposed `USB_DP`/`USB_DM` 90 ohm
  differential port.
- **No board draw.** A UFP/device port **sinks** — it does not source VBUS — so
  this sheet adds no `+3V3`/`+5V` load to a consuming board's power tree (the
  Rd's pull the source's CC; a downstream bridge's own divider senses VBUS).

## Local test vs board gates

`test_usb_uart_connector.py` runs the **subsystem-local** slices offline:
declared abstract interface, model completeness (every pin netted-or-NC),
device-role wiring (Rd pulldowns / flip-pair short / VBUS bulk / SBU NCs),
decoupling completeness (design_rules DECAP/EP/STRAP), part-rating coverage +
per-rail cap derating, the SPICE-subckt ↔ netlist passive match, and the bind
contract (including the diff-pair-complement re-point). **Cross-board** gates
stay aggregated at board level and are *not* duplicated here: the peer-bridge
linker graph (the three USB nets deferred onto the bridge sheet), the full
power-tree headroom, the SI spec join, board ERC and the board netlist merge —
all run by `schgen board`.

```bash
PYTHONPATH=. python3 -m pytest subsystems/usb_uart_connector/test_usb_uart_connector.py -q
```
