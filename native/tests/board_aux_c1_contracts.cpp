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
    // Keep the real 100n declaration consumed by C2/C4/C5; restore only C1's
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
        require(p->lib_id=="Device:C"&&p->value==(bulk?"10u":"100n")&&
            p->footprint==(bulk?"Capacitor_SMD:C_0805_2012Metric":"Capacitor_SMD:C_0603_1608Metric"),"capacitor identity");
        unsigned codes=0;
        for(const auto& f:p->fields)if(f.key=="LCSC"){
            ++codes;require(f.value==(bulk?"C15850":"C14663"),"capacitor BOM identity");
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
    bad=c;for(auto& p:bad.parts)if(p.ref=="C1")p.footprint="Capacitor_SMD:C_0603_1608Metric";reject(bad);
    bad=c;for(auto& p:bad.parts)if(p.ref=="C1")for(auto& f:p.fields)if(f.key=="LCSC")f.value="C14663";reject(bad);
    bad=c;for(auto& p:bad.parts)if(p.ref=="C1")p.fields.push_back({"LCSC","C15850"});reject(bad);
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
    auto all=load_project_circuits(resolve_project_paths(root,"carrier"));std::vector<ProjectCircuit> one;
    for(auto& s:all)if(s.name=="board_aux"){s.circuit=c;one.push_back(s);}
    auto power=analyze_power(all);require(power.ok(),"power");require(analyze_part_rules(one,power).ok(),"ratings");
    auto bom=check_bom_values(one,load_bom_value_catalog(root/"schgen/verify/data/lcsc_values.json"));require(bom.ok&&bom.unverified.empty(),"BOM values");
    require(check_pin_completeness(one,lib,load_nc_allowlist(root/"schgen/verify/data/nc_allowlist.json")).ok,"pins");
    FootprintResolutionOptions fp;fp.parts_dir=root/"parts";fp.library_tables={root/"som/fp-lib-table"};fp.kicad_footprint_root="/Applications/KiCad/KiCad.app/Contents/SharedSupport/footprints";
    require(check_footprint_pads(one,lib,fp).ok,"footprint coverage");
    const auto req=parse_placement_requirements(parse_json_file((assets/"carrier/subsystems/board_aux/placement_requirements.json").string()));
    require(req.ownership==carrier_surface_requirement_declaration("board_aux").required.ownership,"compiled declaration");
    std::cout<<"PASS C1-only: independent frozen18-reference/all-pin/NC identity; 3 connectivity/feature mutations and 9 capacitor mutations rejected; C1-C5 exact value/package/BOM identities; live/derived parity, ERM, power, ratings, BOM values, pins, footprints, compiled manifest. PCA9306 unchanged/not certified.\n";
    return 0;
}catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}}
