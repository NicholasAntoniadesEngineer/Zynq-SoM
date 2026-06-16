# power — multi-rail regulator tree (buck → buck → LDO, PG LEDs) reusable subsystem

A project-agnostic, self-contained schgen subsystem: a **3-stage regulator
chain** — an **LM61460** 6 A synchronous buck (`+VIN → +5V`), a **TPS54302** 3 A
synchronous buck (`+5V → +3V3`) and an **AP2112K** 600 mA LDO (`+3V3 → +1V8`) —
each rail with an **enable port** and a **power-good LED** (the +1V8 PG uses an
AO3400A FET sense because a red LED's Vf exceeds 1.8 V). It declares its interface
as **abstract** port + rail names and knows nothing about any board; a consuming
project supplies a **bind map** (`abstract → real net`) to drop it onto real nets.
This is the largest, most complex carrier subsystem.

## Package contents

| file | role |
|------|------|
| `power.py`      | the NETLIST — `circuit(meta=None)`, abstract ports/rails |
| `power.cir`     | SPICE subckt — the interface-spanning passive network (per-stage input/output bypass + bulk) with the abstract rails as subckt pins |
| `test_power.py` | LOCAL electrical-correctness test (offline, runs the board gate slices on just this subsystem) |
| `README.md`     | this file |

Active parts are **referenced, never vendored**: the LM61460/TPS54302/AP2112K/
AO3400A symbols/footprints/LCSC come from the global `parts/` lib via
`use_part()`. **U1 (LM61460) draws its FAITHFUL `parts/LM61460AANRJRR/`
dossier symbol** — no `lib_id=` override (the **"0 hand-built symbols"**
migration; the old hand-built `schgen:LM61460` is gone, and
`schgen.verify.symbol_law.PENDING_MIGRATION` is now empty). The placer's
box-buck stage handler lays the faithful all-passive QFN box out cleanly. The
14 pins are authored **by number** (1 BIAS, 2 VCC, 3 AGND, 4 FB, 5 PGOOD, 6 RT,
7 EN/SYNC, 8 VIN1, 9 PGND1, 10 SW, 11 PGND2, 12 VIN2, 13 RBOOT, 14 CBOOT); the
swap was NETLIST-NEUTRAL (same pin numbers + footprint).

## The abstract interface (the reuse contract)

A consuming project binds these names. Rails classify as POWER/GROUND by name (a
leading `+` = POWER; `GND` = GROUND), exactly as real board rails do, so a
standalone build and a bound build share net classes.

### Rails (POWER / GROUND)

Each regulator exposes **two** external rails — a **reg-side** node and the board
**rail** the loads see — so a project's series current-monitor (e.g. an INA3221)
can sit on a shunt **between** them and measure consumer draw. See *The reg-side
vs rail-side split* below.

| abstract | class | meaning / constraint |
|----------|-------|----------------------|
| `+VIN`          | POWER  | regulator-tree input — drives the +5V buck VIN1/VIN2 pins + the input bypass/bulk. Worst case 21 V (a 20 V PD source +5%). On a board with an inlet current-monitor this is the **post-shunt** rail. |
| `+VOUT_5V_REG`  | POWER  | +5V buck **regulator-side** output: the inductor node, the 3×22 µF output bulk, the FB sense, the BIAS tie and the PG LED. |
| `+VOUT_5V`      | POWER  | board **+5V rail** the loads see (it feeds the +3V3 buck input). |
| `+VOUT_3V3_REG` | POWER  | +3V3 buck regulator-side output (2×22 µF bulk + FB sense + PG LED). |
| `+VOUT_3V3`     | POWER  | board **+3V3 rail** — feeds the +1V8 LDO input **and** the +1V8 PG LED anode (the LED's supply must be up before +1V8 exists). |
| `+VOUT_1V8_REG` | POWER  | +1V8 LDO regulator-side output (1 µF output cap). |
| `+VOUT_1V8`     | POWER  | board **+1V8 rail** the loads see. |
| `GND`           | GROUND | ground — also the LM61460 **heat path** (PGND1/PGND2/AGND, the VQFN-HR's EP-equivalent, all on the GND pour). |

### Ports (PORT)

| abstract | type | meaning |
|----------|------|---------|
| `EN_VOUT_5V`  | single | +5V buck enable (EN/SYNC pin 7). |
| `EN_VOUT_3V3` | single | +3V3 buck enable. |
| `EN_VOUT_1V8` | single | +1V8 LDO enable. |

Two physical pins are explicit author **no-connects**: U1.5 (PGOOD, the unused
open-drain status output — the rail-up LED is the indicator) and U3.4 (the LDO's
NC pin).

### Internal SIGNAL nets (private wiring — never bound)

The regulator control nodes are **internal SIGNAL** and stay verbatim — they are
private wiring and are rejected by `bind()`:

`SW_5V0`, `BOOT_5V0`, `FB_5V0`, `CFF_5V0`, `BIAS_5V0`, `U1_VCC`, `RT_5V0`,
`PG_5V0` (the +5V buck); `SW_3V3`, `BOOT_3V3`, `FB_3V3`, `PG_3V3` (the +3V3
buck); `PG_1V8_G` / `PG_1V8_D` / `PG_1V8_K` (the +1V8 PG-sense FET gate / drain /
LED-cathode nodes).

> The FB-divider tap (`FB_*`), the switch node (`SW_*`) and the BOOT/CBOOT node
> are SIGNAL because they are the regulator's *internal* feedback/switching
> wiring, not a rail anything off-sheet connects to. A current-monitor would
> never shunt these.

## The reg-side vs rail-side split

Each regulator's **output cluster** (inductor node, output bulk caps, FB sense,
PG LED, BIAS tie) sits on a `+VOUT_x_REG` net; the board **rail** the loads see
is the separate `+VOUT_x` net. A project that inserts a **series shunt** (an
INA3221 rail-current monitor, say) bridges `+VOUT_x_REG → +VOUT_x` so the
*consumer* current flows through — and is **measured by** — the shunt, while the
regulator's own input-cap ripple and output bulk stay on the reg side and are not
double-counted. A project with no monitor simply binds the two abstract names to
the same real rail.

Crucially, **which side a consumer sits on is part of the contract**: the +3V3
buck's *input* caps (C7/C8) sit on `+VOUT_5V` (the rail side) because the +3V3
buck is a **+5V consumer**, so its draw is measured by the +5V shunt; the LDO's
*input* cap (C12) sits on `+VOUT_3V3` for the same reason. Get the side wrong and
the monitor measures the wrong current.

## Parts (from the global `parts/` lib + inline passives)

| ref | value | lib / part | LCSC |
|-----|-------|-----------|------|
| U1 | LM61460AANRJRR | `parts/LM61460AANRJRR/` — **faithful dossier symbol (0 hand-built symbols)** | C2864505 |
| U2 | TPS54302DDCR | `Regulator_Switching:TPS54302` (3 A sync buck) | C311983 |
| U3 | AP2112K-1.8 | `Regulator_Linear:AP2204K-1.5` drawing (= AP2112K SOT-23-5) | C176944 |
| Q1 | AO3400A | `Transistor_FET:Q_NMOS_GSD` (+1V8 PG sense FET) | C20917 |
| L1, L2 | 10 µH | `SWPA8040S100MT` (Sunlord shielded power inductor) | C37429 |
| C1, C25 | 100n | +5V buck VIN HF bypass (50 V X7R, one per VIN/PGND pair) | C14663 |
| C2, C3 | 10u | +5V buck input bulk (1206, ≥10 µF) | C13585 |
| C5, C6, C26 | 22u | +5V buck output bulk (0805 25 V) | C45783 |
| C4, C9 | 100n | BOOT (CBOOT) caps | C14663 |
| C24 | 1u | LM61460 VCC int-LDO bypass | C15849 |
| C28 | 1u | LM61460 BIAS bypass | C15849 |
| C27 | 22p | +5V FB feedforward (C0G) | C1653 |
| C23 | 75p | +3V3 FB feedforward (C0G) | C22399620 |
| C7 | 100n | +3V3 buck input bypass | C14663 |
| C8, C10, C11 | 22u | +3V3 buck input/output bulk | C45783 |
| C12, C13 | 1u | LDO input / output caps | C15849 |
| R1 | 40.2k | +5V FB top (**BOM-critical**: a 120k mis-key → ~13 V, fatal) | C12447 |
| R2 | 10k | +5V FB bottom | C25804 |
| R4 | 100k | +3V3 FB top | C25803 |
| R5 | 22k | +3V3 FB bottom | C31850 |
| R10 | 22k | LM61460 RT (fSW = 600 kHz) | C31850 |
| R11 | 10R | LM61460 BIAS series | C22859 |
| R12 | 1k | +5V FB feedforward RFF | C21190 |
| R3 | 1k | +5V PG LED resistor | C21190 |
| R6, R9 | 330R | +3V3 / +1V8 PG LED resistors | C23138 |
| R7 | 1k | +1V8 PG-sense FET gate-stop | C21190 |
| R8 | 100k | +1V8 PG-sense FET gate pulldown | C25803 |
| D1, D2, D3 | red | rail-present LEDs | C2286 |
| TP1–TP4 | +VOUT_5V / +VOUT_3V3 / +VOUT_1V8 / GND | `Connector:TestPoint` (rail probes) | — |

## Consuming it from a project

A project supplies a thin adapter declaring ONE standard `META` dict (the adapter
contract, `schgen.core.subsystem.Meta`) and forwards it:

```python
from subsystems.power import power

META = {
    # abstract subsystem net -> your real board net (ALL external rails + ports)
    "bind": {
        "+VIN": "+VIN_SYS",
        "+VOUT_5V_REG": "+5V_REG",   "+VOUT_5V": "+5V",
        "+VOUT_3V3_REG": "+3V3_REG", "+VOUT_3V3": "+3V3",
        "+VOUT_1V8_REG": "+1V8_REG", "+VOUT_1V8": "+1V8",
        "GND": "GND",
        "EN_VOUT_5V": "EN_5V0", "EN_VOUT_3V3": "EN_3V3",
        "EN_VOUT_1V8": "EN_1V8",
    },
    # optional: tell the linker which of your sheets binds a deferred enable
    "expects": {"EN_VOUT_5V": "bringup (rail-enable cells)", ...},
    # optional house-style overrides (keep your power-tree note byte-stable)
    "notes": {"draws_5v": "PG LED (...) + FB divider 60 uA", ...},
}

def circuit():
    return power.circuit(META)
```

The four standard `META` keys (`bind` / `expects` / `buses` / `notes`) are
universal across every reusable subsystem — a typo'd top-level key is a hard
`CircuitError`, never silently dropped. `bind` renames every external **in place,
order-preserving** (POWER/GROUND/PORT only — a SIGNAL net is private wiring and is
never rebound; a SIGNAL key or a collision is a hard `CircuitError`). Because the
rename preserves net insertion order, parts, refs, NCs and port-type payloads,
**binding to the exact names a hand-written sheet used yields a byte-identical
emitted sheet.** The carrier adapter is `carrier/subsystems/power.py` — and the
carrier's `power.kicad_sch` golden render + its power-tree report are unchanged by
the migration.

## Design notes (datasheet)

- **+5V buck = LM61460, 6 A.** The board's heaviest converter (2.95 A @ 5 V). FB
  divider 40.2k/10k @ Vref 1.0 V → 5.02 V; fSW 600 kHz (RT = 22k); 10 µH; 100 nF
  CBOOT (RBOOT shorted, fastest SW edge); **BIAS tied to VOUT** via 10 Ω + 1 µF
  (DS 9.2.2.9, cuts internal-LDO loss at VOUT = 5 V); a 22 pF CFF + 1k RFF FB
  feedforward (DS 9.2.2.10, phase boost with the all-ceramic 3×22 µF output).
- **The LM61460 heat path is GND.** The VQFN-HR has **no center EP**; its
  die-attach heat path is the PGND1/PGND2 power-ground pads (+ AGND), all on the
  GND pour. They are netted to GND (a real net, not a prose layout note), so the
  EP-equivalent is netlist-verifiable.
- **+3V3 buck = TPS54302, 3 A.** FB divider 100k/22k @ Vref 0.596 V → 3.31 V;
  100 nF BOOT; 10 µH; 75 pF FB feedforward (all-ceramic output idiom).
  *Thermal:* SOT-23-6 with no EP — the gate's bare 2s2p RthJA overstates Tj, so
  U2 carries a **layout-critical thermal waiver** (power-pour + thermal-via
  layout → ~45–55 °C/W; verify by sim/bench, else move to an EP buck).
- **+1V8 LDO = AP2112K, 600 mA.** 1 µF in / 1 µF out.
- **Power-good LEDs.** +5V and +3V3 light a red LED directly off the reg-side
  rail. +1V8 can't (red Vf ≈ 2.0 V > 1.8 V), so an AO3400A senses +1V8 (1k
  gate-stop + 100k pulldown → Vgs ≈ 1.78 V, clear of the 1.45 V Vth-max) and
  sinks a 330R+LED chain from +3V3, which is necessarily up before +1V8.

## Local test vs board gates

`test_power.py` runs the **subsystem-local** slices offline: declared abstract
interface, the faithful `LM61460AANRJRR:LM61460AANRJRR` dossier symbol (0
hand-built symbols), model completeness (every pin
netted-or-NC), the LM61460 GND heat path, decoupling completeness (design_rules
DECAP/EP/STRAP), the **FB-divider ratios** (the BOM-critical regulator output
set), the **reg-side vs rail-side split**, internal-SIGNAL preservation,
part-rating coverage + per-rail cap derating, the SPICE-subckt ↔ netlist passive
match, and the bind contract.

The analytic **SPICE FB-divider voltage** check is intrinsically rail-NAME-aware
(it validates each divider against the real rail's nominal via
`powertree.rail_volts`), so — like the I2C pull-up and power-tree headroom — it is
a **board-level** concern and the local test runs it on the **bound** (carrier-
named) circuit. **Cross-board** gates stay aggregated at board level and are
*not* duplicated here: the EN linker graph, the full power-tree headroom across
the regulator tree, the thermal join, board ERC and the board netlist merge — all
run by `schgen board`.

```bash
PYTHONPATH=. python3 -m pytest subsystems/power/test_power.py -q
```
