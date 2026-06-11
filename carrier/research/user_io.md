# Research dossier: user_io (wave 2)

Date: 2026-06-11. Scope: 4 user LEDs + 4 user buttons on PL bank-13 pins,
switchable per the bring-up architecture (PLAN: stage 2 = "enable user LEDs"
-> the LEDs sit on a gated rail). All stock/price/library figures queried
LIVE against the JLCPCB parts API on 2026-06-11.

---

## 0. Verified facts

### LEDs — the task constraint "0603 + distinct colors + Basic" is INFEASIBLE
Live check of the JLC BASIC library: the only 0603 LEDs in it are
**KT-0603R (red, C2286)** and **KT-0603W (white, C2290)** — every other 0603
color (KT-0603Y/B/G/O) is Extended; the Basic green/yellow are 0805
(KT-0805G C2297 / KT-0805Y C2296). Two ways out, both documented:

**PICK (one footprint, distinct colors, 2x Extended):** all 0603, red +
white Basic, green + blue Extended (stock healthy, prices ~1 cent):

| Pos | Color | MPN | LCSC | Stock seen | Lib | Vf | Unit @1 |
|-----|-------|-----|------|-----------:|-----|----|---------|
| D1 | red | KT-0603R | C2286 | 6,132,891 | **Basic** | 1.8-2.4 V | $0.007 |
| D2 | green | KT-0603G | C12624 | 29,509 | Extended | ~3.1 V | $0.012 |
| D3 | blue | KT-0603B | C2288 | 136,467 | Extended | ~3.1 V | $0.010 |
| D4 | white | KT-0603W | C2290 | 2,496,862 | **Basic** | 2.6-3.1 V | $0.012 |

Fallback (all-Basic, mixed size): KT-0603R + KT-0603W + KT-0805G (C2297,
3.1M stock) + KT-0805Y (C2296, 1.0M) — zero Extended feeders, two LED
footprints. Take this only if the two Extended feeders matter more than the
single-footprint LED row.

### Series resistors and brightness at the task's 1k
On a 3.3 V rail through 1k: red ~1.2 mA (KT series is rated 300 mcd @ 20 mA
-> clearly visible), green/blue/white ~0.2-0.5 mA (these are 5 mA-rated
high-efficiency parts, ~30-40 mcd at that current — visible indoors, dimmer
than the red). 1k (C21190, Basic, same part power.py uses) everywhere is
kept per task; if bring-up finds the InGaN colors too dim, drop THEIR series
to 470R (0603WAF4700T5E, C23178-class Basic) — one-line value change here.

### Buttons + pulls (already-proven parts)
| Item | MPN | LCSC | Stock seen | Lib | Unit @1 |
|------|-----|------|-----------:|-----|---------|
| Tact switch 5.1x5.1 SMD (x4) | XKB TS-1187A-B-A-B | C318884 | 1,830,400* | **Basic** | $0.020 |
| 10k 0603 pull-ups (x4) | UNI-ROYAL 0603WAF1002T5E | C25804 | 3,983,200* | **Basic** | $0.0011 |
| 1k 0603 LED series (x4) | UNI-ROYAL 0603WAF1001T5E | C21190 | (power.py pick) | **Basic** | ~$0.001 |
| 100n 0603 rail bypass | CL10B104KB8NNNC | C1591 | 281,873 | Extended* | $0.010 |

*TS-1187A/C25804 figures from the 2026-06-10 debug_boot dossier (same
parts, already in parts/ + subsystems); C1591 re-verified today.
Contact map (TS-1187A, per parts/TS-1187A-B-A-B + debug_boot usage): pins
1/2 = one contact pair, 3/4 = the opposite pair; signal on 1+2, GND on 3+4.

---

## 1. Bank-13 pin allocation (THE point of this dossier)

### Inventory and prior claims
`carrier/som_interface.json` J2 exposes **43 bank-13 IOs**. Verbatim
`IO_*_13` consumers today (grep of carrier/subsystems/*.py): **pmod only**,
16 pins (L2/L3/L4/L5/L7/L8/L9_DQS/L10 pairs). The lcd sheet's 34 panel
signals are CONTRACT-named (LCD_*) and not yet bound to IO pins — but its
dossier (lcd_backlight.md) claims bank 13 with a count made BEFORE pmod
existed ("34 <= 43, 9 spare").

### >>> BOARD-LEVEL CONFLICT (flag for PLAN, decide before wave-3 J2 gen)
Bank 13 is over-subscribed: lcd 34 + pmod 16 + user_io 8 = **58 > 43**.
Even without user_io, lcd+pmod = 50 > 43. Proposed resolution (NOT enacted
here): move the LCD bus to **J3 bank 34 (exactly 34 IOs)** — single-bank,
sets the rail-map constraint +VCCO_34 = +3V3 (LCD_PCLK must land on a
bank-34 MRCC/SRCC pin), leaving bank 13 to pmod + user_io with 19 spares.
Alternative: split LCD across J2 bank 33 (29 IOs) + spill; worse (two banks,
bank 33 also hosts hdmi candidates). Decision belongs to PLAN/user.

### user_io picks — 8 pins NO subsystem uses, chosen to spend the cheapest
pins first: 4 singleton P-pins whose N-halves are not on J2 (worthless as
pairs -> buttons), 1 true singleton + the pair whose mate doubles as VREF +
one full plain pair (LEDs). All MRCC/SRCC clock pins and the full plain
pairs L16/L17/L18/L23 stay free.

| Function | Net (verbatim, som_interface.json) | J2 pin | Why this pin |
|----------|-----------------------------------|--------|--------------|
| LED1 (red) | IO_25_13 | 23 | true singleton |
| LED2 (green) | IO_L6_P_13 | 21 | pair-mate is the VREF pin (pair already compromised) |
| LED3 (blue) | IO_L24_P_13 | 10 | one plain pair spent |
| LED4 (white) | IO_L24_N_13 | 7 | (same pair) |
| BTN1 | IO_L15_P_13 | 9 | singleton (no N on J2) |
| BTN2 | IO_L19_P_13 | 12 | singleton |
| BTN3 | IO_L21_P_13 | 13 | singleton |
| BTN4 | IO_L22_P_13 | 19 | singleton |

Post-allocation bank-13 ledger: 43 total - 16 pmod - 8 user_io = **19 free**
(4 full plain pairs L16/L17/L18/L23, clock pairs L11_SRCC/L12_MRCC/
L13_MRCC/L14_SRCC, L1 pair, L6_N_VREF).

---

## 2. Reference circuit

- **LEDs (active-low sinks, rail-gated):** `+3V3_USER_LED` (bring-up-gated
  port, stage-2 "enable user LEDs") -> LED anode; cathode -> 1k -> PL pin.
  PL drives low = LED on; rail gate off = all four dead regardless of PL
  state (exactly the staged-bring-up behaviour PLAN asks for). 100n bypass
  on the gated rail.
- **Buttons (active-low):** PL pin + 10k pull-up to **+3V3** (= +VCCO_13
  level, the pmod dossier's locked rail-map entry) and tact contacts 1/2;
  contacts 3/4 to GND. No RC debounce — PL debounces in fabric (free), and
  the SoM-side bank has no Schmitt requirement for slow human inputs.
- Pull-ups ride the UNgated +3V3 (not +3V3_USER_LED): a pressed button must
  read correctly during bring-up stage 2 even when the LED rail is off; PL
  is only alive when +3V3 is up anyway (SoM VCCO feeds).

## 3. BOM rollup (qty/board)
4x LED (2 Basic + 2 Ext, ~$0.04) + 4x 1k + 4x 10k (Basic, ~$0.01) +
4x TS-1187A (Basic, $0.08) + 1x 100n. Extended feeders added: 2 (green,
blue LEDs) — or 0 with the mixed-size fallback.

## Risks / open items
1. **Bank-13 oversubscription** (section 1) — needs a PLAN decision; if the
   LCD stays on bank 13, user_io and/or pmod must move to J3 bank 35 and
   this dossier's pin table regenerates.
2. **InGaN LED brightness at 1k** — visible but dim; 470R fix documented.
3. **Extended LED feeders (2)** — swap to the all-Basic 0805 fallback if
   feeder count is squeezed at order time.
4. The +3V3_USER_LED gate (load switch + DIP position) is the bringup
   sheet's to own (M2), same contract as +3V3_PMOD / +3V3_SD.

Sources: JLCPCB selectSmtComponentList API (live, 2026-06-11);
carrier/som_interface.json; carrier/research/debug_boot_pmod.md +
lcd_backlight.md + bringup_power_gating.md; carrier/PLAN.md (bring-up
stages, Basic-preferred); KT-0603/0805 datasheet rows from the JLC part
records (Vf/If/mcd).
