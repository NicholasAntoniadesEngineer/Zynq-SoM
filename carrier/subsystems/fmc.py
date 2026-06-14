"""fmc — VITA 57.1 FMC LPC mezzanine site, REDUCED carrier subset.

Authored per carrier/research/fmc.md (remaining-pin audit + live-verified
parts, 2026-06-11). Populated: LA00-LA11 (12 pairs, all the VADJ-matched
bank-35 pairs the audit leaves free) + CLK0/CLK1_M2C on true MRCC/SRCC
pairs. LA12-LA33, DP0, GBTCLK0, VREF_A_M2C: author NC (documented
deviations in the dossier, incl. LA01_CC not clock-capable and 12P0V NOT
PROVIDED — the carrier has no 12 V rail).

Connector: Samtec ASP-134603-01 (LCSC C2836665 — LIVE 2026-06-11: stock
282, Extended, $17.75; SEAF-based SOCKET, rows C/D/G/H = LPC; the
ZedBoard's carrier-side part. The mezzanine-side ASP-134604-01 is the
WRONG side — see dossier section 2). Pin->signal map loaded from the
machine-parsed carrier/research/fmc_lpc_pinmap.json (no hand-typed
pinout); this module asserts its GND census before binding.

VADJ: +2V5_VADJ from TLV75725PDYDR (C35209004) fed by +3V3 — fixed 2.5 V
per PLAN round 2, the SAME voltage bank 35 runs at (+VCCO_35, camera
dossier) so LA levels are consistent by construction.

PWR-3 THERMAL SWAP (SBVS322C, 2026-06-13): the LDO was the TLV75725PDBVR
(DBV, SOT-23-5, RthJA ~231 C/W) — at the 0.4 A / ~0.8 V-drop budget that
is Pd ~0.32 W, Tj ~125 C at Ta=50 C, no margin (and 0.4 A only by derating
the 1 A part HARD on the bare DBV). Swapped to the TLV75725PDYDR (DYD,
SOT-23-5 thermal-pad / EP variant, RthJA ~92.5 C/W with the EP soldered to
a ground pour): the SAME 0.32 W now lifts Tj only ~30 C -> Tj ~80 C at
Ta=50 C, a comfortable margin below the 125 C limit. The EP pad (footprint
pad 6) is netted to GND in the schematic (DEF-E) — a real, gate-checkable
ground connection, not merely a layout pour bond.

Part already in the repo (parts/TLV75725PDYDR, LCSC C35209004, LIVE
2026-06-13: Extended, stock 133, min-qty 1). Authored via use_part with the
in-repo 6-pin TLV75725PDYDR symbol (DEF-E): the orderable identity
(MPN/LCSC/datasheet), the DYD thermal-pad FOOTPRINT and the DRAWING all come
from the parts/ folder, so pin 6 = EP exists in the model and is netted to
GND (vs the former AP2204K-1.5 5-pin override, whose symbol omitted the EP).
Pin map 1=IN 2=GND 3=EN 4=NC 5=OUT 6=EP. Honest budget unchanged at 0.4 A
continuous, now with real thermal headroom.

Ports use FUNCTIONAL pair-suffixed names (hdmi pattern; the linker infers
pair polarity from suffixes, which raw IO_*_P_35 names defeat); the
FMC->IO_*_35 binding contract is the dossier section-1 table.

SILKSCREEN INTENT (reduced-LPC note) — although the connector is a full
LPC-mechanical SEAF socket, this is a REDUCED LPC site (only LA00-LA11 +
CLK0/CLK1_M2C populated; LA12-LA33/DP0/GBTCLK0/VREF/12P0V are author NCs
above). The PCB silkscreen at this site MUST be labelled to that effect
(e.g. "FMC LPC (REDUCED) — LA00-LA11, no 12V") so an integrator does not
seat a mezzanine that assumes a full LA bus, a 12 V supply, or the GTP
GBTCLK/DP lanes. This is a fab-art/silkscreen requirement, not a netlist
change; tracked here so it is not lost at layout.
"""

from __future__ import annotations

import json
from pathlib import Path

from schgen.model import Circuit

PINMAP = Path(__file__).resolve().parents[1] / "research" / "fmc_lpc_pinmap.json"

R0603 = "Resistor_SMD:R_0603_1608Metric"
C0603 = "Capacitor_SMD:C_0603_1608Metric"
C0805 = "Capacitor_SMD:C_0805_2012Metric"

J35_MAP = "som_j3/j1 bank-35 pin map (dossier fmc.md section 1, P3 linker)"
J33_MAP = "som_j2/j3 bank-33 spare (P3 linker)"
J1_I2C = "som_j1_connector (STM32 GPIO function map)"

# FMC signal -> carrier port stem (pair polarity suffix appended).
# The SoM IO_*_35 binding for each lives in carrier/research/fmc.md sec. 1.
POPULATED_PAIRS = {
    "CLK0_M2C": "FMC_CLK0_M2C",   # -> IO_L12_MRCC_*_35 (J3.14/16)
    "CLK1_M2C": "FMC_CLK1_M2C",   # -> IO_L11_SRCC_*_35 (J3.8/10)
    "LA00_CC": "FMC_LA00_CC",     # -> IO_L14_SRCC_*_35 (J3.22/20)
    "LA01_CC": "FMC_LA01_CC",     # -> IO_L21_DQS_*_35 (J3.24/26, not CC)
    "LA02": "FMC_LA02",           # -> IO_L17_*_35 (J3.37/35)
    "LA03": "FMC_LA03",           # -> IO_L20_*_35 (J3.34/32)
    "LA04": "FMC_LA04",           # -> IO_L22_*_35 (J3.42/44)
    "LA05": "FMC_LA05",           # -> IO_L23_*_35 (J3.47/45)
    "LA06": "FMC_LA06",           # -> IO_L24_*_35 (J3.51/49)
    "LA07": "FMC_LA07",           # -> IO_L19_P_35/IO_L19_N_VREF_35 (J3.50/52)
    "LA08": "FMC_LA08",           # -> IO_L1_*_35 (J1.74/92)
    "LA09": "FMC_LA09",           # -> IO_L4_*_35 (J1.80/84)
    "LA10": "FMC_LA10",           # -> IO_L5_*_35 (J1.90/88)
    "LA11": "FMC_LA11",           # -> IO_L6_P_35/IO_L6_VREF_N_35 (J1.78/76)
}


def _signal_pins() -> dict[str, list[str]]:
    """signal name -> connector pin numbers, from the committed VITA map."""
    by_sig: dict[str, list[str]] = {}
    for pin, sig in json.loads(PINMAP.read_text()).items():
        by_sig.setdefault(sig, []).append(pin.lower())
    return by_sig


def circuit() -> Circuit:
    c = Circuit("fmc", "FMC LPC site (reduced: LA00-11 + CLK0/1, VADJ 2.5V)")
    sig = _signal_pins()
    assert len(sig["GND"]) == 61, "VITA LPC map drifted: GND census != 61"

    c.use_part("ASP-134603-01", ref="J1")   # VITA grid pins (c1..h40) numeric

    # ---- grounds (61 positions, from the machine-parsed map) ---------------
    c.net("GND", *[f"J1.{p}" for p in sorted(sig["GND"])])

    # ---- populated LA/CLK pairs -> typed functional ports -------------------
    # VITA spells clock-capable pairs LAnn_P_CC / LAnn_N_CC (CC after the
    # polarity); plain pairs and the M2C clocks end in _P/_N.
    for fmc_sig, stem in POPULATED_PAIRS.items():
        if fmc_sig.endswith("_CC"):
            base = fmc_sig[: -len("_CC")]
            (p_pin,), (n_pin,) = sig[f"{base}_P_CC"], sig[f"{base}_N_CC"]
        else:
            (p_pin,), (n_pin,) = sig[f"{fmc_sig}_P"], sig[f"{fmc_sig}_N"]
        c.port(f"{stem}_P", f"J1.{p_pin}")
        c.port(f"{stem}_N", f"J1.{n_pin}")
        c.port_type(f"{stem}_P", kind="diff_pair", pair_with=f"{stem}_N",
                    impedance=100, expect=J35_MAP)

    # ---- unpopulated user signals: author NC (dossier deviations) ----------
    nc_signals = (["DP0_C2M_P", "DP0_C2M_N", "DP0_M2C_P", "DP0_M2C_N",
                   "GBTCLK0_M2C_P", "GBTCLK0_M2C_N", "VREF_A_M2C", "12P0V"]
                  + [f"LA{i:02d}_{h}" for i in range(2, 34) for h in "PN"
                     if f"LA{i:02d}" not in POPULATED_PAIRS]
                  + [f"LA{i:02d}_{h}_CC" for i in (17, 18) for h in "PN"])
    for s in nc_signals:
        for pin in sig.get(s, []):
            c.nc(f"J1.{pin}")

    # ---- service: I2C to the SC bus, GA straps, presence, PG, JTAG ---------
    c.port("STM32_I2C2_SCL", f"J1.{sig['SCL'][0]}",
           kind="i2c", role="scl", bus="STM32_I2C2", speed_hz=400_000,
           expect=J1_I2C)
    c.port("STM32_I2C2_SDA", f"J1.{sig['SDA'][0]}",
           kind="i2c", role="sda", bus="STM32_I2C2", speed_hz=400_000,
           expect=J1_I2C)
    c.net("GND", f"J1.{sig['GA0'][0]}", f"J1.{sig['GA1'][0]}")  # addr 0x50

    c.part("R1", "Device:R", "10k", R0603, LCSC="C25804")       # PRSNT pull
    c.port("FMC_PRSNT_N", f"J1.{sig['PRSNT_M2C_L'][0]}", "R1.2",
           expect=J33_MAP)
    c.net("+3V3", "R1.1")

    c.part("R2", "Device:R", "10k", R0603, LCSC="C25804")       # PG_C2M
    c.net("FMC_PG_C2M", f"J1.{sig['PG_C2M'][0]}", "R2.2")
    c.net("+2V5_VADJ", "R2.1")                # asserts when VADJ is live

    # JTAG: bypass TDI->TDO; TCK/TRST_L held low, TMS held high (dossier 5)
    c.net("FMC_JTAG_BYPASS", f"J1.{sig['TDI'][0]}", f"J1.{sig['TDO'][0]}")
    for ref, signal, rail in (("R3", "TCK", "GND"), ("R4", "TRST_L", "GND"),
                              ("R5", "TMS", "+3V3")):
        c.part(ref, "Device:R", "10k", R0603, LCSC="C25804")
        c.net(f"FMC_{signal}", f"J1.{sig[signal][0]}", f"{ref}.2")
        c.net(rail, f"{ref}.1")

    # ---- power: 3P3V + 3P3VAUX from +3V3; VADJ from the local LDO ----------
    c.part("C1", "Device:C", "10u", C0805, LCSC="C15850")
    c.part("C2", "Device:C", "100n", C0603, LCSC="C1591")
    c.net("+3V3", *[f"J1.{p}" for p in sorted(sig["3P3V"])],
          f"J1.{sig['3P3VAUX'][0]}", "C1.1", "C2.1")
    c.net("GND", "C1.2", "C2.2")

    # VADJ LDO: +3V3 -> TLV75725 (DYD thermal-pad) -> +2V5_VADJ (EN strapped
    # on; 0.4 A budget). PWR-3 thermal swap: source the orderable identity
    # (MPN/LCSC/datasheet) + the DYD thermal-pad FOOTPRINT from the in-repo
    # parts/TLV75725PDYDR folder. DEF-E: use that folder's 6-pin symbol (no
    # lib_id override) so pin 6 = EP exists in the model and is netted to GND
    # in the schematic below — a real, gate-checkable ground connection, not
    # just a layout pour bond. Pin-by-number map 1=IN 2=GND 3=EN 4=NC 5=OUT
    # 6=EP.
    c.use_part("TLV75725PDYDR", ref="U1",
               footprint="TLV75725PDYDR:TLV75725PDYDR")
    c.part("C3", "Device:C", "1u", C0603, LCSC="C15849")        # LDO in
    c.part("C4", "Device:C", "10u", C0805, LCSC="C15850")       # LDO out
    c.part("C5", "Device:C", "100n", C0603, LCSC="C1591")       # at connector
    c.net("+3V3", "U1.1", "U1.3", "C3.1")
    c.net("GND", "U1.2", "U1.6", "C3.2", "C4.2", "C5.2")
    c.nc("U1.4")
    c.net("+2V5_VADJ", "U1.5", "C4.1", "C5.1",
          *[f"J1.{p}" for p in sorted(sig["VADJ"])])

    # round-4 coverage gate: the locally-generated VADJ rail
    c.testpoint("+2V5_VADJ")

    # power-tree budget (round 4, fmc.md section 4 — the PLAN flag numbers):
    # 3P3V mezzanine allocation 1.0 A from the +3V3 buck; VADJ budget is the
    # local LDO's honest 0.4 A continuous thermal limit
    c.draws("+3V3", 1.000, "FMC 3P3V+3P3VAUX mezzanine allocation "
                           "(fmc.md section 4)")
    # wave-3 VADJ re-budget (wave3_function_map.md sec 3.1): the TLV75725
    # thermal envelope is 0.40 A total. PWR-3 swapped DBV->DYD (thermal pad,
    # RthJA ~92.5 C/W EP-to-GND vs 231 C/W bare): the SAME 0.32 W (0.4 A at
    # ~0.8 V drop) now sits at Tj ~80 C (Ta=50 C), not the old ~125 C — so the
    # 0.40 A is no longer a hard derate but a comfortable continuous limit.
    # The Zynq bank-35 VCCO (LVDS_25 drivers: 12 FMC LA + 3 camera CSI pairs,
    # ~0.045 A) ALSO rides +2V5_VADJ, so the FMC mezzanine allocation drops
    # 0.40 -> 0.35 A to hold the envelope. (The bank-35 VCCO draw itself awaits
    # the rail-tie template — powertree KNOWN-DEFERRED — but the headroom is
    # reserved here regardless, per the dossier.)
    c.draws("+2V5_VADJ", 0.350, "FMC VADJ mezzanine budget (TLV75725 DYD 0.40 A "
                                "envelope less ~0.05 A bank-35 VCCO; "
                                "wave3_function_map.md sec 3.1)")
    return c
