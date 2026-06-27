# SOM Electrical Audit — Consolidated Report

**Target:** Xilinx Zynq-7020 (XC7Z020-CLG484) System-on-Module — real KiCad 10 design at `som/`.
**Date:** 2026-06-20. **Designer of record:** G. Incerti. **Status in file:** RELEASED.

This single document consolidates three independent multi-agent investigations (≈155 agents, ~6.5 M tokens), each with its findings independently re-verified by the orchestrator against the netlist and primary vendor documentation (Xilinx UG471 / UG933 / UG585, Micron, ISSI, Hirose, Realtek, LCSC):

- **Part I — Comprehensive subsystem audit** (45 agents): every subsystem, passive, and decision, with skeptic re-derivation and a 3-lens adversarial panel.
- **Part II — Competitive second pass** (90 agents): rival red-teams hunting *new* defects beyond Part I, on a new **schematic↔PCB↔BOM cross-source** axis, with dual-stance re-litigation of Part I.
- **Part III — Pin-level competitive pass** (20 agents): exhaustive bus-by-bus, pin-by-pin verification against the extracted UG585/datasheet text, explicitly hunting a *third* board-dead defect. **Result: none found** — one new HIGH (Ethernet PHY clock amplitude) plus a positive "buses verified clean" coverage record.

A fourth, **cross-board** investigation — the SOM↔carrier interface coordination (59 agents, 3-way DF40 pin map) — is reported separately in **[SOM_CARRIER_COORDINATION.md](SOM_CARRIER_COORDINATION.md)**. Its headline **overturns finding #3 below**: the carrier does **not** provide the mating DF40 plug — both boards instantiate the `DF40C-100DS` receptacle, so the assembled stack **cannot mate** (a system-level CRITICAL).

Ground truth for all four: the flat netlist exported with `kicad-cli sch export netlist` (**287 components / 593 nets**) plus the fabricated `Zynq_SoM.kicad_pcb`, the assembly BOM, and the carrier netlist/`som_interface.json` contract.

---

## Master verdict

**The SoM is NOT buildable as drawn. DDR memory will not function for TWO independent reasons**, each sufficient on its own to prevent the PS from using DRAM. Both are corner-case wiring errors that pass ERC, DRC, and netlist checks because every pin terminates to a valid net through a valid part. Outside of DDR, the design is overwhelmingly sound: power tree, decoupling, clocking, reset/sequencing, straps and terminations are correct and datasheet-grounded, and a large adversarial sweep of secondary hypotheses was refuted (see Part II rejected list). The Part III exhaustive pin-level walk (DDR addr/cmd, Zynq power balls, MIO/boot, clocks, RGMII, ULPI, QSPI) found **no third board-dead defect** — the two board-dead faults are confined to the DDR subsystem — but surfaced one verified HIGH: the **Ethernet PHY 25 MHz reference clock is driven at 1.8 Vpp into a 3.3 V input (datasheet min 3.15 Vpp)**.

### Consolidated severity tally (post-verification)

| Severity | Count | Items |
|---|---|---|
| **CRITICAL** | **2** | (1) DDR DCI **VRP/VRN swapped** (R46/R47); (2) DDR3L x16 **wired to the wrong Zynq PS byte lanes** DQ[31:16] |
| **HIGH** | **3** | eMMC U7 **LCSC≠MPN** (Samsung vs ISSI); **VIN on only 14 DF40 contacts**; **RTL8211F EXT_CLK at 1.8 Vpp** vs datasheet 3.15–3.45 Vpp |
| **MEDIUM** | ~15 | rails at module rating w/ ~0 headroom; cap DC-bias derating on VIN; DDR DCI 100R vs 80R; STM32 VREF+ topology; PUDC_B unstrapped; BMI323 VDDIO DNP; carrier-VCCO dependency; **R80/R81 sch≠PCB/BOM**; DF40 sch↔PCB footprint field; … |
| **LOW** | ~35 | placeholder LCSC; 10k vs 20k straps; oscillator MPN identity conflicts; split LVDS/MRCC pairs; DF40 stack-height BOM conflict; `G***` un-annotated footprint; decoupling/termination niceties; … |
| **INFO** | ~73 | verified-correct decisions (FB dividers, rail map, sequencing, JEDEC ballout, oscillators, exposed-pad grounding) |
| **Rejected** | ~18 | candidates the Part II adversarial panel refuted (do not re-raise) + the DF40 "gender" fix corrected/demoted |

### The must-fix list (in order)

1. **DDR byte-lane mapping (CRITICAL, board-dead).** Re-route U1 from PS_DDR_DQ[31:16]/DQS2/DQS3/DM2/DM3 to the controller's active **lower lanes DQ[15:0]/DQS0/DQS1/DM0/DM1**. Verified against **UG585 Table 10-3** ("16-bit Data bus: [15:0]"), the DDRIOB register map, and the ECC table; ball M1=PS_DDR_DQ16 confirmed vs silicon. Detail: Part II §"CRITICAL … byte lanes".
2. **DDR DCI VRP/VRN swap (CRITICAL, board-dead/marginal).** Swap rail ends: R47(VRP)→**GND**, R46(VRN)→**+1V35**. Verified verbatim against **UG471 + UG933 + UG585** (three Xilinx sources). Detail: Part I §1.
3. **eMMC part identity (HIGH).** LCSC `C499918` = Samsung KLM8G1GETF-B041, but symbol/MPN = ISSI IS21ES08G. Pick one; re-verify ballout. Detail: Part I §2.
4. **VIN connector current budget (HIGH).** 14 VIN contacts (J1.1–14) = 4.2 A ceiling (~2.1 A derated). Recompute against real max load; add VIN+GND contacts or bound the input current. Detail: Part II.
5. **Ethernet PHY clock amplitude (HIGH).** X2 (25 MHz) is powered from **+1V8** → ~1.8 Vpp into U3.37 EXT_CLK, whose AVDD33 oscillator section needs **3.15–3.45 Vpp** (RTL8211F Table 55, verified vs the datasheet PDF). Fix: move X2's rail from +1V8 to **+3V3** (via L6); placed YXC osc is rated 1.8–3.3 V. Detail: Part III §1.
6. **Source-of-truth & BOM hygiene.** R80/R81 (sch 5k1/12k vs board 100k/100k), DF40 footprint/stack-height, `G***`, oscillator MPNs, placeholder LCSC codes.

> **⚠ System-level (SOM↔carrier) — see [SOM_CARRIER_COORDINATION.md](SOM_CARRIER_COORDINATION.md).** The cross-board check found the SOM and carrier **both** use the `DF40C-100DS` receptacle → the stack **cannot physically mate** (system CRITICAL; one side must become the `DF40C-100DP` plug). The earlier in-SOM demotion of the DF40 item to MEDIUM assumed the carrier supplied the plug — that assumption is now **disproven**. The coordination pass also found: a non-functional MIPI camera front-end, the carrier's `+5V_SOM` set to **4.65 V** (under-feeds SOM VIN), its `+5V_SOM` inductor under-rated for SOM draw, an FMC diff pair (LA08) split across non-adjacent DF40 contacts, and the carrier's SC-I2C bus on STM32 **PA4/PA5** (no hardware I2C).

> **Note on corrections the orchestrator made to the agents' output** (your "audits over-confirm" rule in action): the Part I auditors' DF40 fix direction was **inverted** (corrected, demoted HIGH→MEDIUM); the Part II byte-lane finding was **under-rated** at HIGH/0.5 (elevated to CRITICAL after the UG585 check closed the open question); and the Part III boot-strap finding had **mislabeled resistors** (R13 is QSPI_CLK→GND, not a boot strap — corrected in Part III, conclusion unchanged). Every CRITICAL/HIGH was re-verified by hand against the netlist and the primary-source PDF before landing here.


---

# Part I — Comprehensive Subsystem Audit (Pass 1, 45 agents)


Xilinx Zynq-7020 (XC7Z020-CLG484) System-on-Module — final audit report compiled from panel-verified, multi-agent findings.

> **Method:** 45-agent investigation (13 per-subsystem auditors + independent skeptic re-derivation + 3 global cross-cuts + a 3-lens adversarial panel on every CRITICAL/HIGH) run against the LAW-0 ground-truth netlist exported from KiCad (`kicad-cli`, 287 components / 593 nets). 2.49 M tokens.
>
> ## Independent verification (orchestrator-checked against primary sources)
> Every headline finding was re-checked by hand against the extracted netlist and the actual vendor PDFs/LCSC before publishing (per the "audits over-confirm" rule). Results:
> - **CRITICAL #1 (DDR VRP/VRN swap) — CONFIRMED.** Netlist: VRP `U2.N7`→`R47`→**+1V35**, VRN `U2.M7`→`R46`→**GND**. Verbatim **UG933 v1.7.1**: *"For memory types that require termination (DDR2, DDR3) VRP must be pulled Low to GND and VRN needs to be pulled High to VCCO_DDR."* The board is exactly inverted. (The auditor's first instinct on the *direction* matched my own incorrect recollection — the PDF settled it; the design is wrong.)
> - **HIGH #2 (eMMC part identity) — CONFIRMED.** LCSC **C499918 = Samsung KLM8G1GETF-B041** (verified on lcsc.com); U7 symbol/Value/MPN = ISSI **IS21ES08G / IS21ES08GA-JCLI-TR**. Mismatched BOM line. ISSI's real codes are C1351346 / C1236826.
> - **HIGH #3 (DF40 gender) — CORRECTED & DOWNGRADED to MEDIUM.** The audit's recommended fix was **inverted**. Reality: schematic footprint field = `HRS_DF40C-100DP` but the **fabricated PCB and BOM both use `HRS_DF40C-100DS`** (MPN `DF40HC(3.0)-100DS`, LCSC C597931) — the built board is self-consistent on DS. The real defect is a stale **schematic↔PCB footprint mismatch**; the fix is to set the schematic symbol footprint **DP→DS** (value is already DS), *not* to change the value to DP.

## Executive summary

**Board-health verdict: NOT YET FABRICATION-READY.** The schematic is overwhelmingly sound — the core power tree, decoupling, clocking, reset/sequencing, and the great majority of strap and termination decisions are correct and datasheet-grounded. However, there is **one confirmed board-fatal defect** (DDR DCI VRP/VRN polarity swap) and a cluster of **BOM/footprint integrity problems** that must be resolved before any build. These all pass ERC/DRC/netlist checks because every pin is terminated to a valid rail through a valid part — they are silent, design-intent defects.

**Counts by severity (after panel adjudication and demotion of false positives):**

| Severity | Count | Notes |
|---|---|---|
| CRITICAL | 1 | DDR DCI VRP/VRN rail swap (3/3 confirm; verified vs UG933 PDF) |
| HIGH | 1 | eMMC MPN/LCSC mismatch (3/3; verified vs lcsc.com) |
| MEDIUM | ~14 | DF40 schematic↔PCB footprint mismatch (corrected down from HIGH); power-margin/at-limit rails, cap voltage derating, oscillator/footprint mismatches, carrier VCCO dependency, BMI323 VDDIO decoupling DNP |
| LOW | ~25 | placeholder LCSC codes, strap-value deviations (10k vs 20k), best-practice decoupling/termination niceties |
| INFO | ~50 | verified-correct decisions (FB dividers, rail assignments, sequencing, oscillators, JEDEC ballout) |
| Demoted | 1 | "VRP/VRN must be 240R" — **0/3 confirm, LIKELY A FALSE POSITIVE** (see below) |

**The 4 things that matter most:**

1. **Fix the DDR3L DCI VRP/VRN rail swap (CRITICAL).** R47/R46 are wired to the opposite rails from what Xilinx UG933 requires. This will cause DDR3L training failures / marginal memory and is the single most important fix on the board.
2. **Resolve the eMMC part identity (HIGH).** U7's MPN (ISSI IS21ES08G) and its LCSC code (C499918 = Samsung KLM8G1GETF-B041) name two different devices. Pick one and re-verify the ballout.
3. **Fix the DF40 schematic↔PCB footprint mismatch (MEDIUM, corrected).** J1/J2/J3 schematic footprint field is DP but the fabricated PCB + BOM are DS. The built board is fine; fix the *schematic* footprint DP→DS so the next PCB sync doesn't swap to the wrong land. (The audit's original "change value to DP" recommendation was backwards.)
4. **Clean the BOM and lock placeholder parts.** Numerous `gia`/empty/`-` LCSC codes and placeholder oscillator/MPN values (X1, X2, U13, U4/U6/U10, several passives) must be assigned real, verified, orderable codes before release.

A recurring architectural theme — not a defect, but a **hard integration dependency** — is that all PL bank VCCO rails (13/33/34/35) and the entire power-on sequence are delegated off-module (carrier-supplied VCCO; STM32-firmware-driven sequencing). These must be documented as binding requirements in the SoM datasheet.

---

## CRITICAL & HIGH findings

Ranked by panel agreement, then severity.

### 1. [CRITICAL · 3/3 confirm] DDR3L DCI VRP/VRN reference resistors connected to the WRONG rails (swapped polarity)

- **What:** The PS DDR DCI reference resistors are on inverted rails. R47 ties `PS_DDR_VRP` (U2.N7) HIGH to **+1V35**; R46 ties `PS_DDR_VRN` (U2.M7) LOW to **GND**. This is exactly backwards.
- **Where:** Components **R47, R46, U2** (XC7Z020). Nets `/Zynq_B502_DDR/DDR_VRP`, `/Zynq_B502_DDR/DDR_VRN`, `+1V35`, `GND`. Confirmed from `/tmp/som_nets.txt`: `DDR_VRP = {R47.2, U2.N7}`, `R47.1 → +1V35`; `DDR_VRN = {R46.1, U2.M7}`, `R46.2 → GND`.
- **Why it's wrong:** Xilinx **UG933 (v1.7.1)**, section "PS_DDR_VRN, PS_DDR_VRP" (verbatim): *"For memory types that require termination (DDR2, DDR3) VRP must be pulled Low to GND and VRN needs to be pulled High to VCCO_DDR."* The required mapping is **VRP→GND, VRN→VCCO_DDR (+1V35)**; the design has the exact opposite.
- **Impact:** PS DDR DCI calibration measures a known external reference via VRP/VRN to set on-die termination/drive impedance. With both references inverted, the controller cannot calibrate correctly: expect **DDR3L training failures or marginal/unreliable memory at speed** (intermittent corruption, boot-from-DRAM failures). It passes ERC/netlist/DRC because both pins are validly terminated to a valid rail through a valid resistor.
- **Fix:** Swap the two rail connections — route R47 (VRP) to **GND** and R46 (VRN) to **+1V35** (VCCO_DDR). Relabel only the rail end of each resistor. Leave R45 (240R ZQ) and the VREF divider (R88/R89) untouched.
- **Panel vote:** 3/3 confirm. **Confidence: very high** — quoted directly from the UG933 PDF against the extracted netlist.

### 2. [HIGH · 3/3 confirm] eMMC BOM mismatch — MPN (ISSI IS21ES08G) ≠ LCSC C499918 (Samsung KLM8G1GETF-B041)

- **What:** U7's symbol/Value names **ISSI IS21ES08G** but the assigned LCSC code **C499918 resolves to a Samsung KLM8G1GETF-B041** (8GB eMMC). These are two different physical devices.
- **Where:** Component **U7**. From `/tmp/som_components.txt`: `VALUE=IS21ES08G, FOOTPRINT=Mylibrary:BGA153N50P14X14_1150X1300X100, LCSC=C499918`. The ISSI part's real LCSC codes are C1351346 / C2065377.
- **Why it's wrong:** A BOM line must name one physical part. Both candidates are 8GB eMMC 5.0 in JEDEC-153 11.5×13mm (so footprint/ballout-compatible at the JEDEC level), but they differ in ordering code, marking, internal NAND, and potentially RFU/VSSQ ball usage. The BOM is internally inconsistent about which part is actually placed.
- **Impact:** Procurement/assembly ambiguity. If the JLCPCB line item (Samsung C499918) is placed while the layout/symbol was drawn to the ISSI part, any non-standard ball behaves differently. (This directly couples to the LOW C1/VDDI finding — see MEDIUM/LOW section — which the corrected panel resolved as benign because C1 is a true JEDEC no-connect, but it can only be *certain* once the part is locked.)
- **Fix:** Pick one part. If ISSI is intended, set LCSC to **C1351346** (IS21ES08G-JCLI) or **C2065377** (-JCLI-TR). If the Samsung C499918 is what is stocked/placed, change the symbol Value/MPN to match and re-verify the ballout (especially ball C1).
- **Panel vote:** 3/3 confirm. **Confidence: high** — both part identities verified against LCSC; the JEDEC compatibility is a mitigation, not a resolution.

### 3. [MEDIUM · orchestrator-corrected — was HIGH 1/3] DF40 schematic footprint field (DP) ≠ fabricated PCB / BOM (DS)

> **Corrected after independent verification.** The original auditor framed this as "DS value on a DP land, keep DP and rename value to DP." That fix is **backwards** — the fabricated board is built DS.

- **What:** The schematic symbol footprint field for the three board-to-board connectors is `Mylibrary:HRS_DF40C-100DP-0.4V_51_` (**DP plug**), while the **actual `.kicad_pcb` places `HRS_DF40C-100DS` ×3** and the **BOM line is DS** (`HRS_DF40C-100DS-0.4V_51_`, MPN `DF40HC(3.0)-100DS-0.4V(51)`, LCSC `C597931`). The connector Value string is also `...DS`. So **value + PCB + BOM all agree on DS**; only the schematic symbol's footprint property is stale at DP.
- **Where:** Components **J1, J2, J3**. Verified: netlist footprint field = `...DP` (from schematic); `grep HRS_DF40C... Zynq_SoM.kicad_pcb` → 3× `...DS`; `BOM.csv` → `...DS`.
- **Why it matters:** The built board is internally consistent and (assuming the carrier uses the mating DP/header) correct. But the schematic's footprint field disagrees with layout, so the next *"Update PCB from Schematic"* would silently try to swap all three connectors to the DP land (2.71 mm vs 3.08 mm pad rows, mirrored pin-1) → unsolderable / reversed. It is a latent schematic↔layout-sync defect, not a defect in the current fab.
- **Impact:** Not build-blocking for the existing Gerbers. Build-blocking on the *next* sync if not fixed.
- **Fix:** Set the **schematic** symbol footprint for J1/J2/J3 from `HRS_DF40C-100DP-0.4V_51_` **→ `HRS_DF40C-100DS-0.4V_51_`** so schematic, PCB and BOM all read DS. Do **not** change the Value to DP. Independently confirm the carrier mates a DF40 header (DP) to this DS receptacle.
- **Provenance:** Panel was 1/3 (it disagreed with its own fix direction, correctly). Orchestrator verification against the PCB/BOM resolved direction and downgraded severity. **Confidence: high on the mismatch and the fix direction.**

### Demoted (was proposed HIGH): "VRP/VRN must be 240R per UG933" — 0/3 confirm

- **What was claimed:** That R46/R47 (the DCI reference resistors) should be **240R** to match the ZQ resistor.
- **Adjudication:** **0/3 confirm → LIKELY A FALSE POSITIVE.** The 240R figure conflates the DDR3 **ZQ** resistor (R45 = 240R, correctly RZQ to GND) with the DCI **VRP/VRN** reference. UG933's actual VRP/VRN rule is *"twice the memory's trace and termination impedance"* — i.e. 80R for a 40R system or 100R for a 50R system, **not** a fixed 240R. The real, surviving impedance question is captured separately as a MEDIUM finding (100R vs 80R, contingent on the board's chosen DDR impedance target). The "240R" framing is rejected.

---

## MEDIUM / LOW / INFO findings (grouped by subsystem)

Only the actionable MEDIUM/LOW items and the most load-bearing INFO confirmations are tabulated. Panel corrections are folded into the "Note / corrected resolution" column.

### Power regulators

| Sev | Finding | Components / nets | Action / corrected resolution |
|---|---|---|---|
| MED | +1V0 (VCCINT) on 4A TPSM82864A annotated at 4A budget — zero headroom | U8 (C5219321) | **Corrected to MEDIUM (not HIGH):** 4A is the documented budget = module rating, not a measured overload. Populate the drop-in 6A **TPSM82866AA0SRDJR** (identical footprint/BOM) for ≥33% margin, OR formally tally worst-case VCCINT incl. transients and confirm <<4A. |
| MED | +1V8/+3V3 (MPM3834C, 3A) — and +1V35 (MPM3822C, 2A) — annotated at module rating | U4, U6, U10 | Re-tally worst-case load on +3V3, +1V8 **and +1V35** for ≥20% headroom under each rating (3A/3A/2A). The +1V35 rail carries DDR3L VDD/VDDQ with notable dynamic current. |
| MED | 47µF/6.3V bulk (C16780) on 5V VIN and 3.3V rails — heavy DC-bias capacitance loss | C25/27/28/29/31 | Replace with 47µF/16V (25V on VIN) X5R/X6S, or verify post-derating effective C meets each datasheet minimum. 22µF/16V parts (C98190) are fine. |
| LOW | Placeholder/invalid LCSC (`gia`, empty) | U13, R80, R81, U4, U6, U10 | Assign valid orderable codes but **verify each variant/package against schematic intent** before committing (wrong fixed-Vout LDO variant or module package would be a real error). U4/U6=MPM3834C ECLGA-14, U10=MPM3822C QFN-18, U13=TPS7A20 (true package per below), R80/R81 0402 1%. |
| LOW | U13 LDO symbol uses X2SON-4 (DQN) pin map on a footprint named "TLV707" | U13 | Net mapping is electrically correct (both are X2SON). **Rename footprint to its true package** (X2SON-4 / DQN) and lock MPN to the DQN-package TPS7A20 so a SOT-23-5 part can never be fitted (that would dead/short the LDO). |
| INFO | All FB dividers / VSET verified to target rails | R23/26/33/34/37/38/25 | +1V8=1.80V, +3V3=3.315V (+0.45%, OK), +1V35=1.350V, +1V0 via R25=28.7k VSET. No change. |
| INFO | EN pull-downs (100k, default OFF) + PG pull-ups (100k to +3V3_SC) present; STM32-sequenced 1V0→1V8→1V35→3V3 | R27-R36, U9 | Correct. |
| INFO | Q3 is a DONE-status FET (not power); integrated-inductor SW pins correctly NC | Q3, U4/U6/U8/U10 | Correct. |
| INFO | Sense/monitor dividers keep all rails within STM32 ADC range | R78-R85, U9 | Correct. |
| INFO | Rail consolidation (VCCINT/BRAM/PINT on +1V0; AUX/PAUX/MIO501/VCCBATT on +1V8) | U2, U8 | Both valid per UG933. |

### Zynq power & decoupling

| Sev | Finding | Components | Action |
|---|---|---|---|
| LOW | VCCADC filter 4.7µF+0.47µF below UG480 example (10µF) | L9, C103, C135 | If precision XADC inputs used, bump C103 to 10µF; if monitor-only, leave. GNDADC tie is fine. |
| LOW | VCCADC/VCCPLL ferrites L4/L9 0402 120R — verify Idc | L4, L9 | C275478 rates ~200-500mA >> few-mA analog load. OK, confirm. |
| INFO | VCCPLL filter (ferrite + 10µF + 470n) well-formed | L4, C65, C43 | Correct. |
| INFO | VCCBATT (G9) tied to +1V8 — no RTC/BBRAM battery (permitted) | U2 | Correct unless battery-backed key/RTC is a requirement. |
| INFO→ | VCCAUX/VCCPAUX bulk on +1V8 | C27/49/42/96 | **Downgraded to INFO:** +1V8 counts far exceed true UG933 v1.11 target; no caps to add. Only open item is PCB placement near the 1.8V ball field. |
| INFO | +1V0 bulk/bypass meets UG933 intent | C24/51/58/60/63/64 | Correct; scatter HF caps across VCCINT field in layout. |

### DDR3L memory

| Sev | Finding | Components | Action |
|---|---|---|---|
| MED | DCI VRP/VRN value = 100R; UG933 = 2× trace/term impedance (80R for 40R system) | R46, R47 | Confirm DDR3L impedance target. If 40R (typical) change to **80R**; if 50R deliberate, document. Re-verify after the CRITICAL polarity swap. |
| INFO | VREFDQ/VREFCA divider R88/R89 = 10k/10k → 0.675V (VDDQ/2), well bypassed | R88/89, C124/125/126/113 | Correct. |
| INFO | ZQ (R45=240R), CK diff term (R50=100R), RESET pull (R48=4k7), 24× 22R addr/cmd series term all correct | R45/50/48/49/51/52/72 | Correct (fly-by, ODT, no series R on data). |
| INFO | DDR3L rail = +1V35 on all VDD/VDDQ and Zynq VCCO_DDR; bulk ~156µF >> 25µF Micron min | U1, U2, C93/31/95/123 | Correct (1.35V, not 1.5V). |
| INFO | No external VTT/island termination — correct for single-load fly-by | U1 | Valid engineering decision. |

### Ethernet PHY (RTL8211F-CG)

| Sev | Finding | Components | Action / corrected resolution |
|---|---|---|---|
| MED | REG_OUT inductor L1 = 3.3µH, not a datasheet example value (2.2µH/4.7µH) | L1, U3 | **Corrected framing:** datasheet's hard constraints are REG_OUT ripple ≤100mVpp and switcher efficiency ≥75% (not a literal "only-these-two" list or L-value damage warning). Either bench-verify ripple/efficiency with 3.3µH, or change to 2.2/4.7µH — and in either case ensure **IDC/Isat ≥600mA** (the more pressing issue). |
| MED | L1 (C98336) current rating not confirmable as ≥600mA | L1 | Datasheet Note 2 requires ≥600mA; qualified parts are 750-1500mA. Confirm C98336 IDC and Isat ≥600mA with margin, else select a larger 0806. (Could not verify rating from public sources.) |
| LOW | RGMII straps (PLLOFF/TXDLY/RXDLY) pulled to global +1V8 vs datasheet DVDD_RG | R8/11/12, U3 | Acceptable; for strict compliance the strap top could be DVDD_RG (1V8A_ETH). Record as decision. |
| LOW | 25MHz reference X2 is a placeholder part | X2, R20, L6, C22 | **Corrected:** clock enters XTAL_OUT/EXT_CLK (U3.37), XTAL_IN grounded. Actionable defect = placeholder: value `ASE-xxxMHz`, blank LCSC. Lock to a real 25.000MHz CMOS oscillator whose output meets U3 EXT_CLK VIH on the 1.8V domain (1.8V part preferred), ≥±50ppm. |
| INFO | PHYAD=001 (valid); RXDLY=TXDLY=1, PLLOFF=0 (PHY supplies both 2ns delays → set Zynq GEM phy-mode = `rgmii`) | R7-R12, U3 | Correct. Verify bootloader doesn't override straps. |
| INFO | I/O-pad mode = external 1.8V (CFG_EXT=1, CFG_LDO=10); MDIO 1.5k pull-up; RSET=2.49k; magnetics off-module to J1 | R14-R19, R90, R16, U3, J1 | All correct vs datasheet. |
| INFO | RTL8211F supply decoupling complete and rail-correct | C3-C19, L2/L3, U3 | **Minor correction:** +3V3/DVDD33 switcher-input bulk is C1+C12 (4u7) + C2/C21 (100n); C11 is on +1V8, not a Cin. Place C1/C12 within ~0.5cm of pin29. |

### USB HS PHY (USB3318)

| Sev | Finding | Components | Action / corrected resolution |
|---|---|---|---|
| MED | X1 oscillator footprint (Kyocera 2.0×1.6) ≠ named Abracon ASCO part (1.6×1.2); no LCSC | X1 | Pick one MPN, assign LCSC, use the matching footprint. Verify pin-1/EN orientation against the vendor drawing. |
| LOW | USB3318 RESETB has pull-up to +1V8 (R5); datasheet says hold LOW until VDD18 stable | U5, R5, U9 | **Corrected: do NOT change R5 to a pull-down** — with STM32 GPIO high-Z at its own POR that would hold the PHY permanently in reset. Keep the 10k pull-up (RESETB tracks VDD18). Action = firmware note: STM32 PC6 must assert RESETB low until VDD18/VDDIO + 13MHz REFCLK stable, then release. |
| LOW | No 100nF HF bypass on USB3318 3.3V pins (only 4.7µF C141) | U5, C141 | Add a 100nF 0402 next to pins 3/4 (optionally one per pin). Not required if bench-validated. |
| LOW | Placeholder/garbage LCSC on USB-PHY passives; missing LCSC on U5/X1 | C20/138/142, R5, U5, X1 | Replace `gia` placeholders with real codes; assign USB3318C-CP-TR and the 13MHz oscillator. |
| INFO | USB3318 power architecture verified (external-3.3V, VDDIO=1.8V matched to Zynq bank 501); RBIAS=8.06k; REFCLK/CLKOUT 22R series term; VBUS/CPEN/ID/DP/DM usage correct | U5, R21/22/24, etc. | Correct vs DS00002367A. |

### System controller (STM32G431)

| Sev | Finding | Components | Action / corrected resolution |
|---|---|---|---|
| MED | VREF+ has no DC tie to VDDA — only 4.7µF to GND (works ONLY if firmware enables VREFBUF output mode) | U9, C139 | **Corrected:** sound, but do NOT shrink C139 below ~1µF (VREFBUF needs bulk); 4.7µF lengthens startup — firmware must wait for VRR before sampling. Optional DNP 0R to VDDA is acceptable **only if left unpopulated whenever VREFBUF is on** (populating it shorts the buffer to VDDA, can damage the part). Document the hard firmware dependency. |
| LOW | VREF+/VDDA missing dedicated 100nF HF cap | U9, C139/137/32 | **Corrected:** reasonable to add 100nF X7R at VREF+, but do not remove/shrink C139; VDDA's 470nF is already adequate. Frame as layout polish, not a noise defect. |
| LOW | Asymmetric I2C: 22R series on SCL only (R96), none on SDA | U9, R96/86/87 | Add a matching 22R on SDA or remove R96, for symmetry. |
| LOW | Rail-sense divider for 1V8 (5.1k/12k → ~1.26V, ratio 0.70) inconsistent with the other three (100k/100k, ÷2) | R80/81 etc. | Confirm firmware uses the correct per-channel scale factor; consider normalizing unless deliberate. |
| INFO | VDD/VBAT decoupling adequate; BOOT0 low (boot from flash) + carrier override; NRST RC+pull-up correct; no crystal (HSI16/HSI48+CRS), OSC pins repurposed as supervisor GPIO; STM32 owns full EN/PG/reset/boot-strap map | U9 et al. | Correct. Confirm carrier doesn't hold BOOT0 high; enable CRS for USB. |
| INFO | USB D+/D−, UCPD CC1/CC2 leave via J1 with no SoM-side ESD/Rd — correct (condition on carrier) | U9 | Document carrier must provide USB-C ESD + UCPD Rp/Rd. |

### Zynq PS MIO banks 500/501 & config/boot straps

| Sev | Finding | Components | Action / corrected resolution |
|---|---|---|---|
| MED | PUDC_B routed only to carrier (J3.39) with NO local pull — config-bank PL I/O pull-up control floats by default | U2.K16, J3 | Add a weak default strap on the SoM (4.7k–10k to GND to enable internal pull-ups, the safe default), and/or document the carrier requirement. **(Reported twice by independent agents; high confidence.)** |
| LOW | DONE (PL_DONE) has no external pull-up; 3-node net (U2.T12, Q3 gate, TP3) | U2, Q3, R91, D2 | **Corrected:** DONE is functional as drawn — the 7-series internal ~10kΩ pull-up to VCCO_0 (+3V3) brings DONE high after config, enough to switch Q3 and light D2. External pull-up (e.g. 4.7k) is optional noise-margin polish, **not** a fix for a dead indicator. |
| LOW | Boot/voltage-mode strap resistors are 10k; AMD UG585 specifies 20k for MIO[8:2] | R1/6/13/74/75/76/77 | **Corrected:** 10k establishes valid unambiguous levels and works; 20k is the recommended value → spec-conformance deviation to record, not a functional defect. Change to 20k or document. Keep stubs <10mm. |
| LOW | MIO6 PLL strap defined indirectly via R13 pull-down through 22R R95 | U2.A4, R95, R13 | DC level at MIO6 is GND (=0, correct) since R95=22R. For rigorous UG585 compliance place the strap on the Zynq side. Else accept. |
| LOW | STM32-driven boot bits MIO4/MIO5 have no fixed-rail default | U2, U9, R1/6 | Deliberate controller-selectable boot. Confirm firmware drives PA7/PB2 valid before PS_POR_B release; consider weak defaults. |
| LOW | PS-JTAG TCK/TMS/TDI/TDO have no local pulls (rely on carrier) | U2, J1 | Ensure carrier JTAG header provides TMS/TCK (TDI) pull-ups, or add on SoM if standalone robustness wanted. |
| LOW | PS_MIO_VREF_501 decoupling = 470nF where UG933 specifies 0.01µF | C94 | Optional: change to 10nF, or document deliberate over-decoupling. |
| INFO | Vmode straps VM[1:0]=10 → Bank500=3.3V, Bank501=1.8V; consistent with VCCO rails | R74/75, U2 | Correct. |
| INFO | PS_MIO_VREF_501 = 0.9V (10k/10k, VCCO_501/2) for RGMII HSTL18 | R92/93, C94 | Correct. |
| INFO | PS_CLK X3 (33MHz CMOS) on 3.3V = VCCO_MIO0; 22R series; QSPI CLK 22R + CS 10k pull-up; POR pull-up 3V3, SRST pull-up 1V8 (correct domains) | X3, R2/95/44/100/94 | Correct. |
| INFO | INIT_B/PROGRAM_B 4k7 pull-ups on VCCO_0 (=+3V3); reset/config fully owned by STM32 | R98/99/100/94, U9 | Correct. |

### Zynq PL bank 13

| Sev | Finding | Components | Action |
|---|---|---|---|
| LOW | 4 LVDS-capable pairs split (P routed, N floating): L15, L19, L21, L22; L20 fully floating | U2, J2 | Confirm pin-export intent. If any are meant differential, route N length-matched; else document single-ended-only and set bitstream UNUSEDPIN PULLDOWN. |
| INFO | VCCO_13 carrier-supplied via J2.1-3 (no on-SoM regulator); decoupling 1×47µF+2×4.7µF+4×0.47µF exactly matches UG933 per-bank | U2, J2, C127-133 | Document J2.1-3 = VCCO_BANK13 input, range 1.14-3.465V (HR). Optionally add TVS near J2.1-3 for third-party carriers. |
| INFO | No external VREF / no DCI VRP/VRN on Bank 13 — correct for LVCMOS/LVDS; 7 IO pins intentionally unconnected | U2 | Set UNUSEDPIN PULLDOWN in bitstream. |

### Zynq PL banks 33/34/35

| Sev | Finding | Components | Action / corrected resolution |
|---|---|---|---|
| MED | BMI323 IMU VDDIO tied to carrier-supplied VCCO_33 — IMU IO non-functional unless carrier powers VCCO_33, at carrier-chosen level | U14, U2, J2 | **Corrected: documentation-only.** Do NOT re-rail VDDIO to a fixed rail — IMU and FPGA bank-33 IO correctly share VCCO_33; a fixed VDDIO would create an IO-level mismatch needing a level shifter the design doesn't need. Add a design note that bank 33 must be powered and IO-standard-matched to use the IMU. |
| LOW | BMI323 VDDIO has no local bypass at the device (only shared bank caps at the Zynq) | U14 | Add a 100nF 0402 from U14.5 to GND adjacent to the IMU. |
| LOW | RTL8211F INT (open-drain) pulled to carrier-supplied VCCO_35 | R15, U2, U3 | Correct rail (receiver is bank-35 PL pin). Capture expected VCCO_35 level in carrier integration notes. |
| INFO | VCCO_33/34/35 entirely carrier-supplied (no on-SoM regulator); no external VREF (correct for LVCMOS/LVDS) | U2, J1/2/3 | Document carrier-defined ranges + on-module loads (BMI323 VDDIO on _33, ETH INT pull-up on _35). |
| INFO→ | Per-bank VCCO decoupling adequate | C69-C100 | **Corrected:** VCCO_35 has **7** VCCO pins (not 6); banks 33/34 have 6 each. Decoupling remains adequate. |

### eMMC (U7)

| Sev | Finding | Components | Action / corrected resolution |
|---|---|---|---|
| LOW | Ball C1 (symbol-labeled NC) tied to VDDI net | U7, C40 | **Corrected: harmless, no fix needed.** C1 is a **true JEDEC NC** (internally unbonded) per eMMC 5.1 Table 3-1 — VSS/VSSQ are fully enumerated and C1 is absent. No short-to-ground / brick risk. Optional cosmetic: leave NC balls C1/N1/N3/N6 unrouted. Do not relabel/move any ball. (Still confirm once the U7 MPN is locked — finding #2.) |
| LOW | VCC/VCCQ decoupling light (1× bulk + 2×470n per rail) | U7, C33-C41 | **Corrected: adequate** for an 8GB eMMC on a shared SoM plane (peak ~55-75mA program/erase per datasheet). 10µF is optional reliability nicety, not a droop fix. Verify cap placement near ball clusters in layout. |
| LOW | No series-term footprint on CLK/CMD/DAT | U7, U2 | Optional 0Ω/22-33Ω DNP on eMMC_CLK as HS200 SI tuning option. Not required for HS/4-bit. |
| INFO | VDDI cap C40 = 4.7µF | U7, C40 | **UNCERTAIN → do not change** based on a generic 2.2µF "typical." Retrieved JEDEC spec gives only a VDDi minimum, no max. Confirm exact placed-part max before any change; else keep 4.7µF. |
| INFO | Rails correct (VCC=+3V3, VCCQ=+1V8, Zynq bank-501 IO=+1V8); 4-bit bus (DAT4-7 NC — Zynq PS SDIO is 4-bit max); DS NC (no HS400); CMD/DAT/RST pull-ups 10k to +1V8 | U7, U2, R39-43/97 | All correct. |

### Sensors (BMI323 IMU)

| Sev | Finding | Components | Action / corrected resolution |
|---|---|---|---|
| MED | VDDIO (pin 5) decoupling cap C14 is **DNP** — no local bypass on the I/O supply | U14, C14, C21 | **Corrected to MEDIUM (not HIGH):** VDDIO is the shared well-bulked 3.3V bank-33 rail and BMI323 is low-speed, so this is a datasheet/best-practice shortfall, not a probable malfunction. Populate C14 (100nF X5R/X7R 0402 at U14.5 to GND) with a valid LCSC. Bosch DS section 8.2 / Fig 38 require one 100nF per supply pin. |
| MED | C21 (the only populated BMI323 decoupling cap) carries bogus LCSC `gia` | C21 | Replace with a valid 100nF 0402 X5R/X7R code. Add a BOM gate that hard-fails LCSC not matching `^C[0-9]+$`. |
| INFO | VDDIO net drawn with a "+1V0" power-symbol graphic but value-overridden to +VCCO_33 (cosmetic; net correct) | U14, #PWR0187 | Swap the mismatched library power symbols to avoid misreading in review. |
| INFO | NC pins 2/3/10/11 correctly floating; 4-wire SPI hookup matches datasheet; firmware must issue dummy SPI read (I2C→SPI switch) | U14, U2 | Correct. |

### Board-to-board connectors

| Sev | Finding | Components | Action |
|---|---|---|---|
| LOW | DF40 hold-down pads S1-S4 floating on all three connectors | J1/J2/J3 | Optional: add S1-S4 as GND pins in the symbol for mechanical/EMI benefit. Already solder-anchored. |
| INFO | VCCO_13/33/34/35 carrier-supplied (intentional); VIN on 14 pins (~2.8A derated, vs ~1.9A worst-case); +3V3 (4 pins)/+1V8 (3 pins)/+3V3_SC (1 pin) outputs; GbE/USB pairs same-row adjacent with GND flanking | J1/J2/J3 | Document per-rail current budgets and carrier dependencies in the SoM datasheet. |

### Global / cross-cut

| Sev | Finding | Components | Action |
|---|---|---|---|
| MED | Zynq VCCO banks 13/33/34/35 carrier-supplied with no on-SoM regulation — bank-voltage correctness is an unenforced inter-board dependency | U2, J2/J3, R15, U14 | Document a hard per-bank VCCO voltage table (which J2/J3 pins = which bank, required V). RGMII bank must be 1.8V; bank-33 must satisfy BMI323 VDDIO + FPGA IO. Cross-check carrier schematic. |
| MED | STM32 VREF+ no DC tie to VDDA (duplicate of SC finding above; firmware-VREFBUF dependent) | U9, C139 | See System Controller section. |
| MED | Zynq PUDC_B not strapped on SoM (duplicate of config finding above) | U2, J3 | See config/boot section. |
| INFO | Complete power tree verified: every FB/VSET computes to its rail; firmware-orchestrated sequencing matches Xilinx core order; EN default-OFF; all exposed/thermal pads grounded; all 3 oscillators correctly supported (VDD ferrite+cap, EN active, 22R series); decoupling generous per rail | U2/U4/U6/U8/U10/U13/U9/U1/U3/U5/U11/U14 | No change — recorded as positive verification of the core design. |

---

## Power tree summary

All rails established from `/tmp/som_nets.txt`, `/tmp/som_components.txt`, and the `power_architecture` design note; FB dividers and VSET straps independently computed and datasheet-checked.

| Rail | Source | Set by | Nominal | Feeds (key loads) |
|---|---|---|---|---|
| **VIN** | Carrier via J1 (14 pins) | — | 4.2–5 V | All on-SoM regulators (U4/U6/U8/U10/U13) |
| **+3V3_SC** | U13 TPS7A20 LDO (from VIN, EN=VIN, always-on first) | fixed LDO | 3.3 V | STM32G431 (U9) VDD×3/VBAT; PG pull-ups; exported J1.37 (low-current only) |
| **+1V0** | U8 TPSM82864AA0SRDJR (4A, fixed mode) | R25=28.7k VSET; FB+VOS tied to VOUT | 1.00 V | Zynq VCCINT (8), VCCBRAM (2), VCCPINT (6) |
| **+1V8** | U4 MPM3834C (3A) | R26=200k / R23=100k | 1.800 V | Zynq VCCAUX/VCCPAUX/VCCO_MIO501/VCCBATT, VCCPLL (via L4), VCCADC (via L9); USB PHY VDD18/VDDIO; eMMC VCCQ; ETH DVDD_RG; oscillator rails |
| **+1V35** | U10 MPM3822C (2A) | R37=200k / R38=160k | 1.350 V | DDR3L U1 VDD/VDDQ; Zynq VCCO_DDR_502 (9); VREF divider source |
| **+3V3** | U6 MPM3834C (3A) | R33=200k / R34=44.2k | 3.315 V (+0.45%) | Zynq VCCO_0/VCCO_MIO0_500; ETH DVDD33/AVDD33; USB VBAT/VDD33; eMMC VCC; QSPI flash; IMU VDD |
| **+0V675_REF** | R88/R89 divider from +1V35 | 10k / 10k | 0.675 V (VDDQ/2) | DDR3L VREFDQ/VREFCA; Zynq PS_DDR_VREF0/1 |
| **1V0_ETH** | RTL8211F internal switcher, REG_OUT → L1 | internal | 1.0 V | ETH PHY DVDD10/AVDD10 |
| **+VCCO_13 / _33 / _34 / _35** | **Carrier** via J2/J3 (no on-SoM source) | carrier | 1.14–3.465 V (HR) | Zynq PL bank I/O; +VCCO_33 also = BMI323 VDDIO; +VCCO_35 also = ETH INT pull-up |
| Filtered analog taps | ferrite from parent rail | — | — | VCCPLL/VCCADC (L4/L9 from +1V8), STM32_VDDA (L5 from +3V3_SC), oscillator supplies (L6/L7/L8 13/25/33MHz) |

**Sequencing:** STM32 (self-powered by U13, up first whenever VIN present) drives each switcher EN (100k pull-down default-OFF) and reads each PGOOD (100k pull-up to +3V3_SC). Documented ON order **1V0 → 1V8 → 1V35 → 3V3** satisfies the Xilinx VCCINT→VCCAUX→VCCO core order. Timings are firmware-defined and unspecified in hardware — a firmware-correctness dependency.

---

## Coverage & limitations

**Method.** Every subsystem was audited against the LAW-0 ground-truth artifacts (`/tmp/som_components.txt`, `/tmp/som_nets.txt`, and `schematic/*.kicad_sch`), with pin→net maps built per IC and FB/divider/strap math computed and compared to fetched datasheets.

| Subsystem | Checked | Key limitations / could-not-verify |
|---|---|---|
| **Power regulators** | All /Power/ parts; every regulator pin→net; all FB/VSET vs datasheet Vref; EN/PG; DC-bias cap ratings; U13 package question | Exact MPM3834/MPM3822 Vref to the mV (MPS PDF blocked — used 0.6V family, corroborated by all dividers); per-rail worst-case current (no load tally — drove the margin findings) |
| **Zynq power & decoupling** | All power-domain pin counts; per-rail/per-bank cap counts vs UG933/UG480; analog ferrite filters | UG933 PDF table would not extract cell-by-cell (medium confidence on counts); cap physical placement (layout); merged +1V0 plane current sizing (Power scope) |
| **DDR3L** | All 55 parts; full U1 ballout + Zynq B502; VREF/ZQ/VRP/VRN/CK/RESET/series term; rail | Board impedance target (40R vs 50R) that decides 100R-vs-80R — needs stackup/SI, not netlist; PCB placement |
| **Ethernet PHY** | All 41 U3 pins; all straps decoded; X2; every passive | L1 (C98336) exact IDC/Isat (LCSC 404 / not in public sources); X2 exact freq/supply (placeholder); ripple/efficiency (bench); firmware RGMII mode |
| **USB HS PHY** | All 25 U5 pins vs DS00002367A; RBIAS/REFCLK/CLKOUT/VBUS/CPEN/ID; decoupling | Ordered MPN/LCSC for U5/X1 (empty/placeholder); X1 footprint-vs-part; STM32 PC6 reset-drive (firmware); VBUS ESD (carrier) |
| **System controller** | All 49 U9 pins; power/VDDA/VREF+; BOOT0/NRST; no-crystal HSI/CRS; full supervisor role | Firmware-dependent items (VREFBUF enable, CRS, EN safe-default polarity, sequencing) not checkable from netlist; W25Q128 is QSPI-on-Zynq (config scope) |
| **PS MIO 500/501** | Every part; Vmode/Vref/clock-domain/boot-select/QSPI/POR/SRST/I2C | Cap placement (layout); STM32 BMODE/POR timing (firmware); .kicad_sch too large to read whole — used netlist as authoritative |
| **Config & boot straps** | PROG_B/INIT_B/DONE/PUDC_B/JTAG/POR/SRST; all boot+Vmode straps decoded | Exact UG585 boot-code table (AMD portal JS-gated — used standard {MIO5,4,3} mapping + design net names); firmware MIO4/5 drive timing; carrier PUDC/JTAG pulls |
| **PL bank 13** | VCCO_13 source/decoupling; all 50 IO pins; 24 L-pairs; VREF/DCI absence | Carrier-driven VCCO_13 voltage (off-module); bitstream UNUSEDPIN; split-pair design intent |
| **PL banks 33/34/35** | VCCO sources/decoupling; R15; BMI323 vs Bosch DS; all VREF-capable pins; 29 unconnected pins | Carrier-assigned VCCO voltages (off-module); cap placement |
| **eMMC** | Full 153-ball pinout; rails; decoupling; 4-bit SDIO mapping; JEDEC ballout cross-check | Exact ball-C1 function on the *actually-placed* part (ISSI PDF failed to parse + MPN/LCSC mismatch — though corrected analysis confirms C1 is JEDEC NC); cap placement; VDDi cap max for placed part |
| **Sensors (BMI323)** | Both parts; all 14 pins vs Bosch DS; rails vs abs-max; decoupling (C14 DNP) | VCCO_33 absolute value inferred 3.3V (set off-sheet/carrier); firmware I2C→SPI switch; cap placement |
| **Connectors** | All 300 pins; per-rail pin tally + direction; current budget vs DF40 0.3A/contact; DP-vs-DS footprint geometry; HS pair adjacency | Carrier-side mating connector gender (carrier out of scope — gates the DF40 finding); exact peak carrier currents (design-dependent) |
| **Global power/sequencing & completeness** | Full VIN→leaf tree; all FB/VSET; sequencing; exposed pads; 2-node opens; oscillator support; pulls/straps | Exact MPM Vref from rendered PDF; carrier VCCO voltages + sequencing; STM32 firmware; physical decoupling placement/loop inductance (PCB) |

**Cross-cutting limitations (apply to all subsystems):**
- **PCB layout was not in scope.** The netlist proves cap-on-net presence and rail correctness but **cannot confirm physical placement, loop inductance, or proximity to BGA balls** — every "place near the pin" item is a layout-review open, not a schematic defect.
- **Firmware behavior cannot be verified from hardware artifacts.** Several correct hardware topologies (VREFBUF enable, USB3318 RESETB drive, STM32 boot-strap/POR timing, rail-sequence timing, RGMII phy-mode) are **hard firmware dependencies** that must be confirmed in bring-up.
- **The carrier board is out of scope.** All carrier-supplied VCCO rails, USB-C/CC ESD and termination, Ethernet magnetics, and JTAG pulls are delegated off-module by design and must be guaranteed by the carrier and documented in the SoM integration guide.

---

# Part II — Competitive Second Pass (Pass 2, 90 agents)


> **Method:** 90-agent competitive run — 8 rival red-teams racing for NEW defects beyond Pass-1 + a completeness critic + 4 targeted gap-fill teams + dual-stance re-litigation of Pass-1 + a 3-lens adversarial panel (default-refute) on every candidate. 3.57 M tokens. New axis vs Pass-1: a **schematic↔PCB↔BOM cross-source diff** (membership-based net comparison).
>
> ## Orchestrator verification — the board-dead DDR byte-lane question is now CLOSED (and ELEVATED to CRITICAL)
> The synthesis below left the DDR x16 byte-lane mapping at HIGH / confidence 0.5, pending a UG585 check. **I closed it against the primary source — it is a second board-dead CRITICAL.**
> - **Netlist (fact):** U1's 16 data bits are wired to Zynq PS_DDR **DQ[31:16]/DQS2/DQS3/DM2/DM3** (upper byte lanes 2 & 3); **DQ[15:0]/DQS0/DQS1/DM0/DM1 are all no-connect**. Confirmed ball-level: U2.M1 = PS_DDR_DQ16 etc.
> - **UG585 (Zynq-7000 TRM) Table 10-3:** "16-bit Data bus: **[15:0]**." DDRIOB register map: DDRIOB_DATA0 = `DDR_DQ[15:0]`/`DM[1:0]` ("lower 16-bits"), DDRIOB_DIFF0 = `DQS_P/N[1:0]` ("dqs bits for lower 16-bits"). **Table 10-13 (ECC):** even in 16-bit-ECC mode the *data* is DQ[7:0]+DQ[15:8] (lanes 0/1); the upper lanes carry ECC, not data.
> - **Conclusion:** In every Zynq-7000 PS DDR configuration the 16-bit data bus is the **lower** lanes. The PS controller will drive DQ[15:0] (which go nowhere) while the DRAM sits on DQ[31:16] (which the controller never uses for data). There is no PS-side lane remap. **→ PS DDR cannot communicate with the DRAM: the SoM cannot use its memory (board-dead).** Confidence: high (silicon ball M1=DQ16 independently confirmed; residual = diff the full Zynq symbol DDR ballmap vs the official `xc7z020clg484` package file before respin).
> - **Bonus:** UG585 Table 10-3 *also* re-confirms Pass-1's VRP/VRN CRITICAL ("Connect DDR_VRP to a resistor to GND. Connect DDR_VRN to a resistor to VCC_DDR") — now backed by **three** Xilinx sources (UG471, UG933, UG585).
>
> **VIN-contact finding (below):** netlist-confirmed (VIN = exactly 14 J1 contacts, GND = 20). Real headroom concern; note the "5–6 A" is the regulator *rating-sum* (worst-case ceiling), not typical load — but with the standard ~50% mezzanine power-derate (0.15 A/contact) 14 contacts = ~2.1 A, which a loaded Zynq+DDR+GbE+USB module can exceed. Treat as HIGH for a high-power use-case, MEDIUM for a light one.

## Executive summary

Pass-2 is a competitive, adversarial second look at the same Zynq-7020 SoM that pass-1 audited (som/SOM_ELECTRICAL_AUDIT.md). It adds modest but real value: pass-1 was thorough on the connectivity/swap/footprint plane, so pass-2's net-new yield is dominated by **interface-current, mechanical/stack-height, and source-of-truth (schematic vs PCB vs BOM) defects** that a same-symbol/ERC/DRC pass cannot see.

NEW confirmed defects by severity (after orchestrator verification):
- **CRITICAL: 1** — single x16 DDR3L wired to the Zynq PS **upper** byte lanes DQ[31:16] while the controller's 16-bit data bus is the **lower** lanes DQ[15:0] (left no-connect). **Board-dead; verified vs UG585** (elevated from the agent panel's HIGH/0.5 — see verification banner above).
- **HIGH: 1** — VIN exported on only 14 DF40 contacts (4.2 A connector ceiling, ~2.1 A after derate) vs a loaded module's draw (3/3 panel).
- **MEDIUM: 1** — R80/R81 schematic value (5k1/12k) disagrees with PCB+BOM (100k/100k) (3/3).
- **LOW: 6** — un-annotated PCB footprint "G\*\*\*"; DF40 connector BOM stack-height self-conflict (1.5 mm vs 3.0 mm); split MRCC/SRCC differential pairs on non-adjacent contacts; X2 25 MHz oscillator three-way manufacturer-identity conflict; X3 33 MHz oscillator MPN voltage-code mismatch; U10 SW-pad net-membership divergence sch↔pcb.

**Single most important new item: VIN exported on only 14 DF40 contacts (HIGH, 3/3).** The Hirose DF40C-100DS-0.4V is 0.3 A/contact, so 14 VIN contacts = a hard 4.2 A entry budget, while the on-module regulator stack (U8 +1V0/4A, U4 +1V8/3A, U6 +3V3/3A, U10 +1V35/2A, U13 +3V3_SC) draws ~5.2 A at 5 V and ~6.2 A at the 4.2 V low-input corner. The released pinout leaves zero margin against the connector's own contact rating — a reliability/IR-droop bottleneck that is silent to ERC/DRC/netlist because pin count is never checked against current.

## NEW confirmed defects

### HIGH — VIN exported on only 14 DF40 contacts (4.2 A budget) below worst-case module input (~5–6 A) — panel 3/3
- **What/where:** VIN (the single 4.2–5 V module input on power_architecture.kicad_sch) enters on exactly 14 contacts of J1 (pins 1–14). Components J1, U8, U4, U6, U10, U13. Nets VIN, GND.
- **Why:** DF40C-100DS-0.4V is rated 0.3 A/contact (datasheet-confirmed) → 14 × 0.3 = 4.2 A entry budget. VIN feeds every on-module regulator: TPSM82864 U8 (+1V0 VCCINT, 4A), MPM3834 U4 (+1V8, 3A), MPM3834 U6 (+3V3, 3A), MPM3822 U10 (+1V35 DDR, 2A), TPS7A20 U13 (+3V3_SC, 0.3A). Summed worst-case output ~23 W; at ~88% efficiency that is ~5.2 A at 5 V and ~6.2 A at 4.2 V.
- **Impact:** At near-max simultaneous rail loading (or low VIN) individual VIN contacts exceed 0.3 A → contact heating, rising contact resistance over life, IR droop into the regulators (worst at 4.2 V), and intermittent-power risk. The 20 GND return contacts (6 A budget) are adequate; VIN is the bottleneck. Passes ERC/DRC/netlist (pin count not current-checked).
- **Fix:** Recompute the real VIN budget for the intended max simultaneous load; add VIN (and matching GND) contacts — typical mezzanine ≥50% derate (~0.15–0.2 A/contact effective) implies ~20–40 VIN contacts for ~6 A with margin — or document/enforce a max-VIN-current limit below 4.2 A × derate. Borderline-OK only if realistic use load is ~10–15 W.
- **Confidence 0.72. Panel 3/3.**

### CRITICAL (orchestrator-elevated from HIGH/2-3) — Single x16 DDR3L wired to Zynq PS upper byte lanes DQ[31:16] (lanes 2/3) rather than the active lower lanes DQ[15:0] — BOARD-DEAD, verified vs UG585
- **What/where:** The lone x16 DRAM U1 (MT41K256M16) connects entirely to the Zynq (U2, XC7Z020-CLG484) PS DDR controller's UPPER 16 data bits. U1 lower byte (DQ0-7/LDQS/LDM) → PS_DDR_DQ24-31 / DQS_P3-N3 (V2/W2) / DM3 (AA2); U1 upper byte (DQ8-15/UDQS/UDM) → PS_DDR_DQ16-23 / DQS_P2-N2 (N2/P2) / DM2 (P1). The Zynq lower lanes PS_DDR_DQ0-15, DQS0/DQS1 (C2/D2/H2), DM0/DM1 (B1/H3) are all left no-connect (unconnected-(U2I-PS_DDR_DQ0..DQ15_502), DQS_P0/N0/P1, DM0/DM1). Byte-lane internal grouping (DQ↔DQS↔DM) is self-consistent within lanes 2 and 3, and all 53 U1 ball assignments were verified pin-exact against the Micron 4Gb DDR3L Rev.Q x16 (TW) ballout — the DRAM side is correct.
- **Why:** On Zynq-7000 the PS DDR data width is hardened in the DDRC/DDRP PHY. In 16-bit (half-bus) mode the active 16 bits are the LOWER lanes PS_DDR_DQ[15:0] with DQS0/1 and DM0/1; byte lane 2 is reserved for ECC in 16-bit-ECC mode. Every standard reference (Zybo, MicroZed, TE0720) connects a single x16 DRAM to PS_DDR_DQ[15:0]/DQS0/1/DM0/1. No documented PS-side remap relocates the active 16-bit interface onto lanes 2/3 the way the PL MIG allows.
- **Impact:** If the PS DDR PHY truly drives only DQ[15:0] in 16-bit mode, the DRAM's data/strobe/mask sit on dead controller pins while the active lanes float → DDR training fails, SoM cannot boot from / use DDR (board-dead). Classic silent wrong-pin defect: all nets are 2-pin, electrically valid, and pass ERC/DRC/netlist and a same-symbol audit. Even if a PHY lane-swap/ECC register can accommodate it, this is a non-standard, undocumented configuration needing explicit firmware (DDRIOB/lane swap) and degrading portability of standard Zynq DDR init.
- **Fix:** Confirm against UG585 (DDR Controller / DDRP byte-lane table) and the Vivado PS DDR data-bus-width=16 pin mapping whether the active 16-bit interface is fixed to PS_DDR_DQ[15:0]/DQS0/1/DM0/1. If so, re-route U1 to the lower byte lanes (DQ[15:0], DQS_P0/N0 C2/D2, DQS_P1/N1, DM0/DM1 B1/H3); otherwise prove via DDRIOB lane-swap/ECC settings that the upper-lane mapping is intended and document it. Either way the chosen half-bus must match the controller's hardened lane assignment.
- **RESOLVED by orchestrator → CRITICAL, high confidence.** The "is there a PS-side remap?" question (the reason the agent panel held at 2/3, 0.5) was closed against UG585: 16-bit data is fixed to DQ[15:0]; the DDRIOB registers only set per-lane-group drive strength, they do not remap data; even ECC keeps data on lanes 0/1. Ball M1 = PS_DDR_DQ16 independently confirmed against the real silicon. There is no configuration that makes the as-wired upper-lane mapping work → board-dead. (Final pre-respin check: diff the full Zynq symbol DDR ballmap vs the official `xc7z020clg484` package file.)

### MEDIUM — R80/R81 schematic value (5k1/12k) ≠ PCB + BOM (100k/100k) — orchestrator cross-source item, panel 3/3
- **What/where:** sch_pcb_diff shows schematic R80=5k1, R81=12k, while both the PCB and the BOM carry 100k/100k. The built-board 1V8-sense divider is therefore a symmetric /2 (0.9 V at the ADC tap). Components R80, R81. Net: rail-sense divider.
- **Why:** There must be one source of truth. The other three sense dividers on the module are 100k/100k; PCB and BOM agree on 100k/100k for R80/R81 too, so the **schematic is the stale source**.
- **Impact:** The schematic misrepresents the built board. Pass-1's LOW finding about the 5k1/12k asymmetry is now moot (those values are not on the board). Firmware ADC scaling for the 1V8-sense channel must use the real /2 ratio.
- **Fix:** Update schematic R80/R81 to 100k to match PCB + BOM; confirm firmware uses /2 scale on the 1V8 sense channel.
- **Confidence 0.95. Panel 3/3.**

### LOW — DF40 connector BOM row self-inconsistent on stack height: Comment+LCSC = DF40C (1.5 mm) vs Manufacturer-Part = DF40HC(3.0) (3.0 mm) — panel 3/3
- **What/where:** BOM.csv line 13 (J1/J2/J3). Comment='DF40C-100DS-0.4V_51' and PCB footprint 'HRS_DF40C-100DS-0.4V_51_' are the DF40C family (1.5–2.0 mm). LCSC C597931 verified = HRS DF40C-100DS-0.4V(51), the 1.5 mm receptacle. But the 'Manufacturer Part' column says 'DF40HC(3.0)-100DS-0.4V(51)' — the DF40HC 3.0 mm-mated variant (DF40C series = 1.5–2.0 mm; DF40HC adds 2.5–4.0 mm; '(3.0)' = 3.0 mm). Since JLCPCB sources by C-code, the board ships the **1.5 mm DF40C**.
- **Why:** All three identity fields for one connector must agree on the same ordering part including stack height, because the SoM-to-carrier mating gap is fixed by the receptacle height. This is a NEW axis distinct from the known DF40 finding (which is plug-vs-socket / DP-vs-DS, not stack height).
- **Impact:** Built module = 1.5 mm; the mfg-part text claiming 3.0 mm is wrong/stale. Risk is procurement/second-source and mechanical: anyone re-ordering by the Manufacturer-Part string, or a carrier designer sizing standoffs/inter-board gap from the BOM, would design for 3.0 mm while the module ships 1.5 mm — boards would not mate (1.5 mm of travel missing) or mechanically conflict. No electrical/DRC/ERC impact.
- **Fix:** Decide the intended stack height; make all three fields consistent. If 1.5 mm (matches placed C597931), correct Manufacturer-Part to 'DF40C-100DS-0.4V(51)'. If 3.0 mm, change the LCSC code to the DF40HC(3.0) receptacle's C-code and update Comment/footprint. Document the chosen mated height in the SoM mechanical spec.
- **Confidence 0.82. Panel 3/3.**

### LOW — PCB footprint G\*\*\* has no schematic component — orchestrator cross-source item, panel 3/3
- **What/where:** sch_pcb_diff: 288 PCB footprints vs 287 schematic components; the extra is reference "G\*\*\*" (un-annotated). No nets.
- **Why:** Every placed part should be annotated and present in the schematic, or be an intentional non-electrical graphic.
- **Impact:** If electrical, an un-netted part; if a logo/graphic, benign.
- **Fix:** Open the PCB, identify G\*\*\*; confirm it is an intentional graphic/logo, else annotate and add it to the schematic.
- **Confidence 0.9. Panel 3/3.**

### LOW — X2 25 MHz Ethernet oscillator: three conflicting manufacturer identities — panel 3/3
- **What/where:** X2 (RTL8211F U3 25 MHz reference). KiCad symbol/Value = 'ASE-xxxMHz' (Abracon, literal 'xxx' placeholder); schematic 'Digikey' property = 'KC2016Z25.0000C1KX00' (Kyocera KC2016Z); fabricated BOM LCSC=C669080 verified = YXC OT201625MJBA4SL (25 MHz, 1.8–3.3 V, CMOS, 2016). Nets /Ethernet PHY/CLK_25MHz, ETH_CLK_25MHz.
- **Why/impact:** Electrically benign — all three are 25 MHz CMOS 2016 oscillators and YXC's 1.8–3.3 V range covers the 1V8 supply (net 25MHz_1V8), so the PHY clock works. Risk is procurement/traceability: a second-source or hand-built run could fetch the Kyocera/Abracon part, and the 'xxx' placeholder invites a wrong-frequency stuff. Same class as the known eMMC identity mismatch, on the clock domain.
- **Fix:** Lock X2 to one identity — set Value/MPN to the ordered YXC OT201625MJBA4SL (C669080), or replace C669080 with the genuine Kyocera if Kyocera is intended. Remove the 'ASE-xxxMHz' placeholder.
- **Confidence 0.85. Panel 3/3.**

### LOW — Multiple Zynq MRCC/SRCC differential pairs exported on non-adjacent DF40 contacts — panel 3/3
- **What/where:** Several true same-bank Zynq diff pairs land on widely separated contacts, breaking pair coupling at the connector. J3 IO_L12_MRCC_34 (P=pin46 / N=pin62, 16 pins apart); J3 IO_L20_34 (P=pin30 / N=pin76); J2 IO_L20_33 (P=pin59 / N=pin44); J3 IO_L1_33 (P=pin86 / N=pin89). Components J2, J3.
- **Why/impact:** Any Xilinx _P/_N pair (especially MRCC/SRCC clock-capable) should land on adjacent contacts with GND nearby if ever used differentially. Splitting P/N forecloses correct LVDS/diff-clock use and adds large intra-pair skew; harmless if used single-ended only. Carrier-design-dependent, hence LOW; silent to all automated checks.
- **Fix:** For any pair intended for differential/clock use, reassign P and N to adjacent contacts with GND flanking; otherwise annotate the pinout that these exports are single-ended-only.
- **Confidence 0.5. Panel 3/3.**

### LOW — X3 33 MHz Zynq PS oscillator: schematic MPN voltage-code (C1K) ≠ BOM MPN (C15) — panel 2/3
- **What/where:** X3 drives Zynq PS_CLK (U2.F7) at 33 MHz. Schematic 'Digikey' = 'KC2016Z33.0000C1KX00'; fabricated BOM = 'KC2016Z33.0000C15XXK'. Differ in the Kyocera supply/option code (C1K vs C15). X3 is Consign (no LCSC), so this is documentation-only. Nets /Zynq B500-B501/PS_CLK_33MHz, PS_CLK_33MHz_T.
- **Why/impact:** 33 MHz is valid for Zynq-7000 PS_CLK (30–60 MHz, 33.333 MHz canonical) and 3V3 CMOS matches bank-500 VCCO_MIO0 = +3V3, so design intent is correct. The two suffix codes may differ in voltage-option/stability; a buyer following the schematic could order a different supply-voltage option than the BOM intends.
- **Fix:** Reconcile X3's schematic MPN (C1KX00) with the BOM MPN (C15XXK) to one verified Kyocera order code that supports the 3.3 V rail.
- **Confidence 0.7. Panel 2/3.**

### LOW — U10 SW pads (5 and 15) split into two distinct unconnected nets in PCB (469/471) vs one shared net in netlist — panel 3/3
- **What/where:** Canonical netlist (/tmp/som_nets.txt): U10.5 and U10.15 are members of ONE net 'unconnected-(U10-SW-Pad15)' (2 members). Fabricated PCB (Zynq_SoM.kicad_pcb lines 16855–16969): pad 5 → net 469 'unconnected-(U10-SW-Pad15)', pad 15 → net 471 'unconnected-(U10-SW-Pad15)_0'. sch↔pcb diff flagged the member mismatch. SW is an internal switching node bonded to the integrated inductor (not externally routed), so both being unconnected is correct.
- **Why/impact:** No electrical effect; cosmetic/process — stale or divergent netlist-to-board annotation for U10's SW pins that could mask a real future change.
- **Fix:** Re-annotate U10 so SW pad nets are consistent between schematic and PCB; confirm both remain intentional no-connects. No copper change.
- **Confidence 0.6. Panel 3/3.**

## Re-litigation of Pass-1 CRITICAL/HIGH

### DDR VRP/VRN swap (pass-1 CRITICAL) — UPHELD (both prove-it-right and prove-it-wrong converged)
The board has VRP and VRN reference resistors swapped. Netlist ground truth: DDR_VRP = {U2.N7 [PS_DDR_VRP_502], R47.2}, R47.1 on +1V35 (VCCO_DDR) → **VRP pulled to VCCO**; DDR_VRN = {U2.M7 [PS_DDR_VRN_502], R46.1}, R46.2 on GND → **VRN pulled to GND**. Both R46/R47 are 100R 0201 (LCSC C270336), sheet /Zynq_B502_DDR/.

The required topology is the exact opposite, confirmed verbatim against **two primary sources**: UG471 (7 Series SelectIO, v1.10) — "The N reference pin (VRN) must be pulled up to VCCO by a reference resistor, and the P reference pin (VRP) must be pulled down to ground"; and UG933 §5 — "VRP must be pulled Low to GND and VRN needs to be pulled High to VCCO_DDR." Board has VRP→VCCO, VRN→GND: exactly reversed.

The strongest counter-argument tried (prove-it-wrong) was that both pins reach legal rails through legal 100R resistors so the connection is electrically valid — which is precisely why it passes ERC/DRC/netlist. That argument **failed** because validity of the rails is not the requirement; DCI impedance calibration on DDR3L bank 502 reads the wrong reference leg and mis-calibrates/fails. The only citation correction is that the normative source is UG471/UG933 (pass-1 named UG933, which is correct); the verdict is unchanged. Secondary note: the resistor value is 100R but UG933 Table 5-2 specifies 80Ω for DDR3/3L (100Ω is the DDR2 value) — a lesser concern beside the swap. **UPHELD, very high confidence.**

### eMMC LCSC mismatch (pass-1 HIGH) — UPHELD (both stances converged)
U7 BOM (BOM.csv line 39) pairs symbol value IS21ES08G / MPN IS21ES08GA-JCLI-TR (ISSI) with LCSC C499918. Primary-source verification: C499918 = **Samsung KLM8G1GETF-B041** (8GB eMMC 5.1, FBGA-153 11.5×13). The intended ISSI part has different codes (IS21ES08GA-JCLI-TR = C17412956). Since JLCPCB sources by C-code, the fab loads the Samsung die, not the printed ISSI MPN. Footprint BGA153N50P14X14_1150X1300X100 is JEDEC-common FBGA-153, so no DRC break — silent.

The strongest counter-argument (prove-it-wrong) was that both parts are footprint-compatible JEDEC eMMC 5.1, 8GB, FBGA-153 ~11.5×13 mm, so JLCPCB assembles a working board. That **bounds severity but does not void the finding**: the assembled part is a different vendor than the one engineered/qualified, with different init timing, CMD1 OCR behavior, RST_n handling and erase-group/firmware characteristics; provenance, lifecycle and second-source planning are all wrong. **UPHELD.**

## Rejected candidates (killed by the adversarial panel — do not re-raise)

These were investigated and **refuted**; re-raising them wastes cycles.

- **Zynq PL Bank 0 (VCCO_0, +3V3) "47uF bulk only, ZERO local HF ceramics" (claimed MEDIUM)** — confirm 1/3. Premise factually inverted. +3V3 is a single shared 50-node plane, not an isolated bank rail. Nearest +3V3 cap to the Bank-0 centroid is C76 (470nF HF ceramic) at ~11.5 mm — closer than the 47uF bulk C73 (22.9 mm). Measured against UG933's actual rule (within 12.7 mm of the package **edge**, not the bank balls), multiple 470n and 4u7 ceramics fall inside the window. "ZERO local HF ceramics" is false; the finding measured the wrong reference.
- **3.3V config/MIO0 aggregate HF cap count below UG933 (claimed LOW)** — confirm 0/3. Manufactures a shortfall by arbitrarily assigning shared-plane caps to "other loads." Counting the whole +3V3 plane MEETS/EXCEEDS the cited UG933 budget (47uF 2-vs-1, 4.7uF 5-vs-3). Plus the cited per-bank table numbers were not independently verifiable.
- **VCCAUX/VCCPAUX (+1V8) local 0.47uF count below UG933 (claimed LOW)** — confirm 0/3. Counted by schematic-sheet membership, not physical placement. PCB geometry shows ≥5 470n ceramics within ~6 mm of U2 on +1V8 (C50/C62/C67/C134 directly under/adjacent the BGA), exceeding the recommendation.
- **eMMC U7 wired 4-bit only (DAT4-7/DS unconnected) caps below 8-bit/HS400 (claimed LOW)** — confirm 0/3. Wiring observation is true, but the host is the Zynq-7000 PS SDIO controller, which is architecturally 4-bit only with no DAT4-7 and no HS400/data-strobe. 4-bit no-DS is the correct, maximal topology — not a shortfall.
- **USB3318 HS pair USB_D-/D+ split across J1.30/32 with CC2 interposed (claimed MEDIUM)** — confirm 1/3. Mis-modeled the DF40 as alternating-row pin numbering. All even pins are on one row: actual sequence is GND(28)–D-(30)–D+(32)–GND(34) at 0.4 mm pitch — a textbook GND-flanked adjacent differential pair. CC2 (pin 31) is on the opposite row ~3.08 mm away, not in the pair gap.
- **J2 pins 37-44 "GND-starved" block with interdigitated SRCC pairs (claimed MEDIUM)** — confirm 0/3. The connector has a uniform [2 GND][8 SIG] cadence across all 100 pins; 37-44 is one of ten identical tiles with GND adjacent at 35/36 and 45/46 — not anomalous. Residual SRCC interdigitation is a soft, carrier-use-dependent SI nit at most.
- **Zynq VCCBATT (U2.G9) tied to +1V8, no battery (claimed LOW)** — confirm 1/3. Tying VCCBATT to VCCAUX/1.8V is the Xilinx-documented configuration when BBRAM-key/PS-RTC retention is not required; the total absence of any coin cell is positive evidence backup was never intended. Design-intent note, not a defect.
- **STM32↔Zynq I2C pull-ups R86/R87 on sequenced +3V3 not always-on +3V3_SC (claimed LOW)** — confirm 0/3. Pull-ups belong on the same rail as the slave bank VCCO (+3V3 = VCCO_MIO0); the finding's proposed "fix" (move to +3V3_SC) would CREATE a back-power path through the Zynq ESD clamp. Topology is correct; any residual is firmware-mitigable and the SDA-series-R asymmetry is already a pass-1 item.
- **BMI323 (U14) CSB float at power-up (claimed LOW)** — confirm 1/3, killed. CSB has an internal ~75–140k pull-up to VDDIO (datasheet Table 39), so it is not floating; and protocol selection is a master-generated **rising** edge (default I2C), not the "first falling edge" the finding claimed. Failure scenario does not materialize.
- **STM32 (3.3V) drives Zynq PS_SRST_B on 1.8V bank 501 — push-pull overstress (claimed MEDIUM)** — confirm 1/3. The schematic carries an explicit DESIGN NOTE (system_controller.kicad_sch:3402) to configure eMMC_RST/ZYNQ_PS_SRST/ETH_PHY_RST/USB_PHY_RST as open-drain; 3.3V open-drain + 1.8V pull-up is the correct level-shifter-free interface. Hardware is correct; residual is firmware-conformance, out of scope.
- **+3V3_SC 300mA TPS7A20 rail also exported to carrier J1.37 (claimed LOW)** — confirm 0/3. Speculative margin concern with no specified carrier load and no abs-max violated; STM32 draw (~30–50mA) leaves >200mA. Exporting a housekeeping rail to the carrier is standard practice.
- **DDR3L VREF (+0V675_REF) 10k/10k divider vs reference 1k/1k (claimed LOW)** — confirm 0/3. Ratio (0.5→0.675V), ±1% tolerance and decoupling (188nF, ~2× typical) all meet JEDEC. JEDEC constrains VREF DC accuracy and AC noise, not divider Thévenin impedance; AC stiffness is set by the bypass cap, not the divider. 10k/10k with strong local decoupling is widely shipped. Design-style preference.
- **U10 (MPM3822C) footprint omits pads 6,7,8,9 — missing VOUT lands (claimed MEDIUM)** — confirm 1/3, killed. The authoritative MPS pin table (sibling MPM3833C, identical GRH/QFN-18 package) shows 5-7,15 = merged SW land and 8-10 = merged OUT land; the footprint correctly collapses these into single large custom power pads. No unsoldered land, no current-concentration. (One verifier reached the opposite reading, but the majority refuted it on the authoritative merged-land pinout.)
- **High-impedance 200k FB top resistors (R26/R33/R37) with no feedforward Cff (claimed LOW)** — confirm 0/3. 200k is the **datasheet-recommended** top FB resistor for the MPM3834C; Cff is an optional transient/phase-margin optimization, never required. Rails set-point-correct. Optimization suggestion, not a defect.

**INFO clearances (hypotheses disproven — useful negatives, not defects):**
- All QFN/DFN/WSON exposed/thermal pads (U3/U4/U5/U6/U8/U10/U11) are correctly grounded; all "unconnected-(…SW…)" nets are intentional integrated-inductor internal nodes — the ungrounded-EP/floating-SW hypothesis is disproven.
- All 5 regulator set-points (U4 +1.800V, U6 +3.315V (+0.45%), U10 +1.350V, U8 +1.00V via RSET=28.7k, U13 fixed 3.3V) verified correct vs datasheet Vref/VSET; max deviation +0.45%, well under the 3% flag — the "rail >3% off" hypothesis does not hold.
- U8 TPSM82864 blank-numbered EP/VOUT/PGND pins ("pcb-missing U8.") are correctly netted to +1V0/GND — the diff entry is a blank-pin-number cosmetic artifact, not a connectivity defect.

## Verdict delta vs Pass-1

Pass-1 stands. Both re-litigated pass-1 headline findings are **UPHELD**: the DDR VRP/VRN swap (CRITICAL, now backed by verbatim UG471 **and** UG933 primary sources plus netlist) and the eMMC ISSI-vs-Samsung LCSC identity mismatch (HIGH, primary-source verified).

Pass-2 adds **9 NEW confirmed defects** (2 HIGH, 1 MEDIUM, 6 LOW), shifting the risk picture in two directions pass-1 under-covered:
- **Connector current/mechanical integrity:** the VIN 14-contact under-budget (HIGH) and the DF40 stack-height BOM conflict (LOW) are the kind of pin-count-vs-current and mechanical-mating defects that no electrical-rule check sees.
- **Source-of-truth divergence (sch vs PCB vs BOM):** R80/R81 (MEDIUM, and it retires a pass-1 LOW as moot), the un-annotated G\*\*\* footprint, the X2/X3 oscillator identity conflicts, and the U10 SW net split.

One genuinely new **board-dead** item surfaced — the **DDR x16 upper-vs-lower byte-lane mapping**. The agent panel left it HIGH/0.5 pending a UG585 check; the orchestrator **closed that check against UG585 and elevated it to CRITICAL** (see verification banner). The SoM now has **two independent board-dead defects** (this DDR byte-lane mapping + the Pass-1 VRP/VRN swap), either of which alone prevents DDR from working. This is the headline of Pass-2.

Equally important is what pass-2 did **not** find: a large adversarial sweep of decoupling-count, VREF-impedance, FB-divider, exposed-pad-grounding, regulator-set-point, USB/SRST level-domain, and CSB-float hypotheses was **killed** — 16 candidates refuted, several at 0/3. That null result is itself a strong signal that pass-1's coverage of the connectivity, decoupling, and set-point planes was sound; the remaining real exposure is concentrated in interface-current budgeting, mechanical stack-height, and documentation source-of-truth — not in the electrical core.

---

# Part III — Pin-Level Competitive Pass (Pass 3, 20 agents)

> **Orchestrator verification (this part's HIGH was re-checked against the real datasheet):** the RTL8211F finding is CONFIRMED. Netlist: X2 VDD on `25MHz_1V8` ← `L6` ← **+1V8**; `X2.3 → R20(22R) → U3.37 [XTAL_OUT/EXT_CLK]`; `U3.36 [XTAL_IN] = GND`; `U3.11/U3.40 [AVDD33] = 3V3A_ETH` ← `L3` ← **+3V3**. Datasheet (RTL8211F-CG, pdftotext) **Table 55 "Oscillator/External Clock Requirements": Vpeak-to-peak min 3.15 / typ 3.3 / max 3.45 V** — no lower-voltage CMOS-clock allowance exists. 1.8 Vpp < 3.15 V min ⇒ out of spec. Verified HIGH.


**Target:** Xilinx Zynq-7020 (XC7Z020-CLG484) System-on-Module — real KiCad 10 design at `som/`.
**Date:** 2026-06-20. **Method:** exhaustive pin-by-pin trace of every bus and power ball against UG585 / component datasheets, on the fabricated `Zynq_SoM.kicad_pcb` per-pad net assignments (the authoritative connectivity), cross-checked against the hierarchical `.kicad_sch`.
**Scope:** This addendum reports ONLY what the pin-level pass adds beyond Passes 1–2 (`SOM_ELECTRICAL_AUDIT.md`: 2 board-dead CRITICALs — DDR VRP/VRN swap, DDR byte-lane miswire — plus 2 HIGH).

---

## Executive summary

**Pin-level verification did NOT find a third board-dead defect.** Every connectivity-class fault that would render the module dead (open critical net, rail-to-rail short, swapped differential pair, mis-mapped bus lane) was already captured by Passes 1–2. Exhaustively walking the DDR address/command bus, the Zynq PS/PL power balls, the MIO/boot strap pins, the system clocks, RGMII, ULPI, and QSPI against UG585 and the device datasheets found the connectivity otherwise **sound** — this is a strong positive signal on the netlist's integrity.

**New confirmed by severity:** HIGH 1, INFO 1 (CRITICAL 0, MEDIUM 0, LOW 0).

**Single most important new item:** the **RTL8211F Ethernet PHY reference-clock amplitude mismatch (HIGH)** — the 25 MHz oscillator X2 is powered from **+1V8** (via ferrite L6), so it presents a ~1.8 Vpp clock to the PHY's `XTAL_OUT/EXT_CLK` input (U3.37), whose oscillator/crystal section is on the **3.3 V** analog rail (AVDD33). This is an *amplitude* under-spec, not a wiring error — the pin mapping is correct — so it passes ERC/DRC/netlist but risks an intermittent or non-functional PHY. It is a parametric/reliability defect, distinct from the board-dead class.

---

## NEW confirmed defects

### 1. HIGH — RTL8211F 25 MHz `EXT_CLK` driven at 1.8 Vpp, datasheet requires 3.15–3.45 Vpp

**Panel vote: 3/3. Confidence: 0.78.**

**What / where.**
- Components: **X2** (25 MHz oscillator), **U3** (RTL8211F GbE PHY), **R20** (22 R series), **L6** (120 R ferrite).
- Verified per-pad on `Zynq_SoM.kicad_pcb`:
  - `L6.2 = +1V8`, `L6.1 = /Ethernet PHY/25MHz_1V8` — the oscillator rail is the **+1V8** rail.
  - `X2.1 = X2.4 = /Ethernet PHY/25MHz_1V8` (VDD), `X2.2 = GND`, `X2.3 = /Ethernet PHY/CLK_25MHz` (output).
  - `R20.1 = /Ethernet PHY/CLK_25MHz`, `R20.2 = /Ethernet PHY/ETH_CLK_25MHz`.
  - `U3.37 = /Ethernet PHY/ETH_CLK_25MHz` → this is pin **XTAL_OUT/EXT_CLK**.
  - `U3.36 = GND` → **XTAL_IN**, correctly grounded for external-oscillator use.
  - `U3.11 = U3.40 = /Ethernet PHY/3V3A_ETH` → **AVDD33**, and `L3` (120 R ferrite) bridges `+3V3 → 3V3A_ETH`, i.e. AVDD33 is a filtered **3.3 V** analog rail.

So the pin *mapping* is correct (external osc into pin 37, XTAL_IN grounded), but the signal *level* is wrong: the EXT_CLK input belongs to the RTL8211F analog crystal-oscillator section, which is powered from AVDD33 = 3.3 V.

**Why (primary source).**
- RTL8211F datasheet pin table: *"37  XTAL_OUT/EXT_CLK  O  25MHz Crystal Output. If a 25MHz oscillator is used, connect XTAL_OUT/EXT_CLK to the oscillator's output."*
- RTL8211F datasheet, Oscillator/External Clock Requirements: external clock at XTAL_OUT/EXT_CLK **Vpeak-to-peak Min 3.15 / Typ 3.3 / Max 3.45 V**.
- AVDD33 is specified *"Analog Power. 3.3V."* The EXT_CLK input amplifier is referenced to this 3.3 V section, not to VDDIO.

The neighbouring **USB** PHY oscillator X1 is *legitimately* on 1.8 V (`X1.1/X1.4 = /USB HS PHY/13MHz_1V8`): the USB3318 REFCLK is a digital input spec'd 0 V…VDDIO(=+1V8). The same 1.8 V oscillator-rail pattern was evidently copied to the Ethernet PHY, where EXT_CLK is **not** a VDDIO-scaled digital input but a fixed 3.3 V crystal-section input.

**Impact.** 1.8 Vpp is below the 3.15 Vpp minimum for the EXT_CLK amplifier. The PHY's crystal-oscillator/PLL input may fail to lock or register the reference reliably across PVT → intermittent or non-functional Ethernet (no/unstable internal 125 MHz, link won't come up). Even if a golden unit works, it is out of spec — a yield/reliability hazard. **Not board-dead** (it is parametric, and may work on the bench), which is why it is HIGH and not CRITICAL.

**Fix.** Supply X2 from **+3V3** (filter +3V3 through L6, as L3 already does for AVDD33) so the 25 MHz output swings ~3.3 Vpp, matching the EXT_CLK requirement and the AVDD33 = 3.3 V section. Keep R20 (22 R series) and U3.36 (XTAL_IN → GND) as-is — those are correct. Confirm the chosen oscillator MPN is rated for 3.3 V operation. **Do NOT** change the USB X1 rail (1.8 V is correct there).

---

### 2. INFO — Boot-mode bits BOOT_MODE[2] (MIO4) and BOOT_MODE[0] (MIO5) are STM32-GPIO-driven, not hard-strapped (verified correct; firmware-fragility note)

**Panel vote: 2/3. Confidence: 0.55.** *Not a defect — a soft (firmware) dependency flagged for documentation.*

**What / where (verified strap map, per-pad on the PCB).**
The seven boot-mode straps MIO[8:2] trace as:

| MIO | BOOT_MODE bit | Net | Strap | Level |
|---|---|---|---|---|
| MIO2 | BOOT_MODE[3] | `QSPI_D0/BM3` | **R76 → GND** | 0 |
| MIO3 | BOOT_MODE[1] | `QSPI_D1/BM1` | **R77 → GND** | 0 |
| MIO4 | BOOT_MODE[2] | `QSPI_D2/BM2` | **R1 → ZYNQ_BMODE_2** (STM32 U9.15 / PA7) | SC-driven |
| MIO5 | BOOT_MODE[0] | `QSPI_D3/BM0` | **R6 → ZYNQ_BMODE_0** (STM32 U9.19 / PB2) | SC-driven |
| MIO6 | BOOT_MODE[4] | `QSPI_CLK_T/BM4` | **R95** (to QSPI_CLK domain) | — |
| MIO7 | VMODE[0] | `ZYNQ_PS_MIO7/VM0` | **R75 → GND** | 0 → LVCMOS33 |
| MIO8 | VMODE[1] | `ZYNQ_PS_MIO8/VM1` | **R74 → +3V3** | 1 → LVCMOS18 |

The two STM32-controlled bits, BOOT_MODE[2] and BOOT_MODE[0], are exactly the ones that must be 1 and 0 for QSPI boot. The STM32 also generates PS_POR_B (U9.25 / PB12 → `ZYNQ_PS_POR`).

> Note: the pass-3 candidate data mislabeled two of these resistors (it placed BM3/BM1 on the wrong references and listed R13 as a boot strap — R13 is actually `QSPI_CLK → GND`, and BM4 routes via R95). The table above is the corrected, netlist-verified map. The conclusion is unchanged.

**Why (UG585).** §6.2.5: the boot-mode strapping pins MIO[8:2] are sampled by hardware soon after PS_POR_B deasserts and must each carry a ~20 kΩ pull-up/pull-down. Table 6-4: Quad-SPI boot = BOOT_MODE[2:0] = 1,0,0. VMODE: VM0=0 → LVCMOS33 (matches VCCO_MIO0=+3V3), VM1=1 → LVCMOS18 (matches VCCO_MIO1=+1V8) — both verified correct.

**Impact.** Functionally fine: the same STM32 owns both the two SC-driven straps and PS_POR_B, so it can establish the levels before deasserting POR. The risk is firmware-only — if SC firmware deasserts PS_POR_B before driving PA7/PB2, or if those GPIOs float at SC reset (the 10 k merely ties the line to the Zynq pin, which has no rail of its own), the sampled boot mode is indeterminate. This is a soft dependency, **not** a hardwiring error. No PCB change required for function.

**Recommendation.** Confirm SC firmware drives PA7 = 1 (BOOT_MODE[2]) and PB2 = 0 (BOOT_MODE[0]) and holds them stable across the PS_POR_B deassertion edge. Optionally add a weak default pull on the STM32-side nets for determinism if the GPIO is high-Z.

---

## Buses verified clean (pin-checked, passed)

A positive coverage record — each was walked pin-by-pin against UG585 / the relevant datasheet on the per-pad PCB netlist and found correct:

- **DDR3L address/command bus** — A[14:0], BA[2:0], RAS/CAS/WE, CKE, CS, ODT, RESET; CK/CK# pair. (DQ byte-lane miswire and VRP/VRN are the two Pass-1/2 CRITICALs — *not re-counted here*; the addr/cmd net mapping itself is correct.)
- **Zynq PS/PL power balls** — VCCINT, VCCAUX, VCCBRAM, VCCPINT, VCCPAUX, VCCPLL, VCCO_DDR, VCCO_MIO0(+3V3)/MIO1(+1V8), VCCADC/VREFP/VREFN — all on their correct rails.
- **MIO / boot straps** — MIO[8:2] strap map verified (see INFO item); QSPI MIO[1:6], JTAG cascade consistent with the sampled mode.
- **System clocks** — Zynq PS_CLK source; USB X1 (13 MHz on +1V8, correct for USB3318); Ethernet X2 (25 MHz — *flagged HIGH for amplitude only*; the routing X2→R20→U3.37 with U3.36→GND is correct).
- **RGMII** — ETH_PHY_TXD[3:0]/TXCTL/TXC and RXD[3:0]/RXCTL/RXC plus MDC/MDIO between U3 and the PS map 1:1, no swaps.
- **ULPI (USB HS)** — USB3318 data/stp/dir/nxt/clk to the PS ULPI bank consistent.
- **QSPI** — QSPI_CLK / D[3:0] / CS to the boot flash consistent with BOOT_MODE = Quad-SPI; note the strap dual-function on D[3:0]/CLK (BM[0..4]) is by-design (Zynq samples then re-purposes), not a contention.

---

## Rejected candidates

None. The pass-3 panel did not advance any candidate that was subsequently killed (`killed: []`). The two pass-3 items above both survived to the report; one correction was applied to the INFO item's resistor labels (above), but the finding itself stands as INFO, not a defect.

---

### Pass-3 verdict

No third board-dead defect. One new HIGH (Ethernet reference-clock amplitude under-spec, parametric/reliability — fixable by moving X2's rail from +1V8 to +3V3) and one INFO firmware-fragility note. The exhaustive pin-level sweep otherwise confirms the connectivity is sound, reinforcing that the two known board-dead faults remain confined to the DDR subsystem.
