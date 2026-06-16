# hdmi_rx — HDMI-A sink: connector + TMDS-RX ESD + EDID EEPROM (reusable subsystem)

A project-agnostic, self-contained schgen subsystem: a **HDMI Type-A receptacle**
(SOFNG HDMI-019S) as an HDMI **sink**, with low-cap **TMDS RX ESD** (TI
TPD4E02B04), a **slow-line ESD** array (TI TPD4E05U06), a 2-Kbit **EDID EEPROM**
(ST M24C02) on the source-mastered DDC bus, passive **HPD** assert, a cable-5V
**presence divider**, and a **CEC** pull-up. It declares its interface as
**abstract** port + rail names and knows nothing about any board; a consuming
project supplies a **bind map** (`abstract -> real net`) to drop it onto real
nets. The RX-side sibling of `subsystems/hdmi_tx/` (the source port).

## Package contents

| file | role |
|------|------|
| `hdmi_rx.py`      | the NETLIST — `circuit(meta=None)`, abstract ports/rails |
| `hdmi_rx.cir`     | SPICE subckt — the passive network with the abstract rails/ports as subckt pins |
| `test_hdmi_rx.py` | LOCAL electrical-correctness test (offline, runs the board gate slices on just this subsystem) |
| `README.md`      | this file |

Active parts are **referenced, never vendored**: the HDMI-019S, M24C02-WMN6TP,
TPD4E02B04DQAR and TPD4E05U06DQAR symbol/footprint/LCSC come from the global
`parts/<MPN>/` dossiers.

### Faithful receptacle symbol (0 hand-built symbols)

J1 draws its **FAITHFUL `parts/HDMI-019S/` dossier symbol** — no `lib_id=`
override (the **"0 hand-built symbols"** migration; the old hand-built
`schgen:HDMI_A_RX` is gone and `symbol_law.PENDING_MIGRATION` is now empty). The
dossier box lays its 23 pins out by package edge (pins 1-9 left, 10-23 right,
+5V top, GND bottom), each shield pad distinct; the placer's connector
box-handler escapes the dense right edge + the cable-5V trunk cleanly (a
top-edge tap whose trunk faces away routes around the body, never through it).
The swap was NETLIST-NEUTRAL (same pin numbers + footprint). The EEPROM uses the
stock KiCad `Memory_EEPROM:M24C02-WMN` drawing (not a `schgen:` symbol).

## The abstract interface (the reuse contract)

A consuming project binds these names. Rails classify as POWER/GROUND by name
(the `+` prefix → POWER; `GND`/`CHASSIS_GND` → GROUND).

### Rails (POWER / GROUND)

| abstract | class | meaning / constraint |
|----------|-------|----------------------|
| `+VDD_LOGIC`  | POWER  | the **gated module rail**. Only the CEC 27k pull-up sits here (~0.12 mA when CEC is driven low). EEPROM + EDID WC# are cable-5V-fed, so nothing else draws from it. |
| `GND`         | GROUND | ground (TMDS shields + DDC/CEC ground + EEPROM ground + both ESD arrays' GND pads). |
| `CHASSIS_GND` | GROUND | the four HDMI shell legs; star-bonded to `GND` by the consuming board. |

### Ports (PORT)

| abstract | type | meaning |
|----------|------|---------|
| `TMDS_RX_D2/D1/D0/CLK_P/N` | tmds_pair (100 Ω) | the 4 **RX** TMDS differential pairs into the receiver bank. Each is **one net** connector → low-cap ESD shunt tap → receiver (DC-coupled, a shunt TAP, not a series break). |
| `HDMI_5V_DET` | single | the cable-5V **presence detect** — a 10k/15k divider output (3.15 V max at 5.25 V → LVCMOS33-safe) to a 3V3 receiver input. |
| `CEC`         | single | 3V3-domain CEC to the receiver, with the spec **27k pull-up** to `+VDD_LOGIC`. |

The **DDC I2C** (`HDMI_RX_SDA`/`HDMI_RX_SCL`), the **HPD** assert
(`HDMI_RX_HPD`) and the cable-5V **quasi-rail** (`HDMI_RX_5V`) are **private
SIGNAL wiring** — they run entirely connector ↔ EEPROM ↔ ESD on this sheet (DDC
is source-mastered over the cable; HPD is 5-V-domain and not routed to a 3V3
bank), so they are **never** part of the contract and are never bound. HDMI pin
14 (HEC/Utility) is reserved → an author no-connect on the receptacle.

### Parts (from the global `parts/` lib + inline passives)

| ref | value | lib / part | LCSC | note |
|-----|-------|-----------|------|------|
| J1 | HDMI-019S | `parts/HDMI-019S/` (faithful dossier) | C111617 | **0 hand-built symbols** — migrated, netlist-neutral |
| U1 | M24C02-WMN6TP | `Memory_EEPROM:M24C02-WMN` | C7562 | EDID EEPROM (cable-5V fed) |
| U2 | TPD4E02B04DQAR | `parts/TPD4E02B04DQAR/` | C106794 | TMDS RX ESD (D2+D1) |
| U3 | TPD4E02B04DQAR | `parts/TPD4E02B04DQAR/` | C106794 | TMDS RX ESD (D0+CLK) |
| U4 | TPD4E05U06DQAR | `parts/TPD4E05U06DQAR/` | C138714 | slow-line ESD (DDC/CEC/HPD) |
| R1 | 1k   | `Device:R` (HPD passive assert) | C21190 | |
| R2 | 27k  | `Device:R` (CEC pull-up) | C22967 | to `+VDD_LOGIC` |
| R3 | 10k  | `Device:R` (5V-det divider top) | C25804 | |
| R4 | 15k  | `Device:R` (5V-det divider bottom) | C22809 | |
| C1 | 100n | `Device:C` (EEPROM cable-5V bypass) | C14663 | |

## Consuming it from a project

A project supplies a thin adapter declaring ONE standard `META` dict (the adapter
contract, `schgen.core.subsystem.Meta`) and forwards it:

```python
from subsystems.hdmi_rx import hdmi_rx

META = {
    # abstract subsystem net -> your real board net
    "bind": {
        "+VDD_LOGIC": "+3V3_HDMI_RX", "GND": "GND", "CHASSIS_GND": "CHASSIS_GND",
        "TMDS_RX_D2_P": "MY_TMDS_2_P", "TMDS_RX_D2_N": "MY_TMDS_2_N",
        # ... D1 / D0 / CLK ...
        "HDMI_5V_DET": "MY_5V_DET", "CEC": "MY_CEC",
    },
    # optional: tell the linker which of your sheets binds a deferred port
    # (the P line of each TMDS pair carries the pair's deferral)
    "expects": {"TMDS_RX_D2_P": "my_connector", "CEC": "my_connector", ...},
    # optional house-style override (keep your power-tree note byte-stable)
    "notes": {"draws": "CEC 27k pull-up (...)"},
}

def circuit():
    return hdmi_rx.circuit(META)
```

The four standard `META` keys (`bind` / `expects` / `buses` / `notes`) are
universal across every reusable subsystem — a typo'd top-level key is a hard
`CircuitError`, never silently dropped. `bind` renames every external **in
place, order-preserving** (POWER/GROUND/PORT only — a SIGNAL net is private
wiring and is never rebound; a SIGNAL key or a collision is a hard
`CircuitError`). Because the rename preserves net insertion order, parts, refs,
NCs, lib_ids (J1 = the faithful `HDMI-019S:HDMI-019S` dossier symbol) and port-type payloads,
**binding to the exact names a hand-written sheet used yields a byte-identical
emitted sheet.** The carrier adapter is `carrier/subsystems/hdmi_rx.py`.

## Design notes (datasheet + HDMI 1.4)

- **DC-coupled RX TMDS + ESD (LAW 0).** Each of the 8 TMDS lines is **one net**
  connector → low-cap ESD shunt tap → receiver. Two TI TPD4E02B04DQAR 4-ch arrays
  (0.2 pF/line typ ≪ the 0.5 pF/line TMDS budget, 8 kV contact) shunt the 8 lines
  (D2+D1 on U2, D0+CLK on U3) as **shunt taps, not series** — the netlist gate
  proves each lane is `{J1.pin, U.IOn}`.
- **Sink termination lives at the receiver (SI-HDMIRX-TERM).** A 7-series HR bank
  does **not** self-terminate TMDS_33, so the mandatory 2×49.9 Ω/pair-to-AVCC
  sink termination is a **layout requirement at the FPGA bank balls**, not on this
  sheet (terminating at the far connector end would stub/reflect the line).
- **EDID EEPROM, cable-5V powered.** The sink must present EDID with the board off
  (HDMI 1.4 §8.5), so the M24C02 runs from the **cable's +5V** (pin 18). DDC
  pull-ups live on the **source** side per spec — none here. E0/E1/E2 grounded
  (addr 0xA0/0x50).
- **EDID write-protect (COMP-1).** WC# (U1.7) is **hardwired** to the EEPROM's own
  cable-5V VCC node (U1.8) — a netlist fix, not a strap. A gated 3.3 V rail would
  be wrong twice: domain (dead in the board-off EDID-read case → WC# floats →
  write-enabled) and level (the 5 V-VCC EEPROM's VIH(min)=0.7·VCC≈3.5 V > 3.3 V).
  This is a permanently write-protected, fixed EDID.
- **HPD assert + presence detect.** 1k from the cable 5V to HPD asserts hot-plug
  passively (private SIGNAL, 5-V-domain — not routed to a 3V3 bank); a 10k/15k
  divider gives the `HDMI_5V_DET` port (3.15 V max at 5.25 V).
- **Slow-line ESD (HDMIRX-3).** One TI TPD4E05U06DQAR (VRWM 5.5 V > 5.25 V max
  cable rail, 0.5 pF/line, ±12 kV) protects DDC SCL/SDA (3.3 V) **and** CEC/HPD
  (5 V) in a single GND-referenced shunt cell — a 3.6 V-standoff part would
  conduct at 5 V, which is why the TMDS array is not reused here.

## Local test vs board gates

`test_hdmi_rx.py` runs the **subsystem-local** slices offline: declared abstract
interface + TMDS-pair types, model completeness (every pin netted-or-NC, ESD pads
NC), the EDID WC#-to-cable-5V hardwire (COMP-1), decoupling completeness
(design_rules DECAP/EP/STRAP), part-rating coverage + derate, the SPICE-subckt ↔
netlist passive match, the faithful `HDMI-019S:HDMI-019S` dossier symbol (0
hand-built symbols), and the bind
contract. **Cross-board** gates stay aggregated at board level and are *not*
duplicated here: the DDC source-side pull-ups, the receiver-side TMDS sink
termination, the link/port-driver graph, the full power-tree headroom, board ERC,
and the board netlist merge — all run by `schgen board`.

```bash
PYTHONPATH=. python3 -m pytest subsystems/hdmi_rx/test_hdmi_rx.py -q
```
