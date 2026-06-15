"""devkit_mini — a hypothetical mini baseboard that CONSUMES the library subsystems.

This is a SECOND, independent consumer of the project-agnostic ``subsystems/``
library, alongside the real ``carrier/``. It exists to PROVE the reusable-subsystem
architecture: every ``subsystems/<name>/`` package ports to this board with ZERO
changes to the library — the only project-specific surface is the ``META`` dict each
adapter below declares (the STANDARD contract, ``schgen.core.subsystem.Meta``).

Each adapter here is the EXACT same shape as ``carrier/subsystems/<name>.py``: import
the library subsystem, declare ONE module-level ``META`` (``bind`` / ``expects`` /
``buses`` / ``notes``), and forward it via ``_lib.circuit(META)``. The board build
(or a test) gets the bound :class:`~schgen.core.model.Circuit` back.

THE DEVKIT NET-NAMING CONVENTION (deliberately DIFFERENT from the carrier so this is
a real re-bind, not a copy — see README.md for the full table):

  rails (every name still classifies POWER/GROUND by the model's regex):
    +3V3_MINI   the board's common 3.3 V-class LOGIC rail. SHARED across ALL four
                subsystems (usb_pd VDD, usbc_otg FLT pull, uart_bridge VREGIN/VDD/VIO,
                microsd CARD side) — the carrier instead spreads these over +3V3_SC /
                +3V3 / +3V3_SD. Sharing one rail here is the cross-subsystem
                composition proof.
    +5V_DEV     the 5 V host supply the OTG port SOURCES onto the cable (carrier: +5V_USB).
    +1V8_FPGA   the 1.8 V SDIO host-signalling reference for the SD level translator
                (carrier: +1V8).
    +VBUS_RAW   the raw receptacle VBUS the PD PHY senses, ahead of any eFuse
                (carrier: +VBUS_IN).
    GND         ground — SHARED across all four subsystems (identity bind everywhere).

  buses / signal groups (project-owned names; carrier names shown for contrast):
    MINI_I2C0   the PD control I2C bus           (carrier: STM32_I2C2)
    PD_CC1/2    the Type-C CC lines              (carrier: STM32_USB_CC1/2)
    SD0_*       the SDIO host-side bus            (carrier: SDIO_*)
    FPGA_UART0_*  the host UART (post-crossover)  (carrier: ZYNQ_PS_UART0_*)
    USB2_*      the USB data pairs / VBUS         (carrier: USB_D+/-, USB_UART_*)

The devkit's "host" is a hypothetical FPGA SoC (hence +1V8_FPGA / FPGA_UART0_*),
distinct from the carrier's STM32 system-controller + Zynq PS naming — so binding the
same library package to the two boards yields two entirely different net sets while the
library file is byte-for-byte identical.
"""

from __future__ import annotations

from schgen.core.model import Circuit

from subsystems.usb_pd import usb_pd as _usb_pd
from subsystems.usbc_otg import usbc_otg as _usbc_otg
from subsystems.microsd import microsd as _microsd
from subsystems.uart_bridge import uart_bridge as _uart_bridge

# ---- project-wide net names (the convention; DIFFERENT from the carrier) --------
# The common 3.3 V-class logic rail + ground are SHARED across every subsystem after
# binding — that shared identity is what makes these four cells compose into one board.
V3V3 = "+3V3_MINI"     # carrier spreads this over +3V3_SC / +3V3 / +3V3_SD
V5V = "+5V_DEV"        # carrier: +5V_USB
V1V8 = "+1V8_FPGA"     # carrier: +1V8
VBUS_RAW = "+VBUS_RAW"  # carrier: +VBUS_IN
GND = "GND"            # identity (the one net every board agrees on)

# Linker deferral strings — the devkit's connector/expander sheets that will bind
# the deferred ports. Project-specific prose (the carrier cites its own J1/bringup
# sheets); only the STRING differs, the mechanism is identical.
_J_CONN = "devkit_conn (mini header J5 GPIO map)"
_UART_HDR = "devkit_uart_header (FPGA UART0 pin map)"
_USB_CONN = "devkit_usb_receptacles (USB2 connector sheet)"


# ---- usb_pd: FUSB302B Type-C / PD sink PHY --------------------------------------
# Devkit binds the PD PHY VDD onto the SHARED +3V3_MINI logic rail (an always-on rail
# that exists before PD negotiation), the I2C onto its own MINI_I2C0 bus, INT_N to a
# board interrupt. Carrier put these on +3V3_SC / STM32_I2C2 / SC_INT_N.
USB_PD_META = {
    "bind": {
        "+VDD_LOGIC": V3V3,          # carrier: +3V3_SC
        "+VBUS_SENSE": VBUS_RAW,     # carrier: +VBUS_IN
        "GND": GND,
        "CC1": "PD_CC1",             # carrier: STM32_USB_CC1
        "CC2": "PD_CC2",             # carrier: STM32_USB_CC2
        "I2C_SDA": "MINI_I2C0_SDA",  # carrier: STM32_I2C2_SDA
        "I2C_SCL": "MINI_I2C0_SCL",  # carrier: STM32_I2C2_SCL
        "INT_N": "MINI_PD_INT_N",    # carrier: SC_INT_N
    },
    "expects": {
        "I2C_SDA": _J_CONN,
        "I2C_SCL": _J_CONN,
        "INT_N": _J_CONN,
    },
    "buses": {"i2c": "MINI_I2C0"},   # carrier: STM32_I2C2
    "notes": {"draws": "FUSB302B VDD (<1 mA) on the shared +3V3_MINI logic rail; "
                       "MINI_I2C0 + INT pull-ups are board-shared, off-subsystem"},
}


def usb_pd_circuit() -> Circuit:
    return _usb_pd.circuit(USB_PD_META)


# ---- usbc_otg: USB 2.0 HS host port (Type-C) ------------------------------------
# Devkit sources the cable VBUS from +5V_DEV through the TPS2051C, pulls FLT# to the
# SHARED +3V3_MINI logic rail (so it's the SAME net as the PD PHY VDD — composition),
# and routes the data pair to the FPGA USB host PHY. Carrier used +5V_USB / +3V3_SC.
USBC_OTG_META = {
    "bind": {
        "+VBUS_SUPPLY": V5V,         # carrier: +5V_USB
        "+VDD_LOGIC": V3V3,          # carrier: +3V3_SC  (SHARED logic rail)
        "GND": GND,
        "CHASSIS_GND": "CHASSIS_GND",
        "USB_DP": "USB2_HOST_DP",    # carrier: USB_D+
        "USB_DM": "USB2_HOST_DM",    # carrier: USB_D-
        "VBUS": "USB2_HOST_VBUS",    # carrier: USB_VBUS
        "VBUS_EN": "USB2_HOST_EN",   # carrier: VBUS_OUT_EN
        "FLT_N": "USB2_HOST_FLT_N",  # carrier: USBOTG_FLT_N
        "USB_ID": "USB2_HOST_ID",    # carrier: USB_ID
    },
    "expects": {
        "VBUS_EN": _J_CONN,
        "USB_ID": _J_CONN,
        "FLT_N": _J_CONN,
    },
    "notes": {
        "draws_vbus": "downstream USB device budget (TPS2051C limited) from +5V_DEV",
        "draws_flt": "USB2_HOST_FLT# 100k pull-up on the shared +3V3_MINI logic rail",
    },
}


def usbc_otg_circuit() -> Circuit:
    return _usbc_otg.circuit(USBC_OTG_META)


# ---- microsd: TXS02612 level-translated microSD slot ----------------------------
# Devkit host side is the 1.8 V FPGA SDIO domain (+1V8_FPGA); the FIXED 3.3 V card
# rail rides the SHARED +3V3_MINI logic rail (the same net as PD VDD + UART VDD + OTG
# FLT pull) — the carrier instead used a dedicated bring-up-gated +3V3_SD. SD bus uses
# the project's own SD0_* names (carrier: SDIO_*).
MICROSD_META = {
    "bind": {
        "+VDD_HOST": V1V8,           # carrier: +1V8
        "+VDD_CARD": V3V3,           # carrier: +3V3_SD  (devkit shares the logic rail)
        "GND": GND,
        "SD_CLK": "SD0_CLK",         # carrier: SDIO_CLK
        "SD_CMD": "SD0_CMD",         # carrier: SDIO_CMD
        "SD_D0": "SD0_DAT0",         # carrier: SDIO_D0
        "SD_D1": "SD0_DAT1",         # carrier: SDIO_D1
        "SD_D2": "SD0_DAT2",         # carrier: SDIO_D2
        "SD_D3": "SD0_DAT3",         # carrier: SDIO_D3
        "CD_N": "SD0_DETECT_N",      # carrier: SD_CARD_DETECT
    },
    "expects": {
        "CD_N": _J_CONN,
    },
    "notes": {
        "draws_card": "SD card write burst ~200 mA + pulls + TXS02612 VCCB "
                      "on +3V3_MINI",
        "draws_host": "TXS02612 VCCA (FPGA 1.8 V SDIO level)",
    },
}


def microsd_circuit() -> Circuit:
    return _microsd.circuit(MICROSD_META)


# ---- uart_bridge: CP2102N USB-UART console --------------------------------------
# Devkit self-powers the CP2102N from the SHARED +3V3_MINI logic rail, senses the
# console receptacle's own VBUS, and applies the SAME bridge<->host null-modem
# crossover the carrier does — but to the devkit's FPGA_UART0_* names (carrier wired
# the crossover to ZYNQ_PS_UART0_*). This proves the crossover lives entirely in the
# project bind, not the library.
UART_BRIDGE_META = {
    "bind": {
        "+VDD_IO": V3V3,                 # carrier: +3V3  (SHARED logic rail)
        "GND": GND,
        "USB_VBUS": "USB2_UART_VBUS",    # carrier: USB_UART_VBUS
        "USB_DP": "USB2_UART_DP",        # carrier: USB_UART_DP
        "USB_DM": "USB2_UART_DM",        # carrier: USB_UART_DM
        "UART_TXD": "FPGA_UART0_RXD",    # bridge TXD -> host RXD  (carrier: ZYNQ_PS_UART0_RXD)
        "UART_RXD": "FPGA_UART0_TXD",    # host TXD -> bridge RXD  (carrier: ZYNQ_PS_UART0_TXD)
        "UART_RTS_N": "FPGA_UART0_CTS_N",  # bridge ~RTS -> host ~CTS
        "UART_CTS_N": "FPGA_UART0_RTS_N",  # host ~RTS -> bridge ~CTS
    },
    "expects": {
        "USB_VBUS": _USB_CONN,
        "USB_DP": _USB_CONN,
        "UART_TXD": _UART_HDR,
        "UART_RXD": _UART_HDR,
        "UART_RTS_N": _UART_HDR,
        "UART_CTS_N": _UART_HDR,
    },
    "notes": {"draws": "CP2102N active ~14 mA typ + RST 1k pull-up on +3V3_MINI"},
}


def uart_bridge_circuit() -> Circuit:
    return _uart_bridge.circuit(UART_BRIDGE_META)


# ---- the project: the full set of bound subsystem circuits ----------------------
# Ordered list of (subsystem-name, adapter) — the devkit's bill of subsystems. A real
# board build would iterate this exactly as `schgen board` iterates the carrier's
# adapters; the test below iterates it to prove every cell builds + composes.
PROJECT = (
    ("usb_pd", usb_pd_circuit),
    ("usbc_otg", usbc_otg_circuit),
    ("microsd", microsd_circuit),
    ("uart_bridge", uart_bridge_circuit),
)

# The rails this project expects to be SHARED across subsystems after binding (the
# composition contract): the common logic rail and ground appear, as the SAME net, in
# more than one subsystem. Asserted by the test.
SHARED_RAILS = (V3V3, GND)


def subsystem_circuits() -> "list[tuple[str, Circuit]]":
    """Build and return every devkit subsystem Circuit, bound to the project's net
    names. The helper a board build (or the test) calls to get the whole board's
    subsystem set."""
    return [(name, build()) for name, build in PROJECT]
