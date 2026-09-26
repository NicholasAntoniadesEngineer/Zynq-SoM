#include "schgen/subsystem_build.hpp"
#include "schgen/board_pipeline.hpp"
#include "schgen/native_render.hpp"
#include "schgen/project_outputs.hpp"
#include "schgen/validation.hpp"

namespace schgen {
SubsystemBuildResult build_subsystem_sheet(const CircuitSheetIr& circuit,SymbolLibrary& library,
        const std::filesystem::path& output,const SubsystemBuildOptions& options){
    namespace fs=std::filesystem;
    if(output.empty())throw ProjectError("subsystem build output must be explicit");
    if(circuit.name.empty()||circuit.name=="."||circuit.name==".."||
       circuit.name.find_first_of("/\\")!=std::string::npos||circuit.name.find('\0')!=std::string::npos)
        throw ProjectError("unsafe subsystem build name");
    SubsystemBuildResult result;
    const auto electrical=check_circuit_electrical(circuit,library);
    result.electrical_ok=electrical.ok();result.report=electrical.summary()+"\n";
    if(!result.electrical_ok){result.report+="BUILD: FAIL ("+circuit.name+")\n";return result;}
    auto page=place_and_route_schematic(circuit,library);
    const auto resolve=[&](const std::string& id)->const SymbolDef&{return library.get(id);};
    const auto cc=check_board_sheet_cc(circuit,page.placement,page.routed,resolve);
    result.cc_ok=cc.ok();result.report+=cc.summary()+"\n";
    const auto& p=page.placement;SchematicDesign design;design.circuit=circuit;
    design.parts=p.parts;design.powers=p.powers;design.hlabels=p.hlabels;design.llabels=p.llabels;
    design.no_connects=p.no_connects;design.paper=p.paper;apply_schematic_route(design,page.routed);
    fs::create_directories(output);result.schematic=output/(circuit.name+".kicad_sch");
    publish_text(result.schematic,emit_schematic(design,resolve).text);
    publish_text(output/(circuit.name+".kicad_pro"),board_project_json(parse_json_text("{}"),circuit.name));
    const auto net=check_netlist(circuit,result.schematic,options.extraction);
    result.netlist_ok=net.ok;result.report+=net.summary()+"\n";
    const auto erc=run_kicad_erc(result.schematic,options.extraction);
    result.erc_ok=erc.exit_code==0;
    publish_text(output/(circuit.name+".erc.rpt"),strip_board_report_timestamp(erc.report.empty()?erc.stderr_text:erc.report));
    result.report+="ERC GATE: "+std::string(result.erc_ok?"PASS":"FAIL")+"\n";
    const auto visual=check_visual_geometry(page.geometry);
    result.visual_ok=visual.ok;result.report+=visual.summary()+"\n";
    if(!options.no_render)try{
        NativeRenderOptions render;render.kicad_cli=options.extraction.kicad_cli;
        render_sheet_to_png(result.schematic,output/(circuit.name+".png"),300,render);
        result.rendered=true;
    }catch(const std::bad_alloc&){throw;}catch(const std::exception& error){result.report+="render FAILED: "+std::string(error.what())+"\n";}
    result.report+="BUILD: "+std::string(result.ok()?"PASS":"FAIL")+" ("+circuit.name+")\n";
    publish_text(output/(circuit.name+".gates.txt"),result.report);
    return result;
}
}
