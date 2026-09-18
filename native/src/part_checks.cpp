#include "schgen/part_checks.hpp"
#include "model_checks_internal.hpp"

namespace schgen {
using namespace model_checks;

const PartRatingsTable& default_part_ratings() {
    static const PartRatingsTable table = {
        {"C14663", {"mlcc", 50.0, std::nullopt, std::nullopt, "±10%", "X7R", 125.0, std::nullopt, "JLC desc CC0603KRX7R9BB104 100nF 50V X7R"}},
        {"C1591", {"mlcc", 50.0, std::nullopt, std::nullopt, "±10%", "X7R", 125.0, std::nullopt, "JLC desc CL10B104KB8NNNC 100nF 50V X7R"}},
        {"C100042", {"mlcc", 50.0, std::nullopt, std::nullopt, "±10%", "X7R", 125.0, std::nullopt, "JLC desc CC0603KRX7R9BB103 10nF 50V X7R"}},
        {"C1622", {"mlcc", 50.0, std::nullopt, std::nullopt, "±10%", "X7R", 125.0, std::nullopt, "JLC desc CL10B473KB8NNNC 47nF 50V X7R"}},
        {"C1631", {"mlcc", 50.0, std::nullopt, std::nullopt, "±10%", "X7R", 125.0, std::nullopt, "JLC desc 0603B682K500NT 6.8nF 50V X7R"}},
        {"C15849", {"mlcc", 50.0, std::nullopt, std::nullopt, "±10%", "X5R", 85.0, std::nullopt, "JLC desc CL10A105KB8NNNC 1uF 50V X5R"}},
        {"C125847", {"mlcc", 50.0, std::nullopt, std::nullopt, "±10%", "X7R", 125.0, std::nullopt, "JLC desc CC0805KKX7R9BB225 2.2uF 50V X7R"}},
        {"C15850", {"mlcc", 25.0, std::nullopt, std::nullopt, "±10%", "X5R", 85.0, std::nullopt, "JLC desc CL21A106KAYNNNE 10uF 25V X5R"}},
        {"C13585", {"mlcc", 50.0, std::nullopt, std::nullopt, "±10%", "X5R", 85.0, std::nullopt, "JLC desc CL31A106KBHNNNE 10uF 50V X5R"}},
        {"C596319", {"mlcc", 50.0, std::nullopt, std::nullopt, "±10%", "X7R", 125.0, std::nullopt, "JLC desc CC1210KKX7R9BB106 10uF 50V X7R"}},
        {"C45783", {"mlcc", 25.0, std::nullopt, std::nullopt, "±20%", "X5R", 85.0, std::nullopt, "JLC desc CL21A226MAQNNNE 22uF 25V X5R"}},
        {"C970684", {"elec", 16.0, std::nullopt, std::nullopt, "±20%", std::nullopt, 105.0, std::nullopt, "DMBJ RVT1C101M0605 100uF 16V SMD aluminium electrolytic — bias-stable VBUS bulk (audit 2026-06-20)"}},
        {"C976030", {"elec", 35.0, std::nullopt, std::nullopt, "±20%", std::nullopt, 105.0, std::nullopt, "DMBJ RVT1V471M1010 470uF 35V SMD aluminium electrolytic — motor-rail bulk on ESC_VRAIL_IN; 35V >= 4S+margin (OPEN-3, LCSC product page)"}},
        {"C9196", {"mlcc", 2000.0, std::nullopt, std::nullopt, "±10%", "X7R", 125.0, std::nullopt, "JLC desc 1206B102K202NT 1nF 2kV X7R (ethernet Bob-Smith)"}},
        {"C113796", {"mlcc", 50.0, std::nullopt, std::nullopt, "±5%", "C0G", 125.0, std::nullopt, "JLC desc CC0603JRNPO9BN201 200pF 50V C0G"}},
        {"C22399620", {"mlcc", 50.0, std::nullopt, std::nullopt, "±5%", "C0G", 125.0, std::nullopt, "JLC desc CGA0603C0G750J 75pF 50V C0G"}},
        {"C1653", {"mlcc", 50.0, std::nullopt, std::nullopt, "±5%", "C0G", 125.0, std::nullopt, "JLC desc CL10C220JB8NNNC 22pF 50V C0G (buck FB feedforward)"}},
        {"C49326329", {"mlcc", 100.0, std::nullopt, std::nullopt, "±5%", "C0G", 125.0, std::nullopt, "JLC desc 0603C0G470J101NT 47pF 100V C0G"}},
        {"C22769", {"res", 75.0, std::nullopt, 0.1, "±1%", std::nullopt, 155.0, std::nullopt, "JLC desc 0603WAF150KT5E 1.5R 100mW 75V"}},
        {"C22775", {"res", 75.0, std::nullopt, 0.1, "±1%", std::nullopt, 155.0, std::nullopt, "JLC desc 0603WAF1000T5E 100R 100mW 75V"}},
        {"C25803", {"res", 75.0, std::nullopt, 0.1, "±1%", std::nullopt, 155.0, std::nullopt, "JLC desc 0603WAF1003T5E 100k 100mW 75V"}},
        {"C25804", {"res", 75.0, std::nullopt, 0.1, "±1%", std::nullopt, 155.0, std::nullopt, "JLC desc 0603WAF1002T5E 10k 100mW 75V"}},
        {"C22797", {"res", 75.0, std::nullopt, 0.1, "±1%", std::nullopt, 155.0, std::nullopt, "JLC desc 0603WAF1302T5E 13k 100mW 75V"}},
        {"C22809", {"res", 75.0, std::nullopt, 0.1, "±1%", std::nullopt, 155.0, std::nullopt, "JLC desc 0603WAF1502T5E 15k 100mW 75V"}},
        {"C21190", {"res", 75.0, std::nullopt, 0.1, "±1%", std::nullopt, 155.0, std::nullopt, "JLC desc 0603WAF1001T5E 1k 100mW 75V"}},
        {"C22859", {"res", 75.0, std::nullopt, 0.1, "±1%", std::nullopt, 155.0, std::nullopt, "JLC desc 0603WAF100JT5E 10R 100mW 75V (LM61460 BIAS series)"}},
        {"C8218", {"res", 75.0, std::nullopt, 0.1, "±1%", std::nullopt, 155.0, std::nullopt, "JLC desc 0603WAF2000T5E 200R 100mW 75V"}},
        {"C23345", {"res", 75.0, std::nullopt, 0.1, "±1%", std::nullopt, 155.0, std::nullopt, "JLC desc 0603WAF220JT5E 22R 100mW 75V"}},
        {"C31850", {"res", 75.0, std::nullopt, 0.1, "±1%", std::nullopt, 155.0, std::nullopt, "JLC desc 0603WAF2202T5E 22k 100mW 75V"}},
        {"C25961", {"res", 75.0, std::nullopt, 0.1, "±1%", std::nullopt, 155.0, std::nullopt, "JLC desc 0603WAF2212T5E 22.1k 100mW 75V"}},
        {"C22967", {"res", 75.0, std::nullopt, 0.1, "±1%", std::nullopt, 155.0, std::nullopt, "JLC desc 0603WAF2702T5E 27k 100mW 75V"}},
        {"C23138", {"res", 75.0, std::nullopt, 0.1, "±1%", std::nullopt, 155.0, std::nullopt, "JLC desc 0603WAF3300T5E 330R 100mW 75V"}},
        {"C23061", {"res", 75.0, std::nullopt, 0.1, "±1%", std::nullopt, 155.0, std::nullopt, "JLC desc 0603WAF4752T5E 47.5k 100mW 75V"}},
        {"C114625", {"res", 75.0, std::nullopt, 0.1, "±1%", std::nullopt, 155.0, std::nullopt, "JLC desc RC0603FR-0749R9L 49.9R 100mW 75V"}},
        {"C23162", {"res", 75.0, std::nullopt, 0.1, "±1%", std::nullopt, 155.0, std::nullopt, "JLC desc 0603WAF4701T5E 4.7k 100mW 75V"}},
        {"C23186", {"res", 75.0, std::nullopt, 0.1, "±1%", std::nullopt, 155.0, std::nullopt, "JLC desc 0603WAF5101T5E 5.1k 100mW 75V"}},
        {"C188263", {"res", 75.0, std::nullopt, 0.1, "±1%", std::nullopt, 155.0, std::nullopt, "JLC desc RC0603FR-075K49L 5.49k 100mW 75V"}},
        {"C23206", {"res", 75.0, std::nullopt, 0.1, "±1%", std::nullopt, 155.0, std::nullopt, "JLC desc 0603WAF5602T5E 56k 100mW 75V"}},
        {"C23212", {"res", 75.0, std::nullopt, 0.1, "±1%", std::nullopt, 155.0, std::nullopt, "JLC desc 0603WAF6801T5E 6.8k 100mW 75V"}},
        {"C844583", {"res", 75.0, std::nullopt, 0.1, "±1%", std::nullopt, 155.0, std::nullopt, "JLC desc CRCW060368K1FKEA 68.1k 100mW 75V"}},
        {"C14890", {"res", 75.0, std::nullopt, 0.1, "±1%", std::nullopt, 155.0, std::nullopt, "JLC desc 0603WAF7322T5E 73.2k 100mW 75V"}},
        {"C4275", {"res", 75.0, std::nullopt, 0.1, "±1%", std::nullopt, 155.0, std::nullopt, "JLC desc 0603WAF750JT5E 75R 100mW 75V"}},
        {"C23107", {"res", 75.0, std::nullopt, 0.1, "±1%", std::nullopt, 155.0, std::nullopt, "JLC desc 0603WAF7682T5E 76.8k 100mW 75V"}},
        {"C23198", {"res", 75.0, std::nullopt, 0.1, "±1%", std::nullopt, 155.0, std::nullopt, "JLC desc 0603WAF5232T5E 52.3k 100mW 75V"}},
        {"C188070", {"res", std::nullopt, std::nullopt, 1.0, "±1%", std::nullopt, 155.0, std::nullopt, "JLC desc RLM12FTCMR010 10mR 1W 1206 shunt"}},
        {"C393094", {"res", std::nullopt, std::nullopt, 1.0, "±1%", std::nullopt, 155.0, std::nullopt, "JLC desc RLM12FTCMR020 20mR 1W 1206 shunt"}},
        {"C25508", {"res", std::nullopt, std::nullopt, 0.0625, "±5%", std::nullopt, 155.0, std::nullopt, "4D03WGJ0330T5E 4x33R 0603x4 isolated array, 1/16W/elem (motor_io ESC-output series-damping)"}},
        {"C38117", {"ind", std::nullopt, 2.4, std::nullopt, "±20%", std::nullopt, std::nullopt, std::nullopt, "JLC desc SWPA4030S100MT 10uH Isat 2.4A"}},
        {"C37429", {"ind", std::nullopt, 4.1, std::nullopt, "±20%", std::nullopt, std::nullopt, std::nullopt, "JLC desc SWPA8040S100MT 10uH Isat 4.1A"}},
        {"C8678", {"diode", 40.0, 3.0, std::nullopt, std::nullopt, std::nullopt, 125.0, std::nullopt, "JLC desc SS34 Schottky 40V 3A"}},
        {"C22452", {"diode", 40.0, 5.0, std::nullopt, std::nullopt, std::nullopt, 125.0, std::nullopt, "JLC desc SS54 Schottky 40V 5A"}},
        {"C85181", {"diode", 5.1, std::nullopt, 0.37, std::nullopt, std::nullopt, 150.0, std::nullopt, "JLC desc MMSZ5231B 5.1V Zener 370mW"}},
        {"C10214", {"diode", 22.0, std::nullopt, std::nullopt, std::nullopt, std::nullopt, 150.0, std::nullopt, "JLC desc SMBJ22A 22V standoff TVS 600W"}},
        {"C2288", {"diode", std::nullopt, 0.02, std::nullopt, std::nullopt, std::nullopt, 85.0, std::nullopt, "JLC desc KT-0603B blue LED 20mA"}},
        {"C12624", {"diode", std::nullopt, 0.02, std::nullopt, std::nullopt, std::nullopt, 85.0, std::nullopt, "JLC desc KT-0603G green LED 20mA"}},
        {"C2286", {"diode", std::nullopt, 0.02, std::nullopt, std::nullopt, std::nullopt, 85.0, std::nullopt, "JLC desc KT-0603R red LED 20mA"}},
        {"C2290", {"diode", std::nullopt, 0.02, std::nullopt, std::nullopt, std::nullopt, 85.0, std::nullopt, "JLC desc KT-0603W white LED 20mA"}},
        {"C7519", {"diode", 5.25, std::nullopt, std::nullopt, std::nullopt, std::nullopt, 125.0, std::nullopt, "JLC USBLC6-2SC6 ESD standoff 5.25V"}},
        {"C1973318", {"diode", 5.5, std::nullopt, std::nullopt, std::nullopt, std::nullopt, 85.0, std::nullopt, "TPD6E001 6-ch ESD: SLLS685D VCC/standoff 0.9-5.5V, IOx 0..VCC, 1.5pF, abs-max VCC 7V"}},
        {"C124691", {"diode", 5.5, std::nullopt, std::nullopt, std::nullopt, std::nullopt, 125.0, std::nullopt, "TPD4E1U06DBVR 4-ch GND-ref ESD: SLLS478 VRWM 5.5V, CL 0.8pF, +-8kV IEC61000-4-2 (pmod/pmod_expansion clamps; audit 2026-06-20)"}},
        {"C106794", {"diode", 5.5, std::nullopt, std::nullopt, std::nullopt, std::nullopt, 125.0, std::nullopt, "TPD4E02B04 TMDS RX ESD VRWM 5.5V"}},
        {"C138714", {"diode", 5.5, std::nullopt, std::nullopt, std::nullopt, std::nullopt, 125.0, std::nullopt, "TPD4E05U06 4-ch GND-ref TVS: SLVSBO7O VRWM 5.5V, VBR(min) 6V, CL 0.5pF, +-12kV contact (HDMI-RX slow-line ESD)"}},
        {"C42440491", {"diode", 28.0, std::nullopt, std::nullopt, std::nullopt, std::nullopt, 150.0, std::nullopt, "SMBJ28A 28V standoff TVS 600W SMB (motor_io ESC-rail clamp; note its clamp >INA3221 26V CM, so the rail is bounded <=4S, not the TVS)"}},
        {"C2836319", {"diode", 5.0, std::nullopt, std::nullopt, std::nullopt, std::nullopt, 125.0, std::nullopt, "MSKSEMI SRV05-4 5-line steering-diode + surge-TVS ESD array: VRWM 5V (rated for 5V lines), VBR ~6V, clamp ~12.5-17V, SOT-23-6 (motor_pwm 8-ch ESC-output 5V ESD)"}},
        {"C20917", {"other", 30.0, 5.7, 1.4, std::nullopt, std::nullopt, 150.0, std::nullopt, "AO3400A N-ch 30V Vds 5.7A SOT-23"}},
        {"C90761", {"ic", std::nullopt, 3.0, std::nullopt, std::nullopt, std::nullopt, 150.0, 28.0, "TPS54331DDAR buck recommended 3.5-28V 3A"}},
        {"C311983", {"ic", std::nullopt, 3.0, std::nullopt, std::nullopt, std::nullopt, 125.0, 28.0, "TPS54302DDCR buck recommended 4.5-28V 3A"}},
        {"C2864505", {"ic", std::nullopt, 6.0, std::nullopt, std::nullopt, std::nullopt, 150.0, 42.0, "LM61460AANRJRR buck (TI SNVSBD5D) abs-max VIN 42V, 6A, Tj op-max 150C; VQFN-HR EP-equiv heat path"}},
        {"C2866319", {"ic", std::nullopt, std::nullopt, std::nullopt, std::nullopt, std::nullopt, 125.0, 60.0, "TPS26631 eFuse recommended 4.5-60V"}},
        {"C176944", {"ic", std::nullopt, 0.6, std::nullopt, std::nullopt, std::nullopt, 85.0, 6.0, "AP2112K-1.8 LDO abs-max 6V 600mA"}},
        {"C35209004", {"ic", std::nullopt, 1.0, std::nullopt, std::nullopt, std::nullopt, 125.0, 6.0, "TLV75725 LDO abs-max 6V 1A"}},
        {"C55136", {"ic", std::nullopt, std::nullopt, std::nullopt, std::nullopt, std::nullopt, 125.0, 6.0, "SY6280AAC load switch abs-max 6V"}},
        {"C82173", {"ic", std::nullopt, std::nullopt, std::nullopt, std::nullopt, std::nullopt, 125.0, 32.0, "SY7201ABC boost abs-max 32V"}},
        {"C129581", {"ic", std::nullopt, 0.5, std::nullopt, std::nullopt, std::nullopt, 125.0, 7.0, "TPS2051C USB switch abs-max 7V"}},
        {"C132291", {"ic", std::nullopt, std::nullopt, std::nullopt, std::nullopt, std::nullopt, 125.0, 6.0, "FUSB302B PD PHY abs-max VDD 6V"}},
        {"C181255", {"ic", std::nullopt, std::nullopt, std::nullopt, std::nullopt, std::nullopt, 125.0, 6.0, "INA3221 monitor abs-max 6V"}},
        {"C6779", {"ic", std::nullopt, std::nullopt, std::nullopt, std::nullopt, std::nullopt, 125.0, 7.0, "SN74HCT245PWR octal bus buffer abs-max VCC 7V; HCT TTL thresholds accept 3.3V inputs at 5V VCC (motor_io PL->ESC level buffer)"}},
        {"C7666", {"ic", std::nullopt, std::nullopt, std::nullopt, std::nullopt, std::nullopt, 125.0, 6.5, "SN74LVC1G08 abs-max Vcc 6.5V"}},
        {"C969151", {"ic", std::nullopt, std::nullopt, std::nullopt, std::nullopt, std::nullopt, 85.0, 4.3, "CP2102N abs-max VDD 4.3V"}},
        {"C140276", {"ic", std::nullopt, std::nullopt, std::nullopt, std::nullopt, std::nullopt, 85.0, 3.6, "TXS02612 level-shifter 1.1-3.6V"}},
        {"C130204", {"ic", std::nullopt, std::nullopt, std::nullopt, std::nullopt, std::nullopt, 85.0, 6.0, "TCA9535 expander abs-max Vcc 6V"}},
        {"C33196", {"ic", std::nullopt, std::nullopt, std::nullopt, std::nullopt, std::nullopt, 85.0, 7.0, "PCA9306 level translator abs-max 7V"}},
        {"C7719", {"ic", std::nullopt, std::nullopt, std::nullopt, std::nullopt, std::nullopt, 85.0, 6.0, "TPS3823-33 supervisor abs-max Vdd 6V"}},
        {"C7562", {"ic", std::nullopt, std::nullopt, std::nullopt, std::nullopt, std::nullopt, 85.0, 6.5, "M24C02 EEPROM abs-max Vcc 6.5V"}},
        {"C129895", {"ic", std::nullopt, std::nullopt, std::nullopt, std::nullopt, std::nullopt, 85.0, 6.5, "24AA025E48 EEPROM+MAC abs-max Vcc 6.5V"}},
        {"C3019759", {"ic", std::nullopt, std::nullopt, std::nullopt, std::nullopt, std::nullopt, 85.0, 5.5, "RV-3028-C7 RTC 1.1-5.5V"}},
        {"C201665", {"ic", std::nullopt, std::nullopt, std::nullopt, std::nullopt, std::nullopt, 85.0, 5.5, "TPD12S016 HDMI ESD/level-shift 4.5-5.5V"}}
    };
    return table;
}

std::optional<PartRatings> part_ratings_from_json(const JsonNode& node) {
    if(node.kind!=JsonKind::Object)return {};
    auto kind=object_field(node,"kind");
    if(!kind||kind->kind==JsonKind::Null||(kind->kind==JsonKind::String&&kind->string_value.empty()))return {};
    if(kind->kind!=JsonKind::String)throw ModelCheckError("part ratings: kind must be a string");
    PartRatings r;r.kind=kind->string_value;
    auto number=[&](const char* name)->std::optional<double>{auto n=object_field(node,name);if(!n||n->kind==JsonKind::Null)return {};if(n->kind!=JsonKind::Number||!std::isfinite(n->number_value))throw ModelCheckError(std::string("part ratings: ")+name+" must be a finite number");return n->number_value;};
    auto str=[&](const char* name)->std::optional<std::string>{auto n=object_field(node,name);if(!n||n->kind==JsonKind::Null)return {};if(n->kind!=JsonKind::String)throw ModelCheckError(std::string("part ratings: ")+name+" must be a string");return n->string_value;};
    r.v_max=number("v_max");r.i_max=number("i_max");r.p_max=number("p_max");r.tol=str("tol");r.dielectric=str("dielectric");r.temp_max=number("temp_max");r.vin_max=number("vin_max");r.source=str("source").value_or("");return r;
}
const PartRatings* ratings_for_part(const CircuitPartIr& part,const PartRatingsTable& table) {return find(table,trim(field(part,"LCSC")));}

std::optional<double> parse_resistor_ohms(const std::string& value) {
    auto s=numeric_text(trim(value));replace_all(s,"Ω","");replace_all(s,"ohm","");
    static const std::regex infix(R"(^([0-9]+)([RrKkMm])([0-9]+)$)"),suffix(R"(^([0-9]+(?:\.[0-9]+)?)([RrKkMm]?)$)");
    auto mult=[](std::string s){s=upper(s);return s=="K"?1e3:s=="M"?1e-3:1.0;};
    std::smatch m;
    // Preserve the baseline's /10 fractional rule (4k70 is 11k) and M=milli.
    if(std::regex_match(s,m,infix))return (std::strtod(m[1].str().c_str(),nullptr)+std::strtod(m[3].str().c_str(),nullptr)/10)*mult(m[2]);
    if(std::regex_match(s,m,suffix))return std::strtod(m[1].str().c_str(),nullptr)*mult(m[2]);
    return {};
}
double capacitor_derating(const PartRatings& r,const PartRulePolicy& p) {
    auto d=upper(r.dielectric.value_or(""));if(d=="C0G"||d=="NP0")return p.derate_c0g;
    if(r.kind=="elec"||r.kind=="tant")return p.derate_elec;return p.derate_mlcc;
}
namespace {
std::vector<double> pin_volts(const CircuitSheetIr& c,const std::string& ref,const PowerPolicy& p) {
    std::vector<double> out;
    for(const auto& n:c.nets)if(std::any_of(n.pins.begin(),n.pins.end(),[&](const auto& pin){return pin.ref==ref;}))if(auto v=rail_volts(n.name,p))out.push_back(*v);
    return out;
}
void part_finding(PartCheckResult& res,const std::string& key,const std::string& msg) {
    if(auto waiver=find(res.waived,key))res.notes.push_back("WAIVED "+msg+" ["+waiver->second+"]");else res.findings.push_back(msg);
}
}
PartCheckResult analyze_part_rules(const std::vector<ProjectCircuit>& sheets,const PowerCheckResult& power,const PartRatingsTable& ratings,const PartRulePolicy& policy,const PowerPolicy& power_policy) {
    PartCheckResult res;res.waived=waivers(sheets,"part_rule_waivers");
    std::vector<const ProjectCircuit*> order;for(const auto& s:sheets)order.push_back(&s);
    std::stable_sort(order.begin(),order.end(),[](auto a,auto b){return a->name<b->name;});
    for(auto sc:order) {
        ModelSheetIndex idx(sc->circuit);
        for(const auto& [ref,part]:idx.parts) {
            auto r=ratings_for_part(*part,ratings);auto key=sc->name+":"+ref,lcsc=field(*part,"LCSC");
            if(!r){if(!trim(lcsc).empty())res.unspecced.push_back(key+" ("+part->value+", LCSC "+lcsc+") — no ratings row");continue;}
            if((r->kind=="mlcc"||r->kind=="elec"||r->kind=="tant"||r->kind=="film")&&r->v_max&&*r->v_max!=0) {
                auto vs=pin_volts(sc->circuit,ref,power_policy);
                if(vs.empty()){res.unspecced.push_back(key+" ("+part->value+") — cap rail unresolved");continue;}
                double rail=*std::max_element(vs.begin(),vs.end());if(rail<=0)continue;
                ++res.checked;double derate=capacitor_derating(*r,policy),need=derate*rail;
                if(*r->v_max<need)part_finding(res,key,"CAP_V "+key+" ("+part->value+", LCSC "+lcsc+"): "+g(*r->v_max)+"V "+(r->dielectric&&!r->dielectric->empty()?*r->dielectric:r->kind)+" on a "+g(rail)+"V rail — needs >= "+g(derate)+"x = "+g(need)+"V (margin "+f(*r->v_max/rail,1)+"x). Pick a higher-V part or c.waive_part_rule("+repr(ref)+", reason)");
            } else if(r->kind=="res"&&r->p_max&&*r->p_max!=0) {
                auto ohms=parse_resistor_ohms(part->value);auto vs=pin_volts(sc->circuit,ref,power_policy);
                if(ohms&&*ohms>0&&vs.size()>=2) {
                    double dv=*std::max_element(vs.begin(),vs.end())-*std::min_element(vs.begin(),vs.end()),p=dv*dv / *ohms;
                    ++res.checked;
                    if(p>policy.derate_res * *r->p_max)res.notes.push_back("RES_POWER(advisory) "+key+" ("+part->value+"): P~="+f(p*1000,0)+"mW across "+g(dv)+"V > "+g(policy.derate_res)+"x rated "+f(*r->p_max*1000,0)+"mW — verify it is not a full-rail dissipator");
                }
            }
        }
    }
    std::map<std::pair<std::string,std::string>,std::string> lcsc;
    for(const auto& s:sheets)for(const auto& p:s.circuit.parts)lcsc[{s.name,p.ref}]=trim(field(p,"LCSC"));
    for(auto r:sorted_regs(power)) {
        auto it=lcsc.find({r->sheet,r->ref});auto rating=find(ratings,it==lcsc.end()?std::string{}:it->second);
        auto key=r->sheet+":"+r->ref;
        if(!rating||!rating->vin_max){res.unspecced.push_back(key+" ("+r->value+") — no vin_max rating");continue;}
        auto v=rail_volts(r->vin,power_policy);
        if(!v){res.unspecced.push_back(key+" ("+r->value+") — input rail "+r->vin+" unresolved");continue;}
        ++res.checked;
        if(*rating->vin_max<*v)part_finding(res,key,"IC_VIN "+key+" ("+r->value+"): abs-max input "+g(*rating->vin_max)+"V < its rail "+r->vin+" "+g(*v)+"V — over-stress");
    }
    return res;
}
PartCheckResult analyze_part_rules(const std::vector<ProjectCircuit>& sheets,const PartRatingsTable& ratings,const PartRulePolicy& policy,const PowerPolicy& power_policy) {
    return analyze_part_rules(sheets,analyze_power(sheets,power_policy),ratings,policy,power_policy);
}
std::string part_rules_report(const PartCheckResult& res,const PartRulePolicy& p) {
    std::vector<std::string> ls{"schgen per-part rule engine (ratings vs netlist usage)",std::string(78,'='),"",
        "enforced: CAP_VOLTAGE (MLCC "+g(p.derate_mlcc)+"x / C0G "+g(p.derate_c0g)+"x / elec "+g(p.derate_elec)+"x rail), IC_VIN (abs-max >= input rail). advisory: RES_POWER ("+g(p.derate_res)+"x).",
        std::to_string(res.checked)+" part-checks evaluated; ratings from schgen/ratings.py (LCSC-keyed)."};
    if(!res.waived.empty()){ls.insert(ls.end(),{"","author waivers, verbatim ("+std::to_string(res.waived.size())+"):"});for(const auto& [k,v]:sorted(res.waived))ls.push_back("  "+pad(k,22)+" "+v.second);}
    auto section=[&](const std::vector<std::string>& entries,const std::string& heading,const std::string& prefix){auto rows=entries;std::sort(rows.begin(),rows.end());if(!rows.empty()){ls.insert(ls.end(),{"",heading+" ("+std::to_string(rows.size())+"):"});for(const auto& s:rows)ls.push_back(prefix+s);}};
    section(res.notes,"notes / advisory","  + ");section(res.unspecced,"UNSPEC — reported, NOT failing","  ? ");
    if(res.findings.empty())ls.insert(ls.end(),{"","errors: none"});else section(res.findings,"ERRORS","  ERROR: ");
    ls.insert(ls.end(),{"",std::string("PART RULES: ")+(res.ok()?"PASS":"FAIL")+" ("+std::to_string(res.checked)+" checks, "+std::to_string(res.findings.size())+" findings, "+std::to_string(res.unspecced.size())+" unspeced, "+std::to_string(res.waived.size())+" waived)"});return join(ls);
}
PartCheckResult run_part_checks(const std::vector<ProjectCircuit>& sheets,const std::filesystem::path& dir,const PowerCheckResult* power,const PartRatingsTable& ratings,const PartRulePolicy& policy,const PowerPolicy& pp) {
    auto res=power?analyze_part_rules(sheets,*power,ratings,policy,pp):analyze_part_rules(sheets,ratings,policy,pp);
    publish(dir/"part_rules.txt",part_rules_report(res,policy)+"\n");return res;
}
JsonNode part_result_json(const PartCheckResult& res) {
    return obj({{"findings",strings(res.findings)},{"notes",strings(res.notes)},{"unspecced",strings(res.unspecced)},{"waived",waiver_json(res.waived)},{"checked",j(double(res.checked))}});
}
JsonNode part_ratings_json(const PartRatings& r) {
    return obj({{"kind",j(r.kind)},{"v_max",opt(r.v_max)},{"i_max",opt(r.i_max)},{"p_max",opt(r.p_max)},{"tol",opt(r.tol)},{"dielectric",opt(r.dielectric)},{"temp_max",opt(r.temp_max)},{"vin_max",opt(r.vin_max)},{"source",j(r.source)}});
}

PartCheckResult part_result_from_json(const JsonNode& n) {
    object_shape(n,{"findings","notes","unspecced","waived","checked"},"part result");
    PartCheckResult r;r.findings=read_strings(member(n,"findings"));r.notes=read_strings(member(n,"notes"));r.unspecced=read_strings(member(n,"unspecced"));r.waived=read_waivers(member(n,"waived"));r.checked=count(member(n,"checked"));return r;
}

} // namespace schgen
