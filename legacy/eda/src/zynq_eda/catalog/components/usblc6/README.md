# USBLC6-4SC6 — Quad-line ESD protection for USB 2.0

Low-capacitance (typ 2.5 pF) monolithic ESD/TVS array. Four steering-
diode pairs to a shared V_BUS clamp rail (rail-to-rail topology). One
device protects two USB 2.0 D+/D- pairs OR one pair plus two single-
ended lines. SOT-23-6L (3.0 × 1.75 mm, 0.95 mm pitch).

* **Datasheet:** ST Microelectronics USBLC6-2/USBLC6-4, Rev 5, Oct 2011 — `datasheet.pdf`
* **Reference figures:** Figure 14 (USB 2.0 application), Figure 18 (PCB layout, C_BUS)
* **LCSC:** C111212

> **Note:** the file shipped in this folder is the USBLC6-2 datasheet
> (single-line variant); the USBLC6-4 part is the four-line drop-in
> covered by the same document family. Pin map, package, V_BUS reference
> rail, and external-part requirements are identical.

## Rails consumed / produced

| Net | Direction | Notes |
|---|---|---|
| `+VIN` (or `+5V`) | consumed | V_BUS pin (pin 3) — anode of positive-going clamp diodes. Local 100 nF cap. |
| `GND` | consumed | Pin 2 — return path for negative clamp current. |
| — | produced | None. Pure passive ESD array. |

## Key external parts

| Pin(s) | Part token | Value | Why (DS reference) |
|---|---|---|---|
| V_BUS (pin 3) | `100n_0402_X7R` | 100 nF | Figure 18 — C_BUS clamp-rail decoupling |

No external parts on any I/O pin — the data lines pass through the
package with no series resistance or shunt capacitance beyond the
device's intrinsic line-to-GND capacitance (~2.5 pF typ).

## Layout constraints

* **Place within 5 mm of the USB connector** on the cable-facing side
  of the D+/D- pair. The ESD protection must sit *between* the
  disturbance source (the cable) and the device being protected
  (the USB PHY).
* **Route data lines THROUGH the package**, not as a tee-stub branch
  off the main differential pair. The "optimised layout" in DS Fig 7
  has the data line entering one side of the SOT-23-6 and exiting the
  other. A stub kills the protection effectiveness and ruins the
  differential impedance.
* **90 Ω differential impedance** through the footprint; length-match
  D+/D- through the package. The 0.04 pF typ I/O-to-I/O capacitance
  contributes negligible imbalance.
* **GND pin (pin 2) → GND plane via shortest trace.** Parasitic
  inductance on the GND return adds L · dI/dt directly to the clamp
  voltage seen by the protected line (DS Sec 2.2: at 24 A/ns and 6 nH
  parasitic, this adds 144 V to V_CL).
* **V_BUS pin (pin 3) → +5V rail via shortest trace.** Same parasitic
  inductance argument applies to the positive-going clamp.

## Notes on carrier usage

* Used in the `usb_pd` block (`projects/carrier/blocks/usb_pd.py`) as
  the ESD protection between the USB-C connector and the SoM USB PHY.
  The block's `net_overrides` rename `I/O1 → USB_DP`, `I/O2 → USB_DM`;
  `I/O3` and `I/O4` are unused (single pair to protect).
* `IC_INSTANCE_COUNT["USBLC6-4SC6"] = 3` — three instances are
  consumed by the carrier: usb_pd port D+/D-, usbc_otg port D+/D-,
  and (third instance reserved for) the UART bridge USB pair.
