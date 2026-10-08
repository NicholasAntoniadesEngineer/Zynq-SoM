#include "schgen/board_pcb.hpp"
#include "schgen/pcb_verification.hpp"
#include "fresh_project_schematic.hpp"
#include <fstream>
#include <iostream>
#include <iterator>

namespace {
std::string read(const std::filesystem::path& path) {
    std::ifstream input(path, std::ios::binary);
    if (!input) throw std::runtime_error("cannot read " + path.string());
    return {std::istreambuf_iterator<char>(input), std::istreambuf_iterator<char>()};
}
void equal(const std::filesystem::path& actual, const std::filesystem::path& expected) {
    if (read(actual) != read(expected)) throw std::runtime_error("publication differs: " + actual.string());
}
}

int main(int argc, char** argv) {
    using namespace schgen;
    try {
        if (argc != 3) throw std::runtime_error("usage: board_live_contracts REPOSITORY SCRATCH");
        const auto root = std::filesystem::absolute(argv[1]);
        if (PcbVerificationResult{}.ok()) throw std::runtime_error("unexecuted aggregate cannot pass");
        for (const auto* project : {"carrier", "devkit_mini"}) {
            const auto paths = resolve_project_paths(root, std::filesystem::path(project));
            const auto schematic=test::fresh_project_schematic(paths,load_project_circuits(paths));
            const auto missing=schematic.parent_path()/"missing-explicit-input.kicad_sch";
            bool missing_rejected=false;
            try{(void)prepare_board_pcb(paths,{},{},missing);}
            catch(const std::exception& error){missing_rejected=std::string(error.what()).find(missing.filename().string())!=std::string::npos;}
            if(!missing_rejected)throw std::runtime_error("missing explicit schematic silently fell back or lost its diagnostic");
            const auto stage = prepare_board_pcb(paths,{},{},schematic);
            const auto repeated = prepare_board_pcb(paths,{},{},schematic);
            if(stage.placement.model.board_w!=repeated.placement.model.board_w ||
               stage.placement.model.board_h!=repeated.placement.model.board_h ||
               stage.emission.pcb!=repeated.emission.pcb)
                throw std::runtime_error(std::string(project)+": two fresh in-process builds differ");
            if(std::string(project)=="carrier"){
                auto strict=pcb_emit_policy(stage.inputs.floorplan.project);
                strict.thermal_credit_needs={{"LM61460",1000,10.0,{"F.Cu","B.Cu"}}};
                const auto changed=render_pcb(stage.placement.model,strict);
                if(changed.pcb!=stage.emission.pcb)
                    throw std::runtime_error("thermal evidence reporting must not change emitted copper");
                bool warning=false;
                for(const auto& message:changed.diagnostics)
                    if(message.find("THERMAL VIA SHORTFALL")!=std::string::npos && message.find("/1000 GND vias")!=std::string::npos)warning=true;
                if(!warning)throw std::runtime_error("stricter thermal evidence must report its actual via shortfall");
            }
            const double reference_area=std::string(project)=="carrier"?168.*163.:98.*98.;
            if(stage.placement.model.board_w*stage.placement.model.board_h>reference_area)
                throw std::runtime_error(std::string(project)+": qualified reference area regressed");
            const auto output = std::filesystem::path(argv[2]) / project;
            std::filesystem::create_directories(output);
            std::filesystem::copy_file(paths.project_root / "Zynq_Carrier.kicad_pro",
                output / "Zynq_Carrier.kicad_pro", std::filesystem::copy_options::overwrite_existing);
            publish_board_pcb(stage, output);
            const auto existing=read_pcb_project(paths.project_root/"Zynq_Carrier.kicad_pro");
            const auto policy=pcb_emit_policy(stage.inputs.floorplan.project);
            if(read(output/"Zynq_Carrier.kicad_pcb")!=stage.emission.pcb||
               read(output/"Zynq_Carrier.kicad_pro")!=render_pcb_project(stage.placement.model,"Zynq_Carrier.kicad_pro",&existing,policy)||
               read(output/"docs/FLOORPLAN.md")!=stage.placement.floorplan.documents.markdown||
               read(output/"docs/FLOORPLAN.svg")!=stage.placement.floorplan.documents.svg)
                throw std::runtime_error("publication differs from current generated artifacts");
            equal(output / "manufacturing/Zynq_Carrier_pcb.kicad_dru",
                root / "native/tests/data/pcb_emit" / (std::string(project) + ".kicad_dru"));
            PcbEmittedBoard emitted{(output / "Zynq_Carrier.kicad_pcb").string(),
                sexpr_loads(read(output / "Zynq_Carrier.kicad_pcb")), true};
            const auto checks = verify_pcb_geometry(stage, emitted, 0);
            if (!checks.ok()) throw std::runtime_error(std::string(project) + ": independent PCB aggregate failed");
            const auto repeated_checks=verify_pcb_geometry(repeated,emitted,0);
            const auto report = [&](const std::string& text, const std::string& again) {
                if(text!=again)throw std::runtime_error("current independent reports are not reproducible");
            };
            report(checks.ratsnest.summary(),repeated_checks.ratsnest.summary());
            report(checks.placement.placement_contract.summary(),repeated_checks.placement.placement_contract.summary());
            report(checks.placement.placement_flow.summary(),repeated_checks.placement.placement_flow.summary());
            report(checks.placement.coverage_report.text,repeated_checks.placement.coverage_report.text);
            report(checks.placement.composition.text(),repeated_checks.placement.composition.text());
            report(checks.return_stitch.summary(),repeated_checks.return_stitch.summary());
            report(checks.escape_lanes.summary(),repeated_checks.escape_lanes.summary());
            report(checks.fanout.summary(),repeated_checks.fanout.summary());
            auto invalid=stage;
            invalid.placement.model.insts.at(0).x=-1000.;
            if(verify_pcb_geometry(invalid,emitted,0).ok())throw std::runtime_error("off-board mutation passed independent geometry aggregate");
            if (checks.return_path.ok || checks.return_path.n_fail() != 29)
                throw std::runtime_error("fixed SoM return-path debt must remain visible");
            emitted.exists = false;
            bool rejected = false;
            try { verify_pcb_geometry(stage, emitted, 0); }
            catch (const ProjectError&) { rejected = true; }
            if (!rejected) throw std::runtime_error("missing emitted board must fail");
            std::cout << project << ": fresh extraction, reproducible placement/publication, area non-regression and independent geometry PASS\n";
        }
        return 0;
    } catch (const std::exception& error) {
        std::cerr << error.what() << '\n';
        return 1;
    }
}
