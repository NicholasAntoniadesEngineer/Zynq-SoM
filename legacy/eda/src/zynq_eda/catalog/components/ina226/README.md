# INA226AIDGSR -- I2C 36 V current / voltage / power monitor

TI INA226 16-bit bidirectional current shunt and bus-voltage monitor
with an I2C interface and an open-drain alert output. Used to
instrument each major rail on the carrier; the STM32 co-processor
reads live current / voltage / power over I2C2 and reacts to over-
limit and under-limit conditions via the asynchronous ALERT pin.

```
+VIN -->[R_shunt 10mOhm]-+---> +VIN_LOAD (downstream)
                |        |
                Vin+     Vin-
                 \      /
                  \    /
                  [INA226]
            VS---[+3V3]   VBUS [+VIN]
            GND  SDA --[4k7]--+
                 SCL --[4k7]--+--> +3V3
                 Alert -[4k7]-+
                 A0, A1 -> I2C address strap
```

## Rails consumed / produced

- **Consumes:** `+3V3` on VS (DS V_S range 2.7 - 5.5 V; 330 uA typical
  quiescent per DS Sec 5.5).
- **Produces:** no rails -- the device is non-disturbing; the high-side
  shunt sits in series with whatever rail is being monitored.
- **Measures:** any rail in the 0 - 36 V common-mode range; per-
  instance the monitored rail is wired to Vbus (pin 8) and to either
  side of the shunt resistor.
- **GND:** common ground reference.

## Key external parts (DS Fig 8-1 Typical Circuit Configuration, p.28)

| Part                                  | Where             | Purpose                                                                 | Datasheet ref       |
|---------------------------------------|-------------------|-------------------------------------------------------------------------|---------------------|
| 10 mOhm 2010 1% (`R_SENSE_10mR_2010_1%`) | Vin+ -> Vin-   | Current shunt; 81.92 mV full-scale at 8.192 A; standardised across all 6 instances | Sec 6.5 + Eq 7      |
| 100 nF X7R 0402 (`100n_0402_X7R`)     | VS -> GND         | Local supply bypass; place as close as possible to pins 6/7             | Sec 8.3 + Fig 8-1   |
| 4.7 k 0402 1% (`4k7_0402_1%`)         | SDA -> +3V3       | I2C SDA bus pull-up                                                     | Sec 8.2.1.2         |
| 4.7 k 0402 1% (`4k7_0402_1%`)         | SCL -> +3V3       | I2C SCL bus pull-up                                                     | Sec 8.2.1.2         |
| 4.7 k 0402 1% (`4k7_0402_1%`)         | Alert -> +3V3     | Open-drain Alert pull-up (DS explicitly requires pull-up to V_VS)       | Sec 8.2.1.2 + Fig 8-1 |

This implementation deliberately omits the optional **10 Ohm + 1 nF
differential input filter** that appears in some INA-family app notes:
the INA226 datasheet (SBOS547B, Sep 2024 revision) does **not** show
or recommend a filter in its Typical Application or Layout Example
(Sec 8.2 + Sec 8.4.2). The filter degrades dynamic accuracy on fast
load steps; it is only justified on extremely noisy rails. If a
future rail needs it, add a 10R / 47nF or 10R / 1nF C0G differential
filter as a follow-up.

The current refcircuit also dropped earlier (incorrect) references to
"DS Fig 32" -- the typical-application figure is Figure 8-1 in the
current datasheet revision, and "Fig 32" was a stale reference from
a previous revision number.

## Layout constraints (DS Sec 8.4)

- **Kelvin-connect Vin+ and Vin- to the shunt resistor pads.** Use a
  4-wire connection geometry: dedicated sense traces tap the shunt
  pads directly, separate from the high-current power traces. Any
  trace resistance between the shunt and the input pins shows up as
  shunt-resistance error (DS Sec 8.4.1 Layout Guidelines).
- **Bypass cap close to VS/GND pins.** The 0.1 uF C_BYPASS sits next
  to pins 6 (VS) and 7 (GND) (DS Fig 8-4 Layout Example).
- **Route Vin+ / Vin- as a tight differential pair** from the shunt
  back to pins 10/9 to reject common-mode noise.
- **Vbus to power plane via a via.** The bus voltage measurement
  is internally referenced to the V_S supply but works correctly up
  to 36 V common-mode; route it from the monitored rail's plane to
  pin 8 with a short trace.
- **ALERT can be left floating if unused**, but on the carrier we
  always pull it up so it can flag over-current to the STM32. (DS
  Fig 8-4 note: "Can be left floating if unused".)

## Notes on usage on the carrier

The carrier currently instantiates **1 INA226** in the `power_mon`
block monitoring +VIN at the input bulk (U1, A0=GND/A1=GND,
address 0x40). The catalog's `IC_INSTANCE_COUNT` already provisions
**6 INA226 instances**, anticipating a fully-instrumented carrier
where each major rail (+VIN, +3V3, +2V5, +1V8, +VBUS_OTG, +VCCO_xx)
gets its own monitor with a unique I2C address strap (per DS Table 6-2).
When additional instances are added:

1. Pick a unique `(A1, A0)` strap combination from Table 6-2 (any of
   the 16 addresses).
2. Override `Vbus` via `IcInstance.net_overrides` to point at the
   monitored rail (the refcircuit defaults to `+VIN`).
3. Place a fresh shunt in series with the rail just like the +VIN
   instance.

The 10 mOhm shunt is sized for currents up to 8 A; rails that draw
significantly less than that (e.g. +1V8 at <500 mA) will resolve only
the upper few bits of the 16-bit ADC. If finer resolution becomes
important on a low-current rail, swap in a 100 mOhm shunt for that
specific instance (add `R_SENSE_100mR_xxxx` to the parts registry).
