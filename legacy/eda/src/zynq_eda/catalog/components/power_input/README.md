# Power Input -- SS14 Schottky reverse-polarity protector

A 1 A, 40 V Schottky rectifier (Fairchild / ON Semi SS12-S100 family,
SMA / DO-214AC package) sits in series with the carrier's raw input
power feed from USB-C VBUS, providing reverse-polarity protection and
serving as the anchor point for bulk input capacitance.

```
USB-C VBUS  +VIN_IN -->|--+--+--+----- +VIN (protected) ---> LDOs / TPS2051 / INA226
                  SS14    |  |  |
                       C100u C10u C100n
                          |  |  |
                         GND GND GND
```

## Rails consumed / produced

- **Consumes:** `+VIN_IN` (raw 5 V from USB-C VBUS; can transiently
  swing in either direction)
- **Produces:** `+VIN` (protected 5 V node, available to every
  downstream regulator and load switch)
- **GND:** common ground reference

Forward voltage drop V_F at 1 A is typically ~0.5 V (DS Electrical
Characteristics), so the protected rail sits at ~4.5 V worst-case
which still meets the TLV75733's minimum V_IN = V_OUT + V_DO ~= 3.725 V
at 1 A.

## Key external parts

| Part                              | Where         | Purpose                                                              | Datasheet ref     |
|-----------------------------------|---------------|----------------------------------------------------------------------|-------------------|
| SS14 Schottky (`schottky_SS14`)   | series anode -> cathode | Reverse-polarity protection; V_RRM = 40 V; V_F ~0.5 V at 1 A | DS Sec Absolute Max + Sec Elec |
| 100 uF 1206 X5R (`100u_1206_X5R`) | cathode -> GND  | Bulk input capacitance for downstream LDO inrush                     | App. practice     |
| 10 uF 0402 X5R (`10u_0402_X5R`)   | cathode -> GND  | Mid-frequency bulk between 100 uF ESL and per-IC 1 uF caps           | App. practice     |
| 100 nF 0402 X7R (`100n_0402_X7R`) | cathode -> GND  | HF bypass at the protected +VIN rail                                 | App. practice     |
| 10 uF 0402 X5R (`10u_0402_X5R`)   | anode -> GND    | Pre-Schottky bulk to absorb USB-C cable inductance ringing           | App. practice     |

The SS14 has no datasheet "typical application" diagram because it is
a discrete diode -- the reference network around it is standard
practice for a 1 A 5 V input protection node. The SS12-S100 datasheet
specifies the device parameters (V_RRM = 40 V for SS14, I_F = 1 A
continuous, I_FSM = 40 A non-repetitive peak surge) and the SMA
land-pattern dimensions on p.4.

## Layout constraints

- **Place the SS14 in series with the +VIN trace immediately
  downstream of the USB-C VBUS pins.** Keep the loop to the bulk
  100 uF cap short to minimise inrush ringing when a supply is
  hot-plugged. (DS p.4 land-pattern recommendation.)
- **Wide copper pour on +VIN_IN and +VIN.** The traces carry up to
  1 A continuous; the SS14 dissipates ~0.5 W at 1 A and the package
  R_thJA is 88 degC/W (DS Thermal Characteristics). A polygon pour
  on at least one layer (or >= 30 mil dedicated trace) keeps the
  rise above ambient under 50 degC.
- **Cathode-band orientation:** the marking band on the SMA package
  designates the cathode (DS p.1 figure). Verify silkscreen rotation
  before assembly -- a reversed SS14 turns the supply into a 0.5 V
  forward-biased load instead of a protected rail.
- The two anode-side and three cathode-side bulk caps may be
  consolidated into a single "input bulk cluster" near the USB-C
  receptacle for layout efficiency; the cluster algorithm places them
  perpendicular to the SS14 body.

## Notes on usage on the carrier

A single SS14 is the only instance on the board. The carrier's
`power` block currently treats +VIN as already-protected and does not
include the SS14 directly in the schematic block (one outstanding
work item, see comments in `projects/carrier/blocks/power.py`). The
refcircuit + parts entry exist so that when the input-protection
section is folded into the schematic, the reference design is ready.

A TVS diode (e.g. PESD5V0S2BT, already in the parts registry as
`tvs_PESD5V0S2BT`) can be added in parallel with the bulk cap if the
input is exposed to ESD or long-cable transients exceeding the SS14
40 V V_RRM; for the present USB-C-only feed, the host-side cable's
5 V is well within the SS14's reverse rating.
