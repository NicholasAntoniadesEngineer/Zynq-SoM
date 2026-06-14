"""camera — Raspberry Pi 15-pin FFC port, 2-lane MIPI CSI-2 (XAPP894 RX).

Authored EXACTLY per carrier/research/camera_csi.md (lane map section 1,
netlist sketch section 4): SFW15R-1STE1LF 1.0 mm 15P bottom-contact FFC
(LCSC C3168538 — LIVE-verified 2026-06-11: stock 4,000, Extended; contact
orientation verified against Amphenol drawing 10172241 and the generated
footprint — finding documented in the dossier, section 3).

- CSI pairs (FFC pin n = RPi pin n): D0 on 2/3, D1 on 5/6, CLK on 8/9 ->
  ports CAM_* typed diff_pair 100R, destined for J3 bank 35 (LVDS_25,
  +VCCO_35 = 2.5 V local LDO — dossier risk 1): CLK -> IO_L13_MRCC_P/N_35
  (J3.9/11), D0 -> IO_L10_P/N_35 (J3.5/7), D1 -> IO_L15_DQS_P/N_35
  (J3.17/15). 100R differential terminations live FPGA-side per XAPP894 —
  LAYOUT NOTE: place R1-R3 at the SoM-connector end of the traces, not at
  the FFC. D-PHY pairs are NOT polarity-swappable.

CAM-1 (electrical audit) — STATIC 100R vs MIPI D-PHY Low-Power signalling.
R1-R3 sit PERMANENTLY across each pair. In D-PHY HS bursts that is exactly
right (the LVDS RX needs the 100R differential termination, and on this
Zynq-7020 HR bank there is NO usable run-time DIFF_TERM that follows the
burst — the XAPP894 "7-series + external passives" topology relies on a
fixed external 100R, the IBUFDS has no HS/LP-switched on-die termination to
gate). But in LP mode the two wires of a pair are driven INDEPENDENTLY
(each a single-ended ~1.2 V CMOS-class level, not a differential swing): a
static cross-pair 100R then bleeds current between the two LP-driven lines,
pulling the LP-high line down and degrading LP voltage levels and
Start-of-Transmission detection.
  DECISION: keep the 100R POPULATED (HS genuinely needs it — DNP'ing it,
  option (b), would break HS reception; the HR-bank RX does not gate
  DIFF_TERM, so the 100R is NOT redundant) and restore LP observability the
  XAPP894 way (option (a)): the XAPP894 LP RX does not remove the 100R, it
  TAPS each line through a resistor divider into an extra single-ended
  LVCMOS25 bank input so the fabric can read LP levels DESPITE the HS
  termination. That network is carried here as a DOCUMENTED DNP STUFFING
  OPTION (same convention as the ESD array below and hdmi_rx's TMDS ESD,
  carrier/subsystems/hdmi_rx.py): it is NOT emitted as a populated/ghost
  part because (i) the LP single-ended taps land on the FPGA side, off this
  FFC sheet (the divider belongs at the SoM-connector end with R1-R3), and
  (ii) the reserved bank-35 LP pins (L18/L16) are not authored on this sheet
  yet — they are spent at the CSI-2 RX IP integration, where stuffed-vs-DNP
  is finally decided.
  LP-divider stuffing recipe (XAPP894 D-PHY LP RX, place at the SoM-
  connector end alongside R1-R3, NOT at the FFC): per LP-observed line, a
  series + shunt divider from the line to a bank-35 single-ended LVCMOS25
  input — divide the 1.2 V LP-high down to a clean bank-safe level (e.g.
  series 100k / shunt 100k, 0402; XAPP894 uses ~100k-class taps so the HS
  path is not loaded). Lines to tap: CAM_D0_P/N, CAM_D1_P/N, CAM_CLK_P
  (LP-CLK_N optional) onto a reserved bank-35 pair. IO_L18_P/N_35 (J3.27/25) is
  free; IO_L16_P/N_35 (J3.31/29) is NO LONGER available — the board_services
  watchdog now owns it (WATCHDOG_KICK / WATCHDOG_RST_N), so a full LP populate
  must repick a second genuinely-free bank-35 pair (verify vs som_conn_gen
  FUNCTION_MAP first) (dossier risk 4, camera_csi.md sec "D-PHY on a
  7-series HR bank"). For VIDEO-ONLY continuous capture with fixed timing the
  dividers may stay DNP and LP events are inferred (fragile across sensor
  resets) — rev A reserves the footprints so a populate is a BOM-line change
  with zero netlist/layout churn here.
- Control on J3 bank 33 (3.3 V): CAM_SCL/CAM_SDA (FFC 13/14, dedicated
  Zynq-fabric I2C bus — NOT STM32_I2C2) with 4k7 pull-ups (C23162, Basic,
  LIVE-verified 10M stock) to the GATED +3V3_CAM rail — a powered-down
  camera must not be back-fed through its bus pull-ups. CAM_EN (FFC 11,
  module shutdown) + CAM_LED (FFC 12, v1-only indicator) plain ports.
- Power: FFC 15 -> +3V3_CAM (bring-up-gated module rail, SY6280 cell #4 on
  bringup_modules, 523 mA limit vs 300 mA budget) with 100n + 10u at the
  connector (C1591 + C15850, the wave-1 pair). FFC 1/4/7/10 -> GND;
  mounting-plate tabs 16/17 -> GND.
- ESD: omitted on rev A per dossier section 4 (short internal cable;
  TPD4E05U06 across the FFC-facing lines remains a stuffing option).
- LP-RX (dossier risk 4): see the CAM-1 note above — the XAPP894 LP
  resistor-divider taps are a DOCUMENTED DNP stuffing option on a reserved
  bank-35 pair (L18_35, J3.27/25 — L16_35 J3.31/29 is now the watchdog; repick
  the 2nd pair vs FUNCTION_MAP before stuffing), NOT spent on this FFC sheet;
  they restore LP observability alongside the populated HS 100R. Video-only
  capture works without them.

Terminations 100R = 0603WAF1000T5E (C22775, Basic, LIVE-verified 8.7M).
"""

from __future__ import annotations

from schgen.core.model import Circuit

R0603 = "Resistor_SMD:R_0603_1608Metric"
C0603 = "Capacitor_SMD:C_0603_1608Metric"
C0805 = "Capacitor_SMD:C_0805_2012Metric"

J3_35 = "som_j3_connector (PL bank 35, LVDS_25, +VCCO_35=2.5V)"
J3_33 = "som_j3_connector (PL bank 33, +VCCO_33=3.3V)"
BRINGUP = "bringup (gated +3V3_CAM rail, module cell 4)"

# (pair, P-side FFC pin, N-side FFC pin, termination ref)
PAIRS = (
    ("CAM_D0", "3", "2", "R1"),
    ("CAM_D1", "6", "5", "R2"),
    ("CAM_CLK", "9", "8", "R3"),
)


def circuit() -> Circuit:
    c = Circuit("camera", "RPi camera port: 2-lane MIPI CSI-2 (15P FFC)")
    c.use_part("SFW15R-1STE1LF", ref="J1")   # bare-number FFC pins stay numeric

    # ---- CSI lanes: FFC -> 100R FPGA-side terminations -> J3 bank 35 -------
    # R1-R3 stay POPULATED: HS D-PHY needs the 100R diff term and the HR-bank
    # RX cannot gate DIFF_TERM (CAM-1, docstring). LP observability is the
    # XAPP894 LP-divider DNP stuffing option on the reserved L18/L16 pairs.
    for name, p_pin, n_pin, term in PAIRS:
        c.part(term, "Device:R", "100R", R0603, LCSC="C22775")
        c.port(f"{name}_P", f"J1.{p_pin}", f"{term}.1")
        c.port(f"{name}_N", f"J1.{n_pin}", f"{term}.2")
        c.port_type(f"{name}_P", kind="diff_pair", pair_with=f"{name}_N",
                    impedance=100, expect=J3_35)   # reciprocal N typed too

    # ---- control: dedicated camera I2C + enable/LED on bank 33 (3.3 V) -----
    c.part("R4", "Device:R", "4k7", R0603, LCSC="C23162")
    c.part("R5", "Device:R", "4k7", R0603, LCSC="C23162")
    c.port("CAM_SCL", "J1.13", "R4.2", kind="i2c", role="scl",
           bus="CAM_I2C", speed_hz=400_000, expect=J3_33)
    c.port("CAM_SDA", "J1.14", "R5.2", kind="i2c", role="sda",
           bus="CAM_I2C", speed_hz=400_000, expect=J3_33)
    c.net("+3V3_CAM", "R4.1", "R5.1")
    c.port("CAM_EN", "J1.11", expect=J3_33)
    c.port("CAM_LED", "J1.12", expect=J3_33)

    # ---- power: gated +3V3_CAM at the connector + grounds ------------------
    c.part("C1", "Device:C", "100n", C0603, LCSC="C1591")
    c.part("C2", "Device:C", "10u", C0805, LCSC="C15850")
    c.net("+3V3_CAM", "J1.15", "C1.1", "C2.1")
    c.net("GND", "J1.1", "J1.4", "J1.7", "J1.10", "C1.2", "C2.2",
          "J1.16", "J1.17")

    # round-4 coverage gate: the dedicated camera I2C bus + the module
    # enable line (every EN is probeable, bring-up philosophy)
    c.testpoint("CAM_SCL")
    c.testpoint("CAM_SDA")
    c.testpoint("CAM_EN")

    # power-tree budget (round 4): RPi V2 module ~250 mA typ, dossier budget
    # 300 mA (camera_csi.md section 0) incl. the I2C pull-ups
    c.draws("+3V3_CAM", 0.300, "RPi camera module budget "
                               "(camera_csi.md: V2 typ ~250 mA)")
    return c
