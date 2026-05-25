# TLV757P-family 1 A LDO (TLV75718 / TLV75725 / TLV75733)

Fixed-output low-dropout linear regulator family from TI used to derive
the carrier's regulated rails from +VIN (5 V from USB-C). Three variants
are stocked, identical apart from output voltage:

| Variant       | V_OUT | Use on the carrier                     |
|---------------|-------|----------------------------------------|
| TLV75718PDBVR | 1.8 V | FPGA 1.8 V banks, 1.8 V peripherals    |
| TLV75725PDBVR | 2.5 V | SSTL / DCI reference rail              |
| TLV75733PDBVR | 3.3 V | Main +3V3 carrier rail (default LDO)   |

All three are SOT-23-5 (DBV) with the same pinout (1=IN, 2=GND, 3=EN,
4=NC, 5=OUT) and an identical external-component network.

## Rails consumed / produced

- **Consumes:** +VIN (5 V nominal; datasheet range 1.45 - 5.5 V)
- **Produces:** +1V8 / +2V5 / +3V3 (variant-dependent, 1 A continuous)
- **GND:** common ground reference

The dropout voltage at 1 A varies with V_OUT (DS Table 5-5): typically
~425 mV at V_OUT >= 3.3 V (so a 5 V input rail comfortably regulates
+3V3). Maximum power dissipation P_D = (V_IN - V_OUT) * I_OUT; thermal
shutdown trips at T_J ~165 degC (DS Sec 5.5).

## Key external parts (per DS Sec 7.1.1, Fig 7-4 Typical Application)

| Part                  | Where             | Purpose                                                     | Datasheet ref |
|-----------------------|-------------------|-------------------------------------------------------------|---------------|
| 1 uF X7R 0402 (`1u_0402_X7R`) | IN -> GND  | Input cap; >= 1 uF for input-impedance reduction + PSRR     | Sec 7.1.1     |
| 1 uF X7R 0402 (`1u_0402_X7R`) | OUT -> GND | Output cap; >= 0.47 uF effective for loop stability         | Sec 7.1.1     |
| 100 nF X7R 0402 (`100n_0402_X7R`) | OUT -> GND | HF bypass on output (transient response, fast load steps) | Sec 7.4.1     |
| 100 k 0402 1% (`100k_0402_1%`) | EN -> IN  | Pull-up to enable always-on; ~55 uA standby at V_IN = 5.5 V | Sec 6.4.1     |

The TLV757P has **no NR/SS pin** -- pin 4 is NC (DS Table 4-1). Earlier
TLV757x devices (non-P suffix) had a noise-reduction / soft-start pin
in this slot, so older notes / app circuits referencing a 10 nF NR/SS
cap do not apply to the P family used here. The KiCad symbol
`Regulator_Linear:TLV75xxxPDBV` correctly marks pin 4 as a hidden NC.

## Layout constraints (DS Sec 7.4)

- **Place input and output caps as close as possible to the device.**
  Each 1 uF ceramic must sit within ~5 mm of its respective IN / OUT
  pin to keep ESL low (DS Sec 7.4.1 Layout Guidelines).
- **Copper ground plane + thermal vias under the device.** Heat
  escapes primarily through the GND pin (DBV has no thermal pad).
  Thermal vias around the device into a ground plane keep T_J in
  spec at 1 A. (DS Sec 7.4 / Sec 7.1.5)
- **Short, low-impedance IN trace.** If the bulk +VIN cap is more
  than a few inches away (e.g. across a long PCB), add additional
  input bulk in parallel with the 1 uF ceramic (DS Sec 7.3).
- **EN pin must be driven** -- never leave it floating. Pulled to IN
  through the 100 k for always-on; route to a GPIO for sequenced
  enable.

## Notes on usage on the carrier

The `power` block (`projects/carrier/blocks/power.py`) instantiates one
of each variant -- U1 (TLV75733, +3V3), U2 (TLV75725, +2V5), U3
(TLV75718, +1V8) -- in parallel off +VIN. Each LDO sources up to 1 A
continuous which is comfortably above the carrier's combined
3V3 / 2V5 / 1V8 load (FPGA banks + peripherals; the Zynq core voltages
come from a separate SoM-side PMIC, not these LDOs).

The 100 k pull-up on EN holds each LDO always-on by default. If
sequencing is needed (e.g. wait for 3V3 to come up before enabling
1V8), replace the 100 k with a GPIO drive from the STM32 co-processor
and route it as a `STM32_LDO_xVx_EN` signal.

Reverse current protection (DS Sec 7.1.4, Fig 7-3) is **not** added at
this point in the chain because (a) +VIN is gated upstream by the
USB-C input only, (b) +1V8 / +2V5 / +3V3 fall together with +VIN
under normal supply collapse so V_OUT > V_IN + 0.3 V cannot occur, and
(c) the absolute maximum V_OUT - V_IN of 0.3 V (DS Sec 5.1) is not
exceeded by any expected transient. If a future revision adds a
backup supply that holds the rails above +VIN during +VIN collapse,
add an SS14 from OUT to IN per DS Fig 7-3.
