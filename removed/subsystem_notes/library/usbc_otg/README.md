# usbc_otg — USB 2.0 High-Speed OTG port (USB-C receptacle, host-capable)

A project-agnostic, reusable schgen subsystem: a USB Type-C receptacle wired as a
host-capable USB 2.0 High-Speed OTG port. A TPS2051C current-limited switch
sources VBUS, a USBLC6-2SC6 array protects the data pair, 56k CC Rp resistors
advertise default-USB host power, and a 1k strap pulls the OTG ID low for the
host role. It declares its interface as abstract port + rail names and knows
nothing about any board; a consuming project supplies a bind map
(`abstract -> real net`) to drop it onto carrier nets.

## Interface

The subsystem builds with abstract net names. A project consumes it through one
standard `META` dict (`schgen.core.subsystem.Meta`): `bind` rebinds every
externally-visible net to a real board name (in place, order-preserving, so
binding to the names a hand-written sheet used yields a byte-identical sheet),
`expects` attaches per-port linker deferrals, `notes` supplies house-style
power-tree draw prose. With `meta=None` the abstract names stay, so the local
test runs offline.

Rails classify as POWER/GROUND by name (leading `+` = POWER; `GND` /
`CHASSIS_GND` = GROUND), so a standalone build and a bound build share net
classes.

### Rails

| abstract | class | meaning |
|----------|-------|---------|
| `+VBUS_SUPPLY` | POWER  | host VBUS supply feeding the TPS2051C switch IN — the rail the port sources onto the cable, current-limited (0.5 A class). Typically a gated module rail. |
| `+VDD_LOGIC`   | POWER  | 3.3 V-class logic rail for the open-drain FLT# pull-up — keeps FLT# within the downstream reader's IO abs-max and readable when `+VBUS_SUPPLY` is gated OFF. |
| `GND`          | GROUND | ground. |
| `CHASSIS_GND`  | GROUND | receptacle shell / shield bond (chassis earth). |

### Ports

| abstract | type | meaning |
|----------|------|---------|
| `USB_DP`, `USB_DM` | usb_hs_pair (90 ohm diff) | USB 2.0 HS data pair to the system PHY, behind the USBLC6-2SC6 ESD array. |
| `VBUS`             | single | connector VBUS the port sources/senses (TPS2051 OUT + the receptacle VBUS pads; also the CC Rp reference and the ESD VBUS pin). |
| `VBUS_EN`          | single | active-high enable for the VBUS switch (held OFF by a 100k pulldown until the host drives it high). |
| `FLT_N`            | single | open-drain over-current fault flag from the power switch. |
| `USB_ID`           | single | OTG ID, strapped low through 1k = host role for this port. |

### Consuming it from a project

```python
from subsystems.usbc_otg import usbc_otg

META = {
    "bind": {
        "+VBUS_SUPPLY": "+5V_USB", "+VDD_LOGIC": "+3V3_SC",
        "GND": "GND", "CHASSIS_GND": "CHASSIS_GND",
        "USB_DP": "USB_D+", "USB_DM": "USB_D-",
        "VBUS": "USB_VBUS", "VBUS_EN": "VBUS_OUT_EN",
        "FLT_N": "USBOTG_FLT_N", "USB_ID": "USB_ID",
    },
    "expects": {"VBUS_EN": "som_j1 (GPIO function map)",
                "USB_ID":  "som_j1 (GPIO function map)",
                "FLT_N":   "bringup (TCA9535 expander port)"},
    "notes": {"draws_vbus": "downstream USB device budget, ...",
              "draws_flt":  "FLT# 100k pull-up on the logic rail"},
}

def circuit():
    return usbc_otg.circuit(META)
```

The diff pair is typed `c.port_type("USB_DP", kind="usb_hs_pair",
pair_with="USB_DM")`; `meta.finish()` re-points the `pair_with` complement
through the same bind map so the board SI gate sees the project pair
(`{USB_D+, USB_D-}`), not the abstract one. Standalone, the complement stays
abstract. The carrier adapter is `carrier/subsystems/usbc_otg.py`.

## Design

- **VBUS is sourced, not consumed.** This is an OTG host port: the TPS2051C
  (0.5 A-class current-limited switch with thermal/short-circuit protection)
  switches `+VBUS_SUPPLY` onto the cable VBUS. EN is active-high with a 100k
  pulldown (R5) so the port stays OFF at power-on until the host drives
  `VBUS_EN` high — without it EN floats and the port could back-feed 5 V on the
  bus before the OTG role is decided.

- **FLT# pull-up rail.** TPS2051C FLT# is open-drain; its 100k pull-up (R3) sits
  on `+VDD_LOGIC`, not `+VBUS_SUPPLY`. This keeps the flag within a downstream
  reader's IO abs-max and valid (low) even when the VBUS supply is gated OFF.

- **VBUS hold-up.** Bulk = C2 (22uF 0805 MLCC, HF companion) + C3 (100uF/16V
  aluminium electrolytic, RVT1C101M0605). The MLCC alone derates to ~15–20uF at
  5 V bias — below the USB 2.0 host minimum / TPS2051C reference — so a device
  hot-plug could droop VBUS below 4.4 V. The electrolytic does not bias-derate,
  so it carries the bulk. C3 pad 1 = + (VBUS), pad 2 = − (GND). C1 (100n) is the
  TPS2051 IN bypass per datasheet.

- **CC host advertising.** Two 56k Rp (R1, R2) from the sourced VBUS to CC1/CC2
  advertise default USB host current per USB Type-C. The CC nets terminate at the
  receptacle and are not exposed ports.

- **OTG ID = host.** `USB_ID` is strapped low through 1k (R4) = host role for
  this port. A dual-role / device port lives elsewhere on the board.

- **ESD on the data pair.** The USBLC6-2SC6 (U2) passes the pair through (1↔6,
  3↔4) with TVS clamps to VBUS/GND; the connector-side stubs are internal SIGNAL
  nets, the PHY-side pair is the exposed `USB_DP`/`USB_DM` 90 ohm differential
  port. SBU1/SBU2 are unused on a USB-2.0-only port and are explicit author
  no-connects on J2.

- **Power-tree budget.** The port draws one downstream USB 2.0 device budget
  (500 mA) on `+VBUS_SUPPLY` through the TPS2051C; the FLT# pull-up draws ~0.5 mA
  on `+VDD_LOGIC`. `VBUS_EN` is a coverage testpoint.

## Parts

| ref | value | lib / part | LCSC |
|-----|-------|-----------|------|
| J2 | TYPE-C-31-M-12 | `parts/TYPE-C-31-M-12` (USB-C receptacle) | — |
| U1 | TPS2051CDBVR   | `parts/TPS2051CDBVR` (current-limited power switch) | — |
| U2 | USBLC6-2SC6    | `parts/USBLC6-2SC6` (USB ESD array) | — |
| C1 | 100n | `Device:C` (TPS2051 IN bypass) | C14663 |
| C2 | 22u  | `Device:C` (VBUS bulk MLCC, 0805) | C45783 |
| C3 | 100u | `parts/RVT1C101M0605_100UF_16V` (VBUS bulk electrolytic, 16V) | — |
| R1, R2 | 56k | `Device:R` (CC host-advertising Rp) | C23206 |
| R3 | 100k | `Device:R` (FLT# pull-up) | C25803 |
| R4 | 1k   | `Device:R` (OTG-ID host strap) | C21190 |
| R5 | 100k | `Device:R` (EN default-OFF pulldown) | C25803 |

(LCSC for the referenced `parts/` actives is carried in their own part
definitions, not in `usbc_otg.py`.)

## Build & test

`test_usbc_otg.py` runs the subsystem-local slices offline: declared abstract
interface, model completeness, decoupling completeness, part-rating + per-rail
cap derating, the SPICE-subckt ↔ netlist passive match, and the bind contract
(including the diff-pair-complement re-point). Cross-board gates (EN/FLT linker
graph, full power-tree headroom, SI spec join, board ERC, netlist merge) run at
board level via `schgen board`.

```bash
PYTHONPATH=. python3 -m pytest subsystems/usbc_otg/test_usbc_otg.py -q
```
