#include "board_pipeline_internal.hpp"
#include "schgen/board_policy.hpp"
#include "schgen/pcb_drc.hpp"
#include "schgen/assembly_documents.hpp"
#include "schgen/ratsnest_documents.hpp"
#include "schgen/thermal_checks.hpp"
#include "schgen/copper_debt.hpp"
#include "schgen/manufacturing_checks.hpp"
#include "schgen/process.hpp"
#include <cmath>
#include <climits>
#include <cstdlib>
#include <unistd.h>

namespace schgen::board_pipeline_detail {
namespace {
std::optional<int> baseline(const fs::path& p){try{const auto j=parse_json_file(p.string());const auto* n=object_field(j,"starved_baseline");
    if(!n||n->kind!=JsonKind::Number||!std::isfinite(n->number_value)||n->number_value<0||n->number_value>INT_MAX||std::floor(n->number_value)!=n->number_value)return {};
    return static_cast<int>(n->number_value);}catch(const std::bad_alloc&){throw;}catch(const std::exception&){return {};}}
PcbDrcResult drc(const fs::path& pcb,const std::string& executable,bool warnings){
    auto pattern=(fs::temp_directory_path()/"schgen_pipeline_drc_XXXXXX").string();if(!::mkdtemp(pattern.data()))throw ProjectError("cannot create DRC scratch");
    struct Cleanup{fs::path p;~Cleanup(){std::error_code e;fs::remove_all(p,e);}}cleanup{pattern};
    const auto report=cleanup.p/"drc.json";auto args=pcb_drc_arguments(pcb,report,warnings);args[0]=executable;
    const auto process=run_process(args,std::chrono::minutes{5});return parse_pcb_drc_report(read(report),process);
}
}
void pcb_stages(Context& c){
    const auto pcb_path=c.out/"Zynq_Carrier.kicad_pcb";
    const auto report_root=c.out==c.paths.project_root?c.paths.repository_root:c.out;
    c.attempt("pcb",[&]{if(!c.schematic||!c.link||!c.link->ok())throw ProjectError("current schematic/valid link required; refusing stale board inputs");
        BoardPcbStage stage;stage.circuits=c.circuits;
        stage.inputs=load_board_inputs(c.paths,c.circuits,*c.link,extract_netlist(c.schematic->root_path,c.options.extraction),c.options.pcb);
        stage.inputs.floorplan.sheet_index=c.index;
        if(c.options.native_policy){
            const auto policy=configure_native_board_policy(c.options,c.paths,stage.inputs.floorplan);
            c.report("native_policy.txt",policy.report());
            c.gate("native_policy",policy.providers_complete(),policy.report());
        }
        stage.placement=build_pcb_model(stage.inputs);
        // One receipt owns all actual plan/zone/placement work, not the legacy
        // fallback prefix. Import before emission so failures retain work done.
        c.inbox.merge_once("pcb/placement",pcb_placement_accounting(stage.placement));
        stage.emission=render_pcb(stage.placement.model,pcb_emit_policy(stage.inputs.floorplan.project));
        c.inbox.merge_once("pcb/emission",NativeAccountingBatch{{},stage.emission.fallback_events});
        c.pcb=std::move(stage);publish_board_pcb(*c.pcb,c.out);c.pcb_published=true;
        if(c.pcb->placement.model.escape_plan_record){auto sidecar=*c.pcb->placement.model.escape_plan_record;
            JsonNode meta;meta.kind=JsonKind::Object;for(const auto* key:{"worst_cover_mm","vias","coverage_mm","escape_region","plane","coexistence","som_interface_sha256","constants"})if(const auto* value=object_field(c.pcb->placement.model.escape_meta,key))meta.object_value.emplace_back(key,*value);
            sidecar.object_value.emplace_back("escape_meta",meta);publish_text(c.out/"escape_block.json",json(sidecar)+"\n");}
        c.gate("pcb",true,std::to_string(c.pcb->placement.model.placed)+" footprints; deferred: "+join(c.pcb->placement.model.deferred));});
    c.attempt("pcb_drc",[&]{if(!c.pcb_published)throw ProjectError("no board emitted this invocation");
        auto r=drc(pcb_path,c.options.extraction.kicad_cli,true);const auto errors=r.n_errors?*r.n_errors:drc(pcb_path,c.options.extraction.kicad_cli,false).n_violations;
        const auto report=std::to_string(errors)+" non-unrouted errors; "+std::to_string(r.n_unconnected)+" unrouted (expected); "+r.stderr_tail;
        c.report("pcb_drc.txt",report);c.gate("pcb_drc",errors==0,report);});
    c.attempt("pcb_geometry",[&]{if(!c.pcb_published)throw ProjectError("no board emitted this invocation");
        const auto bp=c.options.fanout_baseline.empty()?c.paths.repository_root/"carrier/reports/fanout_baseline.json":c.options.fanout_baseline;
        PcbEmittedBoard emitted{pcb_path.string(),sexpr_loads(read(pcb_path)),true};
        c.geometry=verify_pcb_geometry(*c.pcb,emitted,baseline(bp));const auto& r=*c.geometry;
        const auto gate=[&](const std::string& name,bool ok,const std::string& report){c.report(name+".txt",report);c.gate(name,ok,report);};
        gate("ratsnest",r.ratsnest.ok,r.ratsnest.summary());gate("placement_mech",r.mechanical.ok,r.mechanical.summary());
        gate("connector_model",r.connector_models.ok,r.connector_models.summary());gate("connector_spacing",r.connector_spacing.ok,r.connector_spacing.summary());
        gate("refdes_silk",r.refdes.ok,"emitted-board refdes overlaps checked");
        gate("placement_contract",r.placement.placement_contract.ok,r.placement.placement_contract.summary());
        gate("placement_flow",r.placement.placement_flow.ok,r.placement.placement_flow.summary());
        gate("contract_coverage",r.placement.coverage_report.violated==0,r.placement.coverage_report.text);
        gate("floorplan_composition",r.placement.composition.hard_red==0&&r.placement.composition.soft_red==0,r.placement.composition.text());
        gate("return_stitch",r.return_stitch.ok,r.return_stitch.summary());gate("escape_lanes",r.escape_lanes.ok,r.escape_lanes.summary());
        gate("return_path",r.return_path.ok,"REPORT-ONLY: fixed SoM interface; remediation judged by return_stitch.\n"+r.return_path.summary());
        gate("fanout",r.fanout.ok,r.fanout.summary());
        if(r.fanout.ok){const auto old=baseline(bp);const auto n=old?std::min(*old,r.fanout.n_starved):r.fanout.n_starved;
            const auto destination=c.out==c.paths.project_root?bp:c.reports/"fanout_baseline.json";
            publish_text(destination,"{\n \"starved_baseline\": "+std::to_string(n)+",\n \"note\": \"fan-out ratchet ceiling — may only DECREASE; a build whose starved count exceeds this FAILS. Reach 0 to promote the gate to HARD.\"\n}\n");}
        c.gate("pcb_geometry",r.ok(),"independent final-board gates complete");});
    c.attempt("assembly",[&]{if(!c.pcb||!c.power)throw ProjectError("PCB/power result unavailable");
        JsonNode result;try{result=run_assembly_documents(c.pcb->placement.model,*c.power,load_project_config(c.paths).name,c.manufacturing/"ASSEMBLY.md",c.renders/"assembly",pcb_emit_policy(c.pcb->inputs.floorplan.project));}
        catch(...){c.fallbacks.record("assembly_generation_failed");throw;}
        const auto v=assembly_verdict(result,report_root);c.gate("assembly",v.first,v.second);});
    c.attempt("ratsnest_images",[&]{if(!c.pcb||!c.geometry)throw ProjectError("PCB/geometry unavailable");const auto r=run_ratsnest_documents(c.pcb->placement.model,c.out,&c.geometry->nets,&c.geometry->edges);c.gate("ratsnest_images",true,ratsnest_document_summary(r,report_root));});
    c.attempt("thermal",[&]{if(!c.power)throw ProjectError("power result unavailable");const auto r=run_thermal_checks(c.circuits,c.reports,&*c.power,c.pcb_published?std::optional<fs::path>{pcb_path}:std::nullopt,c.paths.repository_root);c.gate("thermal",r.ok(),thermal_report(r));});
    c.attempt("copper_debt",[&]{auto sources=author_copper_debt_sources(c.paths.repository_root);
        const auto scope=c.paths.project_root.filename().string();for(auto& x:sources.circuits)if(x.scope==scope){const auto it=std::find_if(c.circuits.begin(),c.circuits.end(),[&](const auto& s){return s.name==x.sheet;});if(it!=c.circuits.end())x.circuit=it->circuit;}
        if(c.pcb)sources.emission=pcb_emit_policy(c.pcb->inputs.floorplan.project);
        std::optional<ThermalCopper> copper;if(c.pcb_published)copper=scan_thermal_copper(pcb_path);
        const auto r=analyze_copper_debt(copper?&*copper:nullptr,sources);c.report("copper_debt.txt",copper_debt_report(r));c.gate("copper_debt",true,copper_debt_report(r));});
    c.attempt("cpl",[&]{if(!c.pcb_published)throw ProjectError("PCB unavailable");const auto destination=c.manufacturing/"Zynq_Carrier_cpl.csv";
        const auto temporary=c.manufacturing/"Zynq_Carrier_cpl.pipeline.csv";
        if(fs::exists(temporary))throw ProjectError("CPL temporary destination already exists");
        const auto r=run_process({c.options.extraction.kicad_cli,"pcb","export","pos","--format","csv","--units","mm","--side","both","--output",temporary.string(),pcb_path.string()},std::chrono::seconds{120});
        if(r.exit_code!=0)throw ProjectError("CPL export failed: "+r.stderr_text);const auto bytes=read(temporary);publish_text(destination,bytes);fs::remove(temporary);c.gate("cpl",true,destination.string());});
    c.attempt("fab_profile",[&]{if(!c.pcb_published)throw ProjectError("PCB unavailable");const auto r=run_manufacturing_fab(c.reports,pcb_path,c.manufacturing/"Zynq_Carrier_pcb.kicad_dru",c.out/"Zynq_Carrier.kicad_pro");c.gate("fab_profile",r.ok,r.report());});
    c.attempt("stage_movement",[&]{if(!c.pcb)throw ProjectError("tracker did not run");const auto& moves=c.pcb->placement.model.stage_moves;
        for(const auto* name:{"l4_pull","edge_seat","breathe","refit_facing","reorder","corridor_eviction","instantiate","escape_copper"})if(!moves.count(name))throw ProjectError(std::string("tracker missing stage ")+name);
        if(moves.at("instantiate")!=0||moves.at("escape_copper")!=0)throw ProjectError("frozen stage moved a part");
        c.gate("stage_movement",true,"complete native movement tracker; frozen stages unchanged");});
}
}
