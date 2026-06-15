# pd_input — USB-C PD power inlet (reusable subsystem)

A project-agnostic, self-contained schgen subsystem: a **USB Type-C / Power-
Delivery power INLET** — the receptacle, a **TPS26631** inlet eFuse (OVP / soft-
start / current limit), an **SMBJ22A** TVS, and a **USBLC6-2SC6** data-pair ESD
array. It declares its interface as **abstract** port + rail names and knows
nothing about any board; a consuming project supplies a **bind map** (`abstract
-> real net`) to drop it onto real nets.

**Pairs with [`subsystems/usb_pd/`](../usb_pd/)** (the FUSB302B CC PHY): this
subsystem owns the **receptacle + the inlet eFuse**; the **CC lines** and the
**raw (pre-eFuse) VBUS** cross to the PHY. Bind `pd_input`'s `+VBUS_CONN` and
`usb_pd`'s `+VBUS_SENSE` to the **same** board net so the PHY observes vSafe5V/
vbus at the connector for attach detection.

## Package contents

| file | role |
|------|------|
| `pd_input.py`      | the NETLIST — `circuit(meta=None)`, abstract ports/rails |
| `pd_input.cir`     | SPICE subckt — the passive network (inlet bypass + eFuse straps) with the abstract ports as subckt pins |
| `test_pd_input.py` | LOCAL electrical-correctness test (offline, runs the board gate slices on just this subsystem) |
| `README.md`        | this file |

Active parts are **referenced, never vendored**: the receptacle
(`TYPE-C-31-M-12`), eFuse (`TPS26631PWPR`) and ESD array (`USBLC6-2SC6`) symbol/
footprint/LCSC come from the global `parts/` library via `use_part`.

## The abstract interface (the reuse contract)

A consuming project binds these names. Rails classify as POWER/GROUND by name
(the `+` prefix + `GND`/`CHASSIS_GND`), exactly as real board rails do, so a
standalone build and a bound build share net classes.

### Rails (POWER / GROUND)

| abstract | class | meaning / constraint |
|----------|-------|----------------------|
| `+VBUS_CONN` | POWER | **RAW receptacle VBUS, ahead of the eFuse** (TVS + inlet 100n + eFuse IN/IN_SYS/UVLO + OVP-divider top). The PD PHY binds its **VBUS-sense to this SAME net** for attach detection. Rides the live cable VBUS — worst case 21.0 V (20 V contract +5%). |
| `+VBUS_OUT`  | POWER | **FUSED output rail** — the dV/dt-charged board bulk starts here (eFuse OUT + the 10u). What the rest of the board consumes (the carrier's `+VIN`). |
| `+VDD_LOGIC` | POWER | always-on logic rail (3.3 V class): the FLT# pull-up **and** the USBLC6 data-ESD clamp reference. Must be alive whenever the fault can be read / the data pair is active — **never** the inlet VBUS (clamping a 3.3 V data pair to a 20 V rail is destructive and defeats the ESD function). |
| `GND`        | GROUND | ground. |
| `CHASSIS_GND`| GROUND | connector shell / earth island (shell pads only). |

### Ports (PORT)

| abstract | type | meaning |
|----------|------|---------|
| `CC1`, `CC2`        | single | Type-C CC lines from the receptacle, crossing to the PD PHY (FUSB302B owns Rd/Rp + the BMC PHY) **and** to the host's CC-sense pins. |
| `USB_D_P`, `USB_D_N`| usb_hs_pair (90R) | USB FS data pair to the host PHY, **post-ESD** (USBLC6 channel output). Cable-flip paired at the receptacle (both flip pads tie to the channel input). |
| `FLT_N`             | single (open-drain) | the eFuse **open-drain fault flag** to a host expander port, pulled to `+VDD_LOGIC`. The `expect=` linker deferral (which sheet binds it) is project-specific → `meta["expects"]["FLT_N"]`. |

### Parts (from the global `parts/` lib + inline passives)

| ref | value | lib / part | LCSC |
|-----|-------|-----------|------|
| J1 | TYPE-C-31-M-12 | `parts/TYPE-C-31-M-12/` (16-contact USB-C, 5 A / 20 V) | C165948 |
| U1 | TPS26631PWPR | `parts/TPS26631PWPR/` (HTSSOP-20 eFuse, 4.5–60 V) | C2866319 |
| U2 | USBLC6-2SC6 | `parts/USBLC6-2SC6/` (data-pair ESD array) | — |
| C1 | 100n | `Device:C` (inlet bypass, DS-min on IN) | C14663 |
| C2 | 10u  | `Device:C` 50 V X7R (eFuse-output board bulk) | C596319 |
| C3 | 47n  | `Device:C` (eFuse dV/dt slew) | C1622 |
| D1 | SMBJ22A | `Device:D_Zener` (600 W unidirectional TVS, 22 V standoff) | C10214 |
| R3 | 100k | `Device:R` (OVP divider top) | C25803 |
| R4 | 5.49k | `Device:R` (OVP divider bottom) | C188263 |
| R5 | 5.1k | `Device:R` (ILIM strap) | C23186 |
| R6 | 100k | `Device:R` (FLT# pull-up to `+VDD_LOGIC`) | C25803 |

The eFuse strap nodes (`PD_OVP_SET`, `PD_ILIM_SET`, `PD_DVDT`) and the cable-flip
data nodes (`PD_USB_DP_CONN`, `PD_USB_DN_CONN`) are the subsystem's **private
SIGNAL wiring** — they are never rebound by `bind`.

## Consuming it from a project

A project supplies a thin adapter declaring ONE standard `META` dict (the
adapter contract, `schgen.core.subsystem.Meta`) and forwards it:

```python
from subsystems.pd_input import pd_input

META = {
    # abstract subsystem net -> your real board net
    "bind": {
        "+VBUS_CONN": "+VBUS_IN", "+VBUS_OUT": "+VIN", "+VDD_LOGIC": "+3V3_SC",
        "GND": "GND", "CHASSIS_GND": "CHASSIS_GND",
        "CC1": "MY_CC1", "CC2": "MY_CC2",
        "USB_D_P": "MY_USB_DP", "USB_D_N": "MY_USB_DN",
        "FLT_N": "MY_PD_FLT_N",
    },
    # optional: tell the linker which of your sheets will bind the fault port
    "expects": {"FLT_N": "my_io_expander (port P15)"},
    # optional house-style override (keep your derived artifacts byte-stable)
    "notes": {"draws": "USB-C PD inlet: ..."},
}

def circuit():
    return pd_input.circuit(META)
```

The four standard `META` keys (`bind` / `expects` / `buses` / `notes`) are
universal across every reusable subsystem — a typo'd top-level key is a hard
`CircuitError`, never silently dropped. `bind` renames every external **in
place, order-preserving** (POWER/GROUND/PORT only — a SIGNAL net is private
wiring and is never rebound; a SIGNAL key or a collision is a hard
`CircuitError`). The rename also carries the **`usb_hs_pair` `pair_with`
payload** on the data pair and the **TestPoint VALUES** along, so binding to the
exact names a hand-written sheet used yields a **byte-identical emitted sheet**.
The carrier adapter is `carrier/subsystems/pd_input.py`.

## Design notes (datasheet + bring-up contract)

- **Raw VBUS is pre-eFuse.** `+VBUS_CONN` is the receptacle VBUS *ahead* of the
  eFuse (TVS + DS-minimum 100n). The eFuse sits between it and `+VBUS_OUT` so the
  PD source never sees the board's bulk capacitance slam, and the PD PHY observes
  attach at the connector. The eFuse's 67 V abs-max rides out what the SMBJ22A
  (22 V standoff, VBR 24.4–26.9 V) lets through.
- **OVP window vs the TVS (the AMX margin).** The OVP divider (R3 100k / R4
  5.49k) cuts off at ~23.06 V typ. R4 was widened from 5.6k → 5.49k so the
  trip-MIN clears the 21.0 V legal contract max while the worst-case cutoff
  still stays **below** the SMBJ22A VBR-min — OVP definitely trips before the TVS
  conducts. Full rationale (every datasheet number) is in the carrier adapter.
- **Soft-start inrush.** dV/dt cap C3 47n → a constant ~1.02 V/ms output slew;
  with ~30 µF downstream bulk the inrush is ~31 mA, two decades under the 3 A
  contract — no foldback on the 5→20 V contract step.
- **MODE / PGTH straps.** MODE→GND = auto-retry (a transient inlet fault recovers
  without a human cycling power); PGTH→GND disables the fast-recovery resample so
  every recovery ramps dV/dt-controlled (PD-friendly). PGOOD then reads low and
  is an author no-connect.
- **No reverse-blocking FET.** A USB-C inlet cannot be reverse-wired, so the
  eFuse B_GATE/DRV (pins 4/5) are explicit author no-connects (DS Fig 8-8). UVLO
  is tied to IN_SYS (never floating) so the internal POR governs and the 5 V
  default VBUS passes — critical, because the logic rail is generated from the
  fused output and an eFuse that blocked 5 V would deadlock PD forever.
- **Data-pair ESD clamp rail.** The FUSB302B only protects the CC lines; the FS
  data pair would reach the host PHY with no ESD. The USBLC6-2SC6 clamps it, with
  its VBUS-referenced rail clamp (pin 5) tied to the **always-on 3.3 V logic
  rail**, never the 20 V inlet VBUS.

## Local test vs board gates

`test_pd_input.py` runs the **subsystem-local** slices offline: declared abstract
interface, model completeness (every pin netted-or-NC), the usb_hs_pair typing,
design_rules DECAP/EP/STRAP, part-rating coverage + per-rail cap derating, the
SPICE-subckt ↔ netlist cap match, and the bind contract (incl. the pair payload +
testpoint VALUE rebind). **Cross-board** gates stay aggregated at board level and
are *not* duplicated here: the link / port-driver graph (CC → the usb_pd PHY,
FLT_N → a host expander), the full power-tree headroom, board ERC, and the board
netlist merge — all run by `schgen board`.

```bash
PYTHONPATH=. python3 -m pytest subsystems/pd_input/test_pd_input.py -q
```
