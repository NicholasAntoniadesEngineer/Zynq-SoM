# uart_bridge — CP2102N USB-to-UART bridge (reusable subsystem)

A project-agnostic, self-contained schgen subsystem providing the SiLabs
**CP2102N** USB-to-UART bridge in its datasheet **self-powered** configuration:
the full bypass network, the open-drain `~RST` pull-up, and the self-powered
VBUS-sense divider. It is the console / bring-up UART bridge for the Zynq-7000
SoM carrier, exposing a USB receptacle on one side and bridge-relative UART
signals on the other. It declares its interface as **abstract** port + rail
names and knows nothing about any board; a consuming project supplies a **bind
map** (`abstract -> real net`) to drop it onto real nets.

## Interface

A consuming project binds these names. Rails classify as POWER/GROUND by name
(the `+` prefix + `GND`), exactly as real board rails do.

### Rails (POWER / GROUND)

| abstract | class | meaning / constraint |
|----------|-------|----------------------|
| `+VDD_IO` | POWER  | CP2102N **self-powered** logic/IO supply (3.3 V class), tied to VREGIN (pin 7) + VDD (pin 6) + VIO (pin 5). Bypassed 100n+10u (VREGIN), 100n (VDD), 100n (VIO); the 1k `~RST` pull-up returns here. |
| `GND`     | GROUND | ground — pin 2 **and** the QFN exposed pad (pin 25). |

### Ports (PORT)

| abstract | type | meaning |
|----------|------|---------|
| `USB_VBUS`         | single | the USB connector's **own** 5 V VBUS (cable-attach sense). Sensed via a 22k1 / 47k5 divider to GND onto the VBUS pin (pin 8) — **not** a board input rail. |
| `USB_DP`, `USB_DM` | usb_hs_pair (90R) | the USB 2.0 HS data pair to the receptacle (pins 3 / 4). |
| `UART_TXD`         | single | bridge **TXD output** (pin 21). |
| `UART_RXD`         | single | bridge **RXD input** (pin 20). |
| `UART_RTS_N`       | single | bridge **`~RTS` output** (pin 19, active-low flow control). |
| `UART_CTS_N`       | single | bridge **`~CTS` input** (pin 18, active-low flow control). |

The four UART signals are brought out **bridge-relative**. The null-modem
**crossover** to a host UART (bridge TXD → host RXD, bridge `~RTS` → host
`~CTS`, etc.) is the consuming project's concern and lives in its bind map, so
the library stays host-agnostic. Two private SIGNAL nets are internal wiring and
are never bound: the `~RST` pull-up node (`CP2102N_RST_N`) and the VBUS-divider
mid node (`CP2102N_VBUS_SNS`).

### Binding it from a project

A project supplies a thin adapter declaring ONE standard `META` dict (the
adapter contract, `schgen.core.subsystem.Meta`) and forwards it to
`circuit(meta)`:

```python
from subsystems.uart_bridge import uart_bridge

META = {
    # abstract subsystem net -> real board net (the UART crossover lives here)
    "bind": {
        "+VDD_IO": "+3V3", "GND": "GND",
        "USB_VBUS": "MY_USB_VBUS", "USB_DP": "MY_USB_DP", "USB_DM": "MY_USB_DM",
        "UART_TXD": "HOST_UART_RXD", "UART_RXD": "HOST_UART_TXD",     # crossover
        "UART_RTS_N": "HOST_UART_CTS_N", "UART_CTS_N": "HOST_UART_RTS_N",
    },
    # tell the linker which of your sheets binds a deferred port
    "expects": {"USB_DP": "my_usb_connector", "USB_VBUS": "my_usb_connector",
                "UART_TXD": "my_host_uart_map"},
    # optional house-style override (keep the derived power-tree note byte-stable)
    "notes": {"draws": "CP2102N active ~14 mA typ + RST 1k pull-up"},
}

def circuit():
    return uart_bridge.circuit(META)
```

`bind` renames every external net in place, order-preserving (POWER/GROUND/PORT
only — a SIGNAL net is private wiring and is never rebound). `expects` attaches a
per-port linker deferral so a project declares which of its sheets binds each
deferred USB/UART port. `notes["draws"]` overrides the power-tree draw-note
prose. With `meta=None` the subsystem keeps its abstract names so the local test
runs offline. The carrier adapter is `carrier/subsystems/uart_bridge.py`.

The USB HS pair is typed **after** the bind: `USB_DP`/`USB_DM` are declared as
plain PORTs, `bind` is applied via `meta.finish`, and only then is the pair typed
on the final (bound) names so the `pair_with` payload points at the real
complement and the board SI gate sees a covered pair.

## Design

- **CP2102N self-powered at 3.3 V.** The CP2102N-A02-GQFN24R is a single-chip
  USB 2.0 to UART bridge with full modem-control lines, chosen for the console /
  programming UART. The D+/D- pair is typed as a 90R differential `usb_hs_pair`
  for routing/SI. In the datasheet self-powered configuration VREGIN
  + VDD + VIO are tied together to `+VDD_IO`, bypassing the internal regulator
  with the 3.3 V rail. Decoupling: 100n + 10u on VREGIN, 100n on VDD, 100n on
  VIO.
- **VBUS sense observes the connector's own 5 V.** The VBUS-sense pin (8) must
  see the USB-UART receptacle's **own** 5 V VBUS for cable-attach detection, via a
  22k1 / 47k5 divider to GND (the pin sits at ~5 V·47.5/(22.1+47.5) ≈ 3.4 V,
  under the 5.8 V abs-max). `USB_VBUS` is a sensed port from the receptacle, not a
  board input rail.
- **`~RST` is open-drain with internal POR.** `~RST` (pin 9) carries the 1k
  external pull-up to `+VDD_IO` **only** — no RC cap, because the CP2102N has its
  own internal power-on reset and a runtime reset is host-driven. The subsystem
  declares the design-rule reset **waiver** (`waive_reset`) so the decoupling
  slice does not flag the missing cap.
- **UART crossover lives in the bind map.** The four UART signals are
  bridge-relative; a project crosses them over to its host UART (TXD↔RXD,
  RTS↔CTS) when it binds. The library is host-agnostic.
- **Faithful dossier symbol.** U1 uses the generated dossier symbol/footprint
  `parts/CP2102N-A02-GQFN24R/` directly (no `lib_id` override). The dossier lays
  out all 25 pins — the 24 device pins plus the QFN exposed pad as pin 25 = the
  second GND pad of the 29-pad footprint — with EasyEDA pin numbers matching the
  SiLabs datasheet 1:1, so by-number netting holds. The exposed pad is a real pad
  + pin + GND net (pin 25 netted to GND alongside pin 2), not a prose layout note.
- **Unused pins are explicit no-connects.** `~RI`/CLK, GPIO.0–3,
  SUSPEND/`~SUSPEND`, `~DSR`/`~DTR`/`~DCD`, and the two physical NC pins (10, 16)
  are unused by design and authored as explicit no-connects.
- **Bring-up test points.** Both console directions are probed at the bridge:
  TP1 on the bridge RXD line, TP2 on the bridge TXD line (stable under the
  TXD↔RXD crossover bind).
- **Power-tree budget.** `+VDD_IO` draws ~15 mA — CP2102N active ICC ~14 mA typ
  (datasheet table 4.3) plus the 1k `~RST` pull-up — declared via `draws`.

## Parts

| ref | value | lib / part | LCSC |
|-----|-------|-----------|------|
| U1 | CP2102N-A02 | `parts/CP2102N-A02-GQFN24R/` (faithful dossier symbol) | C969151 |
| C1 | 100n | `Device:C` (VREGIN bypass) | C14663 |
| C2 | 10u  | `Device:C` (VREGIN bulk)   | C15850 |
| C3 | 100n | `Device:C` (VDD bypass)    | C14663 |
| C4 | 100n | `Device:C` (VIO bypass)    | C14663 |
| R1 | 1k   | `Device:R` (`~RST` pull-up to `+VDD_IO`) | C21190 |
| R2 | 22k1 | `Device:R` (VBUS sense top) | C25961 |
| R3 | 47k5 | `Device:R` (VBUS sense bottom) | C23061 |

## Build & test

`test_uart_bridge.py` runs the subsystem-local electrical slices offline:
declared interface, model completeness (every pin netted or NC), the USB HS pair
typing + its post-bind `pair_with` payload, decoupling completeness (incl. the
`~RST` waiver and EP strap), part-rating + per-rail cap derating, the VBUS
divider topology, the SPICE-subckt ↔ netlist passive match, and the bind
contract. Cross-board gates (link graph, full power-tree headroom, SI
length-match, board ERC, netlist merge) run at board level.

```bash
PYTHONPATH=. python3 -m pytest subsystems/uart_bridge/test_uart_bridge.py -q
```
