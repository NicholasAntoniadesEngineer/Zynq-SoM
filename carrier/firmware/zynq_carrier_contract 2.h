/*
 * zynq_carrier_contract.h -- Zynq carrier <-> SoM STM32 system-controller
 * hardware contract.  GENERATED -- DO NOT EDIT.
 *
 * generated-by: schgen firmware (schgen/firmware.py)
 * regenerate:   PYTHONPATH=. python -m schgen firmware
 * sources:
 *   carrier/som_interface.json
 *   som/Zynq_SoM.kicad_sch (U9 pin map, live kicad-cli extraction)
 *   carrier/subsystems/power/power.py
 *   carrier/subsystems/power_mon/power_mon.py
 *   carrier/subsystems/bringup_rails/bringup_rails.py
 *   carrier/subsystems/bringup_en/bringup_en.py
 *   carrier/subsystems/bringup_en_modules/bringup_en_modules.py
 *   carrier/subsystems/bringup_modules/bringup_modules.py
 *   carrier/subsystems/debug_boot/debug_boot.py
 *   carrier/subsystems/board_aux/board_aux.py
 *   carrier/subsystems/board_services/board_services.py
 *   carrier/research/debug_boot_pmod.md (BOOTSEL decode, SWD reservation)
 *   carrier/research/power_mon.md (I2C address map)
 *   carrier/research/bringup_power_gating.md (EN-cell semantics, GPIO plan)
 *
 * system controller: SoM U9 = STM32G431CBUx
 * All GPIO port/pin values are extracted LIVE from the SoM
 * KiCad netlist at generation time -- they cannot drift from
 * the hardware.
 */
#ifndef ZYNQ_CARRIER_CONTRACT_H
#define ZYNQ_CARRIER_CONTRACT_H

/* ======================================================================== */
/* !! RESERVED FOR SWD -- debug_boot dossier section 0, firmware contract: */
/* !!   STM32_GPIO5 (J1.53) = PA14 = SWCLK */
/* !!   STM32_GPIO6 (J1.45) = PA13 = SWDIO */
/* !! SC firmware must NEVER reconfigure PA13/PA14 -- they are the SC's */
/* !! own SWD port (carrier SWD header, debug_boot J2). */
/* !! Reconfiguring them bricks debug until BOOT0-DFU recovery. */
/* ======================================================================== */

/* ---- STM32-facing nets on the SoM mezzanine connectors ---------------- */
/* net <- J pin (carrier/som_interface.json) <- STM32 GPIO (live U9 map) */
/* STM32_BOOT0 */
#define ZC_STM32_BOOT0_J1_PIN 57
#define ZC_STM32_BOOT0_GPIO_PORT 'B'
#define ZC_STM32_BOOT0_GPIO_PIN 8U
/* STM32_DAC1 */
#define ZC_STM32_DAC1_J1_PIN 49
#define ZC_STM32_DAC1_GPIO_PORT 'A'
#define ZC_STM32_DAC1_GPIO_PIN 4U
/* STM32_DAC2 */
#define ZC_STM32_DAC2_J1_PIN 55
#define ZC_STM32_DAC2_GPIO_PORT 'A'
#define ZC_STM32_DAC2_GPIO_PIN 5U
/* STM32_GPIO1 -- rail-EN override veto -> STM32_RAIL_EN_5V0 */
#define ZC_STM32_GPIO1_J1_PIN 33
#define ZC_STM32_GPIO1_GPIO_PORT 'C'
#define ZC_STM32_GPIO1_GPIO_PIN 11U
/* STM32_GPIO2 -- rail-EN override veto -> STM32_RAIL_EN_3V3 */
#define ZC_STM32_GPIO2_J1_PIN 35
#define ZC_STM32_GPIO2_GPIO_PORT 'B'
#define ZC_STM32_GPIO2_GPIO_PIN 5U
/* STM32_GPIO3 -- rail-EN override veto -> STM32_RAIL_EN_1V8 */
#define ZC_STM32_GPIO3_J1_PIN 43
#define ZC_STM32_GPIO3_GPIO_PORT 'C'
#define ZC_STM32_GPIO3_GPIO_PIN 10U
/* STM32_GPIO4 -- TCA9535 INT# (open-drain, 10k to +3V3_SC) */
#define ZC_STM32_GPIO4_J1_PIN 41
#define ZC_STM32_GPIO4_GPIO_PORT 'A'
#define ZC_STM32_GPIO4_GPIO_PIN 15U
/* STM32_GPIO5 -- RESERVED: SWCLK (see above) */
#define ZC_STM32_GPIO5_J1_PIN 53
#define ZC_STM32_GPIO5_GPIO_PORT 'A'
#define ZC_STM32_GPIO5_GPIO_PIN 14U
/* STM32_GPIO6 -- RESERVED: SWDIO (see above) */
#define ZC_STM32_GPIO6_J1_PIN 45
#define ZC_STM32_GPIO6_GPIO_PORT 'A'
#define ZC_STM32_GPIO6_GPIO_PIN 13U
/* STM32_GPIO7 -- BOOTSEL0 request strap (debug_boot SW1 pos 2) */
#define ZC_STM32_GPIO7_J1_PIN 59
#define ZC_STM32_GPIO7_GPIO_PORT 'B'
#define ZC_STM32_GPIO7_GPIO_PIN 10U
/* STM32_GPIO8 -- BOOTSEL1 request strap (debug_boot SW1 pos 3) */
#define ZC_STM32_GPIO8_J1_PIN 54
#define ZC_STM32_GPIO8_GPIO_PORT 'B'
#define ZC_STM32_GPIO8_GPIO_PIN 11U
/* STM32_NRST */
#define ZC_STM32_NRST_J1_PIN 47
#define ZC_STM32_NRST_GPIO_PORT 'G'
#define ZC_STM32_NRST_GPIO_PIN 10U
/* STM32_USB_CC1 */
#define ZC_STM32_USB_CC1_J1_PIN 29
#define ZC_STM32_USB_CC1_GPIO_PORT 'B'
#define ZC_STM32_USB_CC1_GPIO_PIN 6U
/* STM32_USB_CC2 */
#define ZC_STM32_USB_CC2_J1_PIN 31
#define ZC_STM32_USB_CC2_GPIO_PORT 'B'
#define ZC_STM32_USB_CC2_GPIO_PIN 4U
/* STM32_USB_D_N */
#define ZC_STM32_USB_D_N_J1_PIN 21
#define ZC_STM32_USB_D_N_GPIO_PORT 'A'
#define ZC_STM32_USB_D_N_GPIO_PIN 11U
/* STM32_USB_D_P */
#define ZC_STM32_USB_D_P_J1_PIN 19
#define ZC_STM32_USB_D_P_GPIO_PORT 'A'
#define ZC_STM32_USB_D_P_GPIO_PIN 12U

/* ---- STM32-driven SoM-INTERNAL control nets (not on J1/J2/J3) -------- */
/* The SC drives Zynq boot mode / resets ON-MODULE; the carrier only */
/* requests via the BOOTSEL straps below (debug_boot dossier section 0). */
/* ZYNQ_BMODE_0 -- SoM-internal */
#define ZC_SOM_ZYNQ_BMODE_0_GPIO_PORT 'B'
#define ZC_SOM_ZYNQ_BMODE_0_GPIO_PIN 2U
/* ZYNQ_BMODE_2 -- SoM-internal */
#define ZC_SOM_ZYNQ_BMODE_2_GPIO_PORT 'A'
#define ZC_SOM_ZYNQ_BMODE_2_GPIO_PIN 7U
/* ZYNQ_PL_PROGB -- SoM-internal */
#define ZC_SOM_ZYNQ_PL_PROGB_GPIO_PORT 'A'
#define ZC_SOM_ZYNQ_PL_PROGB_GPIO_PIN 6U
/* ZYNQ_PS_MIO13 -- SoM-internal */
#define ZC_SOM_ZYNQ_PS_MIO13_GPIO_PORT 'B'
#define ZC_SOM_ZYNQ_PS_MIO13_GPIO_PIN 14U
/* ZYNQ_PS_POR -- SoM-internal */
#define ZC_SOM_ZYNQ_PS_POR_GPIO_PORT 'B'
#define ZC_SOM_ZYNQ_PS_POR_GPIO_PIN 12U
/* ZYNQ_PS_SRST -- SoM-internal */
#define ZC_SOM_ZYNQ_PS_SRST_GPIO_PORT 'B'
#define ZC_SOM_ZYNQ_PS_SRST_GPIO_PIN 13U

/* ---- BOOTSEL decode (debug_boot dossier section (c)) ---------------- */
/* Carrier boot-request DIP (debug_boot SW1): pos 2 -> BOOTSEL0, pos 3 -> */
/* BOOTSEL1; closed = LOW, open = HIGH (10k pull-ups to +3V3_SC).        */
/* SC firmware samples BOOTSEL[1:0] at boot and drives ZYNQ_BMODE_0/2    */
/* on-module (constants above).  value = (BOOTSEL1 << 1) | BOOTSEL0      */
#define ZC_BOOTSEL0_GPIO_PORT 'B'   /* STM32_GPIO7, J1.59 */
#define ZC_BOOTSEL0_GPIO_PIN 10U
#define ZC_BOOTSEL1_GPIO_PORT 'B'   /* STM32_GPIO8, J1.54 */
#define ZC_BOOTSEL1_GPIO_PIN 11U
#define ZC_BOOT_REQ_JTAG 0x0
#define ZC_BOOT_REQ_QSPI 0x1
#define ZC_BOOT_REQ_SD 0x2
#define ZC_BOOT_REQ_RESERVED 0x3
/* STM32_BOOT0 (debug_boot SW1 pos 1): closed pulls BOOT0 high through */
/* 100R against the SoM 1k5 pull-down -> closed + reset = USB DFU.      */

/* ---- I2C address map -- bus STM32_I2C2, 7-bit addresses -------------- */
/* (power_mon dossier section 2; strapped addresses derived from the    */
/*  netlists at generation time)                                        */
#define ZC_I2C_ADDR_TCA9535 0x20  /* bring-up override expander (bringup_rails; A2=A1=A0 straps read from the netlist) */
#define ZC_I2C_ADDR_FUSB302B 0x22  /* USB-PD PHY (usb_pd; fixed address, onsemi DS) */
#define ZC_I2C_ADDR_INA3221_1 0x40  /* rail monitor #1 (power_mon U1; A0 strap read from the netlist) */
#define ZC_I2C_ADDR_INA3221_2 0x41  /* rail monitor #2 (power_mon U2; A0 strap read from the netlist) */
#define ZC_I2C_ADDR_ID_EEPROM 0x51  /* board-ID EEPROM w/ EUI-48 MAC (board_services 24AA025E48; A1/A0 straps read from the netlist; on the board_aux-isolated AUX I2C) */
#define ZC_I2C_ADDR_RTC 0x52  /* RTC (board_services RV-3028; fixed address, Micro Crystal DS; on the board_aux-isolated AUX I2C). VBACKUP is a RECHARGEABLE ML1220 (Mn-Li) for a maintenance-free RTC: firmware SHOULD ENABLE the RV-3028 trickle charger (set TCE + a series resistance, e.g. 3k, in the EEPROM Backup register) so it tops up whenever the board is powered. Do NOT fit a primary CR1220 (it would be charged) or a LIR Li-ion (its 4.2 V target exceeds the 3.3 V supply). */
/* G3: STM32_I2C2 is a firmware BIT-BANG on the DAC pins (PA4/PA5, no   */
/* I2C AF; real I2C2 PA8/PA9 is the on-module SC<->Zynq link) -- ~100 kHz */
#define ZC_I2C_BITBANG_SDA_GPIO_PORT 'A'   /* STM32_I2C2_SDA = STM32_DAC1, J1.49 */
#define ZC_I2C_BITBANG_SDA_GPIO_PIN 4U
#define ZC_I2C_BITBANG_SCL_GPIO_PORT 'A'   /* STM32_I2C2_SCL = STM32_DAC2, J1.55 */
#define ZC_I2C_BITBANG_SCL_GPIO_PIN 5U

/* ---- Rail bring-up sequence (derived from the power.py regulator     */
/*      chain: each stage feeds the next) + EN-cell mapping             */
/* EN semantics (bringup_en): EN = DIP AND override; override is a VETO  */
/* -- drive LOW to force a rail OFF; Hi-Z/HIGH leaves the DIP in charge. */
/* Software can NEVER force a rail ON with its DIP open.                */
#define ZC_RAIL_COUNT 3
/* stage 0: +VIN -> +5V (LM61460AANRJRR U1, power sheet; DIP SW1 pos 1; PG LED D1) */
#define ZC_RAIL0_NAME "+5V"
#define ZC_RAIL0_VOUT_MV 5020
#define ZC_RAIL0_EN_NET "EN_5V0"
#define ZC_RAIL0_OVERRIDE_GPIO_PORT 'C'   /* STM32_RAIL_EN_5V0 -> STM32_GPIO1 */
#define ZC_RAIL0_OVERRIDE_GPIO_PIN 11U
/* stage 1: +5V -> +3V3 (LM61460AANRJRR U2, power sheet; DIP SW1 pos 2; PG LED D2) */
#define ZC_RAIL1_NAME "+3V3"
#define ZC_RAIL1_VOUT_MV 3320
#define ZC_RAIL1_EN_NET "EN_3V3"
#define ZC_RAIL1_OVERRIDE_GPIO_PORT 'B'   /* STM32_RAIL_EN_3V3 -> STM32_GPIO2 */
#define ZC_RAIL1_OVERRIDE_GPIO_PIN 5U
/* stage 2: +3V3 -> +1V8 (AP2112K-1.8 U3, power sheet; DIP SW1 pos 3; PG LED D3) */
#define ZC_RAIL2_NAME "+1V8"
#define ZC_RAIL2_VOUT_MV 1800
#define ZC_RAIL2_EN_NET "EN_1V8"
#define ZC_RAIL2_OVERRIDE_GPIO_PORT 'C'   /* STM32_RAIL_EN_1V8 -> STM32_GPIO3 */
#define ZC_RAIL2_OVERRIDE_GPIO_PIN 10U
#define ZC_BRINGUP_INT_GPIO_PORT 'A'   /* SC_INT_N (TCA9535 INT# wire-OR FUSB302 INT) -> STM32_GPIO4 */
#define ZC_BRINGUP_INT_GPIO_PIN 15U

/* ---- TCA9535 module-override port map -- READ from the bringup_rails  */
/*      netlist (P0x/P1x pin -> net), joined to its EN cell + load      */
/*      switch.  Bit index = position in the 16-bit port word           */
/*      (P00=bit0 ... P17=bit15).  POR state = all inputs => DIP rules. */
#define ZC_TCA9535_BIT_EN_HDMI_TX 0  /* P00: BU_OVR_HDMI_TX -> EN_HDMI_TX (+3V3_HDMI_TX, ILIM 523 mA, DIP SW2 pos 8) */
#define ZC_TCA9535_BIT_EN_HDMI_RX 1  /* P01: BU_OVR_HDMI_RX -> EN_HDMI_RX (+3V3_HDMI_RX, ILIM 523 mA, DIP SW2 pos 7) */
#define ZC_TCA9535_BIT_EN_LCD 2  /* P02: BU_OVR_LCD -> EN_LCD (+3V3_LCD, ILIM 1000 mA, DIP SW2 pos 6) */
#define ZC_TCA9535_BIT_EN_CAM 3  /* P03: BU_OVR_CAM -> EN_CAM (+3V3_CAM, ILIM 523 mA, DIP SW2 pos 5) */
#define ZC_TCA9535_BIT_EN_SD 4  /* P04: BU_OVR_SD -> EN_SD (+3V3_SD, ILIM 1000 mA, DIP SW2 pos 4) */
#define ZC_TCA9535_BIT_EN_USB 5  /* P05: BU_OVR_USB -> EN_USB (+5V_USB, ILIM 1000 mA, DIP SW2 pos 3) */
#define ZC_TCA9535_BIT_EN_PMOD 6  /* P06: BU_OVR_PMOD -> EN_PMOD (+3V3_PMOD, ILIM 523 mA, DIP SW2 pos 2) */
#define ZC_TCA9535_BIT_EN_USER_LED 7  /* P07: BU_OVR_USER_LED -> EN_USER_LED (+3V3_USER_LED, ILIM 523 mA, DIP SW1 pos 4) */
#define ZC_TCA9535_BIT_EN_LCD_BL 8  /* P10: BU_OVR_LCD_BL -> EN_LCD_BL (DIP SW2 pos 1) */
/* P11 (bit 9): PMON_ALERT_N -- INPUT: INA3221 CRITICAL wire-OR (power_mon, 10k PU +3V3_SC) */
#define ZC_TCA9535_BIT_EN_HDMI_TX_5V 10  /* P12: BU_OVR_HDMI_TX_5V -> EN_HDMI_TX_5V (+5V_HDMI_TX, ILIM 523 mA, DIP SW6 pos 1) */
#define ZC_TCA9535_BIT_EN_LCD_5V 11  /* P13: BU_OVR_LCD_5V -> EN_LCD_5V (+5V_LCD, ILIM 1000 mA, DIP SW6 pos 2) */
/* P14 (bit 12): USBOTG_FLT_N -- INPUT: TPS2051C fault (usbc_otg, 100k PU re-railed +3V3_SC) */
/* P15 (bit 13): PD_FLT_N -- INPUT: TPS26631 +VIN eFuse fault (pd_input, 100k PU +3V3_SC) */
/* P16 (bit 14): BU_P16 -- spare, 100k to GND */
/* P17 (bit 15): BU_P17 -- spare, 100k to GND */

/* ---- INA3221 rail-telemetry channel map (power_mon netlist) --------- */
/* monitor #1: U1 @ 0x40 */
#define ZC_PMON1_CH1_RAIL "+VIN_SYS"  /* +VIN -> +VIN_SYS */
#define ZC_PMON1_CH1_SHUNT_MOHM 10
#define ZC_PMON1_CH2_RAIL "+5V"  /* +5V_REG -> +5V */
#define ZC_PMON1_CH2_SHUNT_MOHM 10
#define ZC_PMON1_CH3_RAIL "+3V3"  /* +3V3_REG -> +3V3 */
#define ZC_PMON1_CH3_SHUNT_MOHM 10
/* monitor #2: U2 @ 0x41 */
#define ZC_PMON2_CH1_RAIL "+1V8"  /* +1V8_REG -> +1V8 */
#define ZC_PMON2_CH1_SHUNT_MOHM 20
/* U2 ch2: unused (inputs tied to GND per TI DS) */
/* U2 ch3: unused (inputs tied to GND per TI DS) */

#endif /* ZYNQ_CARRIER_CONTRACT_H */
