#include "schgen/example_devkit.hpp"
#include "schgen/project_outputs.hpp"
#include "schgen/native_render.hpp"
#include <algorithm>

namespace schgen {
bool ExampleDevkitResult::ok() const {
    return standalone.size()==4 && hierarchy.per_sheet.size()==4 && !hierarchy.root_path.empty() &&
        std::all_of(standalone.begin(),standalone.end(),[](const auto& sheet){return sheet.ok();}) && hierarchy.ok();
}

ExampleDevkitResult build_example_devkit(const std::vector<CircuitSheetIr>& sheets,SymbolLibrary& library,
                                        const std::filesystem::path& output,const ExampleDevkitOptions& options) {
    if(output.empty())throw ProjectError("example devkit output directory must be explicit");
    const auto& defs=example_devkit_definitions();
    if(sheets.size()!=defs.size())throw ProjectError("example devkit requires exactly four sheets (not the twelve-sheet project)");
    for(std::size_t i=0;i<defs.size();++i)if(sheets[i].name!=defs[i].name)
        throw ProjectError("example devkit sheet order must be usb_pd, usbc_otg, microsd, uart_bridge");
    ExampleDevkitResult result;
    const auto schematic=output/"schematic",reports=output/"reports";
    // Match the legacy example: render the final uniquified hierarchy children,
    // not the temporary standalone sheets that the hierarchy is about to replace.
    SubsystemBuildOptions standalone;standalone.extraction=options.extraction;standalone.no_render=true;
    std::vector<BoardSheetInput> board;
    std::string cc_report="Four-sheet example connectivity checks\n";
    for(std::size_t i=0;i<sheets.size();++i) {
        auto checked=build_subsystem_sheet(sheets[i],library,schematic,standalone);
        result.report+=checked.report;
        cc_report+=sheets[i].name+": "+(checked.cc_ok?"PASS":"FAIL")+"\n";
        result.standalone.push_back(std::move(checked));
        board.push_back({sheets[i],static_cast<std::int64_t>(i+1),std::nullopt});
    }
    BoardSchematicOptions hierarchy;hierarchy.root_name="devkit_mini";hierarchy.sheet_subdir="schematic";
    hierarchy.reports_dir=reports;hierarchy.extraction=options.extraction;hierarchy.netlist_workers=options.netlist_workers;
    result.hierarchy=build_board_schematic(board,library,output,hierarchy);
    result.report+=result.hierarchy.report+"\n";
    if(!options.no_render) {
        const auto renders=output/"renders";std::filesystem::create_directories(renders);
        NativeRenderOptions render;render.kicad_cli=options.extraction.kicad_cli;
        for(std::size_t i=0;i<sheets.size();++i)try {
            render_sheet_to_png(schematic/(sheets[i].name+".kicad_sch"),renders/(sheets[i].name+".png"),300,render);
            result.standalone[i].rendered=true;
        }catch(const std::bad_alloc&){throw;}catch(const std::exception& error){
            result.report+="render "+sheets[i].name+" FAILED (advisory): "+error.what()+"\n";
        }
    }
    result.report+="DEVKIT: "+std::string(result.ok()?"PASS":"FAIL")+" (4 library sheets)\n";
    std::filesystem::create_directories(reports);
    publish_text(reports/"cc_gate.txt",cc_report);
    publish_text(reports/"example_devkit.txt",result.report);
    return result;
}
} // namespace schgen
