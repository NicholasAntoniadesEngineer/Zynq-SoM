# hdmi_rx — HDMI Type-A sink: receptacle + TMDS-RX ESD + EDID EEPROM

A project-agnostic, reusable schgen subsystem providing an HDMI Type-A receptacle
as a video **sink** on the Zynq-7000 SoM carrier. It carries the four DC-coupled
TMDS RX lanes into the receiver bank behind low-cap ESD, a cable-5V-powered EDID
EEPROM on the source-mastered DDC bus, passive hot-plug-detect assert, a 5V
presence divider, and CEC. It declares its interface as abstract port/rail names
and knows nothing about any board; a consuming project supplies a bind map.

## Interface

The subsystem exposes abstract net names; a consuming project binds them via the
standard `META` adapter contract (`schgen.core.subsystem.Meta`). Rails classify by
name (leading `+` → POWER; `GND`/`CHASSIS_GND` → GROUND), so standalone and bound
builds share net classes. `bind` rebinds externally-visible nets in place and
order-preserving, so binding to the names a hand-written sheet used yields a
byte-identical emitted sheet.

**Rails:** `+VDD_LOGIC` (POWER, gated module rail — only the CEC pull-up draws
here), `GND`, `CHASSIS_GND` (the four HDMI shell legs; star-bonded to `GND` by
the consuming board).

**Ports:** `TMDS_RX_{D2,D1,D0,CLK}_{P,N}` (four RX differential pairs, typed
`tmds_pair`, into the receiver bank), `HDMI_5V_DET` (cable-5V presence-detect
divider output), `CEC` (3V3-domain CEC to the receiver).

The DDC I2C (`HDMI_RX_SDA`/`HDMI_RX_SCL`), HPD assert (`HDMI_RX_HPD`) and the
cable-5V quasi-rail (`HDMI_RX_5V`) are **private SIGNAL wiring** — they run
entirely connector ↔ EEPROM ↔ ESD on this sheet and are never part of the
contract. HDMI pin 14 (HEC/Utility) is reserved → author no-connect.

```python
from subsystems.hdmi_rx import hdmi_rx

META = {
    "bind": {
        "+VDD_LOGIC": "+3V3_HDMI_RX", "GND": "GND", "CHASSIS_GND": "CHASSIS_GND",
        "TMDS_RX_D2_P": "MY_TMDS_2_P", "TMDS_RX_D2_N": "MY_TMDS_2_N",
        # ... D1 / D0 / CLK ...
        "HDMI_5V_DET": "MY_5V_DET", "CEC": "MY_CEC",
    },
    # optional: tell the linker which sheet binds a deferred port
    # (the P line of each TMDS pair carries the pair's deferral)
    "expects": {"TMDS_RX_D2_P": "my_connector", "CEC": "my_connector"},
    # optional power-tree draw-note override
    "notes": {"draws": "CEC 27k pull-up (...)"},
}

def circuit():
    return hdmi_rx.circuit(META)
```

The carrier adapter is `carrier/subsystems/hdmi_rx.py`.

## Design

**Connector.** J1 is the SOFNG HDMI-019S receptacle, drawn from its faithful
`parts/HDMI-019S/` dossier symbol. The dossier box lays its 23 pins out by package
edge (1–9 left, 10–23 right, +5V top, GND bottom), with each shield pad distinct:
TMDS shields (2/5/8/11) and pin 17 to `GND`; the four shell tabs (20–23) to
`CHASSIS_GND`. Pin 14 is reserved → no-connect.

**DC-coupled TMDS RX + ESD.** Each of the eight single-ended TMDS lines is one net
from the receptacle to the receiver bank — DC-coupled, with ESD applied as a shunt
TAP, not a series break (the netlist proves each lane is `{J1.pin, U.IOn}`). Two
TI TPD4E02B04DQAR 4-channel GND-referenced arrays cover the eight lines (D2+D1 on
U2, D0+CLK on U3); chosen for 0.2 pF/line typ I/O capacitance (≪ the 0.5 pF/line
TMDS budget) and 8 kV contact (IEC 61000-4-2). Spare USON-10 pads are no-connect.

**Sink termination lives at the receiver.** TMDS sink termination (2×49.9 Ω/pair
to a local 3.3 V AVCC island, 8 R for the 4 pairs) is a mandatory **layout
requirement placed at the FPGA bank balls**, not on this sheet. A 7-series HR bank
cannot self-terminate TMDS_33 (only HP banks implement DIFF_TERM, UG471), so
external sink termination is required — but terminating at the far connector end
would stub the line and reflect, so it must sit at the receiver end.

**EDID EEPROM, cable-5V powered.** U1 is an ST M24C02 (2-Kbit I2C EEPROM, stock
`Memory_EEPROM:M24C02-WMN` symbol) on the source-mastered DDC bus. It runs from
the cable's +5V (pin 18) so the sink presents EDID even when the consuming board
is off (HDMI 1.4 §8.5). E0/E1/E2 are grounded (address 0xA0/0x50). DDC pull-ups
live on the source side per spec — none are duplicated here. C1 (100n) bypasses
the EEPROM VCC.

**EDID write-protect.** WC# (U1.7) is hardwired to the EEPROM's own cable-5V VCC
node (U1.8), so a runtime DDC write can never corrupt the fixed EDID. This is a
permanently write-protected EDID by design, with no field-reprogram path. A gated
3.3 V rail would be wrong twice — domain (dead in the board-off EDID-read case →
WC# floats → write-enabled) and level (the 5 V-VCC EEPROM's VIH(min) =
0.7·VCC ≈ 3.5 V > 3.3 V).

**HPD assert + presence detect.** R1 (1k) from cable 5V to HPD (pin 19) asserts
hot-plug passively, so a plugged source reads EDID with zero board involvement.
HPD is 5-V-domain and stays private (not routed to a 3V3 bank). R3/R4 form a
10k/15k divider on the cable 5V giving `HDMI_5V_DET` (3.15 V max at 5.25 V,
LVCMOS33-safe) for off-sheet source-presence sensing.

**CEC.** Routed to the receiver with the spec 27k pull-up (R2) to the gated module
rail `+VDD_LOGIC` — the only load on that rail (~0.12 mA when CEC is driven low).

**Slow-line ESD.** U4 is one TI TPD4E05U06DQAR (4-channel, GND-referenced, no VCC
pin) protecting the four slow lines as detached shunt taps: D1+ = SCL, D1- = SDA
(DDC, 3.3 V); D2+ = CEC (3.3 V), D2- = HPD (5 V). Its VRWM = 5.5 V is above the
5.25 V max cable rail, so the one part safely serves both the 3.3 V DDC pair and
the 5 V CEC/HPD lines (a 3.6 V-standoff part would conduct at 5 V, which is why
the TMDS array is not reused here). 0.5 pF/line typ, ±12 kV IEC 61000-4-2. Spare
USON-10 pads are no-connect.

## Parts

| ref | value | lib / part | LCSC |
|-----|-------|-----------|------|
| J1 | HDMI-019S | `HDMI-019S:HDMI-019S` (dossier) | C111617 |
| U1 | M24C02-WMN6TP | `Memory_EEPROM:M24C02-WMN` | C7562 |
| U2 | TPD4E02B04DQAR | `TPD4E02B04DQAR` (dossier) | C106794 |
| U3 | TPD4E02B04DQAR | `TPD4E02B04DQAR` (dossier) | C106794 |
| U4 | TPD4E05U06DQAR | `TPD4E05U06DQAR` (dossier) | C138714 |
| R1 | 1k | `Device:R` | C21190 |
| R2 | 27k | `Device:R` | C22967 |
| R3 | 10k | `Device:R` | C25804 |
| R4 | 15k | `Device:R` | C22809 |
| C1 | 100n | `Device:C` | C14663 |

LCSC for J1/U1/U2/U3/U4 come from the global `parts/<MPN>/` dossiers.

## Build & test

`test_hdmi_rx.py` runs the subsystem-local electrical slices offline: abstract
interface + TMDS-pair types, model completeness (every pin netted-or-NC, ESD pads
NC), the EDID WC#-to-cable-5V hardwire, decoupling/strap rules, part-rating
coverage, the SPICE-subckt ↔ netlist passive match, the dossier symbol, and the
bind contract. Cross-board gates (DDC source pull-ups, receiver TMDS termination,
link graph, power-tree headroom, ERC, board netlist merge) run at board level.

```bash
PYTHONPATH=. python3 -m pytest subsystems/hdmi_rx/test_hdmi_rx.py -q
```
