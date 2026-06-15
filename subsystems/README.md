# subsystems — the reusable subsystem library

Project-agnostic, self-contained schgen subsystems. Each
`subsystems/<name>/` package declares its interface as **abstract** port +
rail names and knows nothing about any board; a consuming project drops it onto
real nets with a thin adapter (e.g. `carrier/subsystems/<name>.py`) that
supplies ONE module-level `META` dict and forwards it:

```python
from subsystems.usb_pd import usb_pd

META = {
    "bind":    {"+VDD_LOGIC": "+3V3_SC", "GND": "GND", "CC1": "MY_CC1", ...},
    "expects": {"I2C_SDA": "my_connector"},   # per-port linker deferral
    "buses":   {"i2c": "MY_I2C_BUS"},         # rename a named bus group
    "notes":   {"draws": "FUSB302B VDD (<1 mA); ..."},  # house-style prose
}

def circuit():
    return usb_pd.circuit(META)
```

## The Meta contract

The adapter ↔ library contract is **`schgen/core/subsystem.py`** (the `Meta`
class). The four standard top-level keys are universal across every package; a
typo'd key is a hard `CircuitError`, never silently dropped:

- **`bind`** `{abstract_net: real_net}` — rename the externally-visible
  POWER/GROUND/PORT nets to a project's real names. Applied last, in
  insertion order, so a SIGNAL net (private wiring) is never rebound and
  **binding to the names a hand-written sheet used yields a byte-identical
  emitted sheet**.
- **`expects`** `{abstract_port: deferral}` — attach an explicit linker
  deferral to a port (the project declares which of its sheets binds it).
- **`buses`** `{role: real_bus_name}` — rename a named bus group (e.g.
  `{"i2c": "STM32_I2C2"}`).
- **`notes`** `{key: prose}` — house-style prose overrides (e.g. the
  power-tree `draws` note) so derived artifacts stay stable.

Standalone (`meta=None`) every accessor returns the library default, so each
package's `test_<name>.py` runs offline against the abstract names.

## Package layout + gate

Every `subsystems/<name>/` carries exactly four artifacts (enforced by the
structure gate `schgen/verify/subsystem_structure.py`, run via
`schgen subsystem-check`):

| file | role |
|------|------|
| `<name>.py`      | the NETLIST — `circuit(meta=None)`, abstract ports/rails, a declared `INTERFACE` |
| `README.md`      | the abstract-interface table + design notes |
| `test_<name>.py` | the offline local-correctness test (board-gate slices on just this subsystem) |
| `<name>.cir`     | the SPICE subckt — the passive network with the abstract ports as subckt pins |

Active parts are **referenced, never vendored** — symbol/footprint/LCSC come
from the global `parts/<MPN>/` dossier. Cross-board gates (link, full SI
constraints, board ERC, board netlist merge, power-tree headroom) stay
aggregated at board level and are not duplicated in the package tests.

Scaffold a new package (writes all four stubs):

```bash
PYTHONPATH=. python3 -m schgen subsystem <name>
PYTHONPATH=. python3 -m schgen subsystem-check     # the structure gate
```

## The library

| package | purpose |
|---------|---------|
| [`camera`](camera/README.md)               | RPi 15-pin FFC, 2-lane MIPI CSI-2 camera port |
| [`ethernet`](ethernet/README.md)           | HX5008NL 1000BASE-T magnetics + Bob-Smith termination |
| [`hdmi_tx`](hdmi_tx/README.md)             | TPD12S016 HDMI source port |
| [`lcd`](lcd/README.md)                     | 40-pin TTL RGB888 panel + SY7201 backlight boost + touch I2C |
| [`microsd`](microsd/README.md)             | TXS02612 microSD slot (1.8 V SoM ↔ 3.3 V card translator) |
| [`pd_input`](pd_input/README.md)           | USB-C PD power inlet (receptacle + TVS + bulk → +VIN) |
| [`pmod`](pmod/README.md)                   | 2× Digilent-standard Pmod host ports |
| [`pmod_expansion`](pmod_expansion/README.md) | manual-gated Digilent Pmod expansion port |
| [`uart_bridge`](uart_bridge/README.md)     | CP2102N USB-to-UART bridge |
| [`usb_jtag`](usb_jtag/README.md)           | CH347T USB-JTAG/UART debug bridge |
| [`usb_pd`](usb_pd/README.md)               | FUSB302B USB Type-C / Power-Delivery sink PHY (the first exemplar) |
| [`usbc_otg`](usbc_otg/README.md)           | USB 2.0 HS OTG port (USB-C receptacle, host-capable) |

Carrier-specific sheets that only make sense for this board (the J1/J2/J3
connectors, power / bring-up / power-monitor, board-services HW, the carrier
connectors) are NOT in this library — they live directly under
`carrier/subsystems/`. See [`carrier/subsystems/README.md`](../carrier/subsystems/README.md).
</content>
