# Pulse HX5008NLT - 1000BASE-T Ethernet magnetics

Pulse Electronics HX5008NLT (SOIC-24 wide-body, LCSC C962544) is the
isolation-magnetics module that sits between the SoM's Gigabit PHY and
the carrier's bare RJ45 jack (`components/rj45`). Four 1:1 transformers
with integrated common-mode chokes, 1500 V_RMS hi-pot isolation.

Datasheet (in this folder): Pulse PS-0118.001-D, Rev A, 2015.

## Rails

This part has no DC supply pins — it's a passive transformer module.
Centre-taps are routed through the IEEE 802.3 Bob Smith network to a
quiet CHASSIS_GND, but no power input is required.

| Net           | Purpose                                                                   |
|---------------|---------------------------------------------------------------------------|
| `CHASSIS_GND` | Isolated frame-ground island; absorbs Bob Smith common-mode current      |
| `BS_COMMON`   | Internal node where the four 75R + 1nF/2kV networks tie together         |

## Key external parts

Per IEEE 802.3 Sec 40.7.1 (Bob Smith common-mode termination), one per
pair plus a single shared chassis bypass:

| From pin   | To net        | Part token              | Qty | Why                                              |
|------------|---------------|-------------------------|-----|--------------------------------------------------|
| CT_PAIR0   | BS_COMMON     | `75R_0603_1%`           | 1   | Bob Smith 75R termination on pair 0              |
| CT_PAIR0   | BS_COMMON     | `1n_2kV_0603_safety`    | 1   | 1nF/2kV safety cap, pair 0                       |
| CT_PAIR1   | BS_COMMON     | `75R_0603_1%`           | 1   | Bob Smith 75R termination on pair 1              |
| CT_PAIR1   | BS_COMMON     | `1n_2kV_0603_safety`    | 1   | 1nF/2kV safety cap, pair 1                       |
| CT_PAIR2   | BS_COMMON     | `75R_0603_1%`           | 1   | Bob Smith 75R termination on pair 2              |
| CT_PAIR2   | BS_COMMON     | `1n_2kV_0603_safety`    | 1   | 1nF/2kV safety cap, pair 2                       |
| CT_PAIR3   | BS_COMMON     | `75R_0603_1%`           | 1   | Bob Smith 75R termination on pair 3              |
| CT_PAIR3   | BS_COMMON     | `1n_2kV_0603_safety`    | 1   | 1nF/2kV safety cap, pair 3                       |
| BS_COMMON  | CHASSIS_GND   | `1n_2kV_0603_safety`    | 1   | Single common-node bypass cap to chassis         |

Use 2 kV safety-rated X7R caps (not generic MLCCs) so the network
withstands IEEE 802.3 Sec 14.7 surge events without breakdown.

PHY-side centre taps (TCT1..4 on the datasheet, internal-only in the
carrier symbol) DO NOT need external L or bypass caps for the Realtek
RTL8211F PHY — that PHY supplies internal common-mode bias on its
MDI driver (RTL8211F DS Sec 9.2).

## Layout constraints

* Each MDI pair: 100R differential impedance, length-matched within
  0.5mm intra-pair and <= 2mm skew across the four pairs.
* CHASSIS_GND is an island; bond it to signal GND at a single star
  point near the carrier's power-entry connector.
* Place the magnetics within 30mm of the RJ45 connector. Keep MDI
  traces straight between magnetics and jack (no vias).
* Route the four Bob Smith networks together near the magnetics' line
  side. Use the 2 kV safety caps explicitly — generic MLCCs will fail
  surge events.
* Keep PHY-side MDI traces on a separate layer or with 3x spacing
  from line-side traces to preserve the 1500 V_RMS hi-pot isolation.

## Carrier usage

* `blocks/ethernet.py` instantiates one HX5008NLT between the SoM's
  PHY MDI pins (PHY0..3 P/N in the symbol = TD1..4 in the datasheet)
  and the RJHSE5380 RJ45 jack (MDI0..3 P/N in the symbol = MX1..4 in
  the datasheet). Allowing the magnetics to be a separate module is
  a deliberate debug feature: scope-probable MDI signals between PHY
  and magnetics during bring-up.
