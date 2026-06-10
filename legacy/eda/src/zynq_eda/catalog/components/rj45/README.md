# Amphenol RJHSE5380 - Shielded RJ45 jack (magnetics-less, with LEDs)

Amphenol Communications Solutions RJHSE5380 (LCSC C464586) - a bare
shielded 8P8C RJ45 jack with two integrated LED windows. The
RJHSE-538x series ships in WITH-LEDs and WITHOUT-LEDs variants on the
same footprint; the carrier uses the WITH-LEDs part (the datasheet
PDF in this folder happens to be the WITHOUT-LEDs mechanical drawing,
so refer to the Amphenol product page for the LED pinout).

This jack contains NO magnetics — common-mode termination and
isolation are provided externally by `components/hx5008nlt`. Splitting
the magnetics out as a discrete module makes MDI signals scope-
probable between PHY and magnetics during board bring-up.

## Rails

| Rail          | Pin          | Direction | Notes                                            |
|---------------|--------------|-----------|--------------------------------------------------|
| `+3V3`        | (via 330R)   | input     | LED anode supply (~4mA per LED)                  |
| `CHASSIS_GND` | shield tabs  | passive   | Direct copper bond to frame ground island        |

## Key external parts

| From pin | To net | Part token        | Qty | Why                                              |
|----------|--------|-------------------|-----|--------------------------------------------------|
| LED1_A   | +3V3   | `330R_0402_1%`    | 1   | LED1 (Link) current limit: ~4 mA at V_F = 2.0V   |
| LED2_A   | +3V3   | `330R_0402_1%`    | 1   | LED2 (Activity) current limit: ~4 mA            |

Shield tabs route directly to CHASSIS_GND copper — no resistor or
cap (HX5008NLT's Bob Smith network already AC-couples chassis to
signal ground).

No external R/C on the eight MDI pins — IEEE 802.3 termination is
internal to the magnetics module and the PHY.

## Layout constraints

* Tie all shield-mounting legs to the CHASSIS_GND copper island.
  CHASSIS_GND joins signal GND at a single star point near the
  carrier's power-entry connector.
* Keep this jack within 30mm of the HX5008NLT magnetics. Route the
  four MDI pairs as 100R differential, length-matched within 0.5mm.
* LED traces (LED1_A / LED2_A) are low-speed and route freely; keep
  them >= 3x line width from MDI pairs to avoid coupling switching
  noise onto the cable.

## Carrier usage

* `blocks/ethernet.py` instantiates one RJHSE5380 at the end of the
  Ethernet chain (PHY -> HX5008NLT magnetics -> RJ45). The LED anodes
  pull up to +3V3 via the 330R resistors here; the cathodes (LED1_K,
  LED2_K — not exposed in the simplified symbol) are driven low by
  the SoM PHY's open-drain LED outputs (LINK and ACT).
