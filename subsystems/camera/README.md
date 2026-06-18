# camera — RPi 15-pin FFC, 2-lane MIPI CSI-2 port (reusable subsystem)

A project-agnostic, self-contained schgen subsystem: a Raspberry-Pi 15-pin FFC
camera port carrying **2 data + 1 clock** MIPI CSI-2 D-PHY lanes, with the
Xilinx **XAPP894** "7-series + external passives" HS-RX termination network, a
camera-control I2C bus, and a gated module-power rail. It declares its interface
as **abstract** port + rail names and knows nothing about any board; a consuming
project supplies a **bind map** (`abstract -> real net`) to drop it onto real
nets. Same `subsystems/<name>/` layout as the `usb_pd` exemplar.

## Package contents

| file | role |
|------|------|
| `camera.py`      | the NETLIST — `circuit(meta=None)`, abstract ports/rails |
| `camera.cir`     | SPICE subckt — the passive network (3× 100R terms, 2× I2C pull-ups, gated-rail bypass) with the abstract ports as subckt pins |
| `test_camera.py` | LOCAL electrical-correctness test (offline; runs the board gate slices on just this subsystem) |
| `README.md`      | this file |

The FFC connector is **referenced, never vendored**: its symbol / footprint /
MPN / LCSC come from the global parts library entry `SFW15R-1STE1LF`
(LCSC **C3168538**, Amphenol ICC). The connector's bare-number FFC pins stay
numeric (FFC pad *n* = RPi camera FFC pin *n*).

## The abstract interface (the reuse contract)

A consuming project binds these names. Rails classify as POWER/GROUND by name
(the `+` prefix + `GND`), exactly as real board rails do, so a standalone build
and a bound build share net classes.

### Rails (POWER / GROUND)

| abstract | class | meaning / constraint |
|----------|-------|----------------------|
| `+VDD_CAM` | POWER  | the gated camera module rail (3.3 V class), FFC pin 15. A project MUST supply a **gated** rail here: the camera-control I2C pull-ups land on it, so a powered-down camera is not back-fed through its own bus pull-ups. Local bypass 100n + 10u at the connector lives here. Budget ~300 mA (RPi V2/IMX219 typ ~250 mA). |
| `GND`      | GROUND | ground — FFC grounds (1/4/7/10) + the two mounting-plate tabs (16/17). |

### Ports (PORT)

| abstract | type | FFC pin(s) | meaning |
|----------|------|-----------|---------|
| `CSI_D0_P` / `CSI_D0_N` | diff_pair @100R | 3 / 2 | CSI-2 data lane 0 (N before P on the FFC). |
| `CSI_D1_P` / `CSI_D1_N` | diff_pair @100R | 6 / 5 | CSI-2 data lane 1. |
| `CSI_CLK_P` / `CSI_CLK_N` | diff_pair @100R | 9 / 8 | CSI-2 clock lane. |
| `CAM_SCL` / `CAM_SDA` | i2c (bus `CAM_CCI`, 400 kHz) | 13 / 14 | camera-control I2C (MIPI CCI class). 4k7 pull-ups to `+VDD_CAM` live **here**. |
| `CAM_EN`  | single | 11 | module power-enable / shutdown (RPi `CAM_GPIO0`; V2 uses it). |
| `CAM_LED` | single | 12 | LED indicator (RPi `CAM_GPIO1`; v1-module only — kept routed). |

**D-PHY pairs are NOT polarity-swappable** — P→P, N→N, no exceptions. The
diff-pair typing is authored reciprocally (P↔N) so a router/linker sees the
pairing both ways. The three **100R differential terminations (R1–R3)** are
carried in this subsystem and are **populated** (see CAM-1); place them at the
**host / SoM-connector end** of each trace, *not* at the FFC.

### Parts (from the global `parts/` lib + inline passives)

| ref | value | lib / part | LCSC |
|-----|-------|-----------|------|
| J1 | SFW15R-1STE1LF | `parts/SFW15R-1STE1LF/` (1.0 mm 15P bottom-contact FFC) | C3168538 |
| R1–R3 | 100R | `Device:R` (D-PHY diff terminations) | C22775 |
| R4, R5 | 4k7 | `Device:R` (CAM_SCL / CAM_SDA pull-ups to `+VDD_CAM`) | C23162 |
| C1 | 100n | `Device:C` (`+VDD_CAM` bypass) | C14663 |
| C2 | 10u  | `Device:C` (`+VDD_CAM` bulk)   | C15850 |
| U1, U2 | TPD4E02B04DQAR | `parts/TPD4E02B04DQAR/` (low-cap 4-ch CSI ESD array, 0.2 pF/line) | C106794 |

## Consuming it from a project

A project supplies a thin adapter declaring ONE standard `META` dict (the
adapter contract, `schgen.core.subsystem.Meta`) and forwards it:

```python
from subsystems.camera import camera

META = {
    # abstract subsystem net -> your real board net
    "bind": {
        "+VDD_CAM": "+3V3_CAM", "GND": "GND",
        "CSI_D0_P": "CAM_D0_P", "CSI_D0_N": "CAM_D0_N",
        "CSI_D1_P": "CAM_D1_P", "CSI_D1_N": "CAM_D1_N",
        "CSI_CLK_P": "CAM_CLK_P", "CSI_CLK_N": "CAM_CLK_N",
        "CAM_SCL": "CAM_SCL", "CAM_SDA": "CAM_SDA",
        "CAM_EN": "CAM_EN", "CAM_LED": "CAM_LED",
    },
    # optional: tell the linker which of your sheets will bind a deferred port
    "expects": {"CSI_D0_P": "som_j3 (bank 35)", "CAM_EN": "som_j3 (bank 33)", ...},
    # optional house-style overrides (keep your derived artifacts byte-stable)
    "buses": {"i2c": "CAM_I2C"},                 # the camera-control bus-group name
    "notes": {"draws": "RPi camera module budget (...)"},   # power-tree draw note
}

def circuit():
    return camera.circuit(META)
```

The four standard `META` keys (`bind` / `expects` / `buses` / `notes`) are
universal across every reusable subsystem — a typo'd top-level key is a hard
`CircuitError`, never silently dropped. `bind` renames every external **in
place, order-preserving** (POWER/GROUND/PORT only — a SIGNAL net is private
wiring and is never rebound; a SIGNAL key or a collision is a hard
`CircuitError`). Because the rename preserves net insertion order, parts, refs
and port-type payloads (including the reciprocal diff-pair pairing),
**binding to the exact names a hand-written sheet used yields a byte-identical
emitted sheet.** The carrier adapter is `carrier/subsystems/camera.py`.

## Design notes (reference design + bring-up contract)

- **D-PHY on a 7-series HR bank — the honest part (XAPP894).** A Zynq-7000 HR
  bank has no native MIPI D-PHY receiver. The standard solution (Xilinx
  **XAPP894** "D-PHY Solutions", as used by the Xilinx MIPI CSI-2 RX Subsystem
  in "7-series + external passives" mode and by Digilent's Pcam ports) is
  IOSTANDARD **LVDS_25** on a **2.5 V VCCO** bank with a **fixed external 100R**
  differential termination at the **FPGA end** of each pair. HR-bank D-PHY RX
  tops out around ~800 Mb/s/lane — 2 lanes cover the IMX219 1080p30 / 8 MP
  stills profiles (RPi V2 defaults). Higher-rate / 4-lane sensors (HQ IMX477 max
  modes) are out of scope for this 2-lane port. **Consequence:** the host's
  CSI bank is 2.5 V-only (a local LDO supplies VCCO); nothing 3.3 V may share
  it — so `CAM_SCL/SDA/EN/LED` (3.3 V logic) must land on a **different** bank
  from the CSI lanes.

- **CAM-1 — static 100R vs D-PHY Low-Power signalling.** R1–R3 sit
  *permanently* across each pair. In D-PHY **HS** bursts that is exactly right
  (the LVDS RX needs the 100R differential termination, and a 7-series HR-bank
  RX has **no** run-time `DIFF_TERM` that follows the burst — the XAPP894
  topology relies on the fixed external 100R; the IBUFDS has no HS/LP-switched
  on-die termination to gate). But in **LP** mode the two wires of a pair are
  driven *independently* (each a single-ended ~1.2 V CMOS-class level, not a
  differential swing): a static cross-pair 100R then bleeds current between the
  two LP-driven lines, pulling the LP-high line down and degrading LP levels and
  Start-of-Transmission detection.
  **Decision:** keep the 100R **populated** (HS genuinely needs it — DNP'ing it
  would break HS reception, and the HR-bank RX does not gate `DIFF_TERM`, so the
  100R is **not** redundant) and restore LP observability the XAPP894 way: the
  XAPP894 LP RX does *not* remove the 100R — it **taps each line through a
  resistor divider** into an extra single-ended LVCMOS25 bank input so the
  fabric can read LP levels *despite* the HS termination.

- **XAPP894 LP-divider stuffing option (off this sheet).** That LP tap network
  is a **documented DNP stuffing option**, *not* emitted here — because (i) the
  LP single-ended taps land on the **host side**, off this FFC sheet (the
  divider belongs at the host-connector end alongside R1–R3), and (ii) the
  single-ended LP bank pins are spent at CSI-2 RX IP integration, where
  stuffed-vs-DNP is finally decided. Recipe (place at the host-connector end,
  *not* the FFC): per LP-observed line, a series + shunt divider from the line
  to a single-ended LVCMOS25 bank input — divide the 1.2 V LP-high down to a
  clean bank-safe level (e.g. series 100k / shunt 100k, 0402; XAPP894 uses
  ~100k-class taps so the HS path is not loaded). For **video-only** continuous
  capture with fixed timing the dividers may stay DNP and LP events are inferred
  (fragile across sensor resets); reserving the footprints makes a later
  populate a BOM-line change with zero netlist/layout churn here.

- **Gated rail + pull-ups (back-feed).** The I2C bus pull-ups (4k7) tie to
  `+VDD_CAM`, the **gated** module rail — a powered-down camera must not be
  back-fed through its own bus pull-ups. `CAM_EN` additionally gives a
  logic-level shutdown independent of the rail gate. At the connector:
  100n + 10u local bypass.

- **Connector contact orientation (verified).** The committed `SFW15R-1STE1LF`
  (LCSC C3168538) is the **bottom-contact** variant (Amphenol drawing 10172241,
  sheet 2 note 1: "-1ST is the BOTTOM CONTACT type"); 1.0 mm pitch confirmed
  from the generated footprint (pads at exactly 1.00 mm; the EasyEDA package
  string "…P0.50…" is an LCSC CAD-library typo — the geometry is correct). The
  top-contact `-2STE1LF` (C3167933) shares the **identical** recommended PCB
  layout, so a late top/bottom swap is a **BOM-line change only** (zero
  layout/netlist impact). A bottom-contact part needs the cable contact face
  toward the PCB — the enclosure's cable fold must confirm contacts-down, else
  swap to the top-contact part.

- **ESD.** The three CSI D-PHY pairs are clamped by two low-cap TI
  TPD4E02B04DQAR 4-ch arrays (U1 = D0+D1, U2 = CLK), GND-referenced shunt taps
  on the existing lane nets (0.2 pF/line << the D-PHY budget — the same part
  hdmi_rx uses on TMDS; valid even when `+VDD_CAM` is gated off, no back-power).
  Added 2026-06-18 (user request: ESD on the camera FFC). The slow control lines
  (I2C / EN / LED) stay unclamped — a `TPD4E05U06`-class array there remains a
  stuffing option (adversarial review: not warranted on the short control tail).

- **22-pin cameras.** Pi Zero / Pi-5-style 22-pin cameras need a 22→15 adapter
  cable — by design, not a subsystem change.

## Local test vs board gates

`test_camera.py` runs the **subsystem-local** slices offline: declared abstract
interface, reciprocal diff-pair typing, model completeness (every FFC pad
netted), the design-rules DECAP/EP/STRAP/**I2C** slice (the camera's I2C
pull-ups live here, on the gated rail, so the I2C-pull-up rule is exercised and
satisfied), part-rating coverage + per-rail cap derating, the SPICE-subckt ↔
netlist passive match, and the bind / meta contract. **Cross-board** gates stay
aggregated at board level and are *not* duplicated here: the link / port-driver
graph (which sheet binds each CSI lane / control line), the full power-tree
headroom, board ERC and the board netlist merge — all run by `schgen board`.

```bash
PYTHONPATH=. python3 -m pytest subsystems/camera/test_camera.py -q
```
