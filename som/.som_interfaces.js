export const meta = {
  name: 'som-interface-wiring-audit',
  description: 'Adversarial interface-by-interface wiring verification of the Zynq-7020 and every peripheral bus (DDR/QSPI/eMMC/RGMII/ULPI/SPI/I2C/config/JTAG/clocks), pin+bit-order+direction+protocol level',
  phases: [
    { title: 'Interfaces', detail: 'one deep agent per chip<->peripheral interface' },
    { title: 'GapFill',    detail: 'completeness critic -> targeted round 2' },
    { title: 'Crossfire',  detail: '3-lens adversarial panel (default refute)' },
    { title: 'Synthesize', detail: 'per-interface verdict + ranked findings' },
  ],
}

const ROOT='/Users/nicholasantoniades/Documents/GitHub/Zynq-SoM', SOM=ROOT+'/som'
const NETS='/tmp/som_nets.txt', COMPS='/tmp/som_components.txt', RAW='/tmp/som_netlist.net'
const UG585='/tmp/ug585.txt', AUDIT=SOM+'/SOM_ELECTRICAL_AUDIT.md'

const BASE=`You are a super-intelligent, adversarial SoC interface verification engineer auditing the WIRING of a Xilinx Zynq-7020 (XC7Z020-CLG484, U2) System-on-Module and every peripheral it connects to. Your single goal: prove, interface by interface, that every bus between the Zynq and its peripherals is wired CORRECTLY end-to-end — or find where it is not. You think at the protocol/bit level, not just pin-presence.

THE CHIP + PERIPHERALS:
- U2 Zynq-7020 (PS + PL).  U1 DDR3L MT41K256M16 (PS DDR).  U7 ISSI IS21ES08G eMMC (PS SDIO).  U11 W25Q128 QSPI flash (PS QSPI boot).
- U3 RTL8211F GbE PHY (PS RGMII + MDIO).  U5 USB3318 ULPI PHY (PS USB).  U14 BMI323 IMU (PL SPI/I2C).  U9 STM32G431 system controller (I2C + config + boot straps + JTAG/reset).
- Clocks X1 13MHz->USB3318, X2 25MHz->RTL8211F, X3 33MHz->Zynq PS_CLK. Regulators U4/U6/U8/U10/U13.

GROUND TRUTH (read/grep — the netlist is sacred):
- ${NETS} : every net -> "NET name (n)" then "  REF.PIN [pinfunction]  <value>".  ${COMPS} : ref/value/footprint/LCSC/sheet.  ${RAW} : raw netlist (full pinfunctions/footprints).
- ${UG585} : Zynq-7000 TRM text — grep for MIO mux tables, peripheral pin options, bank rules, boot. THE authority for which Zynq pin can carry which peripheral signal.
- ${AUDIT} : prior consolidated audit. Datasheets via WebSearch/WebFetch (ToolSearch "select:WebSearch,WebFetch") or ${ROOT}/parts/<MPN>/.

ALREADY-CONFIRMED DEFECTS — do NOT re-report; verify everything ELSE on these interfaces and build BEYOND:
- DDR: VRP/VRN swapped (R46/R47); DRAM data on Zynq UPPER byte lanes DQ[31:16] (should be DQ[15:0]). [2 CRITICAL]
- RTL8211F EXT_CLK driven at 1.8Vpp (needs 3.15-3.45Vpp). eMMC U7 LCSC!=MPN. SoM VIN on only 14 DF40 contacts.

HOW TO VERIFY AN INTERFACE (be exhaustive + adversarial):
1. Enumerate EVERY signal of the bus from both datasheets. For each: find its net, confirm the RIGHT pin on the Zynq end (grep ${UG585} for the MIO/pin option or PL pin) AND the right pin on the peripheral end.
2. Hunt the silent wiring faults a pin-presence check misses: BIT-ORDER (DATA[7:0]/IO[3:0]/DQ swapped within a bus — quad-SPI IO2/IO3=WP/HOLD order, ULPI DATA order, RGMII RXD/TXD nibble order), DIRECTION (a PHY-output tied where an input is expected, ULPI CLK source side, RGMII RXC/TXC), MISSING signals (a bus member not connected), WRONG MIO (a peripheral on a MIO the BootROM/PS mux cannot route), PULL/TERMINATION (open-drain without pull, CS without pull, SPI mode pins, I2C addr-select + pull-ups + address collisions), CLOCK to a non-clock-capable pin, RESET/IRQ polarity & domain.
3. For protocols: SPI (mode, CS polarity, MISO/MOSI not swapped), I2C (every device address distinct, SDA/SCL pulls, voltage domain), QSPI (IO order + boot mode), SDIO (bus width + pull-ups), RGMII (TXD/RXD/CTL/clk + delay strategy), ULPI (8b data + DIR/STP/NXT + 60MHz clock direction).
4. Quote the datasheet/UG585 rule for each expectation. A "wrong-pin/swap" claim must show the correct pin per the source. Set confidence honestly; few hard findings beat many weak.
Report ONLY via the schema (is_new=true for a genuine wiring defect beyond the known list).`

const FIND={type:'object',additionalProperties:false,required:['interface','findings','coverage'],properties:{
  interface:{type:'string'},
  coverage:{type:'string',description:'list every signal of the bus you traced and its verdict (correct/suspect)'},
  findings:{type:'array',items:{type:'object',additionalProperties:false,
    required:['severity','category','title','components','nets','observation','expected','impact','recommendation','confidence','is_new'],
    properties:{severity:{type:'string',enum:['CRITICAL','HIGH','MEDIUM','LOW','INFO']},category:{type:'string'},title:{type:'string'},
      components:{type:'array',items:{type:'string'}},nets:{type:'array',items:{type:'string'}},
      observation:{type:'string'},expected:{type:'string'},impact:{type:'string'},recommendation:{type:'string'},confidence:{type:'number'},is_new:{type:'boolean'}}}}}}

const IFACES=[
 {k:'ps-ddr-addrcmd', m:'Zynq PS <-> U1 DDR3L: verify the ADDRESS/COMMAND/CONTROL/CLOCK bus completely (A[14:0], BA[2:0], RAS/CAS/WE, CS, CKE, ODT, CK_P/N, RESET/DRST, ZQ, VREF). Every U1 ball -> right Zynq PS_DDR_* ball (grep UG585 Table 10-3 / pin list). Check CK_P/CK_N polarity, address-bit completeness, control-line correctness, ZQ=240R to GND, VREF divider. Do NOT re-report the data-lane or VRP/VRN knowns; verify the rest is correct.'},
 {k:'ps-qspi',  m:'Zynq PS QSPI <-> U11 W25Q128 boot flash: verify QSPI_CLK, ~CS, and IO0/IO1/IO2/IO3 (DI/DO/WP/HOLD) mapping on BOTH ends. CRITICAL bit-order check: W25Q IO0=DI(MOSI), IO1=DO(MISO), IO2=/WP, IO3=/HOLD must land on the matching Zynq QSPI MIO (MIO1=CS,2-5/... per UG585 boot QSPI mux). Confirm the MIO group is a legal QSPI boot group, ~CS/IO pulls, ~WP/~HOLD handling, and that the dual-function boot-strap on QSPI_D[3:0] does not contend. Quad-mode requires IO2/IO3 correct.'},
 {k:'ps-emmc',  m:'Zynq PS SDIO <-> U7 eMMC: verify CLK, CMD, DAT0-3 (4-bit; DAT4-7/DS NC is correct for PS SDIO), ~RST. Each on the right PS SDIO MIO (grep UG585 SDIO MIO options). Pull-ups: CMD + DAT lines (typ 10k to VCCQ=1.8V) present? RST polarity. VCCQ=1.8V vs MIO bank voltage match. Bus-width consistency.'},
 {k:'ps-rgmii', m:'Zynq PS GEM <-> U3 RTL8211F: verify RGMII TXD0-3/TX_CTL/TXC and RXD0-3/RX_CTL/RXC mapping end-to-end (no TX/RX group swap, no nibble bit swap, clocks on clock-capable pins), MDIO/MDC, PHY ~RST, INT. Decode the RGMII internal-delay strategy (PHY RXDLY/TXDLY straps vs Zynq GEM delay) and confirm it is self-consistent (exactly one source of each 2ns delay). Verify MDIO pull-up + PHYAD straps.'},
 {k:'ps-ulpi',  m:'Zynq PS USB <-> U5 USB3318: verify the ULPI bus DATA0-7 (bit order!), DIR, STP, NXT, and CLK (which side sources the 60MHz ULPI clock - confirm output-clock mode and that CLK goes the right direction), plus ~RESET. Each on the right PS USB MIO (grep UG585 USB MIO). DP/DM routing out to connector. RBIAS, REFCLK(13MHz) presence. A swapped ULPI data bit or wrong CLK direction = dead USB.'},
 {k:'pl-bmi323',m:'Zynq PL <-> U14 BMI323 IMU: determine the interface (SPI 4-wire vs I2C) from the wiring, then verify SCLK/SDI(MOSI)/SDO(MISO)/~CS (SPI) or SDA/SCL+addr (I2C) — MISO/MOSI not swapped, CS has the right idle pull, INT1/INT2 to PL pins, the protocol-select/first-transaction requirement. Bank-33 VCCO domain match. Confirm against BMI323 datasheet.'},
 {k:'zynq-stm32',m:'Zynq <-> U9 STM32 control plane: verify the I2C link (Zynq MIO14/15 <-> STM32 PA8/PA9), SDA/SCL pulls + voltage domain + no address collision on that bus; the config handshake PROGRAM_B/INIT_B/DONE/PS_POR_B/PS_SRST_B (correct pins, pulls, open-drain where needed, direction STM32->Zynq); and the boot-mode strap bits the STM32 drives (BOOT_MODE[2]/[0] via which STM32 GPIO) - confirm they can be set valid before POR release. Find any control-line miswire or domain mismatch.'},
 {k:'config-jtag',m:'Zynq config + PS-JTAG interface: verify the boot-mode strap pattern MIO[8:2] decodes to the intended boot device (QSPI), VMODE bits, PUDC_B default, PROG_B/INIT_B/DONE pulls to correct VCCO, and the JTAG TAP (TCK/TMS/TDI/TDO) wiring + pulls + buffer. Confirm config bank VCCO_0 domain. (TCK-pull and PUDC items may be known - verify the REST.)'},
 {k:'clocks-reset',m:'All clock + reset interfaces: X1 13MHz->USB3318 (which pin, REFSEL, level), X2 25MHz->RTL8211F (pin 37 EXT_CLK - amplitude is a known finding; verify the rest), X3 33MHz->Zynq PS_CLK (exact ball, freq, 3V3 domain). Crystal-vs-CMOS-osc handling (load caps only for crystals). Full reset tree: POR/SRST/PHY-RST/USB-RST/eMMC-RST/DDR-RST - source, polarity, pull, sequence order. Find a clock on a wrong/non-clock pin or a reset that never releases.'},
 {k:'pull-term-pwr',m:'Cross-interface pull/termination/power completeness: every open-drain or bidirectional signal (I2C, INT, RESET, MDIO, DONE) has the right pull to the right rail; every series/parallel termination on a fast bus (QSPI/RGMII/clock/DDR) is present and sane; every peripheral IC has all its power pins on the correct rail and decoupled, and its VCCIO domain matches the Zynq bank/MIO voltage it talks to. Find a missing pull, a wrong-rail pull, a level/domain mismatch between a peripheral and its Zynq interface.'},
 {k:'redteam',  m:'ADVERSARIAL RED-TEAM across ALL interfaces: you are paid to find the most damaging wiring mistake the other teams missed - a swapped differential pair, a bus wired to the wrong peripheral, a signal that is an output on both ends (contention), a peripheral select/addr that collides, a wrong-pin that silently disables a function. Be ruthless; one airtight new wiring defect wins.'},
]

phase('Interfaces')
const r1raw=await parallel(IFACES.map(t=>()=>
  agent(`${BASE}\n\n=== INTERFACE UNDER TEST [${t.k}] ===\n${t.m}\n\nTrace every signal; return NEW wiring defects (is_new=true) + a per-signal coverage note.`,
    {label:`iface:${t.k}`,phase:'Interfaces',schema:FIND,effort:'high'})
))
const r1=r1raw.filter(Boolean).flatMap(r=>(r.findings||[]).map(f=>({...f,team:'r1'})))
const coverage=r1raw.filter(Boolean).map(r=>({interface:r.interface,coverage:r.coverage}))
log(`round1 raw findings: ${r1.length}`)

phase('GapFill')
const critic=await agent(`${BASE}\n\n=== COMPLETENESS CRITIC ===\nInterface teams just ran. Identify any interface, bus signal, or wiring-correctness class NOT yet verified (e.g. a peripheral power/VCCIO domain, a strap, a secondary bus, an unused-pin handling, a test/debug interface). Return up to 4 narrow briefs (title=brief, recommendation=why it could hide a wiring defect; severity=INFO, is_new=true).`,
  {label:'critic',phase:'GapFill',schema:FIND,effort:'high'})
const briefs=((critic&&critic.findings)||[]).slice(0,4)
const r2raw=await parallel(briefs.map((b,i)=>()=>
  agent(`${BASE}\n\n=== TARGETED INTERFACE HUNT (round 2 #${i+1}) ===\nExecute exhaustively, report NEW wiring defects only:\n"${b.title}"\nWhy: ${b.recommendation}`,
    {label:`gapfill:${i+1}`,phase:'GapFill',schema:FIND,effort:'high'})
))
const r2=r2raw.filter(Boolean).flatMap(r=>(r.findings||[]).map(f=>({...f,team:'r2'})))
log(`round2 raw: ${r2.length}`)

const allNew=[...r1,...r2].filter(f=>f&&f.is_new!==false)
function key(f){return ((f.components||[]).slice().sort().join(',')+'|'+(f.title||'').toLowerCase().replace(/[^a-z0-9]+/g,' ').trim().slice(0,40))}
const seen=new Map()
for(const f of allNew){const k=key(f);const o={CRITICAL:5,HIGH:4,MEDIUM:3,LOW:2,INFO:1};if(!seen.has(k)||(o[f.severity]||0)>(o[seen.get(k).severity]||0))seen.set(k,f)}
const deduped=[...seen.values()]
log(`deduped NEW: ${deduped.length}`)

phase('Crossfire')
const VERD={type:'object',additionalProperties:false,required:['refuted','confirmed_severity','reasoning'],properties:{
  refuted:{type:'boolean'},confirmed_severity:{type:'string',enum:['CRITICAL','HIGH','MEDIUM','LOW','INFO','NONE']},reasoning:{type:'string'}}}
const judged=await parallel(deduped.map((f,i)=>()=>
  parallel(['ug585-datasheet-literal','first-principles','protocol-reality'].map(lens=>()=>
    agent(`${BASE}\n\n=== ADVERSARIAL PANEL (lens: ${lens}) — try to REFUTE ===\nDefault refuted=true unless you INDEPENDENTLY reproduce the wiring defect from the netlist + the primary source (grep ${UG585} or the device datasheet). For a "wrong pin / swapped bus" claim, show the correct pin/order per the source. Distinguish a real fault from a correct-but-unusual choice.\n\nFINDING:\ntitle:${f.title}\nseverity:${f.severity}\ncomponents:${(f.components||[]).join(', ')}\nnets:${(f.nets||[]).join(', ')}\nobservation:${f.observation}\nexpected:${f.expected}\nimpact:${f.impact}`,
      {label:`crossfire:${i}:${lens}`,phase:'Crossfire',effort:'medium',schema:VERD})
  )).then(v=>{const vv=v.filter(Boolean);return {...f,confirm:vv.filter(x=>!x.refuted).length,votes:vv.length,detail:vv}})
))
const survivors=judged.filter(Boolean).filter(f=>f.confirm>=2)
const killed=judged.filter(Boolean).filter(f=>f.confirm<2)
log(`survivors>=2/3: ${survivors.length}; killed: ${killed.length}`)

phase('Synthesize')
const payload={
  new_confirmed:survivors.map(s=>({severity:s.severity,panel:`${s.confirm}/${s.votes}`,title:s.title,components:s.components,nets:s.nets,observation:s.observation,expected:s.expected,impact:s.impact,recommendation:s.recommendation,confidence:s.confidence})),
  killed:killed.map(s=>({title:s.title,severity:s.severity,confirm:`${s.confirm}/${s.votes}`,why:(s.detail&&s.detail.map(d=>d.reasoning).join(' | ')||'').slice(0,400)})),
  coverage,
}
const report=await agent(`You are the lead reviewer writing the INTERFACE WIRING audit for a Zynq-7020 SoM. Prior audits (som/SOM_ELECTRICAL_AUDIT.md) already found 2 board-dead DDR defects + others; THIS pass verifies every chip<->peripheral interface pin/bit/direction/protocol level and reports what is NEW plus a positive per-interface coverage record.
Markdown:
# SOM Interface & Wiring Audit
## Executive summary (did interface-level verification find new wiring defects beyond the knowns? counts by severity; the single most important; if an interface is clean, SAY SO)
## NEW confirmed wiring defects (subsection each, ranked: what/where refs+nets / why with UG585-datasheet quote / impact / fix / panel vote)
## Per-interface verdict table (DDR addr/cmd, QSPI, eMMC, RGMII, ULPI, BMI323 SPI, Zynq<->STM32, config/JTAG, clocks/reset, pulls/term/power) — CLEAN / DEFECT, with the key evidence per interface
## Rejected candidates (panel-killed, why)
Be precise; cite refs/nets/pins and the primary-source line. Distinguish real faults from correct-but-unusual. Do NOT invent.
DATA(JSON):
${JSON.stringify(payload).slice(0,55000)}`,
  {label:'synthesize-iface',phase:'Synthesize',effort:'high'})

return {report,counts:{new_confirmed:survivors.length,killed:killed.length,
  critical:survivors.filter(s=>s.severity==='CRITICAL').length,high:survivors.filter(s=>s.severity==='HIGH').length,
  medium:survivors.filter(s=>s.severity==='MEDIUM').length,low:survivors.filter(s=>s.severity==='LOW').length},survivors}
