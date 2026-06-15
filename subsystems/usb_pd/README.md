# usb_pd — FUSB302B USB Type-C / Power-Delivery sink PHY (reusable subsystem)

A project-agnostic, self-contained schgen subsystem: the onsemi **FUSB302BMPX**
USB Type-C / PD sink front-end with its datasheet bypass network and CC analog
filters. It declares its interface as **abstract** port + rail names and knows
nothing about any board; a consuming project supplies a **bind map**
(`abstract -> real net`) to drop it onto real nets. This is the first exemplar of
the `subsystems/<name>/` library layout.

## Package contents

| file | role |
|------|------|
| `usb_pd.py`      | the NETLIST — `circuit(meta=None)`, abstract ports/rails |
| `usb_pd.cir`     | SPICE subckt — the passive network with the abstract ports as subckt pins |
| `test_usb_pd.py` | LOCAL electrical-correctness test (offline, runs the board gate slices on just this subsystem) |
| `README.md`      | this file |

Active part is **referenced, never vendored**: the FUSB302BMPX symbol/footprint/
LCSC come from the global `parts/FUSB302BMPX/`. The sheet deliberately draws the
stock `Interface_USB:FUSB302BMPX` symbol (a `use_part(lib_id=...)` override) so
the WQFN-14+EP stacked-pin drawing and footprint stay faithful while MPN/LCSC/
datasheet still source from `parts/`.

## The abstract interface (the reuse contract)

A consuming project binds these names. Rails classify as POWER/GROUND by name
(the `+` prefix + `GND`), exactly as real board rails do, so a standalone build
and a bound build share net classes.

### Rails (POWER / GROUND)

| abstract | class | meaning / constraint |
|----------|-------|----------------------|
| `+VDD_LOGIC`  | POWER  | FUSB302B VDD logic supply (3.3 V class). MUST be **always-on**, existing **before** PD negotiation — the PHY brings the 20 V in, so it cannot depend on a rail it creates. |
| `+VBUS_SENSE` | POWER  | raw receptacle VBUS for the VBUS-sense pin (U1.2), taken **ahead of any inlet eFuse** so the PHY observes vSafe5V/vbus at the connector for attach detection. Worst case 21.0 V (20 V contract +5%); pin abs-max 28 V. |
| `GND`         | GROUND | ground. |

### Ports (PORT)

| abstract | type | meaning |
|----------|------|---------|
| `CC1`, `CC2`        | single | Type-C CC lines to the receptacle. The FUSB302B **owns** Rd/Rp, vRd sensing, the BMC PHY and VCONN switching on these. 200p analog filter caps to GND live in this subsystem. |
| `I2C_SDA`, `I2C_SCL`| i2c (bus `USB_PD_I2C`, 400 kHz) | control bus to the host MCU; PHY is slave **0x22**. Open-drain — bus pull-ups are **shared** and live **once** on the bus, never here. |
| `INT_N`             | single | open-drain interrupt to the host MCU (wire-OR shareable). Its pull-up is shared and lives **once** on the net, never here. |

VCONN sourcing is unused by design → both VCONN pins (U1.12/U1.13) are explicit
author no-connects.

### Parts (from the global `parts/` lib + inline passives)

| ref | value | lib / part | LCSC |
|-----|-------|-----------|------|
| U1 | FUSB302BMPX | `parts/FUSB302BMPX/` (stock `Interface_USB:FUSB302BMPX` symbol) | C132291 |
| C1 | 100n | `Device:C` (VDD bypass) | C14663 |
| C2 | 10u  | `Device:C` (VDD bulk)   | C15850 |
| C3 | 100n | `Device:C` (VBUS-sense) | C14663 |
| C4 | 200p | `Device:C` (CC1 filter, C0G) | C113796 |
| C5 | 200p | `Device:C` (CC2 filter, C0G) | C113796 |

## Consuming it from a project

A project supplies a thin adapter declaring ONE standard `META` dict (the
adapter contract, `schgen.core.subsystem.Meta`) and forwards it:

```python
from subsystems.usb_pd import usb_pd

META = {
    # abstract subsystem net -> your real board net
    "bind": {
        "+VDD_LOGIC": "+3V3_SC", "+VBUS_SENSE": "+VBUS_IN", "GND": "GND",
        "CC1": "MY_CC1", "CC2": "MY_CC2",
        "I2C_SDA": "MY_SDA", "I2C_SCL": "MY_SCL", "INT_N": "MY_INT_N",
    },
    # optional: tell the linker which of your sheets will bind a deferred port
    "expects": {"I2C_SDA": "my_connector", "I2C_SCL": "my_connector",
                "INT_N": "my_connector"},
    # optional house-style overrides (keep your derived artifacts byte-stable)
    "buses": {"i2c": "MY_I2C_BUS"},        # the I2C bus-group name for SDA/SCL
    "notes": {"draws": "FUSB302B VDD (<1 mA); ..."},  # power-tree draw note
}

def circuit():
    return usb_pd.circuit(META)
```

The four standard `META` keys (`bind` / `expects` / `buses` / `notes`) are
universal across every reusable subsystem — a typo'd top-level key is a hard
`CircuitError`, never silently dropped. `bind` renames every external **in
place, order-preserving** (POWER/GROUND/PORT only — a SIGNAL net is private
wiring and is never rebound; a SIGNAL key or a collision is a hard
`CircuitError`). Because the rename preserves net insertion order, parts, refs,
NCs and port-type payloads, **binding to the exact names a hand-written sheet
used yields a byte-identical emitted sheet.** The carrier adapter is
`carrier/subsystems/usb_pd.py`.

## Design notes (datasheet + bring-up contract)

- **Always-on supply (R1).** Bring-up dossier risk R1
  (`carrier/research/bringup_power_gating.md`): PD negotiation must happen
  *before* any gated rail exists; the board boots on default 5 V VBUS. So
  `+VDD_LOGIC` (and the shared INT_N pull-up) must sit on an always-on system
  rail, never a gated module rail.
- **VBUS sense is pre-eFuse (AMX-1).** The VBUS-sense pin must observe the raw
  connector VBUS for attach detection, *ahead* of any inlet eFuse / dV/dt ramp.
  At the legal 20 V+5% contract U1.2 sits at its 21.0 V recommended-operating
  max and can ride to ~24.4 V in the pre-TVS abnormal-source window — still
  under the 28 V abs-max. No damage corner exists in a normal contract.
- **The PHY owns CC (PD-CC-1).** The FUSB302B provides Rd/Rp, vRd sensing, BMC
  framing and VCONN switching. A host MCU **must not** also enable a native UCPD
  peripheral on the same CC lines — double-termination corrupts the advertised
  current and garbles BMC framing. The MCU talks PD only over I2C (0x22) + INT_N
  and holds its own CC pins input-only / Hi-Z.
- **One pull-up per net.** SDA/SCL and INT_N are open-drain; their pull-ups are
  shared with the rest of the bus and live **once**, off this subsystem. None
  are placed here — so the local test does **not** enforce the I2C-pull-up rule
  (that completeness is a board-level gate).
- **Stacked pins.** The stock WQFN-14+EP symbol stacks duplicate pads — VDD
  (3/4), GND/EP (8/9/15), CC1 (10/11), CC2 (1/14). Each duplicate is declared on
  the same net as its twin; the netlist gate proves KiCad sees all of them.

## Local test vs board gates

`test_usb_pd.py` runs the **subsystem-local** slices offline: declared abstract
interface, model completeness (every pin netted-or-NC), decoupling completeness
(design_rules DECAP/EP/STRAP), part-rating coverage + per-rail cap derating, the
SPICE-subckt ↔ netlist passive match, and the bind contract. **Cross-board**
gates stay aggregated at board level and are *not* duplicated here: the I2C/INT
pull-up completeness (shared off-subsystem), the link / port-driver graph, the
full power-tree headroom, board ERC, and the board netlist merge — all run by
`schgen board`.

```bash
PYTHONPATH=. python3 -m pytest subsystems/usb_pd/test_usb_pd.py -q
```
