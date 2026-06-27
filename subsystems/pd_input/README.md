# pd_input — USB-C PD power inlet (reusable subsystem)

A project-agnostic, self-contained schgen subsystem: the **USB Type-C / Power-
Delivery power INLET** for the Zynq-7000 SoM carrier. It owns the Type-C
receptacle, a **TPS26631** inlet eFuse (OVP / soft-start / current limit), an
**SMBJ22A** TVS, and a **USBLC6-2SC6** data-pair ESD array. It declares its
interface as **abstract** port + rail names and knows nothing about any board.

It **pairs with [`subsystems/usb_pd/`](../usb_pd/)** (the FUSB302B CC PHY):
`pd_input` owns the receptacle + inlet eFuse, and the **CC lines** plus the
**raw (pre-eFuse) VBUS** cross to the PHY. A project binds `pd_input`'s
`+VBUS_CONN` and `usb_pd`'s VBUS-sense to the **same** board net so the PHY
observes vbus at the connector for attach detection.

## Interface

A consuming project supplies one standard `META` dict
(`schgen.core.subsystem.Meta`) and forwards it to `pd_input.circuit(META)`.
`bind` rebinds each externally-visible net (rails + ports) to a real board
net, order-preserving, so binding to the names a hand-written sheet used yields
a byte-identical emitted sheet (the rename also carries the `usb_hs_pair`
`pair_with` payload and the TestPoint values). `expects` attaches a linker
deferral to a port; `notes` overrides house-style prose. With `meta=None` the
abstract names stay, so `test_pd_input.py` runs offline.

```python
from subsystems.pd_input import pd_input

META = {
    "bind": {
        "+VBUS_CONN": "+VBUS_IN", "+VBUS_OUT": "+VIN", "+VDD_LOGIC": "+3V3_SC",
        "GND": "GND", "CHASSIS_GND": "CHASSIS_GND",
        "CC1": "MY_CC1", "CC2": "MY_CC2",
        "USB_D_P": "MY_USB_DP", "USB_D_N": "MY_USB_DN",
        "FLT_N": "MY_PD_FLT_N",
    },
    "expects": {"FLT_N": "my_io_expander (port P15)"},  # which sheet binds the fault port
    "notes": {"draws": "USB-C PD inlet: ..."},          # optional prose override
}

def circuit():
    return pd_input.circuit(META)
```

### Rails (POWER / GROUND)

| abstract | class | meaning / constraint |
|----------|-------|----------------------|
| `+VBUS_CONN` | POWER | RAW receptacle VBUS, **ahead of the eFuse** (TVS + inlet 100n + eFuse IN/IN_SYS/UVLO + OVP-divider top). The PD PHY binds its VBUS-sense to this SAME net. Rides the live cable VBUS — worst case 21.0 V (20 V contract +5%). |
| `+VBUS_OUT`  | POWER | FUSED output rail — the dV/dt-charged board bulk starts here (eFuse OUT + the 10u). What the rest of the board consumes. |
| `+VDD_LOGIC` | POWER | always-on logic rail (3.3 V class): the FLT# pull-up **and** the USBLC6 data-ESD clamp reference. Must be alive whenever the fault can be read / the data pair is active — never the inlet VBUS. |
| `GND`        | GROUND | ground. |
| `CHASSIS_GND`| GROUND | connector shell / earth island (shell pads only). |

### Ports (PORT)

| abstract | type | meaning |
|----------|------|---------|
| `CC1`, `CC2`        | single | Type-C CC lines from the receptacle, crossing to the PD PHY (FUSB302B owns Rd/Rp + BMC) and to the host CC-sense pins. |
| `USB_D_P`, `USB_D_N`| usb_hs_pair | USB FS data pair to the host PHY, **post-ESD** (USBLC6 channel output). Cable-flip paired at the receptacle. |
| `FLT_N`             | single (open-drain) | the eFuse open-drain fault flag to a host expander port, pulled to `+VDD_LOGIC`. The `expect=` deferral (which sheet binds it) is project-specific via `meta["expects"]["FLT_N"]`. |

The eFuse strap nodes (`PD_OVP_SET`, `PD_ILIM_SET`, `PD_DVDT`) and the cable-flip
data nodes (`PD_USB_DP_CONN`, `PD_USB_DN_CONN`) are private SIGNAL wiring and are
never rebound by `bind`.

## Design

- **Raw VBUS is pre-eFuse.** `+VBUS_CONN` is the receptacle VBUS ahead of the
  eFuse (TVS D1 + DS-minimum inlet 100n C1, both on the stacked VBUS/GND pads).
  The TPS26631 sits between it and `+VBUS_OUT` so the PD source never sees the
  board's bulk-cap slam, and the PD PHY observes attach at the connector.

- **eFuse part choice.** The TPS26631PWPR is a wide-input (up to 60 V) eFuse with
  an integrated OVP comparator, adjustable current limit, and dV/dt soft-start —
  it provides the single point of OVP and inrush control for the whole board
  downstream of the connector, which a bare receptacle cannot.

- **OVP window vs the TVS.** The OVP divider R3 100k / R4 5.49k sets the trip at
  ~23.06 V typ on `U1.OVP`. R4 is sized so the trip-MIN clears the 21.0 V legal
  contract max while the worst-case cutoff still stays below the SMBJ22A VBR-min,
  so OVP trips **before** the TVS conducts. The SMBJ22A (22 V standoff, 600 W
  unidirectional) clamps the residual transient; the eFuse's abs-max rides out
  what the TVS lets through.

- **Current limit.** R5 5.1k on `U1.ILIM` sets I_OL ≈ 18/5.1k ≈ 3.5 A, headroom
  over the 3 A PD contract.

- **Soft-start inrush.** dV/dt cap C3 47n gives a constant ~1.02 V/ms output
  slew, keeping inrush well under the 3 A contract on the 5→20 V step.

- **MODE / PGTH straps.** `U1.MODE`→GND = auto-retry (a transient inlet fault
  recovers without a human cycling power); `U1.PGTH`→GND = dV/dt-only recovery so
  every ramp is slew-controlled (PD-friendly). SHDN#, IMON, and PGOOD are unused
  per the datasheet and are author no-connects.

- **No reverse-blocking FET.** A USB-C inlet cannot be reverse-wired, so the
  eFuse B_GATE/DRV are explicit author no-connects (DS Fig 8-8). UVLO is tied to
  IN_SYS (never floating) so the internal POR governs and the default 5 V VBUS
  passes — necessary, because the logic rail is generated from the fused output.

- **Fault flag.** `U1.FLT#` is open-drain, pulled up via R6 100k to `+VDD_LOGIC`
  (an always-on logic rail), never the inlet VBUS (an expander IO abs-max is far
  below the 20 V contract). It exits as the `FLT_N` port.

- **Data-pair ESD.** The PD PHY only protects the CC lines; the FS data pair
  would reach the host PHY with no ESD. A USBLC6-2SC6 (U2) clamps it at the
  receptacle: both cable-flip pads tie to a channel input, the PHY-side ports tap
  that channel's output. Its VBUS-referenced rail clamp (pin 5) ties to
  `+VDD_LOGIC` (≤5.25 V standoff class), never the 20 V inlet VBUS — clamping a
  3.3 V data pair to the 20 V rail would hold the internal TVS in continuous
  avalanche, which is destructive and defeats the ESD function.

- **Shell / SBU.** The receptacle shell pads (`J1.EH`) go to `CHASSIS_GND`; SBU1/
  SBU2 are unused no-connects.

- **Bring-up coverage.** Testpoints on `+VBUS_CONN` and `+VBUS_OUT` answer the
  first bring-up question — is a fault before or after the eFuse. `CHASSIS_GND`
  is testpoint-waived (probeable at any connector shell tab).

## Parts

| ref | value | lib / part | LCSC |
|-----|-------|-----------|------|
| J1 | TYPE-C-31-M-12 | `parts/` `use_part` (USB-C receptacle) | — |
| U1 | TPS26631PWPR | `parts/` `use_part` (eFuse) | — |
| U2 | USBLC6-2SC6 | `parts/` `use_part` (FS data-pair ESD array) | — |
| C1 | 100n | `Device:C` (inlet bypass, DS-min on IN) | C14663 |
| C2 | 10u  | `Device:C` 50 V X7R (eFuse-output board bulk) | C596319 |
| C3 | 47n  | `Device:C` (eFuse dV/dt slew) | C1622 |
| D1 | SMBJ22A | `Device:D_Zener` (TVS, 22 V standoff) | C10214 |
| R3 | 100k | `Device:R` (OVP divider top) | C25803 |
| R4 | 5.49k | `Device:R` (OVP divider bottom) | C188263 |
| R5 | 5.1k | `Device:R` (ILIM strap) | C23186 |
| R6 | 100k | `Device:R` (FLT# pull-up to `+VDD_LOGIC`) | C25803 |

J1/U1/U2 are referenced via `use_part`, so their symbol/footprint/LCSC come from
the global `parts/` library, not this file.

## Build & test

`test_pd_input.py` runs the subsystem-local slices offline: the declared
abstract interface, model completeness (every pin netted-or-NC), usb_hs_pair
typing, DECAP/EP/STRAP design rules, part-rating + per-rail cap derating, the
SPICE-subckt ↔ netlist cap match, and the bind contract. Cross-board gates (link
graph, full power tree, board ERC/netlist merge) run at board level via
`schgen board`.

```bash
PYTHONPATH=. python3 -m pytest subsystems/pd_input/test_pd_input.py -q
```
