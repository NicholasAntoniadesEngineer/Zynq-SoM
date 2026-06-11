# Research dossier: power_mon (wave 2)

Date: 2026-06-11. Scope: rail current/voltage telemetry for the 3 carrier rails
(+5V, +3V3, +1V8) plus the +VIN PD input, reported to the SoM STM32 over the
shared I2C bus. All stock/price/library figures below queried LIVE against the
JLCPCB parts API (the same endpoint `schgen preflight` uses) on 2026-06-11.
Locked context: PLAN rounds 2-3 (USB-C PD 20 V/3 A input; rails +5V/+3V3 bucks
3 A + +1V8 LDO 600 mA; bring-up = stage-by-stage rail enable), and
`carrier/research/bringup_power_gating.md` (I2C bus + GPIO budget + TCA9535).

---

## 0. Verified facts

### Monitor IC candidates (live-verified 2026-06-11)
| Item | MPN | LCSC | Stock seen | Lib | Unit @1 |
|------|-----|------|-----------:|-----|---------|
| Triple-channel monitor (pick, x2) | TI INA3221AIRGVR (VQFN-16) | **C181255** | 2,480 | Extended | $1.55 |
| Single-channel precision alternate | TI INA226AIDGSR (VSSOP-10) | C49851 | 81,477 | Extended | $0.83 |

**The task's "C190480-class" number is a GHOST**: a live exact-code query for
C190480 returns nothing on the JLC parts API. The real JLC code for
INA3221AIRGVR is **C181255** (verified by exact componentCode match, model
string `INA3221AIRGVR`, TI brand, stock 2,480).

### Key electricals (TI datasheets: INA3221 SBOS576, INA226 SBOS547)
| Param | INA3221 | INA226 |
|-------|---------|--------|
| Channels | 3 | 1 |
| Shunt full-scale | ±163.8 mV (LSB 40 uV, 13-bit) | ±81.92 mV (LSB 2.5 uV, 16-bit) |
| Bus voltage range | 0-26 V | 0-36 V |
| Supply VS | 2.7-5.5 V, ~350 uA | 2.7-5.5 V, ~330 uA |
| I2C addresses | 0x40-0x43 via A0 (GND/VS/SDA/SCL) | 0x40-0x4F via A0+A1 |
| Alerts (open-drain) | CRITICAL, WARNING, PV, TC | ALERT |

Both parts measure HIGH-SIDE at up to 26 V common mode -> the 20 V +VIN
channel is in range for either. Pin map used for the netlist is the generated
`parts/INA3221AIRGVR/INA3221AIRGVR.py` (EasyEDA pin table): 1 IN-3, 2 IN+3,
3 GND, 4 VS, 5 A0, 6 SCL, 7 SDA, 8 WARNING, 9 CRITICAL, 10 PV, 11 IN-1,
12 IN+1, 13 TC, 14 IN-2, 15 IN+2, 16 VPU, 17 PAD.

### Decision: 2x INA3221 (not 1x INA3221 + 1x INA226, not 4x INA226)
4 monitored nets need 4 channels. 2x INA3221 = ONE part number (one Extended
feeder fee), 6 channels (2 spare for a future rail), distinct addresses off
the A0 strap, $3.11 total. The mixed INA3221+INA226 option saves $0.72 but
costs a second Extended feeder and a second register map in firmware; 4x
INA226 costs more board area and money. INA3221 accuracy (40 uV shunt LSB ->
4 mA steps on 10 mR) is plenty for bring-up telemetry; INA226 (C49851,
81k stock) stays the drop-in precision alternate if a rail ever needs
0.25 mA resolution.

---

## 1. Channel plan + shunt sizing (from PLAN rail budgets)

Budgets: +VIN = USB-C PD 20 V/3 A (60 W); +5V, +3V3 = TPS54302 bucks, 3 A max
each; +1V8 = AP2112K LDO, 600 mA max.

| Ch | Net (upstream -> downstream) | Budget | Shunt | V@max | P@max | LSB step |
|----|------------------------------|--------|-------|-------|-------|----------|
| U1 ch1 | +VIN -> +VIN_SYS | 3 A | 10 mR | 30 mV | 90 mW | 4 mA |
| U1 ch2 | +5V_REG -> +5V | 3 A | 10 mR | 30 mV | 90 mW | 4 mA |
| U1 ch3 | +3V3_REG -> +3V3 | 3 A | 10 mR | 30 mV | 90 mW | 4 mA |
| U2 ch1 | +1V8_REG -> +1V8 | 0.6 A | 20 mR | 12 mV | 7.2 mW | 2 mA |
| U2 ch2/3 | unused — IN+/IN- tied to GND | — | — | — | — | — |

30 mV is 18% of the INA3221 full scale (headroom for inrush), and a 30 mV
drop is 0.6% of +5V / 0.15% of +VIN — negligible. 90 mW in a 1 W 1206 is a
9% derate. The 20 mR on +1V8 doubles resolution where the budget is 5x
smaller; 12 mV drop on 1.8 V = 0.7%, fine for SD/peripheral logic.

### Shunt parts (live-verified 2026-06-11; 1206 current-sense, 1%)
| Item | MPN | LCSC | Stock seen | Lib | Unit @1 |
|------|-----|------|-----------:|-----|---------|
| 10 mR 1 W 1206 1% +/-100ppm (x3) | TA-I RLM12FTCMR010 | C188070 | 109,351 | Extended | $0.037 |
| 20 mR 1 W 1206 1% +/-50ppm (x1) | TA-I RLM12FTCMR020 | C393094 | 50,938 | Extended | $0.037 |

Same brand/series (one footprint geometry), both >50k stock. True Basic
current-sense parts do not exist at these values (live check: every 10/20 mR
1206 hit is Extended); the TA-I picks are the cheapest high-stock 1 W parts.
Generated folders: `parts/RLM12FTCMR010/`, `parts/RLM12FTCMR020/` (faithful
current-sense pads — do NOT substitute the generic R_1206 footprint).

### Rail net split (the one cross-sheet change)
A series shunt only measures if ALL load current crosses it, so the rail nets
split at the shunt; `power.py` keeps its regulator-side clusters (output caps,
FB divider, PG LED, downstream-regulator inputs) on renamed `_REG`/`_SYS`
nets and the board-facing rail names stay on the load side:

- `+VIN` (PD entry; usb_pd FUSB302 VBUS sense stays here) -> RS1 -> `+VIN_SYS`
  (power.py buck-1 input cluster U1.3/C1/C2/C3).
- `L1.2` cluster renamed `+5V_REG` -> RS2 -> `+5V` (all other sheets).
- `L2.2` cluster renamed `+3V3_REG` -> RS3 -> `+3V3`.
- `U3.5` cluster renamed `+1V8_REG` -> RS4 -> `+1V8`.

Deliberate consequences: buck-2 + LDO draw from the UPSTREAM (_REG) side, so
each rail channel reads its own loads only (not the downstream regulators'
input current) — exactly what per-rail bring-up debugging wants; the FB
dividers keep sensing the regulator-side node (drop across the shunt is <=30 mV,
inside regulation tolerance); PG LEDs stay on the regulator side (they
indicate "regulator up", pre-shunt).

---

## 2. I2C + supply + alert

### Bus: STM32_I2C2 (shared, J1) — ADDRESS MAP (board-wide, record in firmware)
| Addr (7-bit) | Device | Sheet | Strap |
|------|--------|-------|-------|
| 0x20 | TCA9535PWR bring-up expander | bringup (M2) | A2=A1=A0=GND |
| 0x22 | FUSB302B PD PHY | usb_pd | fixed |
| 0x40 | INA3221 #1 (VIN/+5V/+3V3) | power_mon | A0=GND |
| 0x41 | INA3221 #2 (+1V8 + 2 spare) | power_mon | A0=VS |

No collisions. Two standing constraints documented here: (1) the TCA9535
A-straps must stay 000 — at A=010 it would land on 0x22 and collide with the
FUSB302B; (2) INA3221 A0=SDA/SCL extends to 0x42/0x43 if a third monitor is
ever added. Bus pull-ups already exist (usb_pd: 4k7 to +3V3; bringup dossier
3.5 adds 4k7 to +3V3_SC) — power_mon adds NONE.

Ports: `STM32_I2C2_SDA` / `STM32_I2C2_SCL`, typed i2c/400 kHz on bus
"STM32_I2C2", expect='som_j1_connector' — same contract as usb_pd's FUSB302.

### Supply: +3V3_SC (always-on SC rail, J1.37)
Monitoring must work while the monitored rails are DOWN (stage-by-stage
bring-up), so both INA3221s run from +3V3_SC like the rest of the bring-up
infrastructure. Draw: 2x ~350 uA = 0.7 mA, inside the bringup dossier's R3
budget. Decoupling 100n per VS + one shared 10u bulk. VPU (power-valid
comparator pull-up supply) ties to +3V3_SC on both.

### Alert: PMON_ALERT_N -> bringup TCA9535 spare port
STM32_GPIO1-8 are fully allocated (1-3 rail ENs, 4 expander INT, 5/6 SWD,
7/8 BOOTSEL) — there is NO free direct GPIO. The bringup dossier names the
expander's spare ports as THE expansion path, so: both chips' CRITICAL pins
(open-drain) wire-OR onto one net `PMON_ALERT_N`, 10k pull-up to +3V3_SC,
ported with expect="bringup (TCA9535 spare port P11)" — P10 is reserved for
EN_LCD_BL per the bringup dossier. The expander INT# already routes to
STM32_GPIO4; an alert therefore reaches firmware as expander-IRQ ->
read-expander -> read-INA3221-flags. WARNING/PV/TC alerts stay readable over
I2C; the pins are author NCs.

### Unused channels (U2 ch2/ch3)
IN+ and IN- tied to GND (TI datasheet guidance for unused channels: connect
inputs to GND; keeps the channel reading 0 V/0 A instead of floating).

---

## 3. BOM rollup (subsystem, qty/board)

| Qty | Part | LCSC | Lib | Ext cost |
|-----|------|------|-----|----------|
| 2 | INA3221AIRGVR | C181255 | Extended | $3.11 |
| 3 | RLM12FTCMR010 10 mR | C188070 | Extended | $0.11 |
| 1 | RLM12FTCMR020 20 mR | C393094 | Extended | $0.04 |
| 3 | 100n 0603 (2x VS + spare for bulk pairing) | C1591 | Extended* | $0.03 |
| 1 | 10u 0805 | C15850 | Basic | $0.05 |
| 1 | 10k 0603 pull-up | C25804 | Basic | ~$0.00 |

*C1591 reads Extended on today's API (same reclassification power.py already
documents); kept for BOM commonality. Extended feeder count added by this
subsystem: 4 (INA3221, 2 shunt values, C1591 — the last shared with 6 other
sheets).

## Risks / open items
1. **INA3221 stock 2,480** (one vendor reel class) — healthy for protos but
   single-source; preflight re-checks; INA226AIDGSR (81k stock) is the
   fallback at the cost of a firmware driver change + 2 extra channels lost.
2. **Layout**: shunts need Kelvin sense routing (sense traces off the pad
   inner edges, routed as pairs to IN+/IN-). The optional 10R+100n input
   filters from the datasheet are OMITTED on rev A — add only if switching
   noise swamps readings.
3. **Net split lands in power.py** (regulator-side renames). Any future sheet
   must consume the LOAD-side names (+VIN_SYS is power-internal; +5V/+3V3/
   +1V8 stay the public rails).
4. **Firmware contract**: address map above + "CRITICAL limits configured
   before rail enable" belongs in the SC firmware repo notes.

Sources: TI INA3221 datasheet (SBOS576, ti.com), TI INA226 datasheet
(SBOS547), onsemi FUSB302B datasheet (slave addr 0x22), TI TCA9535 (SCPS201E)
via bringup_power_gating.md; JLCPCB selectSmtComponentList API (live stock /
Basic-Extended / price, queried 2026-06-11); carrier/PLAN.md rounds 2-3;
carrier/subsystems/power.py (rail budgets, parts); generated EasyEDA pin
tables in parts/.
