#include "board_pipeline_internal.hpp"
#include "schgen/native_render.hpp"
#include "schgen/symbol_law.hpp"
#include "schgen/diagram.hpp"
#include "schgen/constraints.hpp"
#include "schgen/authoring_gates.hpp"
#include "schgen/project_authoring.hpp"
#include <cstdlib>
#include <unistd.h>

namespace schgen::board_pipeline_detail {
namespace {
struct Scratch {
    fs::path path;
    Scratch(){auto name=(fs::temp_directory_path()/"schgen_board_pipeline_XXXXXX").string();if(!::mkdtemp(name.data()))throw ProjectError("cannot create board pipeline scratch");path=name;}
    ~Scratch(){std::error_code e;fs::remove_all(path,e);}
};
}
void schematic_stage(Context& c){
    c.attempt("subsystem_structure",[&]{const auto r=check_subsystem_structure(c.paths.repository_root/"subsystems",native_subsystem_factories(make_authoring_context(c.paths.repository_root)),AuthoringPackageMode::native_assets);
        c.report("subsystem_structure.txt",r.summary());c.gate("subsystem_structure",r.ok(),r.summary());});
    c.attempt("carrier_structure",[&]{if(!c.authored)throw ProjectError("actual native authoring snapshot unavailable");
        const auto r=check_carrier_structure(c.out/"subsystems",c.paths.repository_root/"subsystems",c.authored->factories,AuthoringPackageMode::native_assets);
        c.report("carrier_structure.txt",r.summary());c.gate("carrier_structure",r.ok(),r.summary());});
    std::vector<BoardSheetInput> inputs;std::vector<std::string> cc_reports,sheet_reports;
    bool cc_ok=true,sheet_ok=true,render_ok=true;
    Scratch scratch;
    for(const auto& sc:c.circuits){
        try {
            const auto electrical=check_circuit_electrical(sc.circuit,c.library);
            if(!electrical.ok()){sheet_ok=false;sheet_reports.push_back(sc.name+": "+electrical.summary());continue;}
            auto page=place_and_route_schematic(sc.circuit,c.library);
            const auto cc=check_board_sheet_cc(sc.circuit,page.placement,page.routed,[&](const std::string& id)->const SymbolDef&{return c.library.get(id);});
            cc_ok=cc_ok&&cc.ok();cc_reports.push_back(cc.summary());
            SchematicDesign d;d.circuit=sc.circuit;const auto& p=page.placement;
            d.parts=p.parts;d.powers=p.powers;d.hlabels=p.hlabels;d.llabels=p.llabels;d.no_connects=p.no_connects;d.paper=p.paper;apply_schematic_route(d,page.routed);
            const auto sch=scratch.path/(sc.name+".kicad_sch");
            publish_text(sch,emit_schematic(d,[&](const std::string& id)->const SymbolDef&{return c.library.get(id);}).text);
            publish_text(sch.parent_path()/(sc.name+".kicad_pro"),board_project_json(parse_json_text("{}"),sc.name));
            const auto net=check_netlist(sc.circuit,sch,c.options.extraction);
            const auto erc=run_kicad_erc(sch,c.options.extraction);
            c.report(sc.name+".erc.rpt",strip_board_report_timestamp(erc.report.empty()?erc.stderr_text:erc.report));
            const auto vis=check_visual_geometry(page.geometry);
            const bool ok=net.ok&&erc.exit_code==0&&vis.ok;sheet_ok=sheet_ok&&ok;
            sheet_reports.push_back(sc.name+": netlist="+(net.ok?"PASS":"FAIL")+" erc="+(erc.exit_code==0?"PASS":"FAIL")+" visual="+(vis.ok?"PASS":"FAIL")+" paper="+p.paper+"\n"+net.summary()+"\n"+vis.summary());
            if(!c.options.no_render)try{NativeRenderOptions ro;ro.kicad_cli=c.options.extraction.kicad_cli;render_sheet_to_png(sch,c.renders/(sc.name+".png"),300,ro);}catch(const std::exception& e){render_ok=false;sheet_reports.push_back(sc.name+": render FAILED: "+e.what());}
            const auto band=std::find_if(c.index.begin(),c.index.end(),[&](const auto& x){return x.first==sc.name;});
            if(band==c.index.end())throw ProjectError("missing stable reference band "+sc.name);
            inputs.push_back({sc.circuit,band->second,BoardPreparedSheet{std::move(page.placement),std::move(page.routed)}});
        }catch(const std::bad_alloc&){throw;}catch(const std::exception& e){sheet_ok=false;cc_ok=false;sheet_reports.push_back(sc.name+": place/route/gate FAIL: "+e.what());}
    }
    c.gate("sheet_gates",sheet_ok&&inputs.size()==c.circuits.size(),join(sheet_reports,"\n"));
    c.status("sheet_render",c.options.no_render?BoardGateStatus::skipped:render_ok?BoardGateStatus::passed:BoardGateStatus::failed,c.options.no_render?"--no-render":"per-sheet native PDF rasterization");
    c.report("cc_gate.txt",join(cc_reports,"\n"));c.gate("cc",cc_ok&&inputs.size()==c.circuits.size(),join(cc_reports,"\n"));
    c.attempt("symbol_law",[&]{const auto r=check_symbol_law(c.sheets,c.library);c.report("symbol_law.txt",r.summary());c.gate("symbol_law",r.ok(),r.summary());});
    c.attempt("link",[&]{c.som=load_som_interface(c.paths.som_interface_file);c.link=link_sheets(c.sheets,parse_json_file(c.paths.som_interface_file.string()),parse_json_file((c.paths.project_root/"som_mapping.json").string()));
        c.report("link_report.txt",c.link->report());c.gate("link",c.link->ok(),c.link->report());});
    c.attempt("constraints",[&]{write_layout_constraints(c.circuits,c.paths.project_root/"research/si_spec.json",c.manufacturing);c.gate("constraints",true,"layout rules and net-class CSV published");});
    c.attempt("diagram",[&]{if(!c.link)throw ProjectError("link result unavailable");write_block_diagram(*c.link,link_som_nets_from_json(parse_json_file(c.paths.som_interface_file.string())),c.docs/"block_diagram.svg");c.gate("diagram",true,"block diagram published");});
    c.attempt("board_schematic",[&]{if(inputs.empty())throw ProjectError("no prepared sheets");
        BoardSchematicOptions o;o.root_name="Zynq_Carrier";o.sheet_subdir="schematic";o.reports_dir=c.reports;o.extraction=c.options.extraction;o.netlist_workers=c.options.netlist_workers;
        c.schematic=build_board_schematic(inputs,c.library,c.out,o);
        c.gate("board_schematic",c.schematic->ok()&&inputs.size()==c.circuits.size(),c.schematic->report);
        c.gate("root_erc",c.schematic->board.erc_ran&&c.schematic->board.erc_exit_code==0,"root ERC informational; see board.erc.rpt");
        JsonNode bands;bands.kind=JsonKind::Object;for(const auto& [name,band]:c.index)bands.object_value.emplace_back(name,number(band));
        publish_text(c.out/"sheet_index.json",json(bands)+"\n");});
}
}
