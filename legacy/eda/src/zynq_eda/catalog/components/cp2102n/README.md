# CP2102N-A02-GQFN24R — USB to UART bridge

Single-chip USB 2.0 full-speed (12 Mbps) to UART bridge. Integrates the
USB PHY, an internal 5 V→3.3 V LDO, a 48 MHz oscillator (no external
crystal), and 4 GPIO/modem-control pins. QFN-24 (4 × 4 mm, 0.5 mm
pitch). Cross-platform VCP / USBXpress drivers.

* **Datasheet:** Silicon Labs CP2102N, Rev 1.5, 2021 — `datasheet.pdf`
* **Reference figures:** Figure 2.1 (bus-powered + internal regulator), Figure 2.5 (USB pins with sense divider)
* **LCSC:** C969151

## Rails consumed / produced

| Net | Direction | Notes |
|---|---|---|
| `+VIN` | consumed | Bus-power: USB cable VBUS goes to the VREGIN pin (5 V input to the internal LDO) and through the 22.1 k / 47.5 k divider into the VBUS sense pin. |
| `CP2102N_VDD33` | produced (local) | 3.3 V regulator output at the VDD pin (100 mA max per DS Table 3.6). Also feeds the chip's own VIO logic supply on the carrier. |
| `GND` | consumed | EP (pin 25) bonded to GND plane with via stitch. |

The 3.3 V output is **not** routed off-block — the regulator only
sources the CP2102N itself (the chip draws ~9.5 mA typ at 115.2 kbaud,
13.7 mA at 3 Mbaud per DS Table 3.2). For carrier 3.3 V rails the
TLV75733 LDO is the source.

## Key external parts (datasheet-mandated)

| Pin(s) | Part token | Value | Why (DS reference) |
|---|---|---|---|
| VREGIN | `4u7_0402_X5R` | 4.7 µF | DS Fig 2.1 — bulk on each power pin |
| VREGIN | `100n_0402_X7R` | 100 nF | DS Fig 2.1 — HF bypass on each power pin |
| VDD | `4u7_0402_X5R` | 4.7 µF | DS Fig 2.1 — regulator output bulk |
| VDD | `100n_0402_X7R` | 100 nF | DS Fig 2.1 — regulator output HF bypass |
| VIO | `100n_0402_X7R` | 100 nF | DS Fig 2.1 — bypass on every power pin |
| VBUS ↔ +VIN | `22k1_0402_1%` | 22.1 kΩ | DS Sec 2.3 — VBUS sense divider upper leg |
| VBUS ↔ GND | `47k5_0402_1%` | 47.5 kΩ | DS Sec 2.3 — VBUS sense divider lower leg |
| ~{RST} | `1k_0402_1%` | 1 kΩ | DS Sec 2.1 — RSTb pull-up to VIO |

The 22.1 k / 47.5 k divider is **mandatory** for bus-powered operation
— the VBUS pin's absolute max is VIO + 2.5 V = 5.8 V with 3.3 V VIO
(Table 3.10), but USB cable VBUS reaches 5.25 V. The divider scales
5.0 V to 3.41 V at the pin (still above the VIH = VIO − 0.6 V = 2.7 V
threshold) and limits current under tolerance stack-up.

No external crystal — DS Table 3.5 specifies the integrated 48 MHz
oscillator at ± 0.7 %.

## Layout constraints

* **Each power pin gets its own 4.7 µF + 0.1 µF.** The datasheet
  caption is explicit: "4.7 µF and 0.1 µF bypass capacitors required
  for each power pin placed as close to the pins as possible." Do not
  share a single 4.7 µF across VREGIN + VDD + VIO.
* **VBUS sense divider on the chip side**, not the cable side. The
  current-limit / level-shift function only works if the divider sits
  next to pin 8.
* **Exposed pad (EP, pin 25)** — 3 × 3 via stitch to GND plane.
  Required for thermal performance (θ_JA = 30 °C/W on QFN24 per
  Table 3.9, dependent on EP bonding).
* **USB D+/D-** — 90 Ω differential impedance from the USB connector
  pads (or USBLC6 output if ESD is upstream) to pins 3/4. Length-match
  within 2 mm.

## Notes on carrier usage

* Used in the `uart_bridge` block (`projects/carrier/blocks/uart_bridge.py`)
  as the **debug-console USB-to-UART bridge** for the Zynq PS UART0.
* The block sets `lib_id="Interface_USB:CP2102N-Axx-xQFN24"` — the
  refcircuit's `pin_net_overrides` use that symbol's exact pin names
  (`~{RST}`, `~{RTS}`, `~{CTS}`, `VREGIN`, etc.) so the cluster pass
  finds them by name.
* `IC_INSTANCE_COUNT["CP2102N-A02-GQFN24R"] = 1` — one bridge on the carrier.
* **Power topology**: VREGIN is the only carrier-facing power input
  (named `+VIN` in the block). The block does **not** consume `+3V3`
  from the rest of the carrier — the bridge is self-powered from the
  USB cable.
* **Net direction convention** for UART: the carrier net naming
  (`ZYNQ_PS_UART0_RXD` = the Zynq's RX pin) means the CP2102N's TXD
  drives `ZYNQ_PS_UART0_RXD`, and the CP2102N's RXD listens on
  `ZYNQ_PS_UART0_TXD`. Same swap for flow control:
  CP2102N `~{RTS}` ↔ Zynq `CTS_N`, CP2102N `~{CTS}` ↔ Zynq `RTS_N`.
