#include "board_aux_frozen_identity.hpp"
#include "schgen/project_authoring.hpp"
#include "schgen/catalog.hpp"
#include "schgen/validation.hpp"
#include "schgen/part_checks.hpp"
#include "schgen/bom_values.hpp"
#include "schgen/pin_completeness.hpp"
#include "schgen/footprint_pads.hpp"
#include "schgen/placement_requirements.hpp"
#include "schgen/component_basis.hpp"
#include "schgen/design_rules.hpp"
#include <iostream>
namespace schgen::board_pipeline_detail { std::string json(const JsonNode&); }
using namespace schgen;
void require(bool ok,const std::string& why){if(!ok)throw std::runtime_error(why);}
void verify_component_basis(const CircuitSheetIr& c){
    // Project the actual authority, never synthesize expected values from c.
    // Keep every obligation on this sheet, including ports and other passives.
    const auto& production=default_component_basis_policy();
    ComponentBasisPolicy focused;
    std::set<std::string> names;
    for(const auto& s:production.sheets)
        if(s.scope=="carrier"&&s.name=="board_aux")focused.sheets.push_back(s);
    for(const auto& u:production.uses)
        if(u.scope=="carrier"&&u.sheet=="board_aux"){
            focused.uses.push_back(u);names.insert(u.declaration);
        }
    for(const auto& d:production.declarations)
        if(names.count(d.name))focused.declarations.push_back(d);
    require(focused.sheets.size()==1&&!focused.uses.empty(),"missing production board_aux basis authority");
    const std::vector<ComponentBasisInput> live{{"carrier","board_aux",c}};
    const auto baseline=audit_component_basis(live,{"carrier"},focused);
    require(baseline.ok(),component_basis_report(baseline));
    auto is_c1=[](const auto& u){return u.target=="C1"&&u.attribute=="value";};
    require(std::count_if(focused.uses.begin(),focused.uses.end(),is_c1)==1,"unique C1 basis obligation");
    // Keep the real 100n declaration consumed by C2/C4; restore only C1's
    // old binding to reproduce the escaped production failure exactly.
    auto stale=focused;
    require(std::any_of(stale.declarations.begin(),stale.declarations.end(),[](const auto& d){
        return d.name=="carrier.board_aux.decap"&&d.value=="100n";
    }),"missing unchanged 100n authority for stale-binding mutant");
    std::find_if(stale.uses.begin(),stale.uses.end(),is_c1)->declaration="carrier.board_aux.decap";
    const auto stale_result=audit_component_basis(live,{"carrier"},stale);
    require(!stale_result.ok()&&std::any_of(stale_result.broken.begin(),stale_result.broken.end(),[](const auto& s){
        return s=="carrier/board_aux:C1.value: emitted 10u != carrier.board_aux.decap=100n";
    }),"real basis gate did not reject stale C1 binding specifically");
    auto reverted=live;
    for(auto& p:reverted.front().circuit.parts)if(p.ref=="C1")p.value="100n";
    const auto value_result=audit_component_basis(reverted,{"carrier"},focused);
    require(!value_result.ok()&&std::any_of(value_result.broken.begin(),value_result.broken.end(),[](const auto& s){
        return s.find("carrier/board_aux:C1.value: emitted 100n != ")==0;
    }),"real basis gate did not reject reverted C1 value");
    auto missing=focused;
    missing.uses.erase(std::remove_if(missing.uses.begin(),missing.uses.end(),is_c1),missing.uses.end());
    const auto missing_result=audit_component_basis(live,{"carrier"},missing);
    require(!missing_result.ok()&&std::any_of(missing_result.raw.begin(),missing_result.raw.end(),[](const auto& s){
        return s.find("carrier/board_aux:C1 -> ")==0;
    }),"real basis gate did not reject missing C1 obligation specifically");
    std::cout<<"PASS production component-basis board_aux projection and 3 gate mutations\n";
}
void verify_caps(const CircuitSheetIr& c){
    for(const auto& ref:{"C1","C2","C3","C4","C5"}){
        const auto p=std::find_if(c.parts.begin(),c.parts.end(),[&](const auto& part){return part.ref==ref;});
        require(p!=c.parts.end(),"missing frozen capacitor");
        const bool bulk=std::string(ref)=="C1"||std::string(ref)=="C3";
        const bool filter=std::string(ref)=="C5";
        require(p->lib_id=="Device:C"&&p->value==(bulk?"10u":filter?"100p":"100n")&&
            p->footprint==(bulk?"Capacitor_SMD:C_0805_2012Metric":"Capacitor_SMD:C_0603_1608Metric"),"capacitor identity");
        unsigned codes=0;
        for(const auto& f:p->fields)if(f.key=="LCSC"){
            ++codes;require(f.value==(bulk?"C15850":filter?"C14858":"C14663"),"capacitor BOM identity");
        }
        require(codes==1,"unique capacitor BOM identity");
    }
}
void cap_mutations(const CircuitSheetIr& c){
    auto reject=[](const auto& bad){bool caught=false;try{verify_caps(bad);}catch(const std::runtime_error&){caught=true;}require(caught,"capacitor mutation escaped");};
    for(const auto& ref:{"C1","C2","C3","C4","C5"}){
        auto bad=c;for(auto& p:bad.parts)if(p.ref==ref)p.value="1n";reject(bad);
    }
    auto bad=c;for(auto& p:bad.parts)if(p.ref=="C1")p.value="100n";reject(bad);
    bad=c;for(auto& p:bad.parts)if(p.ref=="C5")p.value="100n";reject(bad);
    bad=c;for(auto& p:bad.parts)if(p.ref=="C5")for(auto& f:p.fields)if(f.key=="LCSC")f.value="C14663";reject(bad);
    bad=c;for(auto& p:bad.parts)if(p.ref=="C1")p.footprint="Capacitor_SMD:C_0603_1608Metric";reject(bad);
    bad=c;for(auto& p:bad.parts)if(p.ref=="C1")for(auto& f:p.fields)if(f.key=="LCSC")f.value="C14663";reject(bad);
    bad=c;for(auto& p:bad.parts)if(p.ref=="C1")p.fields.push_back({"LCSC","C15850"});reject(bad);
}
void reference_mutations(const ProjectCircuit& sheet){
    const auto rejected=[](const ProjectCircuit& s){
        const auto r=analyze_part_rules({s});
        return std::any_of(r.findings.begin(),r.findings.end(),[](const auto& f){return f.find("PCA9306_REFERENCE ")==0;});
    };
    require(!rejected(sheet),"corrected reference topology rejected");
    auto original=sheet;
    for(auto& n:original.circuit.nets){
        if(n.name=="AUX_ISO_REF")n.name="AUX_ISO_EN";
        n.pins.erase(std::remove_if(n.pins.begin(),n.pins.end(),[](const auto& p){return p.ref=="C5"&&p.pin=="1";}),n.pins.end());
        for(auto& p:n.pins)if(p.ref=="U2"){
            if(p.pin=="7")p.pin="8";else if(p.pin=="8")p.pin="7";
        }
        if(n.name=="+3V3_AUX")n.pins.push_back({"C5","1"});
    }
    for(auto& p:original.circuit.parts)if(p.ref=="C5"){
        p.value="100n";for(auto& f:p.fields)if(f.key=="LCSC")f.value="C14663";
    }
    board_aux_frozen::Pins original_pins;
    for(const auto& n:original.circuit.nets)for(const auto& p:n.pins)original_pins.emplace(std::make_pair(p.ref,p.pin),n.name);
    require(original_pins==board_aux_frozen::pins(),"negative control is not the independently frozen original wiring");
    require(rejected(original),"original reference defect escaped");
    bool original_rejected=false;try{board_aux_frozen::verify(original.circuit);}catch(const std::runtime_error&){original_rejected=true;}
    require(original_rejected,"current pin-identity oracle accepted original defect");
    auto changed=original;
    // The EN resistor is not in series with the reference channel.
    for(auto& p:changed.circuit.parts)if(p.ref=="R4")p.value="200k";
    require(rejected(changed),"EN-only resistor change masked direct reference tie");
    changed=original;
    changed.circuit.waivers.push_back({"part_rule_waivers","U2","must not hide direct tie"});
    require(rejected(changed),"rating waiver masked topology defect");
    changed=original;
    for(auto& p:changed.circuit.parts)if(p.ref=="U2"){p.value="display renamed";p.pin_names.clear();p.fields.clear();}
    require(rejected(changed),"display/alias/BOM metadata masked catalog pinout");
    changed=original;
    // Same physical rail on both reference pins is not the independently
    // sequenced rail defect. This negative control is NOT isolation approval.
    for(auto& n:changed.circuit.nets)n.pins.erase(std::remove_if(n.pins.begin(),n.pins.end(),[](const auto& p){return p.ref=="U2"&&p.pin=="7";}),n.pins.end());
    for(auto& n:changed.circuit.nets)if(n.name=="+3V3_SC")n.pins.push_back({"U2","7"});
    require(!rejected(changed),"same physical reference rail falsely classified as inter-rail tie");
    std::cout<<"PASS corrected reference topology and original-defect/EN/waiver/metadata/same-rail controls; no transient qualification\n";
}
int main(int argc,char**argv){try{
    require(argc==4||argc==5,"usage: c1-contracts REPO CATALOG ASSET_ROOT [--emit]");
    const std::filesystem::path root=argv[1],assets=argv[3];require(open_part_catalog(argv[2]),"catalog");
    ProjectAuthoringInput input;input.context=make_authoring_context(root);
    const auto c=author_project_subsystem("carrier","board_aux",input);
    if(argc==5){require(std::string(argv[4])=="--emit","mode");std::cout<<board_pipeline_detail::json(authored_circuit_json(c))<<'\n';return 0;}
    board_aux_frozen::verify(c);board_aux_frozen::mutation_checks(c);
    const auto frozen=load_circuit_json(assets/"carrier/subsystems/board_aux/circuit.json");
    require(authoring_json_equal(authored_circuit_json(c),authored_circuit_json(frozen)),"derived circuit");
    verify_caps(c);cap_mutations(c);verify_component_basis(c);
    SymbolLibrary lib(root);require(check_circuit_electrical(c,lib).ok(),"ERM");
    const auto decaps=[&](const CircuitSheetIr& sheet){return check_design_rules({sheet},[&](const std::string& id)->const SymbolDef&{return lib.get(id);}).decap;};
    require(decaps(c).empty(),"live auxiliary supply/reference decoupling");
    auto missing_filter=c;
    for(auto& n:missing_filter.nets)n.pins.erase(std::remove_if(n.pins.begin(),n.pins.end(),[](const auto& p){return p.ref=="C5"&&p.pin=="1";}),n.pins.end());
    require(!decaps(missing_filter).empty(),"missing reference filter escaped design rules");
    auto all=load_project_circuits(resolve_project_paths(root,"carrier"));std::vector<ProjectCircuit> one;
    for(auto& s:all)if(s.name=="board_aux"){s.circuit=c;one.push_back(s);}
    require(one.size()==1,"one live auxiliary sheet");reference_mutations(one.front());
    auto power=analyze_power(all);require(power.ok(),"power");
    const auto ratings=analyze_part_rules(one,power);
    require(ratings.ok(),part_rules_report(ratings));
    require(std::find(ratings.unspecced.begin(),ratings.unspecced.end(),
        "board_aux:C5 (100p) — cap rail unresolved")!=ratings.unspecced.end(),
        "unresolved resistor-fed reference voltage must remain explicit, not inferred PASS");
    auto bom=check_bom_values(one,load_bom_value_catalog(root/"schgen/verify/data/lcsc_values.json"));require(bom.ok&&bom.unverified.empty(),"BOM values");
    require(check_pin_completeness(one,lib,load_nc_allowlist(root/"schgen/verify/data/nc_allowlist.json")).ok,"pins");
    FootprintResolutionOptions fp;fp.parts_dir=root/"parts";fp.library_tables={root/"som/fp-lib-table"};fp.kicad_footprint_root="/Applications/KiCad/KiCad.app/Contents/SharedSupport/footprints";
    require(check_footprint_pads(one,lib,fp).ok,"footprint coverage");
    const auto req=parse_placement_requirements(parse_json_file((assets/"carrier/subsystems/board_aux/placement_requirements.json").string()));
    require(req.ownership==carrier_surface_requirement_declaration("board_aux").required.ownership,"compiled declaration");
    std::cout<<"PASS C1 and reference-bias correction: independent historical identity plus exact reviewed rewiring; connectivity/feature and capacitor mutations rejected; C1-C5 exact value/package/BOM identities; live/derived parity, ERM, power, part rules, BOM values, pins, footprints, compiled manifest. Original reference defect remains rejected; transient isolation not certified.\n";
    return 0;
}catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}}
