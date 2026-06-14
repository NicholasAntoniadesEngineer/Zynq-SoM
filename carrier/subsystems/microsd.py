"""microsd — card slot behind the MANDATED SDIO level translator.

PLAN-verified: the SoM's SDIO_* nets run straight to the Zynq at 1.8V and
standard SD cards initialize at 3.3V, so a TXS02612 sits between them:
port A = 1.8V SoM side (contract nets SDIO_* verbatim, typed sd_bus 1.8V),
port B0 = 3.3V card side to the TF-01A push-push slot, port B1 unused.
SEL strapped low selects B0 (verify polarity against the TI datasheet at
bring-up; one-line fix here if inverted). Card-side CMD/DAT pull-ups 10k to
the bring-up-gated +3V3_SD rail; TPD6E001 6-ch ESD across the card lines
with its VCC biased to +3V3_SD (+ local 100n) so the clamp references the
card rail rather than floating worst-case (SD-1, TI SLLS546); card-detect
pulled up and reported.

SD-1 (operating-mode note) — the card side is wired at a FIXED 3.3 V
(+3V3_SD), with no 1.8 V card-rail switch. So this slot supports only the
DEFAULT-speed and HIGH-SPEED SD modes (3.3 V signalling); UHS-I (SDR50/
SDR104/DDR50), which mandates a 1.8 V signalling voltage switch (S18), is
NOT available here. The SoM SDIO controller firmware MUST therefore keep
voltage-switching disabled — do NOT request S18 (CMD11 / 1.8 V switch) in
the initialization flow: the TXS02612 B0 rail is permanently 3.3 V, so a
host that switched to 1.8 V would lose the card. Throughput caps at the
high-speed tier by design (no extra card-rail LDO/level-shift on rev A).
"""

from __future__ import annotations

from schgen.core.model import Circuit

R0603 = "Resistor_SMD:R_0603_1608Metric"
C0603 = "Capacitor_SMD:C_0603_1608Metric"
C0805 = "Capacitor_SMD:C_0805_2012Metric"

BRINGUP = "bringup (gated +3V3_SD rail)"
J1_MAP = "som_j1_connector (STM32 GPIO function map)"

# SoM contract net -> (TXS A-side pin, TXS B0-side pin, slot pin, ESD channel)
LANES = {
    "SDIO_CLK": ("CLKA", "CLKB0", "CLK(SCLK)", "IO1"),
    "SDIO_CMD": ("CMDA", "CMDB0", "CMD(DI)", "IO2"),
    "SDIO_D0": ("DAT0A", "DAT0B0", "DAT0(D0)", "IO3"),
    "SDIO_D1": ("DAT1A", "DAT1B0", "DAT1(RSV)", "IO4"),
    "SDIO_D2": ("DAT2A", "DAT2B0", "DAT2(RSV)", "IO5"),
    "SDIO_D3": ("DAT3A", "DAT3B0", "CDDAT3(CS)", "IO6"),
}
PULLED = ("SDIO_CMD", "SDIO_D0", "SDIO_D1", "SDIO_D2", "SDIO_D3")


def circuit() -> Circuit:
    c = Circuit("microsd", "microSD slot (1.8V SoM <-> 3.3V card, TXS02612)")
    c.use_part("TXS02612RTWR", ref="U1")
    c.use_part("TF-01A", ref="J1")
    c.use_part("TPD6E001RSER", ref="U2")

    # ---- lanes: SoM(1.8V, port) -> TXS -> card(3.3V) + ESD ----------------
    for net, (a, b0, slot, esd) in LANES.items():
        c.port(net, f"U1.{a}")
        card = f"SD_CARD_{net.split('_', 1)[1]}"
        c.net(card, f"U1.{b0}", f"J1.{slot}", f"U2.{esd}")
        c.port_type(net, kind="sd_bus", level_v=1.8)

    # card-side pull-ups to the gated rail
    pull_pins = []
    for i, net in enumerate(PULLED, start=1):
        ref = f"R{i}"
        c.part(ref, "Device:R", "10k", R0603, LCSC="C25804")
        card = f"SD_CARD_{net.split('_', 1)[1]}"
        c.net(card, f"{ref}.2")
        pull_pins.append(f"{ref}.1")

    # card detect: switch closes to GND, pulled up, reported to the SoM
    c.part("R6", "Device:R", "10k", R0603, LCSC="C25804")
    c.port("SD_CARD_DETECT", "J1.CD", "R6.2", expect=J1_MAP)
    pull_pins.append("R6.1")

    # ---- power -------------------------------------------------------------
    c.net("+1V8", "U1.VCCA")                    # VCCA, SoM-side level
    for cap in c.decouple("U1.VCCA", "100n"):   # C14663 Basic, 20.6M stock
        cap.fields["LCSC"] = "C14663"
    # gated card rail (+3V3_SD is the bring-up-gated module rail — SY6280 on
    # the bringup sheet — a POWER net with its own symbol, like +5V_USB):
    # slot VDD + both VCCB + every pull-up + bulk + ESD-array VCC (SD-1)
    c.part("C2", "Device:C", "100n", C0603, LCSC="C1591")
    c.part("C3", "Device:C", "22u", C0805, LCSC="C45783")
    c.net("+3V3_SD", "J1.VDD", "U1.VCCB0", "U1.VCCB1", "C2.1", "C3.1",
          "U2.VCC", *pull_pins)
    c.net("GND", "C2.2", "C3.2")
    # SD-1 (electrical audit): the TPD6E001 VCC sets its clamp reference; a
    # floating VCC gives the WORST-CASE clamp on the user-facing card lines
    # (TI SLLS546). Bias it to the card-side rail +3V3_SD and bypass locally.
    for cap in c.decouple("U2.VCC", "100n"):    # C14663 Basic, 18.1M stock
        cap.fields["LCSC"] = "C14663"

    # SEL low selects port B0; EP + both TXS GND pins + slot VSS/GND pads
    c.net("GND", "U1.SEL", "U1.EP", "U1.GND",
          "J1.VSS", "J1.GND", "U2.GND")

    # unused TXS port B1 + ESD spares
    c.nc("U1.DAT2B1", "U1.DAT3B1", "U1.CMDB1", "U1.CLKB1",
         "U1.DAT0B1", "U1.DAT1B1")
    c.nc("U2.NC")                  # NC pads 4/9 only (VCC biased per SD-1)

    # round-4 coverage gate: SDIO CMD/CLK probed on the 1.8 V SoM side
    # (where the level translator's timing actually matters)
    c.testpoint("SDIO_CMD")
    c.testpoint("SDIO_CLK")

    # power-tree budget (round 4): SD card 3.3 V class up to ~200 mA write
    # bursts (SD phys spec) + 6x 10k pulls + TXS VCCB — inside the 1 A
    # SY6280 cell-5 limit; TXS02612 VCCA side is uA-class but budgeted
    c.draws("+3V3_SD", 0.250, "SD card write burst ~200 mA + pull-ups + "
                              "TXS02612 VCCB")
    c.draws("+1V8", 0.005, "TXS02612 VCCA (SoM-side level)")
    return c
