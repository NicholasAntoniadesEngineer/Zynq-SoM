export const meta = {
  name: 'som-carrier-remediation',
  description: 'High-end remediation pass: design the precise fix for every confirmed SOM + carrier + interface defect, adversarially verify each fix is correct/complete/conflict-free, synthesize one definitive change-list',
  phases: [
    { title: 'FixDesign',  detail: 'one high-end agent per defect designs the exact change' },
    { title: 'FixVerify',  detail: 'independent skeptic proves each fix correct+complete+no-new-bug' },
    { title: 'Integrate',  detail: 'cross-fix conflict + ripple analysis' },
    { title: 'Synthesize', detail: 'definitive SOM / carrier / interface change-list' },
  ],
}

const ROOT='/Users/nicholasantoniades/Documents/GitHub/Zynq-SoM'
const SOM=ROOT+'/som', CARR=ROOT+'/carrier'
const A={
  somnets:'/tmp/som_nets.txt', somcomps:'/tmp/som_components.txt',
  carnets:'/tmp/carrier_nets.txt', carcomps:'/tmp/carrier_components.txt',
  coord:'/tmp/som_carrier_coord.txt', ddr:'/tmp/ddr_reroute.txt',
  ug585:'/tmp/ug585.txt', somraw:'/tmp/som_netlist.net', carraw:'/tmp/carrier_netlist.net',
  audit:SOM+'/SOM_ELECTRICAL_AUDIT.md', coordrep:SOM+'/SOM_CARRIER_COORDINATION.md',
  contract:CARR+'/som_interface.json',
}

const BASE=`You are a principal hardware engineer producing the DEFINITIVE remediation for a Xilinx Zynq-7020 SoM (released KiCad design at ${SOM}) and the carrier it mates with (${CARR}, mezzanine via 3x DF40-100: SoM J1/J2/J3 = carrier J24001/J25002/J26003). Four prior audit passes (~215 agents) already FOUND and VERIFIED the defects; your job now is the FIX — exact, netlist-grounded, and provably correct. Do NOT re-hunt for new bugs. Do NOT restate the problem at length. Produce the precise change and prove it is right.

GROUND TRUTH (read/grep — the netlist is sacred, every change must be expressed as concrete ref/pin/net/value edits):
- ${A.somnets} / ${A.somcomps} : SoM nets + components.  ${A.carnets} / ${A.carcomps} : carrier nets + components.
- ${A.coord} : SoM<->carrier 3-way DF40 pin map.  ${A.ddr} : DDR3L byte-lane reroute data (current wrong map + the correct lower-lane target balls).
- ${A.audit} : consolidated SoM audit (Parts I-III).  ${A.coordrep} : SoM<->carrier coordination report.  ${A.contract} : the DF40 interface contract.
- ${A.ug585} : Zynq-7000 TRM text (grep for pin/bank rules).  ${A.somraw}/${A.carraw} : raw netlists (pinfunctions/footprints).  Schematics: ${SOM}/schematic/*.kicad_sch , ${CARR}/schematic/*.kicad_sch . Datasheets via WebSearch/WebFetch (ToolSearch "select:WebSearch,WebFetch").

FIX QUALITY BAR (this is the whole point):
1. The change must make the design ELECTRICALLY CORRECT and (where relevant) make the SoM work WITH the carrier. Express it as a concrete diff: which file/sheet/component/net, the BEFORE state, the AFTER state, exact values/part numbers/ball assignments.
2. It must be COMPLETE — include every ripple (a reroute that moves a net must move its DQS/DM partners and update both ends; a part change must update symbol+footprint+BOM+LCSC; a connector gender change must keep pin-1 mating correct).
3. It must NOT introduce a new defect (the prior audits caught fixes that were themselves backwards). State explicitly why your change does not break anything adjacent.
4. Verify the AFTER state against the datasheet/UG585 (quote the rule). For part swaps, give a real, in-stock LCSC/MPN — do not guess a code; verify it.
Report ONLY via the schema.`

const FIXSPEC={type:'object',additionalProperties:false,required:['finding_id','board','title','severity','root_cause','changes','ripple_effects','why_no_new_bug','verification','effort','confidence','open_questions'],
  properties:{
    finding_id:{type:'string'}, board:{type:'string',enum:['SOM','CARRIER','BOTH','INTERFACE']},
    title:{type:'string'}, severity:{type:'string',enum:['CRITICAL','HIGH','MEDIUM','LOW']},
    root_cause:{type:'string'},
    changes:{type:'array',items:{type:'object',additionalProperties:false,required:['location','action','before','after'],
      properties:{location:{type:'string',description:'file/sheet/ref/net'},action:{type:'string',enum:['modify','add','remove','reroute','reassign','relabel']},before:{type:'string'},after:{type:'string'},note:{type:'string'}}}},
    ripple_effects:{type:'string'}, why_no_new_bug:{type:'string'},
    verification:{type:'string',description:'how to confirm the fix worked (gate/measurement/datasheet rule, quoted)'},
    effort:{type:'string',enum:['trivial','schematic-only','schematic+layout','layout-major','part-change','firmware']},
    confidence:{type:'number'}, open_questions:{type:'string'}}}

const FIXVERDICT={type:'object',additionalProperties:false,required:['finding_id','fix_correct','fix_complete','introduces_new_bug','reasoning','residual_risk','final_confidence'],
  properties:{finding_id:{type:'string'},fix_correct:{type:'boolean'},fix_complete:{type:'boolean'},introduces_new_bug:{type:'boolean'},
    reasoning:{type:'string',description:'independently re-derive; would applying this exact change make the netlist correct and break nothing?'},
    corrected_changes:{type:'string',description:'if the fix is wrong/incomplete, the corrected change. else empty.'},
    residual_risk:{type:'string'},final_confidence:{type:'number'}}}

// confirmed, verified defects -> fix-design briefs
const FINDINGS=[
 {id:'S1-ddr-vrpvrn',board:'SOM',sev:'CRITICAL',brief:'DDR DCI VRP/VRN swapped: R47(VRP,U2.N7)->+1V35, R46(VRN,U2.M7)->GND. UG585/UG933 require VRP->GND, VRN->VCCO_DDR(+1V35). Design the exact rail-end swap (R46/R47), and ALSO address whether the value should be 100R or 80R per UG933 Table 5-2 for DDR3L (state the board trace-impedance assumption). Schematic + which nets change.'},
 {id:'S2-ddr-bytelane',board:'SOM',sev:'CRITICAL',brief:'DDR3L x16 wired to Zynq PS UPPER byte lanes DQ[31:16]/DQS2/DQS3/DM2/DM3; must move to the controller-active LOWER lanes DQ[15:0]/DQS0/DQS1/DM0/DM1. Use ${A.ddr}: produce the EXACT new mapping — every U1 DRAM data ball -> its new Zynq lower-lane ball, keeping byte-lane integrity (DRAM lower byte+LDQS+LDM as one Zynq byte lane, upper byte+UDQS+UDM as the other), DQS pairs intact, DM with its lane. Note DQ-bit order within a lane may be swapped freely (DDR3) to ease routing, but DQS/DM must follow the lane. State this is a schematic re-net + PCB re-route (layout-major) and what to re-verify (write-leveling/training).'},
 {id:'S3-emmc',board:'SOM',sev:'HIGH',brief:'eMMC U7: symbol/Value/MPN=ISSI IS21ES08G (IS21ES08GA-JCLI-TR) but LCSC C499918=Samsung KLM8G1GETF-B041. Decide ONE part (recommend keeping the ISSI design intent OR switching to the stocked Samsung), give the correct verified LCSC, and list every field to change (Value/MPN/LCSC) + the ballout re-check (esp. ball C1) needed for the chosen part.'},
 {id:'S4-eth-clk',board:'SOM',sev:'HIGH',brief:'RTL8211F 25MHz osc X2 powered from +1V8 (1.8Vpp) into U3.37 EXT_CLK which needs 3.15-3.45Vpp (RTL8211F Table 55). Move X2 supply from +1V8 to +3V3: exact change to ferrite L6 source net (and any cap rail). Confirm the placed oscillator (LCSC C669080 / YXC) is rated for 3.3V. Keep R20 22R + U3.36 XTAL_IN->GND. Do NOT touch USB X1 (1.8V correct there).'},
 {id:'S5-som-hygiene',board:'SOM',sev:'MEDIUM',brief:'SoM schematic/BOM source-of-truth fixes: (a) R80/R81 schematic=5k1/12k but PCB+BOM=100k/100k -> update schematic to 100k; (b) SoM schematic DF40 footprint FIELD=...DP but PCB/BOM=...DS -> this depends on the gender decision (coordinate with I1); (c) placeholder/invalid LCSC (gia/empty) on listed parts -> assign verified codes; (d) BMI323 VDDIO bypass C14 is DNP + C21 LCSC=gia -> populate/fix. Give concrete per-item edits.'},
 {id:'I1-df40-gender',board:'INTERFACE',sev:'CRITICAL',brief:'DF40 double-receptacle: SoM PCB/BOM AND carrier BOTH use DF40C-100DS (receptacle, C597931). DF40 mates DP(plug)<->DS(receptacle). DECIDE which board becomes the DP plug (recommend with reasoning - typically the carrier is the host/plug, SoM stays receptacle, but justify), then specify the EXACT edits on BOTH boards: value, footprint (DS land rows +/-1.54 vs DP land +/-1.355), LCSC/MPN for the DP plug (verify it), stack-height match (both (51)=1.5mm), and the pin-1 mating orientation so logical pin N still meets pin N. Also reconcile the SoM schematic DF40 footprint field with whatever the SoM PCB ends up being.'},
 {id:'I2-fmc-la08',board:'INTERFACE',sev:'HIGH',brief:'FMC_LA08 diff pair split: SoM J1.74(IO_L1_P_35)/J1.92(IO_L1_N_35) carry carrier FMC_LA08_P/N but are 18 contacts apart (7.2mm). Decide the fix: reassign IO_L1_P/N_35 to an ADJACENT same-row DF40 contact pair (delta=2) with GND flank (find a free adjacent pair in ${A.coord}), OR formally declare FMC_LA08 single-ended-only and remove it from the carrier DP100_DIFF class. Recommend, and give exact pin reassignment on both sides if rerouting.'},
 {id:'C1-camera',board:'CARRIER',sev:'CRITICAL',brief:'Carrier MIPI CSI-2 camera (J8001 RPi 15p) D-PHY lanes go straight into Zynq-7020 bank35 with only 3x100R + 2x TPD4E02B04 ESD - no D-PHY receiver and Zynq-7020 has no MIPI hard IP. Design the front-end: recommend ONE of (a) XAPP894 D-PHY-to-LVDS resistor network per lane with bank pins as LVDS_25/HSUL - give the exact resistor topology/values, (b) a dedicated MIPI CSI-2-to-parallel/LVDS bridge IC (name a real part + LCSC), or (c) re-spec to a parallel/sub-LVDS sensor. Specify added parts, bank I/O standard, and the VCCO_35 implication (must stay compatible with the FMC LVDS_25 pairs that share bank35).'},
 {id:'C2-5vsom-volt',board:'CARRIER',sev:'HIGH',brief:'Carrier +5V_SOM buck (U22004 LM61460, Vref 1.0V) FB R22014=47.5k(top)/R22015=13k(bot) -> 4.654V. Re-target to 5.0V: give exact resistor value(s) (keep 47.5k top, change bottom to the value giving ratio 4.0; provide a real E96 value and the resulting Vout), and confirm against LM61460 Vref. Verify SoM VIN >=4.2V after DF40 IR drop at worst-case current.'},
 {id:'C3-5vsom-ind',board:'CARRIER',sev:'HIGH',brief:'Carrier +5V_SOM inductor L22003 = SWPA8040S100MT (10uH, 3.3A Irms/4.1A Isat) cannot source the SoM ~5.2A worst-case input. Select a replacement inductor (~4.7-10uH per LM61460 fsw) rated >=6A Isat and >=5.5A Irms, same/larger footprint - name a real part + LCSC, give DCR, and confirm LM61460 6A capability + thermal at the load.'},
 {id:'C4-sc-i2c',board:'CARRIER',sev:'MEDIUM',brief:'Carrier SC-I2C bus (FUSB302 PD + 2x INA3221 + TCA9535 + PCA9306) lands on SoM J1.49/J1.55 = STM32 PA4/PA5 which have NO hardware I2C. Determine the fix: is there a hardware-I2C-capable STM32 pin pair brought to the SoM connector that is free (check ${A.somnets}/${A.coord} for STM32 pins on J1)? If yes, re-pin the carrier I2C to those contacts. If no free HW-I2C pins exist on the connector, decide between (a) a SoM-side connector reassignment to expose I2C1/I2C2 pins, or (b) accept firmware bit-bang and document FUSB302 PD timing tolerance. Recommend with specifics; cite STM32G431 AF table.'},
 {id:'C5-jtag-tck',board:'CARRIER',sev:'LOW',brief:'PS-JTAG TCK (ZYNQ_TCK, SoM J1.64) has no pull-up either board (carrier pulls TMS R9001/TDI R9002 4k7 to +3V3 but omits TCK). Add a 4k7 pull-up on ZYNQ_TCK to +3V3 on the carrier mirroring R9001/R9002. Give the exact net/sheet and value; confirm +3V3 domain match (VCCO_MIO0=3V3).'},
]

phase('FixDesign')
const designed=await pipeline(FINDINGS,
  (f)=>agent(`${BASE}\n\n=== DESIGN THE FIX [${f.id}] (board=${f.board}, severity=${f.sev}) ===\n${f.brief}\n\nProduce the exact, complete, verified change spec.`,
    {label:`fix:${f.id}`,phase:'FixDesign',schema:FIXSPEC,effort:'high'}),
  (spec,f)=>spec==null?null:agent(`${BASE}\n\n=== ADVERSARIALLY VERIFY THE FIX [${f.id}] ===\nA fix was proposed (below). You are a skeptic. INDEPENDENTLY re-derive from the netlist/datasheet/UG585 whether applying this EXACT change (1) makes the design correct, (2) is complete (every ripple covered), (3) introduces NO new defect. Default to fix_correct=false unless you can prove all three. If wrong or incomplete, give the corrected change. Recall prior audits shipped backwards fixes - check the DIRECTION explicitly.\n\nPROPOSED FIX JSON:\n${JSON.stringify(spec).slice(0,6000)}\n\nReturn your verdict.`,
    {label:`verify:${f.id}`,phase:'FixVerify',schema:FIXVERDICT,effort:'high'}).then(v=>({finding:f,spec,verdict:v}))
)

const ok=designed.filter(Boolean)
phase('Integrate')
const integ=await agent(`${BASE}\n\n=== CROSS-FIX INTEGRATION & CONFLICT ANALYSIS ===\nAll fixes were designed and verified. Analyze INTERACTIONS across them, because several touch the same physical resources:\n- DDR byte-lane reroute (S2), DF40 gender (I1), FMC_LA08 reassignment (I2), SC-I2C re-pin (C4) all touch connector contacts / Zynq balls / layout.\n- DF40 gender (I1) and SoM schematic DF40 field (S5b) must agree.\n- VIN budget interacts: SoM 14-contact limit + carrier +5V voltage (C2) + carrier inductor (C3).\nIdentify: (a) any two fixes that conflict or must be co-designed; (b) the correct ORDER to apply them; (c) any fix whose verifier flagged it wrong/incomplete; (d) anything still open. Output as findings: each 'title'=the interaction/issue, 'recommendation'=how to resolve, severity by impact.\n\nFIX+VERDICT SUMMARY JSON:\n${JSON.stringify(ok.map(o=>({id:o.finding.id,board:o.finding.board,sev:o.finding.sev,effort:o.spec&&o.spec.effort,correct:o.verdict&&o.verdict.fix_correct,complete:o.verdict&&o.verdict.fix_complete,newbug:o.verdict&&o.verdict.introduces_new_bug,changes:o.spec&&o.spec.changes,corrected:o.verdict&&o.verdict.corrected_changes}))).slice(0,12000)}`,
  {label:'integrate',phase:'Integrate',schema:{type:'object',additionalProperties:false,required:['interactions','apply_order','still_open'],properties:{
    interactions:{type:'array',items:{type:'object',additionalProperties:false,required:['title','severity','recommendation'],properties:{title:{type:'string'},severity:{type:'string'},recommendation:{type:'string'}}}},
    apply_order:{type:'array',items:{type:'string'}}, still_open:{type:'string'}}},effort:'high'})

phase('Synthesize')
const payload={fixes:ok.map(o=>({id:o.finding.id,board:o.finding.board,severity:o.finding.sev,title:o.spec&&o.spec.title,
  changes:o.spec&&o.spec.changes,ripple:o.spec&&o.spec.ripple_effects,effort:o.spec&&o.spec.effort,
  verify:o.spec&&o.spec.verification,confidence:o.spec&&o.spec.confidence,open:o.spec&&o.spec.open_questions,
  verdict:o.verdict&&{correct:o.verdict.fix_correct,complete:o.verdict.fix_complete,newbug:o.verdict.introduces_new_bug,corrected:o.verdict.corrected_changes,residual:o.verdict.residual_risk,conf:o.verdict.final_confidence}})),
  integration:integ}
const report=await agent(`You are the lead engineer writing the DEFINITIVE remediation plan to make this Zynq-7020 SoM electrically correct and able to work with its carrier. Audience: the PCB designer who will implement it. Be exact and actionable; this is a change-list, not an essay.
Write Markdown:
# SOM + Carrier Remediation Plan
## Executive summary (what must change, in one paragraph; the absolute must-do CRITICALs; total effort picture)
## A. SOM board changes (one subsection per fix, ordered by severity: exact ref/net/value/ball BEFORE->AFTER, effort tag, how-to-verify, confidence; FOLD IN any verifier correction)
## B. Carrier board changes (same format)
## C. Interface / DF40 mating changes (gender decision + both-side edits + pin-1; diff-pair)
## D. Apply order & cross-fix interactions (from the integration analysis - call out fixes that must be co-designed)
## E. Residual risk / still-open items / what to re-verify after changes
For each fix include a one-line VERIFIED/CORRECTED tag from its adversarial verdict. If a verifier marked a fix wrong/incomplete, present the CORRECTED version as the recommendation and say so. Use tables where it aids the implementer. Do not invent.
DATA(JSON):
${JSON.stringify(payload).slice(0,60000)}`,
  {label:'synthesize-remediation',phase:'Synthesize',effort:'high'})

return {report,
  summary:ok.map(o=>({id:o.finding.id,board:o.finding.board,sev:o.finding.sev,effort:o.spec&&o.spec.effort,
    correct:o.verdict&&o.verdict.fix_correct,complete:o.verdict&&o.verdict.fix_complete,newbug:o.verdict&&o.verdict.introduces_new_bug})),
  integration:integ}
