# usb_uart_connector — USB-C UFP receptacle + ESD for a USB-UART side

A project-agnostic, reusable schgen subsystem: a USB Type-C receptacle wired as a
USB 2.0 device-role (UFP) port that feeds a downstream USB-UART bridge over an
ESD-protected data pair. On the Zynq-7000 SoM carrier it is the connector half of
the USB-UART console link — it presents the cable's VBUS/data to a peer bridge
subsystem. It declares its interface as abstract port + rail names and knows
nothing about any board; a consuming project supplies a bind map to drop it onto
real nets.

## Interface

The subsystem (`circuit(meta=None)`) exposes abstract net names that a consuming
project rebinds through the standard `Meta` adapter contract
(`schgen.core.subsystem`). Standalone (`meta=None`) the abstract names are kept so
the local test runs offline.

Rails (GROUND, classified by name):

| abstract | meaning |
|----------|---------|
| `GND`         | ground — receptacle GND pads, ESD GND ref, CC Rd returns, VBUS bulk return |
| `CHASSIS_GND` | receptacle shell / shield bond (chassis earth), all shell pads via `J1.EH` |

Ports (PORT):

| abstract | type | meaning |
|----------|------|---------|
| `VBUS`             | single | receptacle 5 V VBUS presented to a downstream bridge's VBUS-sense (also the ESD array VBUS clamp ref + the 10u bulk). A PORT, not a sourced rail: a UFP/device port sinks VBUS, it does not source it. |
| `USB_DP`, `USB_DM` | usb_hs_pair (90 ohm diff) | USB 2.0 HS data pair, behind the USBLC6-2SC6 ESD array, to the bridge's USB data pins. Typed `c.port_type("USB_DP", kind="usb_hs_pair", pair_with="USB_DM")`. |

A project binds it with one standard `META` dict and forwards it:

```python
from subsystems.usb_uart_connector import usb_uart_connector

META = {
    "bind": {
        "GND": "GND", "CHASSIS_GND": "CHASSIS_GND",
        "VBUS": "USB_UART_VBUS",
        "USB_DP": "USB_UART_DP", "USB_DM": "USB_UART_DM",
    },
}

def circuit():
    return usb_uart_connector.circuit(META)
```

`bind` renames every external net in place, order-preserving, so binding to the
exact names a hand-written sheet uses yields a byte-identical emitted sheet.
`Circuit.bind()` also re-points the `pair_with` payload through the same map, so a
board build sees the project pair (`{USB_UART_DP, USB_UART_DM}`) in the SI gate;
standalone the complement stays abstract. The contract also accepts an optional
`expects` map (`{port: deferral}`) to attach an explicit linker deferral to a
port; the carrier omits it because this connector PRODUCES the three USB nets and
the peer bridge sheet defers TO it. The carrier adapter is
`carrier/subsystems/usb_uart_connector.py`.

## Design

- Device-role (UFP) Type-C. The receptacle is wired as a USB 2.0 device port. Two
  5.1k Rd pulldowns to GND on CC1/CC2 advertise the device role: the source's Rp
  plus our Rd form the attach divider that tells the source to apply VBUS — not a
  host port's 56k Rp. One Rd per CC pin per the USB Type-C spec; Rd is spec'd at
  5.1k +/-20%, so a 5% JLC Basic part is correct. The CC nets terminate at the Rd
  and are subsystem-internal, not ports.
- VBUS is sensed, not sourced. As a device port it draws power from the host's
  VBUS, so `VBUS` is exposed as a PORT (not a sourced rail). Both stacked VBUS pads
  net together to the ESD array VBUS clamp ref (`U1.5`), the exposed port, and a
  10u bulk/bypass (`C1`, the USB-C UFP `Cbus` decoupling) — the only passive on
  VBUS. The sheet adds no `+3V3`/`+5V` load to the consuming board's power tree.
- USB 2.0 flip pairs. USB 2.0 on a Type-C device shorts the two flip-orientation
  contacts of each data line (`DP1=DP2`, `DN1=DN2`) so the cable works either
  orientation; each shorted pair then passes through the ESD array.
- ESD on the data pair. The port mates an external cable, so the data pair runs
  through a USBLC6-2SC6 low-capacitance TVS/diode array (1<->6, 3<->4 passthrough):
  connector-side DP/DM on `U1.1`/`U1.3`, the protected pair on `U1.6`/`U1.4` (the
  exposed `USB_DP`/`USB_DM` 90 ohm differential port), VBUS clamp ref on `U1.5`,
  GND on `U1.2`. The connector-side stubs are internal SIGNAL nets.
- Shield and unused. The receptacle shell pads bond to `CHASSIS_GND`; both stacked
  GND pads to `GND`. SBU1/SBU2 are unused on a USB-2.0-only console and are
  explicit author no-connects.

Active parts are referenced from the global `parts/` lib via `use_part()`, never
vendored, and connected by pin name.

## Parts

| ref | value | lib / part | LCSC |
|-----|-------|-----------|------|
| J1 | TYPE-C-31-M-12 | `parts/TYPE-C-31-M-12/` (USB-C receptacle) | C165948 |
| U1 | USBLC6-2SC6 | `parts/USBLC6-2SC6/` (USB ESD array) | C7519 |
| C1 | 10u | `Device:C` (VBUS bulk, 0805) | C15850 |
| R1 | 5.1k | `Device:R` (CC1 device-role Rd pulldown, 0603) | C23186 |
| R2 | 5.1k | `Device:R` (CC2 device-role Rd pulldown, 0603) | C23186 |

## Build & test

`test_usb_uart_connector.py` runs the subsystem-local slices offline: declared
abstract interface, model completeness (every pin netted-or-NC), device-role
wiring (Rd pulldowns / flip-pair short / VBUS bulk / SBU NCs), decoupling
completeness, part-rating coverage + per-rail cap derating, the SPICE-subckt ↔
netlist passive match, and the bind contract.

```bash
PYTHONPATH=. python3 -m pytest subsystems/usb_uart_connector/test_usb_uart_connector.py -q
```
