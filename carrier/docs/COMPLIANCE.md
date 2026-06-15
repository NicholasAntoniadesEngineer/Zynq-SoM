# Zynq Carrier — Per-Interface Compliance Checklists

Each interface below lists its standard requirements, **how the board meets
them** (citing the net / part / report of record), and a verdict:

- **PASS** — met in the schematic/netlist as generated, provable from the
  cited artifact.
- **REVIEW** — a *layout-time* concern (impedance, length-match, ESD
  placement) or a documented deferral. The schematic carries the intent; the
  obligation is on the layout engineer / bring-up. Length-match and impedance
  REVIEW items point to `carrier/manufacturing/SI_CONSTRAINTS.md`, which is
  generated from the typed ports and also emitted into the KiCad `.kicad_dru`.
- **N-A** — not applicable to this design (with the reason).

Sources cited are the authored netlists (`carrier/subsystems/*.py`), the part
dossiers (`parts/<MPN>/`), the SI constraints, and the gate reports
(`carrier/reports/*.txt`). This file is tracked in `carrier/manifest.json`
(artifact hash) and guarded by `schgen/tests/test_doc_consistency.py` so it
cannot silently drift from the sheets.

**Tally (verdicts per interface):**

| Interface | PASS | REVIEW | N-A |
|---|---|---|---|
| HDMI 1.4/2.0 (TX source) | 8 | 2 | 1 |
| HDMI 1.4/2.0 (RX sink) | 9 | 2 | 0 |
| Gigabit Ethernet 1000BASE-T | 7 | 2 | 1 |
| USB 2.0 (HS/FS data) | 6 | 2 | 0 |
| MIPI CSI-2 D-PHY | 5 | 3 | 1 |
| USB-PD (FUSB302B / Type-C) | 7 | 1 | 1 |
| FMC LPC (VITA 57.1) | 7 | 2 | 2 |

---

## 1. HDMI 1.4/2.0 — TX (source) — sheet `hdmi_tx`

Reference circuit: TI **TPD12S016** (SLLSE96F) Fig. 15, "HDMI source using one
GPIO".

| # | Requirement | How the board meets it | Verdict |
|---|---|---|---|
| TX-1 | TMDS Z_diff = 100 Ω ±15%, DC-coupled, per-pair length match | TMDS pairs typed `tmds_pair` 100 Ω; flow-through the TPD clamp pads DC-coupled (`hdmi_tx.py` TMDS_LANES). Geometry/skew in SI_CONSTRAINTS.md (DP100_TMDS, ±118 mil intra-pair) | **REVIEW** (layout: impedance + skew) |
| TX-2 | TMDS source ESD on cable lines | All 8 TMDS lines flow through the TPD12S016's integrated clamps | PASS |
| TX-3 | DDC (SCL/SDA) with pull-ups | DDC passes through the TPD level shifters; **DDC pull-ups integrated** in the TPD (DS 7.3.9/7.3.15) — design-rule waiver recorded (`design_rules.txt`) | PASS |
| TX-4 | CEC line + ESD | `ZYNQ_HDMI_TX_CEC` through the TPD level shifter to receptacle pin 13 | PASS |
| TX-5 | HPD (hot-plug detect) | `ZYNQ_HDMI_TX_HPD` through the TPD; CT_HPD strapped (10k to V_CCA) | PASS |
| TX-6 | +5 V to cable (source powers DDC/CEC), current-limited | `HDMI_TX_CON_5V0` from the TPD's integrated **55 mA-limited** switch (DS 7.3.10), receptacle pin 18; 100n + 1u at the connector (HDMI 1.4 §4.2.7) | PASS |
| TX-7 | Level-shifter enable | LS_OE strapped high (10k to V_CCA), DS Fig 15 | PASS |
| TX-8 | Shell/shield to chassis, signal grounds to GND | TMDS shields → GND; four shell legs → `CHASSIS_GND` (star-bonded) | PASS |
| TX-9 | Decoupling on both rails | V_CCA (`+3V3_HDMI_TX`) 100n + 10u bulk; V_CC5V (`+5V_HDMI_TX`) 100n (DS Fig 15) | PASS |
| TX-10 | HEC/Utility (pin 14) | Author no-connect — HEAC unused on this device (HDMI 1.4 N.C. on non-HEAC) | N-A |
| TX-11 | Inter-pair (clock-to-data) skew budget | SI_CONSTRAINTS.md group LM_HDMI_TX_TMDS_SOURCE (±118 mil); match data pairs to clock | **REVIEW** (layout) |

---

## 2. HDMI 1.4/2.0 — RX (sink) — sheets `hdmi_rx`, `hdmi_rx_term`

| # | Requirement | How the board meets it | Verdict |
|---|---|---|---|
| RX-1 | TMDS sink **far-end termination** (2× 49.9 Ω/pair to AVCC=3.3 V) | **8× 49.9 Ω to AVCC=+3V3** on its own netlisted sheet `hdmi_rx_term` (AVCC = VCCO_33 = +3V3, bypassed 100n+1u). Required because a 7-series **HR bank does not self-terminate TMDS_33** (SI-HDMIRX-TERM). Termination current budgeted ~64 mA on +3V3 (`power_tree.txt`) | PASS (netlisted) |
| RX-2 | Termination placed at the RECEIVER end | `hdmi_rx_term` resistors bound to TMDS_RX_* ports that merge with the bank-33 pins at assembly — placed next to the FPGA bank, not the connector | **REVIEW** (layout placement) |
| RX-3 | TMDS Z_diff = 100 Ω ±15%, DC-coupled | Pairs typed `tmds_pair` 100 Ω, DC-coupled connector → bank (`hdmi_rx.py`); SI_CONSTRAINTS.md DP100_TMDS group LM_HDMI_RX_TMDS_SINK | **REVIEW** (layout: impedance + skew) |
| RX-4 | TMDS RX ESD, low capacitance (≤0.5 pF/line) | Two **TPD4E02B04** arrays (0.2 pF/line typ, 8 kV IEC 61000-4-2), shunt taps at the jack; lines stay DC-coupled (`hdmi_rx:U2/U3`) | PASS |
| RX-5 | DDC slow-line ESD (SCL/SDA) | **TPD4E05U06** 5.5 V array on DDC (`hdmi_rx:U4` D1±) — ST AN5121 intent | PASS |
| RX-6 | CEC/HPD ESD (5 V-domain) | Same TPD4E05U06 (5.5 V VRWM clears the 5 V idle) on CEC + HPD (`hdmi_rx:U4` D2±) | PASS |
| RX-7 | EDID EEPROM readable with the carrier OFF | **M24C02** (`0x50`) powered from the **cable's +5 V** (pin 18), not the gated rail — a source always reads EDID (HDMI 1.4 §8.5) | PASS |
| RX-8 | EDID write-protect | **WC# hardwired to the EEPROM's own 5 V VCC** node (COMP-1) — permanent, domain- and level-correct write-protect, holds carrier on or off | PASS |
| RX-9 | HPD assert + 5 V presence detect | 1k from cable +5 V to HPD (pin 19); 10k/15k divider → `HDMI_RX_5V_DET` (3.15 V max, LVCMOS33-safe) | PASS |
| RX-10 | CEC pull-up | 27k to the gated `+3V3_HDMI_RX` (`hdmi_rx:R2`) | PASS |
| RX-11 | Shell/shield bonding | TMDS shields + DDC ground → GND; shell legs → `CHASSIS_GND` | PASS |

---

## 3. Gigabit Ethernet 1000BASE-T — sheets `ethernet`, `rj45_connector`

PHY = on-SoM RTL8211F; carrier carries the discrete magnetics + jack.

| # | Requirement | How the board meets it | Verdict |
|---|---|---|---|
| ETH-1 | Four MDI pairs, 100 Ω ±15% diff (IEEE 802.3 Cl.40) | All 4 PHY-side (`ETH_PHY_MDIx_±`) and 4 line-side (`ETH_LINE_MDI_x_±`) pairs typed `diff_pair` 100 Ω (`ethernet.py`, `rj45_connector.py`); SI_CONSTRAINTS.md groups LM_GIGABIT_ETHERNET_MDI_PHY_SIDE + _LINE_SIDE | PASS (netlist); **REVIEW** (layout impedance) |
| ETH-2 | **Magnetics pinout correct** (the board-killer that was fixed) | **HX5008NL** 24-pad faithful Pulse PS-0118.001-D dossier: chip pairs TDn± on pins 2/3, 5/6, 8/9, 11/12; media pairs MXn± on 23/22, 20/19, 17/16, 14/13 (`ethernet.py` CHANNELS). The prior invented numbering (pins 25/26 = non-existent pads, shorted MX4±) is GONE. **Guarded by the footprint-pad-coverage gate** (`footprint_pads.txt`: every symbol pin has a pad) | PASS |
| ETH-3 | 1:1 isolation transformer | HX5008NL is a 1:1 gigabit magnetics module; in-phase + couples to + across the winding (`ethernet.py` docstring) | PASS |
| ETH-4 | Bob-Smith / HF common-mode termination (IEEE 802.3 §40.7.1) | Each media centre tap: **75 Ω ‖ 1 nF/2 kV → shared BS_COMMON** trunk; one 1 nF/2 kV cap (`ethernet:C5`) BS_COMMON → CHASSIS_GND = the isolation barrier (genuine 2 kV X7R parts, C9196) | PASS |
| ETH-5 | Chip-side centre taps | NC on the carrier — RTL8211F is a voltage-mode driver, self-biases TX common mode; no CT path crosses J1 (`ethernet.py`) | PASS (by PHY design) |
| ETH-6 | MDI / TIA-568 pair-to-contact order | BI_DA=1,2 / BI_DB=3,6 / BI_DC=4,5 / BI_DD=7,8 → `ETH_LINE_MDI_0..3` (`rj45_connector.py` MDI_CONTACTS) | PASS |
| ETH-7 | High-voltage isolation rating | All five caps genuine **1 nF / 2 kV X7R 1206** (IEC 60950/62368 hi-pot), live-verified C9196 (`ethernet.py`) | PASS |
| ETH-8 | Inter-pair / intra-pair length match | SI_CONSTRAINTS.md ±50 mil intra-pair, ≤50 mm inter-pair (RTL8211F / TI SNLA387) | **REVIEW** (layout) |
| ETH-9 | Link/activity LED driving | The jack LEDs are wired as a steady **port-present** indicator off +3V3 (the RTL8211F LED pins live on the SoM and are not exported); documented honestly as power-on, NOT PHY-driven blink (`rj45_connector.py`) | N-A (PHY LED pins not on the contract) |
| ETH-10 | Chassis bonding + mounting holes | Jack shell + 4× M3 corner holes → `CHASSIS_GND`, star-bonded elsewhere (`rj45_connector.py`) | PASS |

---

## 4. USB 2.0 (HS/FS data pairs) — sheets `usbc_otg`, `usb_jtag_connector`, `usb_uart_connector`, `pd_input`

Four USB-C ports carry a USB2 data pair: OTG host (`usbc_otg`), JTAG debug
(CH347T), UART console (CP2102N), and the PD/device port (`pd_input` → SoM
STM32 FS).

| # | Requirement | How the board meets it | Verdict |
|---|---|---|---|
| USB-1 | D+/D- = 90 Ω ±15% differential | All four pairs typed `usb_hs_pair` (90 Ω): `USB_D+/-`, `DBG_USB_DP/DM`, `USB_UART_DP/DM`, `STM32_USB_D_P/N`; SI_CONSTRAINTS.md DP90_USB groups | PASS (netlist); **REVIEW** (layout impedance) |
| USB-2 | Data-pair ESD at the connector | **USBLC6-2SC6** array on every data pair (`usbc_otg:U2`, `pd_input:U2`); CH347/CP2102N ports protected at their own receptacles | PASS |
| USB-3 | ESD clamp rail referenced to a valid ≤5.25 V rail (NOT the 20 V VBUS) | `pd_input` USBLC6 pin 5 → **+3V3_SC** (not the 20 V inlet) — tying it to +VBUS_IN would hold the internal TVS in avalanche (audit CRIT, `pd_input.py`) | PASS |
| USB-4 | VBUS current-limit on a host/OTG port | OTG VBUS via **TPS2051C** current-limited switch from gated `+5V_USB`, EN default-OFF (100k pulldown) until `VBUS_OUT_EN` (`usbc_otg.py`) | PASS |
| USB-5 | VBUS bulk + input bypass | OTG: 22u VBUS bulk + 100n input (TPS2051 DS); PD inlet bulk behind the eFuse (`pd_input.py`) | PASS |
| USB-6 | Fault flag reported, abs-max-safe pull | OTG `USBOTG_FLT_N` pull re-railed to **+3V3_SC** (TCA9535 IO abs-max VCC+0.5 = 3.8 V; a 5 V pull would violate it — G4 fix, `usbc_otg.py`) | PASS |
| USB-7 | Intra-pair length match (≤150 mil) | SI_CONSTRAINTS.md per-port (USB-IF FS/HS) | **REVIEW** (layout) |
| USB-8 | Shell/shield to chassis | All Type-C shells → `CHASSIS_GND` (`usbc_otg.py`, `pd_input.py`) | PASS |

---

## 5. MIPI CSI-2 D-PHY (camera) — sheet `camera`

2-lane D-PHY (CLK + D0 + D1), Xilinx XAPP894 7-series RX topology.

| # | Requirement | How the board meets it | Verdict |
|---|---|---|---|
| CSI-1 | Lanes 100 Ω ±20% differential | CLK/D0/D1 typed `diff_pair` 100 Ω → bank 35 LVDS_25 (`camera.py`); SI_CONSTRAINTS.md LM_MIPI_CSI_2_D_PHY_CAMERA | PASS (netlist); **REVIEW** (layout impedance) |
| CSI-2 | HS-RX 100 Ω diff termination at the receiver | Static **100 Ω** per pair (`R1–R3`), required because the HR bank cannot gate DIFF_TERM in the XAPP894 topology (CAM-1); placed at the SoM-connector end | PASS |
| CSI-3 | Clock-to-data lane skew (timing reference) | SI_CONSTRAINTS.md intra-pair ±20 mil; inter-lane match to clock | **REVIEW** (layout) |
| CSI-4 | LP-mode observability with the static HS term | Documented **DNP stuffing option** (XAPP894 LP resistor-divider taps on a reserved bank-35 pair) — video-only capture works without it (CAM-1, `camera.py`) | **REVIEW** (deferred / DNP) |
| CSI-5 | Camera control I²C, isolated from back-feed | Dedicated Zynq-fabric `CAM_SCL/SDA` (not the SC bus) with 4k7 pull-ups to the **gated** `+3V3_CAM` so a powered-down camera is not back-fed (`camera.py`) | PASS |
| CSI-6 | Power + decoupling at the connector | `+3V3_CAM` (gated, 523 mA limit vs 300 mA budget) with 100n + 10u at the FFC (`camera.py`, `power_tree.txt`) | PASS |
| CSI-7 | Module enable / shutdown | `CAM_EN` (FFC 11) ported to bank 33 | PASS |
| CSI-8 | FFC-line ESD | Omitted on rev A (short internal cable); TPD4E05U06 remains a stuffing option (`camera.py` §4) | N-A (rev A) |
| CSI-9 | Polarity / no pair swap | D-PHY pairs not polarity-swappable — noted as a layout rule (`camera.py`) | **REVIEW** (layout) |

---

## 6. USB-PD (FUSB302B / Type-C) — sheets `pd_input`, `usb_pd`

| # | Requirement | How the board meets it | Verdict |
|---|---|---|---|
| PD-1 | PD PHY owns CC1/CC2 (Rd/Rp, vRd, BMC) | **FUSB302B** (`usb_pd:U1`, `0x22`) CC pins to receptacle CC lines; provides termination + BMC PHY (`usb_pd.py`) | PASS |
| PD-2 | SC must NOT drive its own CC termination | Documented firmware contract PD-CC-1: SC keeps native UCPD disabled / CC GPIOs Hi-Z (double-termination corrupts the contract). SoM CC pins are bare STM32 PB6/PB4 (CC-1 audit) | **REVIEW** (firmware obligation) |
| PD-3 | CC analog filter caps | 200p per CC line (`usb_pd:C4/C5`) | PASS |
| PD-4 | PD PHY alive before any DIP-gated rail | FUSB302B VDD + INT pull on **+3V3_SC** (always-on); PD negotiates on default 5 V VBUS (bring-up risk R1, `usb_pd.py`) | PASS |
| PD-5 | VBUS sense at the receptacle, ahead of the eFuse | VBUS-sense pin on raw `+VBUS_IN` (attach detection needs the connector node, not the eFuse-ramped rail). AMX-1: 21.0 V at the legal contract max, well under the 28 V abs-max | PASS |
| PD-6 | Inlet OVP / over-current / soft-start (eFuse) | **TPS26631** OVP cutoff 23.06 V typ, ILIM 3.53 A, dVdT 1.02 V/ms, auto-retry (`pd_input.py`, see DESIGN_SPEC §3.1) | PASS |
| PD-7 | Inlet TVS | **SMBJ22A** 600 W, 22 V standoff on +VBUS_IN ahead of the eFuse | PASS |
| PD-8 | VCONN sourcing | Unused by design — both VCONN pins author-NC (`usb_pd.py`) | N-A |

---

## 7. FMC LPC (VITA 57.1 LPC subset) — sheet `fmc`

**Reduced** LPC site: LA00–LA11 + CLK0/CLK1_M2C populated.

| # | Requirement | How the board meets it | Verdict |
|---|---|---|---|
| FMC-1 | LA / CLK pairs 100 Ω differential | 12 LA pairs + CLK0/CLK1_M2C typed `diff_pair` 100 Ω (`fmc.py`); SI_CONSTRAINTS.md LM_FMC_LPC_VITA_57_1 (±5 mil intra-pair) | PASS (netlist); **REVIEW** (layout impedance + tight LA-to-CLK match) |
| FMC-2 | Correct carrier-side connector | Samtec **ASP-134603-01** (SEAF socket, the carrier-side part — NOT the mezzanine ASP-134604-01; dossier §2) | PASS |
| FMC-3 | GND census | 61 GND positions asserted from the machine-parsed VITA map (build-time assert in `fmc.py`) | PASS |
| FMC-4 | VADJ supply | **2.5 V** from a local **TLV75725 (DYD)** LDO, EP netted to GND; 0.40 A continuous thermal envelope (`fmc.py`, `thermal.txt` Tj ~80 °C) | PASS |
| FMC-5 | I²C (IPMI ID-EEPROM) + GA address straps | `STM32_I2C2` SCL/SDA to the FMC; GA0/GA1 grounded → `0x50` (`fmc.py`) | PASS |
| FMC-6 | PRSNT_M2C_L + PG_C2M | PRSNT 10k pull to +3V3; PG_C2M asserts when VADJ is live (10k to +2V5_VADJ) (`fmc.py`) | PASS |
| FMC-7 | JTAG chain | TDI→TDO bypass; TCK/TRST_L held low, TMS held high (dossier §5) | PASS |
| FMC-8 | 12 V supply (12P0V) | NOT provided — the carrier has no 12 V rail (author-NC, dossier deviation) | N-A |
| FMC-9 | GTP DP0 / GBTCLK0 lanes + LA12–LA33 | Author-NC (reduced site) — silkscreen MUST be labelled "FMC LPC (REDUCED) — LA00–LA11, no 12 V" so an integrator does not seat a full-LPC mezzanine | N-A (reduced); **REVIEW** (silkscreen at layout) |
| FMC-10 | 3P3V / 3P3VAUX mezzanine supply | From +3V3 (1.0 A allocation, `power_tree.txt`), 10u + 100n at the connector | PASS |

---

## Cross-cutting layout obligations (all interfaces)

These are the REVIEW items that converge on the layout engineer; the
schematic carries the *intent*, the PCB carries the *realization*:

1. **Impedance** — route every typed pair to its class geometry
   (`Zynq_Carrier_pcb.kicad_dru` / SI_CONSTRAINTS.md): 90 Ω USB, 100 Ω
   TMDS/MDI/MIPI/FMC, on the JLC04161H-7628 stackup.
2. **Length-match** — 10 groups, tolerances in SI_CONSTRAINTS.md (tightest:
   FMC ±5 mil, TMDS/MIPI next, USB/MDI loosest).
3. **Receiver-end termination placement** — HDMI-RX 49.9 Ω and camera 100 Ω
   terminations belong at the SoM-connector / FPGA-bank end, not the
   connector.
4. **Thermal** — verify the two waived TPS54302 bucks
   (`power:U2`, `power_som:U4`) at bring-up by thermal sim/bench; the
   bare-package Tj exceeds the guard band and relies on a poured 4-layer
   layout (DESIGN_SPEC §4, `thermal.txt`).
5. **Silkscreen** — the FMC site must be labelled "REDUCED — LA00–LA11, no
   12 V".
