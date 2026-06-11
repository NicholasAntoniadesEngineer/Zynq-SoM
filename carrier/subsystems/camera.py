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
- LP-RX (dossier risk 4): XAPP894 single-ended LP taps are NOT spent here —
  the reserved bank-35 pairs (L18 + L16, J3.27/25/31/29) stay free until
  the CSI RX implementation decides stuffed-vs-DNP; video-only capture
  works without them.

Terminations 100R = 0603WAF1000T5E (C22775, Basic, LIVE-verified 8.7M).
"""

from __future__ import annotations

from schgen.model import Circuit

FFC_LIB = "SFW15R-1STE1LF:SFW15R-1STE1LF"
FFC_FP = "SFW15R-1STE1LF:SFW15R-1STE1LF"
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
    c.part("J1", FFC_LIB, "SFW15R-1STE1LF", FFC_FP, LCSC="C3168538")

    # ---- CSI lanes: FFC -> 100R FPGA-side terminations -> J3 bank 35 -------
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
    return c
