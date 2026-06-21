# Carrier-side rework register

**Scope.** Only changes that are the **carrier's** responsibility — the
schgen-generated design at `carrier/`. Rework that belongs to the **SoM** (the
raw-KiCad design at `som/`) is tracked separately in
[`som/SOM_ELECTRICAL_AUDIT.md`](../som/SOM_ELECTRICAL_AUDIT.md) and
[`som/SOM_CARRIER_COORDINATION.md`](../som/SOM_CARRIER_COORDINATION.md) and is
**deliberately excluded here** (see the last section for why each is SoM-side).

**How to read status.** Every electrical item below is **landed in the schgen
generator** (the design source of truth). A fresh `schgen board` already emits
the corrected design — for a respin there is nothing to do but rebuild. The
*"on a pre-fix board"* note is guidance only: what it would take to rework a
physical carrier fabricated *before* the cited commit. "respin" means the fix is
in copper/part-mapping and a bodge is not practical.

These items came from the multi-agent electrical audit (3 passes) + the 59-agent
SoM↔carrier coordination pass, each finding **re-verified by hand** against the
netlist/datasheet before landing (several audit "fixes" were themselves wrong —
see [`audit-findings-reverify`]). DRC/ERC/netlist were green the whole time;
these are faults those gates structurally cannot see.

---

## A. Closed — board-dead / functional (electrical)

| # | sev | item | root cause | fix landed | commit | on a pre-fix board |
|---|-----|------|-----------|-----------|--------|--------------------|
| C1 | CRITICAL | **DF40 no-mate** — carrier J1/J2/J3 were `DF40C-100DS` receptacles, same gender as the SoM ⇒ stack cannot seat, 0/300 contacts | both boards instantiated the *receptacle*; DS mates only to DP plug | carrier → `DF40C-100DP-0.4V(51)` plug (LCSC **C531031**); pads 1–100 keep the contract net→pad map, 101–104 NC hold-downs | `41c7093` | connector swap: desolder DS, fit DP (different footprint — 104 vs 100 pads; effectively respin the 3 mezz sites) |
| C2 | CRITICAL | **SW2 module-DIP shorted its enable pairs** — `(n,17-n)` diagonal map bridged adjacent enables | `DSHP08` footprint numbers its bottom row 9..16 (unlike DSHP04's 8..5); the adapter assumed the DSHP04 diagonal | fix the **adapter** `SW2_MAP` to the straight `(n,n+8)` column pairing (faithful footprint is source of truth — the audit's "renumber the footprint" was backwards) | `b1f9a2f` | DIP-to-net wiring is in copper ⇒ respin |
| C3 | CRITICAL | **LCD backlight boost diode D1 reversed** — Schottky cathode/anode swapped on the LX node | `Device:D_Schottky` pin1=K/pin2=A; the adapter wired it as if pin1=A | swap so D1.1 (K) → output `LCD_VLED_P`, D1.2 (A) → `LCD_BL_SW` | `b1f9a2f` | 2-pin part — desolder + rotate 180° (bodge feasible) |
| C4 | CRITICAL | **JTAG TDI/TDO swapped** at the CH347T | CH347T pin7 = MISO/TDO (input), pin8 = MOSI/TDI (output) — wired opposite | swap `DBG_FT_TDI`↔`DBG_FT_TDO` on U1.8/U1.7 | `b1f9a2f` | trace swap ⇒ respin (or fine-wire bodge) |

## B. Closed — protection / supply margin (would compromise but not board-dead)

| # | sev | item | fix landed | commit | on a pre-fix board |
|---|-----|------|-----------|--------|--------------------|
| B1 | MEDIUM | **Pmod host ports unprotected** — 16 bank-13 IO exposed at the headers with no ESD | add 4× `TPD4E1U06DBVR` (LCSC C124691) clamping the **SoM-side** net (inboard of the 200R, so the array doesn't mesh the float placer) | `f89059b` | new parts (no pads on old board) ⇒ respin / dead-bug |
| B2 | MEDIUM | **+3V3 FB divider mis-centred** | R4 (FB-bottom) `22.1k → 23.2k` (LCSC **C23346**, verified via EasyEDA API — no guessed code) ⇒ Vout re-centres to 3.32 V; SC setpoint follow-up 3210→3320 mV | `f9b4e06`, `a7fd068` | swap one 0603 resistor (bodge feasible) |
| B3 | MEDIUM | **USB-C VBUS lacked bulk** | add `RVT1C101M0605` 100 µF / 16 V electrolytic (LCSC **C970684**) on VBUS, pad1=+; landing it forced + fixed a root grow-loop edge-fit bug in the placer | `0e00282` | add one electrolytic if a pad exists; else respin |
| B4 | LOW | board_aux rail lacked bulk; ethernet CT / LCD-RGB ESD decisions | board_aux bulk cap added; ethernet centre-tap & LCD-RGB ESD intentionally **skipped** (documented engineering decision) | `5ff8c12` | add one cap (feasible) |

## C. Closed — mechanical / LAW-6 (placement, mating-face, 3D)

| # | item | fix landed | commit |
|---|------|-----------|--------|
| C-mech1 | USB-C faced its mouth inboard | flip mating-face outward in the footprint **and** the 3D model, + the gate | `cf0068e` |
| C-mech2 | QWIIC ZX-SH faced inboard / body off its pads | re-face +Y→−Y; align 3D body to pads | `23dead2`, `36f1ef7` |
| C-mech3 | 3D bodies planted off their pads (6 parts) | re-seat + a HARD model-position gate | `7ef1355` |

## D. Closed — self-documenting silk

| # | item | fix landed | commit |
|---|------|-----------|--------|
| D1 | off-board connectors unlabelled on bare board | short FUNCTION label beside each (PWR / USB OTG / HDMI TX-RX / ETH / …); J-ref hidden | `34a9e03` |
| D2 | interior dev headers unlabelled | GPIO / JTAG / SWD labels | `765f4c4` |
| D3 | **switches unlabelled** | function label on every DIP/button; config DIPs carry inline position legends (RAIL/MOD/5V/BOOT), overlap-aware placement | `6a42bd1` |

---

## E. OPEN — carrier-side (still to do)

| # | sev | item | proposed fix |
|---|-----|------|--------------|
| **OPEN-1** | LOW (silk / LAW-1) | **Interior reference designators overlap** — `TP7001/7002/7003`, `U18001-4`, `U19001-3`, `D33002-4` etc. sit on top of each other on the top silk in the bringup_rails / debug_boot clusters (KiCad auto-ref placement). The *descriptor labels* I added dodge these, but the auto-refs themselves still collide ⇒ text-over-text. Cosmetic (does not affect function), but a clean board wants zero overlap. | Extend the overlap-aware placer (`_place_clear_label` / `_emitted_text_boxes` in `schgen/generate/pcb.py`) to re-place the *component* reference designators too — not just the descriptor labels; **or** hide test-point (`TP*`) refs (they're probed by net, not silk). |
| ~~OPEN-2~~ ✅ RESOLVED (`f648ecb`) | LAW-6, motor_io | **XT60 ESC-power connectors edge-flush** — DONE. The XT60PW-M is horizontal edge-mount with a **+X** mating mouth; the placer only oriented +Y/−Y, so it was extended for +X/−X mouths (new `_ROT_FACE_POS_X/_NEG_X` + the `_mating_face_out_dir`/`connector_edge_rotation` oracle), `XT60PW-M` added to `CONN_MATING_FACE` (+X) + `floorplan._EDGE_FAMILIES` + the `connector_model_gate` exception. Root-caused a coincident-XT60 short (the `CONN_MATING_FACE`/`_EDGE_FAMILIES` authority mismatch tripped the interior re-flow guard) + closed the `connector_spacing_gate` blind spot (LAW-4 coincident-connector hard-fail). Both XT60s now spaced ~16.5 mm along the E edge, mouths off-board; PLACEMENT + CONNECTOR-MODEL gates PASS, DRC 0. |
| **OPEN-3** | MED (motor_io, API-blocked) | **3 sourced-parts adds blocked on the EasyEDA search API outage** (specs ready, NOT guessed — LAW 7): (a) a **5 V-rated** output ESD array on the 8 ESC PWM lines (the 3.3 V PESD3V3L4UG would clamp the 5 V PWM); (b) a **220–470 µF ≥35 V** bulk electrolytic on `ESC_VRAIL_IN` to damp the hot-plug LC ring under the INA3221's 26 V; (c) a **2–3 W 2512 10 mΩ** shunt + a fuse/polyfuse if a rail current ceiling above the present ~7 A (1 W shunt limit) is wanted. | Re-run the EasyEDA search API (`api/eda/product/list?keyword=`) when it recovers, `schgen part add` the verified LCSCs, instantiate, re-gate. |

*(No open carrier-side **electrical** faults — all functional/supply faults are closed in §A/§B. The motor_io OPEN items are LAW-6 placement polish + API-blocked SI/protection adds, all documented in the motor_pwm/motor_sense READMEs.)*

---

## F. NOT carrier-side — SoM design (for reference, do NOT do here)

The carrier's DF40 pin map is **extracted from the SoM** (`som_interface.json` ==
SoM netlist 0/300). Changing a pin assignment carrier-only would *diverge* from
the SoM and break that contract, so these must be done in `som/`:

| item | why SoM-side | tracked in |
|------|--------------|------------|
| **Camera CSI-2 LP receive path** (DNP) | the HS XAPP894 net exists; completing the LP path needs new inputs, but **J3 bank-35 has 0 free pins** ⇒ requires a SoM pinout reallocation | coordination report (downgraded to MEDIUM after re-verify) |
| **FMC_LA08 diff-pair split** (J1.74_P / J1.92_N, 18 contacts apart) | re-pinning means editing the SoM schematic **and** rerouting `som/Zynq_SoM.kicad_pcb`, then re-extracting the contract | coordination report (MEDIUM) |
| **DDR3L VRP/VRN swapped** (R46/R47 rail ends) — board-dead | SoM copper; UG933 requires VRP→GND, VRN→VCCO_DDR | `SOM_ELECTRICAL_AUDIT.md` (CRITICAL) |
| **DDR x16 on wrong PS byte lanes** DQ[31:16] — board-dead | SoM copper; UG585 requires DQ[15:0] for a 16-bit bus | `SOM_ELECTRICAL_AUDIT.md` (CRITICAL) |

**Refuted coordination findings** (verified correct as-drawn — do NOT "fix", it
would *introduce* a defect): +5V_SOM = 4.65 V is correctly centred (real SoM reg
floor 2.75 V); +5V_SOM inductor is adequate (~2.15 A real draw, not 5.2 A); SC-I2C
on PA4/PA5 is forced + fine for the FUSB302's autonomous PHY; JTAG TCK pull-absence
is correct per IEEE 1149.1.
