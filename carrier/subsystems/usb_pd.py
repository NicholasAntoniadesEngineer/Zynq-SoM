"""usb_pd — FUSB302B USB Type-C / Power-Delivery PHY subsystem.

Reference circuit per the onsemi FUSB302B datasheet (and the carrier's
hand-audited usb_pd sheet): VDD bypassed 100n + 10u, VBUS sense bypassed
100n, 200p filter caps on each CC line. VCONN sourcing is unused by design
-> both VCONN pins are explicit author no-connects.

VBUS sense rides +VBUS_IN — the RAW receptacle VBUS, AHEAD of the round-5
TPS26631 inlet eFuse (pd_input): the PD PHY must observe vSafe5V/vbus at
the connector itself for attach detection, not the dVdT-ramped board rail
behind the eFuse.

Bring-up dossier risk R1 (carrier/research/bringup_power_gating.md): PD
negotiation must happen BEFORE any DIP-gated carrier rail exists — the
board boots on default 5 V VBUS. FUSB302 VDD and the INT_N pull-up
therefore live on +3V3_SC (the SoM system-controller rail); the SHARED
STM32_I2C2 bus pull-ups (4k7 to +3V3_SC) live once, on bringup_rails with
the TCA9535 — not duplicated here.

PD-CC-1 (firmware contract) — the FUSB302B OWNS CC1/CC2. Its CC pins
(U1.11/U1.10 = CC1, U1.14/U1.1 = CC2) connect to the receptacle CC lines
(STM32_USB_CC1/2 from pd_input.J1) and provide Rd/Rp, vRd sensing, BMC PHY
and VCONN switching for the whole Type-C/PD stack. The SoM/STM32 system-
controller firmware MUST NOT enable its native UCPD peripheral on these
lines — UCPD would drive its own Rd/Rp and BMC transceiver onto the same
CC nets, contending with the FUSB302B (double-termination corrupts the
advertised current and the PHY garbles BMC framing). The SC talks PD only
over I2C to the FUSB302B (0x22 on STM32_I2C2) + the INT_N line; the CC
pins stay UCPD-disabled / GPIO-Hi-Z on the SC. (CC analog filter caps 200p
live here; the receptacle CC lines themselves are pd_input's.)

Stock symbol Interface_USB:FUSB302BMPX (WQFN-14 + EP): stacked duplicate
pins 4 (VDD), 9/15 (GND/EP), 11 (CC1), 14 (CC2) are declared on the same
nets as their visible twins — the netlist gate proves KiCad sees all of them.
"""

from __future__ import annotations

from schgen.model import Circuit

# DELIBERATE symbol override (use_part lib_id=): the sheet keeps the stock
# stacked-pin KiCad drawing + the stock footprint; MPN/LCSC/datasheet are
# sourced from parts/FUSB302BMPX/ and can never drift from the library.
LIB_ID = "Interface_USB:FUSB302BMPX"
FOOTPRINT = "Package_DFN_QFN:WQFN-14-1EP_2.5x2.5mm_P0.5mm_EP1.45x1.45mm"


def circuit() -> Circuit:
    c = Circuit("usb_pd", "USB-PD: FUSB302B Type-C controller")
    # LCSC C132291 (from parts/FUSB302BMPX) — live-verified 2026-06-11:
    # Extended, stock 7,735
    c.use_part("FUSB302BMPX", ref="U1", lib_id=LIB_ID, footprint=FOOTPRINT)

    # power — +3V3_SC (always-on SC rail), NEVER a DIP-gated carrier rail:
    # PD brings the 20 V in, so it cannot depend on rails it creates (R1)
    c.net("+3V3_SC", "U1.3", "U1.4")              # VDD (+ stacked pin 4)
    c.net("+VBUS_IN", "U1.2")          # VBUS sense: RAW receptacle VBUS,
    c.net("GND", "U1.8", "U1.9", "U1.15")  # ahead of the pd_input eFuse
    for cap, lcsc in zip(c.decouple("U1.3", "100n", "10u"),  # C1, C2
                         ("C14663", "C15850")):              # both Basic
        cap.fields["LCSC"] = lcsc
    for cap in c.decouple("U1.2", "100n"):        # C3 on +VBUS_IN
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

    # I2C + interrupt to the STM32. The generated J1 sheet (wave 3) carries the
    # GPIO->I2C2/INT function map (som_conn_gen FUNCTION_MAP), so these ports
    # bind there by name. The shared-bus SDA/SCL pull-ups live on bringup_rails
    # (+3V3_SC, dossier R1).
    #
    # G2 (wave3_function_map.md sec 1.1): the FUSB302 open-drain INT and the
    # TCA9535 open-drain INT# merge onto the SINGLE shared SC interrupt
    # SC_INT_N (STM32_GPIO4 = PA15) — both devices are on the same bit-banged
    # I2C bus, so IRQ -> read both status registers is the textbook wired-OR.
    # ONE pull-up per net (house rule): the bringup_rails 10k stays, this
    # sheet's redundant 4k7 (old R1) is DELETED — SC_INT_N is no longer pulled
    # here, only ported.
    J1_MAP = "som_j1_connector (wave 3 STM32 GPIO function map)"
    c.port("STM32_I2C2_SDA", "U1.7",
           kind="i2c", role="sda", bus="STM32_I2C2", speed_hz=400_000,
           expect=J1_MAP)
    c.port("STM32_I2C2_SCL", "U1.6",
           kind="i2c", role="scl", bus="STM32_I2C2", speed_hz=400_000,
           expect=J1_MAP)
    c.port("SC_INT_N", "U1.5", expect=J1_MAP)     # wire-OR onto STM32_GPIO4

    # VCONN sourcing unused by design
    c.nc("U1.12", "U1.13")

    # power-tree budget (round 4): FUSB302B IDD < 1 mA (DS). The INT pull-up is
    # now the single bringup_rails 10k (G2 wire-OR) — no pull here anymore.
    c.draws("+3V3_SC", 0.002, "FUSB302B VDD (<1 mA); SC_INT_N pulled on "
                              "bringup_rails (G2 wire-OR, single 10k)")
    return c
