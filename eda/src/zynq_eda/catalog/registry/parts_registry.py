"""Canonical BOM part registry.

Every part that can appear on the carrier is declared here exactly once.
ReferenceCircuits reference these by token; the sheet generator looks
them up; the BOM CSV is produced by exporting this registry filtered
to the parts actually used.

When adding a new part:
    1. Find its LCSC# and verify stock (>= 5x build qty)
    2. Get the datasheet URL
    3. Add a BOMPart entry to REGISTRY below using its canonical token
    4. Run the validator - it will catch token/footprint/package mismatches

LCSC stock figures are snapshot at design time; actual stock varies.
"""

from __future__ import annotations

from zynq_eda.catalog.registry.parts import BOMPart


# ---------------------------------------------------------------------------
# Passives - capacitors
# ---------------------------------------------------------------------------

CAPS: tuple[BOMPart, ...] = (
    BOMPart(
        token="100n_0402_X7R",
        value="100n",
        footprint="Capacitor_SMD:C_0402_1005Metric",
        lcsc="C1525",
        mpn="CL05B104KO5NNNC",
        manufacturer="Samsung Electro-Mechanics",
        package="0402",
        datasheet_url="https://www.lcsc.com/datasheet/lcsc_datasheet_2304140030_Samsung-Electro-Mechanics-CL05B104KO5NNNC_C1525.pdf",
        description="100nF 16V X7R MLCC 0402",
        stock_at_lcsc=26_703_600,
        unit_price_usd=0.0013,
    ),
    BOMPart(
        token="1u_0402_X7R",
        value="1u",
        footprint="Capacitor_SMD:C_0402_1005Metric",
        lcsc="C52923",
        mpn="CL05A105KP5NNNC",
        manufacturer="Samsung Electro-Mechanics",
        package="0402",
        datasheet_url="https://datasheet.lcsc.com/lcsc/1810171717_Samsung-Electro-Mechanics-CL05A105KP5NNNC_C52923.pdf",
        description="1uF 10V X5R MLCC 0402",
        stock_at_lcsc=300_000,
        unit_price_usd=0.005,
    ),
    BOMPart(
        token="4u7_0402_X5R",
        value="4u7",
        footprint="Capacitor_SMD:C_0402_1005Metric",
        lcsc="C368809",
        mpn="CL05A475KP5NRNC",
        manufacturer="Samsung Electro-Mechanics",
        package="0402",
        datasheet_url="https://datasheet.lcsc.com/lcsc/1809181722_Samsung-Electro-Mechanics-CL05A475MP5NSNC_C368809.pdf",
        description="4.7uF 10V X5R MLCC 0402",
        stock_at_lcsc=180_000,
        unit_price_usd=0.005,
    ),
    BOMPart(
        token="10u_0402_X5R",
        value="10u",
        footprint="Capacitor_SMD:C_0402_1005Metric",
        lcsc="C15525",
        mpn="CL05A106MQ5NUNC",
        manufacturer="Samsung Electro-Mechanics",
        package="0402",
        datasheet_url="https://datasheet.lcsc.com/lcsc/2304140030_Samsung-Electro-Mechanics-CL05A106MQ5NUNC_C15525.pdf",
        description="10uF 6.3V X5R MLCC 0402",
        stock_at_lcsc=42_000,
        unit_price_usd=0.014,
    ),
    BOMPart(
        token="22u_0805_X5R",
        value="22u",
        footprint="Capacitor_SMD:C_0805_2012Metric",
        lcsc="C98190",
        mpn="CL21A226MOQNNNE",
        manufacturer="Samsung Electro-Mechanics",
        package="0805",
        datasheet_url="https://datasheet.lcsc.com/lcsc/1810181513_Samsung-Electro-Mechanics-CL21A226MOQNNNE_C98190.pdf",
        description="22uF 16V X5R MLCC 0805",
        stock_at_lcsc=50_000,
        unit_price_usd=0.07,
    ),
    BOMPart(
        token="47u_0805_X5R",
        value="47u",
        footprint="Capacitor_SMD:C_0805_2012Metric",
        lcsc="C16780",
        mpn="CL21A476MQYNNNE",
        manufacturer="Samsung Electro-Mechanics",
        package="0805",
        datasheet_url="https://datasheet.lcsc.com/lcsc/1810261635_Samsung-Electro-Mechanics-CL21A476MQYNNNE_C16780.pdf",
        description="47uF 6.3V X5R MLCC 0805",
        stock_at_lcsc=20_000,
        unit_price_usd=0.10,
    ),
    BOMPart(
        token="100u_1206_X5R",
        value="100u",
        footprint="Capacitor_SMD:C_1206_3216Metric",
        lcsc="C15008",
        mpn="CL31A107MQHNNNE",
        manufacturer="Samsung Electro-Mechanics",
        package="1206",
        datasheet_url="https://datasheet.lcsc.com/lcsc/1810181513_Samsung-Electro-Mechanics-CL31A107MQHNNNE_C15008.pdf",
        description="100uF 6.3V X5R MLCC 1206",
        stock_at_lcsc=10_000,
        unit_price_usd=0.40,
    ),
    BOMPart(
        token="470n_0201_X5R",
        value="470n",
        footprint="Capacitor_SMD:C_0201_0603Metric",
        lcsc="C85926",
        mpn="GRM033R60J474KE90D",
        manufacturer="Murata",
        package="0201",
        datasheet_url="https://datasheet.lcsc.com/lcsc/2110281231_Murata-Electronics-GRM033R60J474KE90D_C85926.pdf",
        description="470nF 6.3V X5R MLCC 0201",
        stock_at_lcsc=100_000,
        unit_price_usd=0.02,
    ),
    BOMPart(
        token="47n_0201_X5R",
        value="47n",
        footprint="Capacitor_SMD:C_0201_0603Metric",
        lcsc="C85925",
        mpn="GRM033R60J473KE19D",
        manufacturer="Murata",
        package="0201",
        datasheet_url="https://datasheet.lcsc.com/lcsc/2110281231_Murata-Electronics-GRM033R60J473KE19D_C85925.pdf",
        description="47nF 6.3V X5R MLCC 0201",
        stock_at_lcsc=80_000,
        unit_price_usd=0.02,
    ),
    BOMPart(
        token="200p_0402_C0G",
        value="200p",
        footprint="Capacitor_SMD:C_0402_1005Metric",
        lcsc="C1546",
        mpn="0402CG201J500NT",
        manufacturer="FH(Guangdong Fenghua Advanced Tech)",
        package="0402",
        datasheet_url="https://datasheet.lcsc.com/lcsc/FH-Guangdong-Fenghua-AdvanTech-0402CG201J500NT_C1546.pdf",
        description="200pF 50V C0G MLCC 0402 (USB-PD CC cReceiver)",
        stock_at_lcsc=500_000,
        unit_price_usd=0.002,
    ),
    BOMPart(
        token="10u_0603_X7R",
        value="10u",
        footprint="Capacitor_SMD:C_0603_1608Metric",
        lcsc="C19702",
        mpn="CL10A106KP8NNNC",
        manufacturer="Samsung Electro-Mechanics",
        package="0603",
        datasheet_url="https://datasheet.lcsc.com/lcsc/1810181513_Samsung-Electro-Mechanics-CL10A106KP8NNNC_C19702.pdf",
        description="10uF 6.3V X7R MLCC 0603 (VCONN bulk)",
        stock_at_lcsc=120_000,
        unit_price_usd=0.012,
    ),
    BOMPart(
        token="10n_0402_X7R",
        value="10n",
        footprint="Capacitor_SMD:C_0402_1005Metric",
        lcsc="C57112",
        mpn="0402B103K500NT",
        manufacturer="FH (Guangdong Fenghua Advanced)",
        package="0402",
        datasheet_url="https://datasheet.lcsc.com/lcsc/0402B103K500NT_C57112.pdf",
        description="10nF 50V X7R MLCC 0402",
        stock_at_lcsc=500_000,
        unit_price_usd=0.001,
    ),
    BOMPart(
        token="22p_0402_C0G",
        value="22p",
        footprint="Capacitor_SMD:C_0402_1005Metric",
        lcsc="C1653",
        mpn="0402CG220J500NT",
        manufacturer="FH",
        package="0402",
        datasheet_url="https://datasheet.lcsc.com/lcsc/0402CG220J500NT_C1653.pdf",
        description="22pF 50V C0G/NP0 MLCC 0402 (crystal load)",
        stock_at_lcsc=200_000,
        unit_price_usd=0.002,
    ),
    BOMPart(
        token="1n_2kV_0603_safety",
        value="1n_2kV",
        footprint="Capacitor_SMD:C_0603_1608Metric",
        lcsc="C70133",
        mpn="GRM188R72E102KW07D",
        manufacturer="Murata",
        package="0603",
        datasheet_url="https://datasheet.lcsc.com/lcsc/GRM188R72E102KW07D_C70133.pdf",
        description="1nF 250V X7R safety MLCC 0603 (Bob Smith termination)",
        stock_at_lcsc=20_000,
        unit_price_usd=0.05,
    ),
)


# ---------------------------------------------------------------------------
# Passives - resistors
# ---------------------------------------------------------------------------

RESISTORS: tuple[BOMPart, ...] = (
    BOMPart(
        token="0R_0402",
        value="0R",
        footprint="Resistor_SMD:R_0402_1005Metric",
        lcsc="C17168",
        mpn="0402WGF0000TCE",
        manufacturer="UNI-ROYAL",
        package="0402",
        datasheet_url="https://datasheet.lcsc.com/lcsc/UNI-ROYAL-Uniroyal-Elec-0402WGF0000TCE_C17168.pdf",
        description="0 ohm jumper 0402 1%",
        stock_at_lcsc=2_881_400,
        unit_price_usd=0.0008,
    ),
    BOMPart(
        token="10R_0402_1%",
        value="10R",
        footprint="Resistor_SMD:R_0402_1005Metric",
        lcsc="C307473",
        mpn="0402WGF100JTCE",
        manufacturer="UNI-ROYAL",
        package="0402",
        datasheet_url="https://datasheet.lcsc.com/lcsc/UNI-ROYAL-Uniroyal-Elec-0402WGF100JTCE_C307473.pdf",
        description="10 ohm 1% 1/16W 0402",
        stock_at_lcsc=500_000,
        unit_price_usd=0.0008,
    ),
    BOMPart(
        token="22R_0402_1%",
        value="22R",
        footprint="Resistor_SMD:R_0402_1005Metric",
        lcsc="C25105",
        mpn="0402WGF220JTCE",
        manufacturer="UNI-ROYAL",
        package="0402",
        datasheet_url="https://datasheet.lcsc.com/lcsc/UNI-ROYAL-Uniroyal-Elec-0402WGF220JTCE_C25105.pdf",
        description="22 ohm 1% 1/16W 0402",
        stock_at_lcsc=898_700,
        unit_price_usd=0.0008,
    ),
    BOMPart(
        token="33R_0402_1%",
        value="33R",
        footprint="Resistor_SMD:R_0402_1005Metric",
        lcsc="C25111",
        mpn="0402WGF330JTCE",
        manufacturer="UNI-ROYAL",
        package="0402",
        datasheet_url="https://datasheet.lcsc.com/lcsc/UNI-ROYAL-Uniroyal-Elec-0402WGF330JTCE_C25111.pdf",
        description="33 ohm 1% 1/16W 0402 (HDMI TMDS series)",
        stock_at_lcsc=200_000,
        unit_price_usd=0.0008,
    ),
    BOMPart(
        token="49R9_0402_1%",
        value="49R9",
        footprint="Resistor_SMD:R_0402_1005Metric",
        lcsc="C87044",
        mpn="RC0402FR-0749R9L",
        manufacturer="YAGEO",
        package="0402",
        datasheet_url="https://datasheet.lcsc.com/lcsc/YAGEO-RC0402FR-0749R9L_C87044.pdf",
        description="49.9 ohm 1% 1/16W 0402 (precision termination)",
        stock_at_lcsc=389_500,
        unit_price_usd=0.0009,
    ),
    BOMPart(
        token="75R_0603_1%",
        value="75R",
        footprint="Resistor_SMD:R_0603_1608Metric",
        lcsc="C22790",
        mpn="0603WAF750JT5E",
        manufacturer="UNI-ROYAL",
        package="0603",
        datasheet_url="https://datasheet.lcsc.com/lcsc/UNI-ROYAL-Uniroyal-Elec-0603WAF750JT5E_C22790.pdf",
        description="75 ohm 1% 1/10W 0603 (Bob Smith Ethernet termination)",
        stock_at_lcsc=300_000,
        unit_price_usd=0.001,
    ),
    BOMPart(
        token="100R_0402_1%",
        value="100R",
        footprint="Resistor_SMD:R_0402_1005Metric",
        lcsc="C25076",
        mpn="0402WGF1000TCE",
        manufacturer="UNI-ROYAL",
        package="0402",
        datasheet_url="https://datasheet.lcsc.com/lcsc/UNI-ROYAL-Uniroyal-Elec-0402WGF1000TCE_C25076.pdf",
        description="100 ohm 1% 1/16W 0402 (LVDS termination, current limit)",
        stock_at_lcsc=6_905_500,
        unit_price_usd=0.0008,
    ),
    BOMPart(
        token="100R_0201_5%",
        value="100R",
        footprint="Resistor_SMD:R_0201_0603Metric",
        lcsc="C270336",
        mpn="0201WMJ0101TEE",
        manufacturer="UNI-ROYAL",
        package="0201",
        datasheet_url="https://datasheet.lcsc.com/lcsc/UNI-ROYAL-Uniroyal-Elec-0201WMJ0101TEE_C270336.pdf",
        description="100 ohm 5% 1/20W 0201",
        stock_at_lcsc=23_100,
        unit_price_usd=0.0008,
    ),
    BOMPart(
        token="240R_0402_1%",
        value="240R",
        footprint="Resistor_SMD:R_0402_1005Metric",
        lcsc="C25094",
        mpn="0402WGF2400TCE",
        manufacturer="UNI-ROYAL",
        package="0402",
        datasheet_url="https://datasheet.lcsc.com/lcsc/UNI-ROYAL-Uniroyal-Elec-0402WGF2400TCE_C25094.pdf",
        description="240 ohm 1% 1/16W 0402 (LED current limit)",
        stock_at_lcsc=200_000,
        unit_price_usd=0.0008,
    ),
    BOMPart(
        token="330R_0402_1%",
        value="330R",
        footprint="Resistor_SMD:R_0402_1005Metric",
        lcsc="C25104",
        mpn="0402WGF3300TCE",
        manufacturer="UNI-ROYAL",
        package="0402",
        datasheet_url="https://datasheet.lcsc.com/lcsc/UNI-ROYAL-Uniroyal-Elec-0402WGF3300TCE_C25104.pdf",
        description="330 ohm 1% 1/16W 0402 (LED current limit)",
        stock_at_lcsc=2_546_500,
        unit_price_usd=0.0009,
    ),
    BOMPart(
        token="1k_0402_1%",
        value="1k",
        footprint="Resistor_SMD:R_0402_1005Metric",
        lcsc="C11702",
        mpn="0402WGF1001TCE",
        manufacturer="UNI-ROYAL",
        package="0402",
        datasheet_url="https://datasheet.lcsc.com/lcsc/UNI-ROYAL-Uniroyal-Elec-0402WGF1001TCE_C11702.pdf",
        description="1 kohm 1% 1/16W 0402",
        stock_at_lcsc=1_500_000,
        unit_price_usd=0.0008,
    ),
    BOMPart(
        token="1k5_0402_1%",
        value="1k5",
        footprint="Resistor_SMD:R_0402_1005Metric",
        lcsc="C25867",
        mpn="0402WGF1501TCE",
        manufacturer="UNI-ROYAL",
        package="0402",
        datasheet_url="https://datasheet.lcsc.com/lcsc/UNI-ROYAL-Uniroyal-Elec-0402WGF1501TCE_C25867.pdf",
        description="1.5 kohm 1% 1/16W 0402",
        stock_at_lcsc=500_000,
        unit_price_usd=0.0008,
    ),
    BOMPart(
        token="2k2_0402_1%",
        value="2.2k",
        footprint="Resistor_SMD:R_0402_1005Metric",
        lcsc="C25879",
        mpn="0402WGF2201TCE",
        manufacturer="UNI-ROYAL",
        package="0402",
        datasheet_url="https://datasheet.lcsc.com/lcsc/UNI-ROYAL-Uniroyal-Elec-0402WGF2201TCE_C25879.pdf",
        description="2.2k ohm 1% 1/16W 0402",
        stock_at_lcsc=600_000,
        unit_price_usd=0.0008,
    ),
    BOMPart(
        token="4k7_0402_1%",
        value="4k7",
        footprint="Resistor_SMD:R_0402_1005Metric",
        lcsc="C25900",
        mpn="0402WGF4701TCE",
        manufacturer="UNI-ROYAL",
        package="0402",
        datasheet_url="https://datasheet.lcsc.com/lcsc/UNI-ROYAL-Uniroyal-Elec-0402WGF4701TCE_C25900.pdf",
        description="4.7 kohm 1% 1/16W 0402 (I2C pull-up)",
        stock_at_lcsc=526_356,
        unit_price_usd=0.0008,
    ),
    BOMPart(
        token="5k1_0402_1%",
        value="5k1",
        footprint="Resistor_SMD:R_0402_1005Metric",
        lcsc="C25905",
        mpn="0402WGF5101TCE",
        manufacturer="UNI-ROYAL",
        package="0402",
        datasheet_url="https://datasheet.lcsc.com/lcsc/UNI-ROYAL-Uniroyal-Elec-0402WGF5101TCE_C25905.pdf",
        description="5.1 kohm 1% 1/16W 0402 (USB-C CC Rd termination)",
        stock_at_lcsc=4_413_500,
        unit_price_usd=0.0009,
    ),
    BOMPart(
        token="10k_0402_1%",
        value="10k",
        footprint="Resistor_SMD:R_0402_1005Metric",
        lcsc="C25744",
        mpn="0402WGF1002TCE",
        manufacturer="UNI-ROYAL",
        package="0402",
        datasheet_url="https://datasheet.lcsc.com/lcsc/UNI-ROYAL-Uniroyal-Elec-0402WGF1002TCE_C25744.pdf",
        description="10 kohm 1% 1/16W 0402 (general pull-up)",
        stock_at_lcsc=3_000_000,
        unit_price_usd=0.0008,
    ),
    BOMPart(
        token="22k1_0402_1%",
        value="22k1",
        footprint="Resistor_SMD:R_0402_1005Metric",
        lcsc="C25768",
        mpn="0402WGF2212TCE",
        manufacturer="UNI-ROYAL",
        package="0402",
        datasheet_url="https://datasheet.lcsc.com/lcsc/UNI-ROYAL-Uniroyal-Elec-0402WGF2212TCE_C25768.pdf",
        description="22.1 kohm 1% 1/16W 0402 (CP2102N VBUS sense divider upper)",
        stock_at_lcsc=200_000,
        unit_price_usd=0.0008,
    ),
    BOMPart(
        token="47k5_0402_1%",
        value="47k5",
        footprint="Resistor_SMD:R_0402_1005Metric",
        lcsc="C25819",
        mpn="0402WGF4752TCE",
        manufacturer="UNI-ROYAL",
        package="0402",
        datasheet_url="https://datasheet.lcsc.com/lcsc/UNI-ROYAL-Uniroyal-Elec-0402WGF4752TCE_C25819.pdf",
        description="47.5 kohm 1% 1/16W 0402 (CP2102N VBUS sense divider lower)",
        stock_at_lcsc=200_000,
        unit_price_usd=0.0008,
    ),
    BOMPart(
        token="100k_0402_1%",
        value="100k",
        footprint="Resistor_SMD:R_0402_1005Metric",
        lcsc="C60491",
        mpn="RC0402FR-07100KL",
        manufacturer="YAGEO",
        package="0402",
        datasheet_url="https://datasheet.lcsc.com/lcsc/YAGEO-RC0402FR-07100KL_C60491.pdf",
        description="100 kohm 1% 1/16W 0402 (HPD pull-up)",
        stock_at_lcsc=600_000,
        unit_price_usd=0.0008,
    ),
    BOMPart(
        token="1M_0402_1%",
        value="1M",
        footprint="Resistor_SMD:R_0402_1005Metric",
        lcsc="C25741",
        mpn="0402WGF1004TCE",
        manufacturer="UNI-ROYAL",
        package="0402",
        datasheet_url="https://datasheet.lcsc.com/lcsc/UNI-ROYAL-Uniroyal-Elec-0402WGF1004TCE_C25741.pdf",
        description="1 Mohm 1% 1/16W 0402 (shield to GND, high-impedance)",
        stock_at_lcsc=500_000,
        unit_price_usd=0.0008,
    ),
    BOMPart(
        token="R_SENSE_10mR_2010_1%",
        value="0R01",
        footprint="Resistor_SMD:R_2010_5025Metric",
        lcsc="C7126",
        mpn="RL2010FK-070R01L",
        manufacturer="YAGEO",
        package="2010",
        datasheet_url="https://datasheet.lcsc.com/lcsc/YAGEO-RL2010FK-070R01L_C7126.pdf",
        description="10 milliohm 1% 0.5W 2010 current-sense shunt (INA226 R_SENSE for rails up to 8A)",
        stock_at_lcsc=83_000,
        unit_price_usd=0.135,
    ),
)


# ---------------------------------------------------------------------------
# Passives - inductors / ferrite beads
# ---------------------------------------------------------------------------

INDUCTORS: tuple[BOMPart, ...] = (
    BOMPart(
        token="ferrite_120R_0402",
        value="120R@100MHz",
        footprint="Inductor_SMD:L_0402_1005Metric",
        lcsc="C275478",
        mpn="MPZ1005S121HT000",
        manufacturer="TDK",
        package="0402",
        datasheet_url="https://datasheet.lcsc.com/lcsc/TDK-MPZ1005S121HT000_C275478.pdf",
        description="Ferrite bead 120 ohm @ 100MHz, 2A, 55 mohm 0402",
        stock_at_lcsc=80_000,
        unit_price_usd=0.013,
    ),
    BOMPart(
        token="ferrite_600R_0402",
        value="600R@100MHz",
        footprint="Inductor_SMD:L_0402_1005Metric",
        lcsc="C337875",
        mpn="BLM15BD601SN1D",
        manufacturer="Murata",
        package="0402",
        datasheet_url="https://datasheet.lcsc.com/lcsc/Murata-Electronics-BLM15BD601SN1D_C337875.pdf",
        description="Ferrite bead 600 ohm @ 100MHz, 200mA, 650 mohm 0402 (power-rail filter)",
        stock_at_lcsc=50_000,
        unit_price_usd=0.016,
    ),
)


# ---------------------------------------------------------------------------
# Passives - LEDs
# ---------------------------------------------------------------------------

LEDS: tuple[BOMPart, ...] = (
    BOMPart(
        token="LED_green_0603",
        value="LED_Green",
        footprint="LED_SMD:LED_0603_1608Metric",
        lcsc="C19273151",
        mpn="YLED0603G",
        manufacturer="YONGYUTAI",
        package="0603",
        datasheet_url="https://datasheet.lcsc.com/lcsc/YONGYUTAI-YLED0603G_C19273151.pdf",
        description="Green LED 0603 510-531nm (status / power-good)",
        stock_at_lcsc=75_000,
        unit_price_usd=0.01,
    ),
    BOMPart(
        token="LED_red_0603",
        value="LED_Red",
        footprint="LED_SMD:LED_0603_1608Metric",
        lcsc="C965799",
        mpn="XL-1608SURC-06",
        manufacturer="XINGLIGHT",
        package="0603",
        datasheet_url="https://datasheet.lcsc.com/lcsc/XINGLIGHT-XL-1608SURC-06_C965799.pdf",
        description="Red LED 0603 625nm (error / fault indicator)",
        stock_at_lcsc=6_386_700,
        unit_price_usd=0.004,
    ),
    BOMPart(
        token="LED_yellow_0603",
        value="LED_Yellow",
        footprint="LED_SMD:LED_0603_1608Metric",
        lcsc="C84256",
        mpn="19-217/Y2C-CQ2R2L/3T",
        manufacturer="EVERLIGHT",
        package="0603",
        datasheet_url="https://datasheet.lcsc.com/lcsc/Everlight-Elec-19-217-Y2C-CQ2R2L-3T_C84256.pdf",
        description="Yellow LED 0603 (Ethernet activity)",
        stock_at_lcsc=200_000,
        unit_price_usd=0.01,
    ),
    BOMPart(
        token="LED_blue_0603",
        value="LED_Blue",
        footprint="LED_SMD:LED_0603_1608Metric",
        lcsc="C72041",
        mpn="19-217/BHC-ZL1M2RY/3T",
        manufacturer="EVERLIGHT",
        package="0603",
        datasheet_url="https://datasheet.lcsc.com/lcsc/Everlight-Elec-19-217-BHC-ZL1M2RY-3T_C72041.pdf",
        description="Blue LED 0603 (user indicator)",
        stock_at_lcsc=100_000,
        unit_price_usd=0.014,
    ),
)


# ---------------------------------------------------------------------------
# Diodes / TVS
# ---------------------------------------------------------------------------

DIODES: tuple[BOMPart, ...] = (
    BOMPart(
        token="schottky_SS14",
        value="SS14",
        footprint="Diode_SMD:D_SMA",
        lcsc="C83852",
        mpn="SS14",
        manufacturer="onsemi",
        package="SMA",
        datasheet_url="https://datasheet.lcsc.com/lcsc/ON-Semicon-SS14_C83852.pdf",
        description="Schottky 40V 1A SMA (VBUS protection, reverse polarity)",
        stock_at_lcsc=49_340,
        unit_price_usd=0.12,
    ),
    BOMPart(
        token="esd_USBLC6_4SC6",
        value="USBLC6-4SC6",
        footprint="Package_TO_SOT_SMD:SOT-23-6",
        lcsc="C111212",
        mpn="USBLC6-4SC6",
        manufacturer="STMicroelectronics",
        package="SOT-23-6",
        datasheet_url="https://www.st.com/resource/en/datasheet/usblc6-4.pdf",
        description="USB 2.0 ESD protection 4-line SOT-23-6 (rev 6)",
        stock_at_lcsc=17_280,
        unit_price_usd=0.17,
    ),
    BOMPart(
        token="tvs_PESD5V0S2BT",
        value="PESD5V0S2BT",
        footprint="Package_TO_SOT_SMD:SOT-23",
        lcsc="C49338",
        mpn="PESD5V0S2BT,215",
        manufacturer="Nexperia",
        package="SOT-23",
        datasheet_url="https://assets.nexperia.com/documents/data-sheet/PESD5V0S2BT.pdf",
        description="ESD/TVS bidirectional 5V SOT-23 (Ethernet MDI protection)",
        stock_at_lcsc=34_915,
        unit_price_usd=0.14,
    ),
)


# ---------------------------------------------------------------------------
# Power management ICs
# ---------------------------------------------------------------------------

POWER_ICS: tuple[BOMPart, ...] = (
    BOMPart(
        token="LDO_TLV75718_1V8",
        value="TLV75718PDBVR",
        footprint="Package_TO_SOT_SMD:SOT-23-5",
        lcsc="C507270",
        mpn="TLV75718PDBVR",
        manufacturer="Texas Instruments",
        package="SOT-23-5",
        datasheet_url="https://www.ti.com/lit/ds/symlink/tlv757p.pdf",
        description="1.8V 1A LDO SOT-23-5 (VCCO 1.8V bank supply)",
        stock_at_lcsc=167,
        unit_price_usd=0.27,
        allow_low_stock=True,  # specialty voltage, low stock acceptable
        alt_digikey="296-49232-1-ND",
    ),
    BOMPart(
        token="LDO_TLV75725_2V5",
        value="TLV75725PDBVR",
        footprint="Package_TO_SOT_SMD:SOT-23-5",
        lcsc="C2872563",
        mpn="TLV75725PDBVR",
        manufacturer="Texas Instruments",
        package="SOT-23-5",
        datasheet_url="https://www.ti.com/lit/ds/symlink/tlv757p.pdf",
        description="2.5V 1A LDO SOT-23-5 (VCCO 2.5V bank supply)",
        stock_at_lcsc=500,
        unit_price_usd=0.27,
        allow_low_stock=True,
        alt_digikey="296-49231-1-ND",
    ),
    BOMPart(
        token="LDO_TLV75733_3V3",
        value="TLV75733PDBVR",
        footprint="Package_TO_SOT_SMD:SOT-23-5",
        lcsc="C485517",
        mpn="TLV75733PDBVR",
        manufacturer="Texas Instruments",
        package="SOT-23-5",
        datasheet_url="https://www.ti.com/lit/ds/symlink/tlv757p.pdf",
        description="3.3V 1A LDO SOT-23-5 (VCCO 3.3V bank supply, default)",
        stock_at_lcsc=65_240,
        unit_price_usd=0.27,
    ),
    BOMPart(
        token="loadsw_TPS2051C",
        value="TPS2051CDBVR",
        footprint="Package_TO_SOT_SMD:SOT-23-5",
        lcsc="C129581",
        mpn="TPS2051CDBVR",
        manufacturer="Texas Instruments",
        package="SOT-23-5",
        datasheet_url="https://www.ti.com/lit/ds/symlink/tps2051c.pdf",
        description="USB load switch 0.5A current-limit, fault flag, SOT-23-5",
        stock_at_lcsc=5_460,
        unit_price_usd=0.13,
    ),
)


# ---------------------------------------------------------------------------
# USB / interface ICs
# ---------------------------------------------------------------------------

USB_ICS: tuple[BOMPart, ...] = (
    BOMPart(
        token="usbc_pd_FUSB302BMPX",
        value="FUSB302BMPX",
        footprint="Package_DFN_QFN:WQFN-14-1EP_2.5x2.5mm_P0.5mm_EP1.45x1.45mm",
        lcsc="C442699",
        mpn="FUSB302BMPX",
        manufacturer="onsemi",
        package="WQFN-14",
        datasheet_url="https://www.onsemi.com/pdf/datasheet/fusb302b-d.pdf",
        description="USB Type-C PD controller, I2C, WQFN-14 (2.5x2.5mm)",
        stock_at_lcsc=5_262,
        unit_price_usd=0.81,
    ),
    BOMPart(
        token="usbuart_CP2102N",
        value="CP2102N-A02-GQFN24R",
        footprint="Package_DFN_QFN:QFN-24-1EP_4x4mm_P0.5mm_EP2.6x2.6mm",
        lcsc="C969151",
        mpn="CP2102N-A02-GQFN24R",
        manufacturer="Silicon Labs",
        package="QFN-24",
        datasheet_url="https://www.silabs.com/documents/public/data-sheets/cp2102n-datasheet.pdf",
        description="USB-to-UART bridge, internal oscillator, QFN-24",
        stock_at_lcsc=11_648,
        unit_price_usd=1.89,
    ),
)


# ---------------------------------------------------------------------------
# Video / display ICs
# ---------------------------------------------------------------------------

VIDEO_ICS: tuple[BOMPart, ...] = (
    BOMPart(
        token="hdmi_companion_TPD12S016",
        value="TPD12S016PWR",
        footprint="Package_SO:TSSOP-24_4.4x7.8mm_P0.65mm",
        lcsc="C201665",
        mpn="TPD12S016PWR",
        manufacturer="Texas Instruments",
        package="TSSOP-24",
        datasheet_url="https://www.ti.com/lit/ds/symlink/tpd12s016.pdf",
        description="HDMI companion: I2C level shifter, 12-ch ESD, 5V load switch",
        stock_at_lcsc=900,
        unit_price_usd=0.83,
    ),
)


# ---------------------------------------------------------------------------
# Memory / RTC / monitoring ICs
# ---------------------------------------------------------------------------

MEMORY_ICS: tuple[BOMPart, ...] = (
    BOMPart(
        token="eeprom_24LC256",
        value="24LC256T-I/SN",
        footprint="Package_SO:SOIC-8_3.9x4.9mm_P1.27mm",
        lcsc="C5458",
        mpn="24LC256T-I/SN",
        manufacturer="Microchip",
        package="SOIC-8",
        datasheet_url="https://ww1.microchip.com/downloads/aemDocuments/documents/MPD/ProductDocuments/DataSheets/21203P.pdf",
        description="256 kbit I2C EEPROM (board ID / EDID), SOIC-8",
        stock_at_lcsc=17_726,
        unit_price_usd=0.58,
    ),
    BOMPart(
        token="rtc_DS3231SN",
        value="DS3231SN#",
        footprint="Package_SO:SOIC-16W_7.5x10.3mm_P1.27mm",
        lcsc="C722469",
        mpn="DS3231SN#",
        manufacturer="Analog Devices (Maxim)",
        package="SOIC-16W",
        datasheet_url="https://www.analog.com/media/en/technical-documentation/data-sheets/DS3231.pdf",
        description="Extremely accurate I2C RTC with integrated TCXO and crystal",
        stock_at_lcsc=82,
        unit_price_usd=7.12,
        allow_low_stock=True,
        alt_digikey="DS3231SN#-ND",
    ),
    BOMPart(
        token="powermon_INA226",
        value="INA226AIDGSR",
        footprint="Package_SO:VSSOP-10_3x3mm_P0.5mm",
        lcsc="C49851",
        mpn="INA226AIDGSR",
        manufacturer="Texas Instruments",
        package="VSSOP-10",
        datasheet_url="https://www.ti.com/lit/ds/symlink/ina226.pdf",
        description="Bidirectional I2C current/power monitor, 36V common-mode",
        stock_at_lcsc=5_462,
        unit_price_usd=0.70,
    ),
)


# ---------------------------------------------------------------------------
# Connectors
# ---------------------------------------------------------------------------

CONNECTORS: tuple[BOMPart, ...] = (
    BOMPart(
        token="conn_USB_C_16P",
        value="USB-C_16P",
        footprint="Connector_USB:USB_C_Receptacle_HRO_TYPE-C-31-M-12",
        lcsc="C165948",
        mpn="TYPE-C-31-M-12",
        manufacturer="Korean Hroparts Elec",
        package="USB-C SMD",
        datasheet_url="https://datasheet.lcsc.com/lcsc/2304140030_Korean-Hroparts-Elec-TYPE-C-31-M-12_C165948.pdf",
        description="USB Type-C 16-pin SMD receptacle, USB 2.0 + power",
        stock_at_lcsc=263_165,
        unit_price_usd=0.17,
    ),
    BOMPart(
        token="conn_RJ45_bare_shielded",
        value="RJHSE5380",
        footprint="Connector_RJ:RJ45_Amphenol_RJHSE5380_Horizontal",
        lcsc="C464586",
        mpn="RJHSE5380",
        manufacturer="Amphenol",
        package="RJ45 TH right-angle",
        datasheet_url="https://www.amphenol-cs.com/product-series/rjhse5380.html",
        description="RJ45 8P8C bare shielded jack, integrated LEDs (no magnetics)",
        stock_at_lcsc=1_283,
        unit_price_usd=0.98,
    ),
    BOMPart(
        token="magnetics_HX5008NLT",
        value="HX5008NLT",
        footprint="Package_SO:SOIC-24W_7.5x15.4mm_P1.27mm",
        lcsc="C962544",
        mpn="HX5008NLT",
        manufacturer="Pulse",
        package="SOIC-24-15.1mm",
        datasheet_url="https://productfinder.pulseeng.com/files/datasheets/HX5008NL.pdf",
        description="1000BASE-T 4-port LAN magnetics module, SOIC-24",
        stock_at_lcsc=2_328,
        unit_price_usd=1.78,
    ),
    BOMPart(
        token="conn_HDMI_A",
        value="HDMI-019S",
        footprint="Connector_HDMI:HDMI_A_SOFNG_HDMI-019S",
        lcsc="C111617",
        mpn="HDMI-019S",
        manufacturer="SOFNG",
        package="HDMI Type-A SMD",
        datasheet_url="https://datasheet.lcsc.com/lcsc/SOFNG-HDMI-019S_C111617.pdf",
        description="HDMI Type-A receptacle 19-pin SMD right-angle",
        stock_at_lcsc=10_535,
        unit_price_usd=0.21,
    ),
    BOMPart(
        token="conn_FFC_40P_0.5mm",
        value="FPC-05F-40PH20",
        footprint="Connector_FFC-FPC:XUNPU_FPC-05F-40PH20",
        lcsc="C2856812",
        mpn="FPC-05F-40PH20",
        manufacturer="XUNPU",
        package="FFC 0.5mm 40P",
        datasheet_url="https://datasheet.lcsc.com/lcsc/XUNPU-FPC-05F-40PH20_C2856812.pdf",
        description="40-pin 0.5mm-pitch FFC bottom-contact (LVDS LCD)",
        stock_at_lcsc=26_530,
        unit_price_usd=0.18,
    ),
    BOMPart(
        token="conn_FFC_15P_1mm",
        value="1.0-15P",
        footprint="Connector_FFC-FPC:BOOMELE_1.0-15P",
        lcsc="C66660",
        mpn="1.0-15P",
        manufacturer="BOOMELE",
        package="FFC 1.0mm 15P",
        datasheet_url="https://datasheet.lcsc.com/lcsc/BOOMELE-1-0-15P_C66660.pdf",
        description="15-pin 1.0mm-pitch FFC bottom-contact (Raspberry Pi camera/CSI-2)",
        stock_at_lcsc=3_375,
        unit_price_usd=0.08,
    ),
    BOMPart(
        token="conn_microSD_DM3AT",
        value="DM3AT-SF-PEJM5",
        footprint="Connector_Card:microSD_HiroseDM3AT-SF-PEJM5_Push-Push",
        lcsc="C114218",
        mpn="DM3AT-SF-PEJM5",
        manufacturer="Hirose",
        package="microSD push-push SMD",
        datasheet_url="https://www.hirose.com/en/product/document?clcode=CL0540-1284-2-51&productname=DM3AT-SF-PEJM5(51)&series=DM3",
        description="microSD push-push socket with card-detect switch",
        stock_at_lcsc=18_973,
        unit_price_usd=1.46,
    ),
    BOMPart(
        token="conn_FMC_FX10A_168P",
        value="FX10A-168P-SV(91)",
        footprint="Connector_Hirose:FX10A-168P-SV_91",
        lcsc="C6624664",
        mpn="FX10A-168P-SV(91)",
        manufacturer="Hirose",
        package="168-pin 0.5mm",
        datasheet_url="https://www.hirose.com/en/product/document?clcode=CL0681-2024-7-91&productname=FX10A-168P-SV(91)&series=FX10A",
        description="168-pin 0.5mm-pitch board-to-board (FMC-LPC compatible alternative)",
        stock_at_lcsc=416,
        unit_price_usd=3.53,
    ),
    BOMPart(
        token="conn_PMOD_2x6_RA",
        value="PinHeader_2x06_P2.54mm",
        footprint="Connector_PinHeader_2.54mm:PinHeader_2x06_P2.54mm_Vertical",
        lcsc="C53026548",
        mpn="PM254R-12-08-H85",
        manufacturer="XFCN",
        package="2x6 2.54mm",
        datasheet_url="https://datasheet.lcsc.com/lcsc/XFCN-PM254R-12-08-H85_C53026548.pdf",
        description="2x6 0.1in pin header right-angle (Digilent PMOD)",
        stock_at_lcsc=780,
        unit_price_usd=0.09,
    ),
    BOMPart(
        token="conn_JTAG_2x7_THT",
        value="PinHeader_2x07_P2.54mm",
        footprint="Connector_PinHeader_2.54mm:PinHeader_2x07_P2.54mm_Vertical",
        lcsc="C7499342",
        mpn="ZX-PM2.54-2-7PY",
        manufacturer="Megastar",
        package="2x7 2.54mm",
        datasheet_url="https://datasheet.lcsc.com/lcsc/Megastar-ZX-PM2-54-2-7PY_C7499342.pdf",
        description="2x7 0.1in pin header (Xilinx JTAG header)",
        stock_at_lcsc=725,
        unit_price_usd=0.17,
    ),
    BOMPart(
        token="conn_SWD_2x5_1.27mm",
        value="PinHeader_2x05_P1.27mm",
        footprint="Connector_PinHeader_1.27mm:PinHeader_2x05_P1.27mm_Vertical_SMD",
        lcsc="C41376037",
        mpn="HX PZ1.27-2x5P TP",
        manufacturer="hanxia",
        package="2x5 1.27mm SMD",
        datasheet_url="https://datasheet.lcsc.com/lcsc/hanxia-HX-PZ1-27-2x5P-TP_C41376037.pdf",
        description="2x5 1.27mm-pitch SMD pin header (ARM Cortex Debug 10-pin)",
        stock_at_lcsc=11_040,
        unit_price_usd=0.08,
    ),
    BOMPart(
        token="conn_SMA_RA_TH",
        value="SMA-K_RA_TH",
        footprint="Connector_Coaxial:SMA_Kinghelm_KH-SMA-P-8496",
        lcsc="C910123",
        mpn="KH-SMA-P-8496",
        manufacturer="kinghelm",
        package="SMA TH right-angle",
        datasheet_url="https://datasheet.lcsc.com/lcsc/kinghelm-KH-SMA-P-8496_C910123.pdf",
        description="SMA female jack 50 ohm right-angle through-hole (XADC / clock SMA)",
        stock_at_lcsc=2_715,
        unit_price_usd=0.74,
    ),
)


# ---------------------------------------------------------------------------
# Switches / buttons / battery
# ---------------------------------------------------------------------------

SWITCHES: tuple[BOMPart, ...] = (
    BOMPart(
        token="sw_tactile_6x6",
        value="TS-1002S-06026C",
        footprint="Switch_SMD:SW_SPST_TL3342",
        lcsc="C455112",
        mpn="TS-1002S-06026C",
        manufacturer="XUNPU",
        package="6x6 SMD tactile",
        datasheet_url="https://datasheet.lcsc.com/lcsc/XUNPU-TS-1002S-06026C_C455112.pdf",
        description="Tactile switch 6x6mm SMD momentary SPST",
        stock_at_lcsc=18_240,
        unit_price_usd=0.06,
    ),
    BOMPart(
        token="sw_dip_4pos_1.27mm",
        value="DS-04P",
        footprint="Switch_SMD:SW_DIP_SPSTx04_Slide_Compact_W6.7mm_P1.27mm_LowProfile",
        lcsc="C18198092",
        mpn="DS-04P",
        manufacturer="Hanbo Electronic",
        package="DIP-4 SMD 1.27mm",
        datasheet_url="https://datasheet.lcsc.com/lcsc/Hanbo-Electronic-DS-04P_C18198092.pdf",
        description="4-position SMD DIP switch SPST 1.27mm pitch (boot/config straps)",
        stock_at_lcsc=1_582,
        unit_price_usd=0.52,
    ),
    BOMPart(
        token="batt_CR2032_holder",
        value="CR2032-BS-6-1",
        footprint="Battery:BatteryHolder_Keystone_3000_1xCR2032",
        lcsc="C70377",
        mpn="CR2032-BS-6-1",
        manufacturer="QIJEY",
        package="CR2032 SMD",
        datasheet_url="https://datasheet.lcsc.com/lcsc/QIJEY-CR2032-BS-6-1_C70377.pdf",
        description="CR2032 coin cell holder SMD (RTC backup)",
        stock_at_lcsc=15_935,
        unit_price_usd=0.14,
    ),
)


# ---------------------------------------------------------------------------
# Master registry (flattened)
# ---------------------------------------------------------------------------

REGISTRY_LIST: tuple[BOMPart, ...] = (
    *CAPS,
    *RESISTORS,
    *INDUCTORS,
    *LEDS,
    *DIODES,
    *POWER_ICS,
    *USB_ICS,
    *VIDEO_ICS,
    *MEMORY_ICS,
    *CONNECTORS,
    *SWITCHES,
)


def _build_registry() -> dict[str, BOMPart]:
    by_token: dict[str, BOMPart] = {}
    for part in REGISTRY_LIST:
        if part.token in by_token:
            raise RuntimeError(
                f"Duplicate part token {part.token!r} in registry "
                f"(LCSC {by_token[part.token].lcsc} and {part.lcsc})"
            )
        by_token[part.token] = part
    return by_token


REGISTRY: dict[str, BOMPart] = _build_registry()


def get_part(token: str) -> BOMPart:
    """Look up a part by token; raises KeyError with helpful message."""
    try:
        return REGISTRY[token]
    except KeyError:
        candidates = [t for t in REGISTRY if token.split("_")[0] in t][:5]
        raise KeyError(
            f"Unknown part token {token!r}. Did you mean: {candidates}?"
        ) from None


def all_parts() -> list[BOMPart]:
    return list(REGISTRY.values())
