"""usb_pd — FUSB302B USB Type-C / Power-Delivery PHY subsystem.

Reference circuit per the onsemi FUSB302B datasheet (and the carrier's
hand-audited usb_pd sheet): VDD bypassed 100n + 10u, VBUS (fed from +VIN)
bypassed 100n, 200p filter caps on each CC line. VCONN sourcing is unused
by design -> both VCONN pins are explicit author no-connects.

Bring-up dossier risk R1 (carrier/research/bringup_power_gating.md): PD
negotiation must happen BEFORE any DIP-gated carrier rail exists — the
board boots on default 5 V VBUS. FUSB302 VDD and the INT_N pull-up
therefore live on +3V3_SC (the SoM system-controller rail); the SHARED
STM32_I2C2 bus pull-ups (4k7 to +3V3_SC) live once, on bringup_rails with
the TCA9535 — not duplicated here.

Stock symbol Interface_USB:FUSB302BMPX (WQFN-14 + EP): stacked duplicate
pins 4 (VDD), 9/15 (GND/EP), 11 (CC1), 14 (CC2) are declared on the same
nets as their visible twins — the netlist gate proves KiCad sees all of them.
"""

from __future__ import annotations

from schgen.model import Circuit

LIB_ID = "Interface_USB:FUSB302BMPX"
FOOTPRINT = "Package_DFN_QFN:WQFN-14-1EP_2.5x2.5mm_P0.5mm_EP1.45x1.45mm"


def circuit() -> Circuit:
    c = Circuit("usb_pd", "USB-PD: FUSB302B Type-C controller")
    # LCSC C132291 (== parts/FUSB302BMPX) — live-verified 2026-06-11:
    # Extended, stock 7,735
    c.part("U1", LIB_ID, "FUSB302BMPX", FOOTPRINT, LCSC="C132291")

    # power — +3V3_SC (always-on SC rail), NEVER a DIP-gated carrier rail:
    # PD brings the 20 V in, so it cannot depend on rails it creates (R1)
    c.net("+3V3_SC", "U1.3", "U1.4")              # VDD (+ stacked pin 4)
    c.net("+VIN", "U1.2")                         # VBUS sense, fed from +VIN
    c.net("GND", "U1.8", "U1.9", "U1.15")         # GND + stacked + EP
    for cap, lcsc in zip(c.decouple("U1.3", "100n", "10u"),  # C1, C2
                         ("C14663", "C15850")):              # both Basic
        cap.fields["LCSC"] = lcsc
    for cap in c.decouple("U1.2", "100n"):        # C3 on +VIN
        cap.fields["LCSC"] = "C14663"

    # Type-C CC lines to the connector (external interface) + 200p filters
    # (200p = C113796, YAGEO NP0 0603, Extended, stock 198,883 — 2026-06-11)
    cc1 = c.port("STM32_USB_CC1", "U1.10", "U1.11")
    cc2 = c.port("STM32_USB_CC2", "U1.1", "U1.14")
    for net in (cc1, cc2):
        ref = c.auto_ref("C")
        c.part(ref, "Device:C", "200p", LCSC="C113796")
        c.net(net.name, f"{ref}.1")
        c.net("GND", f"{ref}.2")

    # I2C + interrupt to the STM32. The SoM contract exposes raw STM32_GPIO*
    # names; the generated J1 sheet (wave 3) carries the GPIO->I2C2/INT
    # function map, so these ports are explicitly deferred. The shared-bus
    # SDA/SCL pull-ups live on bringup_rails (+3V3_SC, dossier R1); only
    # the open-drain INT_N pull-up is this sheet's own.
    J1_MAP = "som_j1_connector (wave 3 STM32 GPIO function map)"
    c.port("STM32_I2C2_SDA", "U1.7",
           kind="i2c", role="sda", bus="STM32_I2C2", speed_hz=400_000,
           expect=J1_MAP)
    c.port("STM32_I2C2_SCL", "U1.6",
           kind="i2c", role="scl", bus="STM32_I2C2", speed_hz=400_000,
           expect=J1_MAP)
    c.port("STM32_FUSB302_INT", "U1.5", expect=J1_MAP)
    c.pullup("U1.5", "4k7", "+3V3_SC") \
        .fields["LCSC"] = "C23162"                # R1 (INT_N), Basic 10M

    # VCONN sourcing unused by design
    c.nc("U1.12", "U1.13")
    return c
