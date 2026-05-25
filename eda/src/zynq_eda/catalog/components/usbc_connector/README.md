# TYPE-C-31-M-12 — USB Type-C SMD receptacle (16-pin, USB 2.0)

16-pin USB Type-C receptacle, USB 2.0 data only (no USB 3.x SuperSpeed
lanes). 5 A / 20 V rated, fully reversible, with the standard 4×GND +
4×VBUS power layout, dual CC pins, dual D+/D- pairs (orientation-
mirrored), dual SBU, and a shield with 4 mounting tabs.

* **Datasheet:** HRO TYPE-C-31-M-12 (mechanical drawing, 1 page) — `datasheet.pdf`
* **Reference:** USB Type-C R2.1 Sec 4.5 (Rd termination), USB 2.0 Sec 7.2.4
* **LCSC:** C165948 (Korean Hroparts Elec)

## Rails consumed / produced

| Net | Direction | Notes |
|---|---|---|
| `VBUS` | produced | Cable VBUS (5 V default, up to 20 V via PD). Carried out of the connector as the carrier's `+VIN`. |
| `GND` | consumed | Signal ground — 4 GND pins (A1, A12, B1, B12). |
| `CHASSIS_GND` | consumed | Mounting-tab return through 1 MΩ + 100 nF AC-coupling network. Isolated from signal GND. |

The connector itself does not consume any power rail — it's a passive
plug interface; the 5.1 kΩ Rd resistors are pulled to signal GND only.

## Key external parts (per pin)

| Pin(s) | Part token | Value | Why |
|---|---|---|---|
| CC1 (A5) | `5k1_0402_1%` | 5.1 kΩ | USB-C R2.1 §4.5.1.2.1 — Rd sink advertisement |
| CC2 (B5) | `5k1_0402_1%` | 5.1 kΩ | USB-C R2.1 §4.5.1.2.1 — one Rd per CC for reversibility |
| VBUS | `10u_0402_X5R` | 10 µF | USB-PD R3.1 §7.1.16 — sink bulk capacitance (1–10 µF) |
| VBUS | `100n_0402_X7R` | 100 nF | USB 2.0 §7.2.4.1 — receptacle HF bypass |
| SHIELD↔CHASSIS_GND | `1M_0402_1%` | 1 MΩ | USB-IF compliance — shield bleed resistor |
| SHIELD↔CHASSIS_GND | `100n_0402_X7R` | 100 nF | USB-IF compliance — shield AC-coupling |

Pins D+, D-, SBU1, SBU2 are routed straight through to downstream
stages (USBLC6 ESD array → USB PHY, or to the STM32 for SBU1=USBOTG_ID)
with no passives at the connector pin.

## Layout constraints

* **D+/D- routing** — 90 Ω differential impedance from each connector
  pad to the USBLC6 / USB PHY. Tie A6 ↔ B6 (D+ pair) and A7 ↔ B7 (D-
  pair) as close to the connector as possible so either plug
  orientation lands on the same pair.
* **VBUS trace width** — ≥ 0.5 mm per VBUS pin (the connector has 4
  VBUS pins to share 5 A; 0.5 mm per pin per IPC-2221A handles >1 A
  each without exceeding the 20 °C rise budget).
* **Shield isolation** — connector shield tabs and the 4 mounting tabs
  go to `CHASSIS_GND` (a separate copper region), NOT directly to
  signal GND. The 1 MΩ + 100 nF network joins them, breaking DC ground
  loops while shunting ESD energy.
* **Rd placement** — 5.1 kΩ resistors within 5 mm of the connector
  CC pins to minimise added CC capacitance.
* **VBUS bypass** — bulk + HF caps within 10 mm of the nearest VBUS pin.

## Notes on carrier usage

* Used in **two** carrier blocks:
  * `usb_pd` (`projects/carrier/blocks/usb_pd.py`) — the PD-capable port.
    CC1/CC2 here go to FUSB302 + the redundant 5.1 kΩ Rd.
  * `usbc_otg` (`projects/carrier/blocks/usbc_otg.py`) — the OTG port.
    CC1/CC2 here go to STM32 control signals + the 5.1 kΩ Rd handles
    mechanical-only sink detection.
* `IC_INSTANCE_COUNT["USBC_SINK"] = 2` — two instances on the carrier.
* The token `USBC_SINK` in the REFCIRCUITS dict is the historical key
  for this part_mpn; the symbol library uses `USBC_16P`.
