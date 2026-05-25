"""Registry token -> KiCad lib_id and refcircuit-pin -> symbol-pin aliases."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SymbolSpec:
    lib_id: str
    pin_aliases: tuple[tuple[str, str], ...] = ()


# refcircuit pin name -> KiCad symbol pin name (token-agnostic defaults)
_COMMON_ALIASES: dict[str, str] = {
    "IN+": "Vin+",
    "IN-": "Vin-",
    "ALERT": "~{Alert}",
    "INT_N": "INT_N",
    "INT/SQW": "~{INT}/SQW",
    "INT_SQW": "~{INT}/SQW",
    "RST_N": "~{RST}",
    "32kHz": "32KHZ",
    "REGIN": "VREGIN",
    "OC_N": "~{FLT}",
    "EN_N": "EN",
    "NR_SS": "NC",
    "DAT3_CD": "DAT3/CD",
    "CD_SW": "DET_B",
    "VSS": "GND",
    "+5V": "+5V",
    "SHIELD": "SH",
    "CENTER": "In",
    "ANODE": "A",
    "CATHODE": "K",
    "SWDIO": "SWDIO",
    "TCK": "TCK",
    "TMS": "TMS",
}


SYMBOL_SPECS: dict[str, SymbolSpec] = {
    "usbc_pd_FUSB302BMPX": SymbolSpec(
        "carrier:FUSB302BMPX",
        (("VBUS", "VBUS"),),
    ),
    "esd_USBLC6_4SC6": SymbolSpec("carrier:USBLC6-4SC6"),
    "conn_USB_C_16P": SymbolSpec("carrier:USBC_16P"),
    "powermon_INA226": SymbolSpec("Sensor_Energy:INA226", (("IN+", "Vin+"), ("IN-", "Vin-"))),
    "loadsw_TPS2051C": SymbolSpec(
        "Power_Management:TPS2051CDBV",
        (("OC_N", "~{FLT}"), ("EN_N", "EN")),
    ),
    "usbuart_CP2102N": SymbolSpec(
        "Interface_USB:CP2102N-Axx-xQFN24",
        (("RST_N", "~{RST}"), ("REGIN", "VREGIN")),
    ),
    "hdmi_companion_TPD12S016": SymbolSpec("carrier:TPD12S016PWR"),
    "eeprom_24LC256": SymbolSpec("Memory_EEPROM:24LC256"),
    "rtc_DS3231SN": SymbolSpec(
        "Timer_RTC:DS3231M",
        (("RST_N", "~{RST}"), ("INT_SQW", "~{INT}/SQW"), ("32kHz", "32KHZ")),
    ),
    "LDO_TLV75718_1V8": SymbolSpec("Regulator_Linear:TLV75718PDBV", (("NR_SS", "NC"),)),
    "LDO_TLV75725_2V5": SymbolSpec("Regulator_Linear:TLV75725PDBV", (("NR_SS", "NC"),)),
    "LDO_TLV75733_3V3": SymbolSpec("Regulator_Linear:TLV75733PDBV", (("NR_SS", "NC"),)),
    "magnetics_HX5008NLT": SymbolSpec("carrier:HX5008NLT"),
    "conn_RJ45_bare_shielded": SymbolSpec("carrier:RJHSE5380"),
    "conn_HDMI_A": SymbolSpec("Connector:HDMI_A", (("SHIELD", "SH"),)),
    "conn_microSD_DM3AT": SymbolSpec(
        "Connector:Micro_SD_Card_Det_Hirose_DM3AT",
        (("DAT3_CD", "DAT3/CD"), ("CD_SW", "DET_B"), ("VSS", "VSS")),
    ),
    "conn_SMA_RA_TH": SymbolSpec(
        "Connector:Conn_Coaxial",
        (("CENTER", "In"), ("XADC_CLK", "In")),
    ),
    "conn_JTAG_2x7_THT": SymbolSpec("carrier:JTAG_2x7"),
    "conn_SWD_2x5_1.27mm": SymbolSpec("carrier:SWD_2x5"),
    "conn_PMOD_2x6_RA": SymbolSpec(
        "Connector_Generic:Conn_02x06_Odd_Even",
        tuple((f"IO{index}", str(5 + index)) for index in range(8)),
    ),
    "conn_FMC_FX10A_168P": SymbolSpec("carrier:FMC_LPC"),
    "conn_FFC_40P_0.5mm": SymbolSpec("carrier:FFC_40P"),
    "conn_FFC_15P_1mm": SymbolSpec("carrier:FFC_15P"),
    "schottky_SS14": SymbolSpec("Device:D_Schottky", (("ANODE", "A"), ("CATHODE", "K"))),
    "sw_tactile_6x6": SymbolSpec("carrier:SW_TACT"),
    "sw_dip_4pos_1.27mm": SymbolSpec("carrier:SW_DIP_4"),
    "LED_green_0603": SymbolSpec("Device:LED", (("ANODE", "A"), ("CATHODE", "K"))),
    "LED_red_0603": SymbolSpec("Device:LED", (("ANODE", "A"), ("CATHODE", "K"))),
    "LED_yellow_0603": SymbolSpec("Device:LED", (("ANODE", "A"), ("CATHODE", "K"))),
    "LED_blue_0603": SymbolSpec("Device:LED", (("ANODE", "A"), ("CATHODE", "K"))),
}


def resolve_symbol_pin(refcircuit_pin: str, registry_token: str) -> str:
    spec = SYMBOL_SPECS.get(registry_token)
    if spec is not None:
        for alias_from, alias_to in spec.pin_aliases:
            if refcircuit_pin == alias_from:
                return alias_to
    return _COMMON_ALIASES.get(refcircuit_pin, refcircuit_pin)


def lib_id_for_token(registry_token: str) -> str:
    spec = SYMBOL_SPECS.get(registry_token)
    if spec is None:
        raise KeyError(
            f"No symbol spec for registry token {registry_token!r}; "
            "add an entry to SYMBOL_SPECS"
        )
    return spec.lib_id
