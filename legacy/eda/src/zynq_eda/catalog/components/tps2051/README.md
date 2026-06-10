# TPS2051CDBVR -- USB current-limited VBUS load switch

TI TPS2051C 0.5 A current-limited, active-high-enable USB power-
distribution switch. Used as the +5 V VBUS source for the carrier's
USB-OTG receptacle, controlled by the STM32 co-processor.

```
+VIN ----IN [TPS2051C] OUT---- VBUS_OTG (USB-C A4/A9/B4/B9)
              |
              EN <-- STM32_USBOTG_VBUS_EN (active high)
              ~FLT --> STM32_USBOTG_OC_N (open-drain, 10k pull-up to +3V3)
              GND
```

## Rails consumed / produced

- **Consumes:** `+VIN` (5 V nominal; DS V_IN range 4.5 - 5.5 V)
- **Produces:** `VBUS_OTG` (gated 5 V to the USB-C OTG connector,
  active when `STM32_USBOTG_VBUS_EN` is high)
- **GND:** common ground

The switch enters constant-current mode at I_OS (typ 1.3 A, max 1.8 A
for the C variant per DS Sec 7.7 Electrical Characteristics) when
the downstream load draws more than the rated 0.5 A. Sustained over-
current trips thermal shutdown (T_J ~135 degC, DS Sec 8.3.4); the
~FLT flag asserts after a 9 ms deglitch (Sec 8.3.5).

## Key external parts (DS Fig 23 Typical Application, p.17)

| Part                              | Where           | Purpose                                                          | Datasheet ref |
|-----------------------------------|-----------------|------------------------------------------------------------------|---------------|
| 1 uF X7R 0402 (`1u_0402_X7R`)     | IN -> GND       | Input bulk; >= 0.1 uF per DS (we use 1 uF for inrush headroom)   | Sec 9.2.2.1   |
| 100 nF X7R 0402 (`100n_0402_X7R`) | IN -> GND       | Local HF bypass matching DS Fig 23's 0.1 uF                       | Fig 23, Sec 11 |
| 100 uF 1206 X5R (`100u_1206_X5R`) | OUT -> GND      | Output bulk; 120-150 uF recommended for USB-2.0 VBUS compliance  | Sec 9.2.2.1   |
| 100 nF X7R 0402 (`100n_0402_X7R`) | OUT -> GND      | HF bypass on OUT (complements bulk for downstream transients)    | Sec 9.2.2.1   |
| 10 k 0402 1% (`10k_0402_1%`)      | ~FLT -> +3V3    | Pull-up for the open-drain fault output                          | Sec 8.3.5 + Fig 23 |

The DS clearly identifies pin 4 as the enable input (active-high for the
TPS2051**C** variant) -- this differs from the active-low TPS2051 (no 'C')
and from the TPS2041C / TPS2061C / TPS2068C low-active variants in the
same family. Use of the wrong variant will leave the load switch
inverted.

## Layout constraints (DS Sec 11)

- **0.1 uF IN bypass close to IN/GND pins with a low-inductance
  trace.** (Sec 11.1 #1)
- **>= 10 uF OUT bulk close to OUT/GND pins.** A 120-150 uF total is
  recommended to meet USB 2.0 VBUS standard requirements; the
  combined 100 uF + 100 nF in our refcircuit meets this with the
  upstream +VIN bulk caps as additional headroom. (Sec 11.1 #2)
- **Copper pour around the device** to spread heat: the DBV SOT-23-5
  has no thermal pad, so theta_JA scales strongly with adjacent
  copper area. (Sec 11.3 Power Dissipation)
- **EN must be driven** -- never floating. The trace from the STM32
  GPIO should be short and routed away from switching nodes to
  prevent false enable triggers during VBUS turn-on.
- A short, wide IN-to-OUT path under the device minimises switch
  R_DS(on) drop at 0.5 A (DS Sec 11.2 Layout Example).

## Notes on usage on the carrier

The `usbc_otg` block (`projects/carrier/blocks/usbc_otg.py`)
instantiates exactly one TPS2051C (U1) between +VIN and VBUS_OTG. The
STM32 co-processor enables the switch via `STM32_USBOTG_VBUS_EN` when
firmware decides to act as a USB host (OTG mode), and reads the
`STM32_USBOTG_OC_N` fault flag asynchronously to detect downstream
shorts or over-current conditions on attached USB-OTG peripherals.

The 0.5 A current limit is comfortably above USB 2.0's 500 mA
high-power device budget but below USB 3.0's 900 mA -- a TPS2061C
(1 A, same pinout / same package) is the drop-in upgrade if USB 3.0
host-power compliance becomes a requirement.
