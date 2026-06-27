# usb_pd — FUSB302B USB Type-C / Power-Delivery sink PHY

A project-agnostic, self-contained schgen subsystem providing the onsemi
FUSB302BMPX USB Type-C / PD sink front-end with its datasheet bypass network and
CC analog filters. It is the PD controller for a Type-C receptacle: it owns CC
termination and BMC framing and negotiates the VBUS contract, while a host MCU
drives policy over I2C. It declares its interface as abstract port + rail names
and knows nothing about any board; a consuming project supplies a bind map
(`abstract -> real net`) to drop it onto real nets.

## Interface

A consuming project supplies one standard `META` dict (the adapter contract,
`schgen.core.subsystem.Meta`) and forwards it to `circuit(meta)`. Rails classify
as POWER/GROUND by name (the `+` prefix + `GND`), so a standalone build and a
bound build share net classes. With `meta=None` the abstract names are kept so
the local test runs offline.

### Rails (POWER / GROUND)

| abstract | class | meaning / constraint |
|----------|-------|----------------------|
| `+VDD_LOGIC`  | POWER  | FUSB302B VDD logic supply (3.3 V class). Must be always-on, existing before PD negotiation — the PHY brings the 20 V in, so it cannot depend on a rail it creates. |
| `+VBUS_SENSE` | POWER  | raw receptacle VBUS for the VBUS-sense pin (U1.2), taken ahead of any inlet eFuse so the PHY observes vSafe5V/vbus at the connector for attach detection. Worst case 21.0 V (20 V contract +5%); pin abs-max 28 V. |
| `GND`         | GROUND | ground. |

### Ports (PORT)

| abstract | type | meaning |
|----------|------|---------|
| `CC1`, `CC2`         | single | Type-C CC lines to the receptacle. The FUSB302B owns Rd/Rp, vRd sensing, the BMC PHY and VCONN switching on these. 200p analog filter caps to GND live in this subsystem. |
| `I2C_SDA`, `I2C_SCL` | i2c (bus `USB_PD_I2C`, 400 kHz) | control bus to the host MCU; PHY is slave 0x22. Open-drain — bus pull-ups are shared and live once on the bus, never here. |
| `INT_N`              | single | open-drain interrupt to the host MCU (wire-OR shareable). Its pull-up is shared and lives once on the net, never here. |

### Binding from a project

```python
from subsystems.usb_pd import usb_pd

META = {
    # abstract subsystem net -> real board net
    "bind": {
        "+VDD_LOGIC": "+3V3_SC", "+VBUS_SENSE": "+VBUS_IN", "GND": "GND",
        "CC1": "MY_CC1", "CC2": "MY_CC2",
        "I2C_SDA": "MY_SDA", "I2C_SCL": "MY_SCL", "INT_N": "MY_INT_N",
    },
    # optional: tell the linker which sheets will bind a deferred port
    "expects": {"I2C_SDA": "my_connector", "I2C_SCL": "my_connector",
                "INT_N": "my_connector"},
    # optional house-style overrides (keep derived artifacts byte-stable)
    "buses": {"i2c": "MY_I2C_BUS"},                   # I2C bus-group name
    "notes": {"draws": "FUSB302B VDD (<1 mA); ..."},  # power-tree draw note
}

def circuit():
    return usb_pd.circuit(META)
```

The four `META` keys (`bind` / `expects` / `buses` / `notes`) are all optional.
`bind` renames every external net in place, order-preserving (POWER/GROUND/PORT
only); a SIGNAL key, a collision, or a typo'd top-level key is a hard
`CircuitError`. Because the rename preserves net insertion order, parts, refs,
NCs and port-type payloads, binding to the names a hand-written sheet used yields
a byte-identical emitted sheet. The carrier adapter is
`carrier/subsystems/usb_pd.py`.

## Design

- **FUSB302BMPX part.** The onsemi FUSB302B is a full USB-C / PD PHY: it
  integrates Rd/Rp termination, vRd CC sensing, the BMC physical layer, and a
  VCONN switch, exposing PD policy to a host MCU over I2C (slave 0x22, 400 kHz)
  plus an open-drain interrupt. This offloads all CC/BMC analog and timing from
  the MCU, which needs only the I2C link and the interrupt. The sheet draws the
  stock `Interface_USB:FUSB302BMPX` symbol via a `use_part(lib_id=...)` override
  so the WQFN-14+EP drawing and footprint stay faithful, while the MPN / LCSC /
  datasheet source from `parts/FUSB302BMPX/`.

- **Always-on VDD.** `+VDD_LOGIC` must be a 3.3 V-class rail that exists before
  PD negotiation: the PHY brings the 20 V contract in, so it cannot depend on a
  rail it creates. It must therefore sit on an always-on system rail, never a
  gated module rail that PD would have to bring up first.

- **Pre-eFuse VBUS sense.** The VBUS-sense pin (U1.2) must observe the raw
  connector VBUS for attach detection, ahead of any inlet eFuse. At the legal
  20 V +5% contract U1.2 sits at its 21.0 V worst case, which stays under the
  28 V abs-max of the pin, so a normal PD contract has no over-voltage corner.

- **The PHY owns CC.** CC1/CC2 belong entirely to the FUSB302B — it provides
  Rd/Rp termination, vRd sensing, BMC framing and VCONN switching on them, and
  reports state to the host MCU over I2C (0x22) + INT_N. The MCU drives PD policy
  through that I2C link only and must not terminate or frame these lines itself.
  Each CC line carries a 200p NP0 cap to GND for analog noise rejection.

- **Bypass network.** Datasheet decoupling: VDD (U1.3) is bypassed 100n + 10u
  (C1/C2) for HF and bulk; the VBUS-sense node (U1.2) carries a 100n (C3).

- **VCONN unused.** VCONN sourcing is unused by design — both VCONN pins
  (U1.12/U1.13) are explicit author no-connects.

- **One pull-up per net.** SDA/SCL and INT_N are open-drain; their pull-ups are
  shared with the rest of the bus and live once, off this subsystem. None are
  placed here, so the local test does not enforce the I2C-pull-up rule — that
  completeness is a board-level gate.

- **Stacked pins.** The stock WQFN-14+EP symbol stacks duplicate pads — VDD
  (3/4), GND/EP (8/9/15), CC1 (10/11), CC2 (1/14). Each duplicate is declared on
  the same net as its twin; the netlist gate proves KiCad sees all of them.

## Parts

| ref | value | lib / part | LCSC |
|-----|-------|-----------|------|
| U1 | FUSB302BMPX | `Interface_USB:FUSB302BMPX` (`parts/FUSB302BMPX/`) | C132291 |
| C1 | 100n | `Device:C` (VDD bypass)  | C14663 |
| C2 | 10u  | `Device:C` (VDD bulk)    | C15850 |
| C3 | 100n | `Device:C` (VBUS-sense)  | C14663 |
| C4 | 200p | `Device:C` (CC1 filter)  | C113796 |
| C5 | 200p | `Device:C` (CC2 filter)  | C113796 |

## Build & test

`test_usb_pd.py` runs the subsystem-local slices offline: abstract interface,
model completeness, decoupling completeness, part-rating coverage + per-rail cap
derating, the SPICE-subckt ↔ netlist passive match, and the bind contract.

```bash
PYTHONPATH=. python3 -m pytest subsystems/usb_pd/test_usb_pd.py -q
```
