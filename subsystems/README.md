# subsystems — the reusable subsystem library

Project-agnostic, self-contained schgen subsystems. Each
`subsystems/<name>/` package declares its interface as **abstract** port and
rail names and knows nothing about any board: no carrier net names, no reads of
`carrier/nets.py` or `som_interface.json`. A consuming project drops the
subsystem onto its real nets with a thin adapter (e.g.
`carrier/subsystems/<name>.py`) that declares ONE module-level `META` dict and
forwards it to the library's `circuit(meta)`:

```python
from subsystems.usb_pd import usb_pd

META = {
    "bind":    {"+VDD_LOGIC": "+3V3_SC", "GND": "GND",
                "CC1": "USB_PD_CC1", "CC2": "USB_PD_CC2"},
    "expects": {"CC1": "usb_pd_connector"},     # per-port linker deferral
    "buses":   {"i2c": "STM32_I2C2"},           # rename a named bus group
    "notes":   {"draws": "FUSB302B VDD (<1 mA); ..."},  # house-style prose
}

def circuit():
    return usb_pd.circuit(META)
```

Called with `meta=None` (standalone) the library keeps its abstract names, so
each package's `test_<name>.py` runs offline against the abstract interface.

## The Meta contract

The adapter ↔ library contract is **`schgen/core/subsystem.py`** (the `Meta`
class). A `META` dict has exactly four legal top-level keys, all optional; any
other key is a hard `CircuitError`, so a typo like `"bus"` for `"buses"` can
never be silently dropped. Every value must be a `{str: str}` mapping.

- **`bind`** `{abstract_net: real_net}` — rename the externally-visible
  POWER / GROUND / PORT nets (a subsystem's rails and ports) to the project's
  real net names. Applied LAST, via `Meta.finish(c)` → `Circuit.bind`.
- **`expects`** `{abstract_port: deferral}` — attach an explicit linker
  deferral string to a port, declaring which of the project's other sheets
  will supply that net. Splatted into the port via `Meta.expect_kw(port)`.
- **`buses`** `{role: real_bus_name}` — rename a named bus group (e.g.
  `{"i2c": "STM32_I2C2"}`) so a board can place the subsystem on one of its own
  named buses. Read by the library via `Meta.bus(role, default)`.
- **`notes`** `{key: prose}` — house-style prose overrides (e.g. the
  power-tree `draws` note) so a project's derived artifacts stay byte-stable.
  Read by the library via `Meta.note(key, default)`.

### bind: rules and the byte-identical guarantee

`bind` is the binding half of the reuse contract, enforced by `Circuit.bind`:

- **Only externals are bindable.** POWER, GROUND and PORT nets are the
  subsystem's edge. A SIGNAL net is the subsystem's private internal wiring and
  is never renamed; a SIGNAL key in the map is a hard error.
- **A typo is a hard error.** An abstract name not present on the circuit
  raises `CircuitError` rather than passing silently. A binding may be the
  identity (`abstract == real`), and a project may bind a subset (unbound
  externals keep their abstract names).
- **No collisions.** Two distinct externals may not bind onto one real net
  (that would silently merge two nets — a LAW-0 short), and a bind target may
  not collide with an existing un-renamed net of a different name.
- **Byte-identical.** The rename is in place and order-preserving: the `nets`
  dict is rebuilt with the new keys in the same insertion order, and parts,
  refs, NCs, pins, port-type payloads and draw budgets are untouched. Binding
  the abstract names to the exact net names a hand-written sheet used yields a
  byte-for-byte identical emitted sheet.

## Package layout and the structure gate

Every `subsystems/<name>/` carries exactly four artifacts, enforced by the
structure gate `schgen/verify/subsystem_structure.py`:

| file | role |
|------|------|
| `<name>.py`      | the netlist — `circuit(meta=None)` with abstract ports/rails and a declared `INTERFACE = RAILS + PORTS` |
| `README.md`      | the abstract-interface table and design notes |
| `test_<name>.py` | the offline local-correctness test (gate slices on just this subsystem) |
| `<name>.cir`     | the SPICE subckt — the passive network with the abstract ports as subckt pins |

Active parts are **referenced, never vendored**: symbol, footprint and LCSC
come from the global `parts/<MPN>/` dossier (or a deliberate stock-symbol
override declared in the library file). Cross-board gates (link, full SI
constraints, board ERC, board netlist merge, power-tree headroom) stay
aggregated at board level and are not duplicated in the package tests.

Scaffold a new package (writes all four stubs), then run the gate:

```bash
PYTHONPATH=. python3 -m schgen subsystem <name>
PYTHONPATH=. python3 -m schgen subsystem-check
```

## The library

| package | purpose |
|---------|---------|
| [`camera`](camera/README.md)                         | RPi 15-pin FFC, 2-lane MIPI CSI-2 camera port |
| [`ethernet`](ethernet/README.md)                     | HX5008NL 1000BASE-T magnetics + Bob-Smith termination |
| [`hdmi_rx`](hdmi_rx/README.md)                       | HDMI sink port (low-cap TMDS RX ESD + EDID EEPROM) |
| [`hdmi_tx`](hdmi_tx/README.md)                       | TPD12S016 HDMI source port |
| [`lcd`](lcd/README.md)                               | 40-pin TTL RGB888 panel + SY7201 backlight boost + touch I2C |
| [`microsd`](microsd/README.md)                       | TXS02612 microSD slot (1.8 V SoM ↔ 3.3 V card translator) |
| [`pd_input`](pd_input/README.md)                     | USB-C PD power inlet (receptacle + TPS26631 eFuse → +VIN) |
| [`pmod`](pmod/README.md)                             | 2× Digilent-standard Pmod host ports |
| [`pmod_expansion`](pmod_expansion/README.md)         | manual-gated Digilent Pmod expansion port |
| [`power`](power/README.md)                           | +VIN → +5V buck (LM61460) → +3V3 buck (LM61460) → +1V8 LDO (AP2112K), each rail with an enable port and a power-good LED |
| [`rj45_connector`](rj45_connector/README.md)         | RJ45 jack (line-side MDI pairs + housing LEDs) |
| [`uart_bridge`](uart_bridge/README.md)               | CP2102N USB-to-UART bridge |
| [`usb_jtag`](usb_jtag/README.md)                     | CH347T USB-JTAG/UART debug bridge |
| [`usb_jtag_connector`](usb_jtag_connector/README.md) | USB-C UFP debug receptacle + ESD (for `usb_jtag`) |
| [`usb_pd`](usb_pd/README.md)                         | FUSB302B USB Type-C / Power-Delivery sink PHY |
| [`usb_uart_connector`](usb_uart_connector/README.md) | USB-C receptacle + ESD (for `uart_bridge`) |
| [`usbc_otg`](usbc_otg/README.md)                     | USB 2.0 HS OTG port (USB-C receptacle, host-capable) |

Carrier-specific sheets that only make sense for this board (the SoM-mezzanine
connectors, bring-up sequencing, the power-monitor / always-on SoM buck,
board-services hardware, FMC, user IO) are not in this library; they live under
`carrier/subsystems/` as hand-written local glue. See
[`carrier/subsystems/README.md`](../carrier/subsystems/README.md).
