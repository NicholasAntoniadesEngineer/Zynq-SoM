# FUSB302BMPX — USB Type-C Port Controller w/ USB-PD

I2C-controlled USB Type-C / USB-PD (BMC PHY) port controller. Negotiates
CC1/CC2 attach detection, plug orientation, and Power Delivery messaging
on behalf of a host MCU. WQFN-14 (2.5×2.5 mm, 0.5 mm pitch).

* **Datasheet:** ONsemi FUSB302B, Rev 5, Aug 2021 — `datasheet.pdf`
* **Reference schematic:** Figure 18 + Table 43 (Recommended Component Values), p. 30
* **LCSC:** C442699

## Rails consumed / produced

| Net | Direction | Notes |
|---|---|---|
| `+3V3` | consumed | VDD (2.7–5.5 V per DS Table 8) — chip supply. Also feeds `+3V3_SC` (filtered/sense-isolated 3V3) for I2C pull-ups. |
| `+VIN` | consumed | VBUS sense — connected to the USB-C VBUS rail through a pin bypass + carrier sense divider. Abs-max 28 V (Table 7). |
| `GND` | consumed | Signal ground; EP (exposed pad) bonded to GND plane with via stitch. |
| — | produced | None. The FUSB302 is a *controller* — VBUS power is gated by the upstream connector + (separately) the TPS2051C load switch. |

VCONN is not sourced by the carrier: this design is a SNK-only role on
the FUSB302 port, so VCONN_1 / VCONN_2 carry only their datasheet-mandated
bypass + bulk caps for the internal VCONN switch's quiet return path.

## Key external parts (datasheet-mandated)

| Pin(s) | Part token | Value | Why (DS reference) |
|---|---|---|---|
| VDD | `1u_0402_X7R` | 1 µF | Table 43 C_VDD2 — bulk |
| VDD | `100n_0402_X7R` | 100 nF | Table 43 C_VDD1 — HF bypass |
| VBUS | `100n_0402_X7R` | 100 nF | Figure 18 — VBUS pin bypass |
| VBUS↔+VIN | `1M_0402_1%` | 1 MΩ | Carrier VBUS sense divider (upper leg, R1) |
| VBUS↔GND | `100k_0402_1%` | 100 kΩ | Carrier VBUS sense divider (lower leg, R2) |
| CC1 | `200p_0402_C0G` | 200 pF | Table 43 C_RECV — receiver filter (200–600 pF range) |
| CC2 | `200p_0402_C0G` | 200 pF | Table 43 C_RECV |
| VCONN_1 | `10u_0603_X7R` | 10 µF | Table 43 C_BULK (10 µF min) |
| VCONN_1 | `100n_0402_X7R` | 100 nF | Table 43 C_VCONN |
| VCONN_2 | `10u_0603_X7R` | 10 µF | Table 43 C_BULK (paralleled on same VCONN net) |
| VCONN_2 | `100n_0402_X7R` | 100 nF | Table 43 C_VCONN |
| SDA | `4k7_0402_1%` | 4.7 kΩ | Table 43 R_PU — I2C pull-up to +3V3_SC |
| SCL | `4k7_0402_1%` | 4.7 kΩ | Table 43 R_PU |
| INT_N | `4k7_0402_1%` | 4.7 kΩ | Table 43 R_PU_INT — open-drain pull-up (was 10 k in older revision) |

The internal 5.1 kΩ Rd is implemented inside the FUSB302 (DS Fig 6 — the
PULLDOWN_SWITCH pulls each CC pin to 5.1 kΩ Rd when configured as a SNK
via `Switches0.PDWN1`/`PDWN2`). The 5.1 kΩ Rd on the USB-C connector
refcircuit is a redundant fallback for mechanical-only sink mode.

## Layout constraints

* **CC1/CC2** — 90 Ω differential impedance to the USB-C connector,
  length-matched within 5 mm. Place C_RECV (200 pF) next to the
  FUSB302 pin (not next to the connector); per Figure 18 the receiver
  filter is on the FUSB302 side.
* **VDD decoupling** — 100 nF within 1 mm of pin 3, 1 µF within 3 mm.
* **VBUS sense** — keep trace from USB-C VBUS to FUSB302 pin 2 under
  10 mm, ≥ 0.3 mm wide. The VBUS comparator trip thresholds are sub-
  volt (Table 10 vBC_LVL ≤ 1.31 V at max range) so series inductance
  matters.
* **Exposed pad (EP, pin 15)** — connect to PCB GND plane with a 3×3
  via stitch (thermal + ground impedance).
* **I2C pull-up rail** — VPU must be in [1.71 V, VDD] (Table 13 note 6).
  Pull-ups tie to `+3V3_SC` (the same rail the STM32 I2C controller's
  VDD comes from) to keep VOH compatible.

## Notes on carrier usage

* Used in the `usb_pd` block (`projects/carrier/blocks/usb_pd.py`) as
  the controller for the **PD-capable USB-C port** (J1). The STM32G431
  on the SoM is the I2C master on `STM32_I2C2_*`; `STM32_FUSB302_INT`
  is the open-drain wire-OR interrupt.
* Not used in `usbc_otg` — that port is a simple sink/host without PD
  negotiation; CC termination there is provided by the 5.1 kΩ Rd
  carried in `USBC_DEVICE_REFCIRCUIT`.
