# uart_bridge — CP2102N USB-to-UART bridge (reusable subsystem)

A project-agnostic, self-contained schgen subsystem: the SiLabs **CP2102N**
USB-to-UART bridge in its datasheet **self-powered** configuration, with the
full bypass network, the open-drain `~RST` pull-up, and the self-powered VBUS-
sense divider. It declares its interface as **abstract** port + rail names and
knows nothing about any board; a consuming project supplies a **bind map**
(`abstract -> real net`) to drop it onto real nets.

## Package contents

| file | role |
|------|------|
| `uart_bridge.py`      | the NETLIST — `circuit(meta=None)`, abstract ports/rails |
| `uart_bridge.cir`     | SPICE subckt — the passive network with abstract ports as subckt pins |
| `test_uart_bridge.py` | LOCAL electrical-correctness test (offline) |
| `README.md`           | this file |

Active part is **referenced, never vendored**: the CP2102N symbol/footprint/LCSC
come from the global `parts/CP2102N-A02-GQFN24R/`. The FAITHFUL generated dossier
symbol/footprint is used directly (the "0 hand-built symbols" law) — **no**
`lib_id` override. The dossier lays out all 25 pins (24 + the QFN exposed pad as
pin 25 = the second GND pad of the 29-pad footprint); its EasyEDA pin numbers
match the SiLabs datasheet 1:1, so the by-number netting is unchanged.

## The abstract interface (the reuse contract)

A consuming project binds these names. Rails classify as POWER/GROUND by name
(the `+` prefix + `GND`), exactly as real board rails do.

### Rails (POWER / GROUND)

| abstract | class | meaning / constraint |
|----------|-------|----------------------|
| `+VDD_IO` | POWER  | CP2102N **self-powered** logic/IO supply (3.3 V class), tied to VREGIN + VDD + VIO. Bypassed 100n+10u (VREGIN), 100n (VDD), 100n (VIO); the 1k `~RST` pull-up sits here too. |
| `GND`     | GROUND | ground — pin 2 **and** the QFN exposed pad (pin 25). |

### Ports (PORT)

| abstract | type | meaning |
|----------|------|---------|
| `USB_VBUS`              | single | the USB connector's **own** 5 V VBUS (cable-attach sense). Sensed via a 22k1 / 47k5 divider to GND onto the VBUS pin — **not** a board input rail. |
| `USB_DP`, `USB_DM`      | usb_hs_pair (90R) | the USB 2.0 HS data pair to the receptacle. |
| `UART_TXD`              | single | bridge **TXD output** (pin 21). |
| `UART_RXD`              | single | bridge **RXD input** (pin 20). |
| `UART_RTS_N`            | single | bridge **`~RTS` output** (pin 19, active-low flow control). |
| `UART_CTS_N`            | single | bridge **`~CTS` input** (pin 18, active-low flow control). |

The four UART signals are brought out **bridge-relative**. A null-modem
**crossover** to a host UART (bridge TXD → host RXD, bridge `~RTS` → host `~CTS`,
etc.) is the consuming project's concern and lives in its **bind map**, so the
library stays host-agnostic.

All GPIO / modem-control (`~DSR`/`~DTR`/`~DCD`) / suspend (`SUSPEND`/`~SUSPEND`) /
`~RI`/`CLK` pins and the two physical NC pins (10, 16) are unused by design →
explicit author no-connects.

Two **private SIGNAL** nets are internal wiring and are NEVER bound: the `~RST`
pull-up node (`CP2102N_RST_N`) and the VBUS-divider mid node
(`CP2102N_VBUS_SNS`).

### Parts (from the global `parts/` lib + inline passives)

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

## Consuming it from a project

A project supplies a thin adapter declaring ONE standard `META` dict (the adapter
contract, `schgen.core.subsystem.Meta`) and forwards it:

```python
from subsystems.uart_bridge import uart_bridge

META = {
    # abstract subsystem net -> your real board net (the UART crossover lives here)
    "bind": {
        "+VDD_IO": "+3V3", "GND": "GND",
        "USB_VBUS": "MY_USB_VBUS", "USB_DP": "MY_USB_DP", "USB_DM": "MY_USB_DM",
        "UART_TXD": "HOST_UART_RXD", "UART_RXD": "HOST_UART_TXD",     # crossover
        "UART_RTS_N": "HOST_UART_CTS_N", "UART_CTS_N": "HOST_UART_RTS_N",
    },
    # optional: tell the linker which of your sheets will bind a deferred port
    "expects": {"USB_DP": "my_usb_connector", "USB_VBUS": "my_usb_connector",
                "UART_TXD": "my_host_uart_map"},
    # optional house-style override (keep your derived power-tree note byte-stable)
    "notes": {"draws": "CP2102N active ~14 mA typ + RST 1k pull-up"},
}

def circuit():
    return uart_bridge.circuit(META)
```

The four standard `META` keys (`bind` / `expects` / `buses` / `notes`) are
universal across every reusable subsystem — a typo'd top-level key is a hard
`CircuitError`, never silently dropped. `bind` renames every external **in place,
order-preserving** (POWER/GROUND/PORT only — a SIGNAL net is private wiring and
is never rebound; a SIGNAL key or a collision is a hard `CircuitError`). Because
the rename preserves net insertion order, parts, refs, NCs and port-type
payloads, **binding to the exact names a hand-written sheet used yields a
byte-identical emitted sheet.** The carrier adapter is
`carrier/subsystems/uart_bridge.py`.

> **Note — the USB HS pair is typed *after* the bind.** `Circuit.bind` renames a
> net's name and the `port_types` dict key, but **not** the nested `pair_with`
> value inside a `PortType`. So the library declares `USB_DP`/`USB_DM` as plain
> PORTs, applies `bind` (via `meta.finish`), and only **then** types the pair on
> the final (bound) names. This keeps the pair's `pair_with` payload pointing at
> the real complement — without it the board's SI gate sees an UNCOVERED pair
> (abstract endpoint on one side, real on the other).

## Design notes (datasheet + bring-up contract)

- **Self-powered at 3.3 V.** Per the CP2102N datasheet self-powered config,
  VREGIN + VDD + VIO are tied together to `+VDD_IO`; the internal regulator is
  bypassed by the 3.3 V rail. Decoupling: 100n+10u on VREGIN, 100n on VDD, 100n
  on VIO.
- **VBUS sense is the connector's own 5 V (spice-gate fix, 2026-06-11).** The
  VBUS-sense pin must observe the USB-UART receptacle's **own** 5 V VBUS for
  cable-attach detection — via a 22k1 / 47k5 divider (the pin sits at
  ~5 V·47.5/(22.1+47.5) ≈ 3.4 V). Authoring this divider off a board input rail
  was caught by the schgen spice gate: after a 20 V PD contract that rail would
  put 13.6 V on the CP2102N VBUS pin (5.8 V abs-max), destroying the bridge.
- **`~RST` is open-drain, internal POR (verification P1).** `~RST` carries the 1k
  external pull-up **only** — no RC cap by design (the CP2102N has its own
  internal POR; a runtime reset is host-driven). The library declares the
  design-rule reset **waiver** so the decoupling slice does not flag it.
- **UART crossover lives in the bind map.** The four UART signals are
  bridge-relative; a project crosses them over to its host UART (TXD↔RXD,
  RTS↔CTS) when it binds. The library is host-agnostic.
- **QFN exposed pad.** The faithful symbol exposes the QFN pad as pin 25 = the
  second GND pad; it is netted to GND alongside its twin pin 2 (a real pad + pin
  + GND net, never a prose layout note).

## Local test vs board gates

`test_uart_bridge.py` runs the **subsystem-local** slices offline: declared
abstract interface, model completeness (every pin netted-or-NC), the USB HS pair
typing + its post-bind `pair_with` payload, decoupling completeness
(design_rules DECAP/EP/STRAP + the `~RST` waiver), part-rating coverage + per-rail
cap derating, the VBUS divider topology, the SPICE-subckt ↔ netlist passive
match, and the bind contract. **Cross-board** gates stay aggregated at board
level and are *not* duplicated here: the link / port-driver graph, the full
power-tree headroom, the SI length-match emission, board ERC, and the board
netlist merge — all run by `schgen board`.

```bash
PYTHONPATH=. python3 -m pytest subsystems/uart_bridge/test_uart_bridge.py -q
```
