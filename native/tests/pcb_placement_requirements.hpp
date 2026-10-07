#pragma once
#include "experiment_metric_contracts.hpp"
#include "schgen/pcb_emit.hpp"
#include "schgen/pcb_placement_gates.hpp"
#include "schgen/ratsnest_gate.hpp"

// Optimisation acceptance is source identity + physical requirements + coherent
// stage/model transport, not the historical optimiser's chosen coordinates.
namespace placement_requirements_test {
using namespace schgen;
template<class Require>
void structure(const PcbPlacementInput& input,const PcbZoneResult& zones,
               const PcbPlacementResult& result,Require require) {
    const auto& model=result.model;
    const auto& plan=result.floorplan.plan;
    experiment_metric_contracts::identity(input,model.insts,require,true);
    require(std::isfinite(model.board_w)&&std::isfinite(model.board_h)&&model.board_w>0&&model.board_h>0,
            "positive finite outline");
    require(model.board_w==plan.board_w&&model.board_h==plan.board_h&&
            model.origin_x==input.floorplan.origin.first&&model.origin_y==input.floorplan.origin.second,
            "plan/model outline and coordinate frame agree");
    require(plan.som.w==input.floorplan.som.w&&plan.som.h==input.floorplan.som.h,
            "source module dimensions retained");
    std::set<std::string> board_refs,final_refs;
    std::map<std::string,std::string> selected_mirrors;
    for(const auto* blocks:{&plan.edge_blocks,&plan.interior_blocks}) for(const auto& block:*blocks) {
        if(!block.shape_idx) continue;
        const auto& shape=zones.geometry.shapes.at(block.name).at(block.shape_idx);
        if(shape.side=="bottom") selected_mirrors.insert(shape.mirror.begin(),shape.mirror.end());
    }
    int top=0,bottom=0;
    for(const auto& part:model.insts) {
        final_refs.insert(part.ref);
        if(part.sheet!="mechanical"||part.ref.rfind("FID",0)!=0) board_refs.insert(part.ref);
        (part.side=="bottom"?bottom:top)++;
        const auto key=input.floorplan.footprint_of.at(part.footprint);
        const auto authoritative=selected_mirrors.count(part.ref)
            ? zones.footprints.at(selected_mirrors.at(part.ref)) : input.footprints.at(key);
        require(part.mod->bytes==authoritative->bytes&&part.mirror==bool(selected_mirrors.count(part.ref)),
                "actual footprint/mirror matches source and selected shape: "+part.ref);
        require(part.x>=model.origin_x&&part.x<=model.origin_x+model.board_w&&
                part.y>=model.origin_y&&part.y<=model.origin_y+model.board_h,
                "component origin inside board: "+part.ref);
    }
    require(model.n_top==top&&model.n_bottom==bottom&&model.placed==static_cast<int>(model.insts.size()),
            "reported population equals actual instances");
    require(model.two_side==input.two_side,"requested placement mode retained");
    std::map<std::string,int> nets{{"",0}};
    for(const auto& [name,pins]:input.netlist) {
        (void)pins;
        if(!name.empty()&&name.rfind("unconnected-",0)!=0) nets.emplace(name,0);
    }
    int net_id=0;for(auto& [name,id]:nets){(void)name;id=net_id++;}
    require(model.net_numbers==nets,"complete source-derived net numbering");
    for(const auto& [net,klass]:model.netclass_of) {
        require(nets.count(net)!=0&&model.classes.count(klass)!=0,"net class resolves to a source net and declared class");
    }
    const std::vector<std::string> stages{"step3_emission","l4_pull","edge_seat","breathe",
        "refit_facing","reorder","corridor_eviction","instantiate","emission_frame","escape_copper"};
    std::map<std::string,int> moved;
    std::map<std::string,PcbPlacementPose> previous;
    std::map<std::string,PcbPlacementPose> fixed;
    for(std::size_t i=0;i<zones.geometry.mh_refs.size();++i) {
        const std::size_t corner=i%4;
        fixed[zones.geometry.mh_refs[i]]={corner==1||corner==2?plan.board_w-5:5,
            corner>=2?plan.board_h-5:5,0,""};
    }
    for(const auto& part:model.insts) if(part.ref.rfind("J",0)==0&&part.sheet.rfind("som_j",0)==0)
        for(const auto& jack:input.floorplan.som.js) if(jack.ref=="J"+part.sheet.substr(5))
            fixed[part.ref]={plan.som_x+jack.x,plan.som_y+jack.y,jack.w<jack.h?90.:0.,""};
    require(!fixed.empty(),"fixed mounting/module witnesses exist");
    for(std::size_t i=0;i<stages.size();++i) {
        const auto& poses=result.stages.at(stages[i]);
        std::set<std::string> refs;
        for(const auto& [ref,pose]:poses) {
            refs.insert(ref);
            require(std::isfinite(std::get<0>(pose))&&std::isfinite(std::get<1>(pose))&&
                    std::isfinite(std::get<2>(pose)),"finite checkpoint pose: "+stages[i]+" "+ref);
        }
        const bool page=i>=8;
        require(refs==(page?final_refs:board_refs),"complete checkpoint population: "+stages[i]);
        for(const auto& [ref,expected]:fixed) {
            const auto& actual=poses.at(ref);
            require(std::get<0>(actual)==(page?fixed_part_grid(model.origin_x+std::get<0>(expected)):std::get<0>(expected))&&
                    std::get<1>(actual)==(page?fixed_part_grid(model.origin_y+std::get<1>(expected)):std::get<1>(expected))&&
                    std::get<2>(actual)==std::get<2>(expected)&&
                    std::get<3>(actual)==(page?"top":""),"source-fixed placement: "+stages[i]+" "+ref);
        }
        if(i!=0&&i!=8) {
            int count=0;
            for(const auto& [ref,pose]:poses) if(previous.at(ref)!=pose) ++count;
            moved[stages[i]]=count;
            if(i==7||i==9) require(count==0,"frozen instantiate/escape geometry");
        }
        previous=poses;
    }
    require(model.stage_moves==moved,"movement ledger independently recounted");
    for(const auto& part:model.insts)
        require(result.stages.at("escape_copper").at(part.ref)==PcbPlacementPose{part.x,part.y,part.rotation,part.side},
                "final checkpoint/model identity: "+part.ref);
}

template<class Require>
void physical(const PcbPlacementInput& input,const PcbModel& model,Require require) {
    const PcbCheckInput check(model);
    const auto gates=check_pcb_placement_gates(input,model);
    require(gates.placement_contract.ok,gates.placement_contract.summary());
    require(gates.placement_flow.ok,gates.placement_flow.summary());
    require(gates.composition.hard_red==0,"all enforced composition terms satisfied");
    const auto mech=check_placement_mech(check);require(mech.ok,mech.summary());
    const auto spacing=check_connector_spacing(check);require(spacing.ok,spacing.summary());
    const auto fanout=check_fanout(check,0);require(fanout.ok,fanout.summary());
    const auto ratsnest=check_ratsnest(check,nullptr,nullptr,input.floorplan.cross_budget_k);
    require(ratsnest.ok,ratsnest.summary());
    const auto lanes=check_escape_lanes(model,pcb_escape_population_from_json(input.floorplan.project.escape),input.interface_bytes);
    require(lanes.ok,lanes.summary());
    const auto v1=check_return_path(input.som_interface,input.return_path_footprints);
    std::map<std::string,ReturnStitchClass> triage;
    const auto add=[&](const std::string& net) {
        const auto classified=classify_pcb_escape_signal(net,input.function_map);
        triage[net]={classified.rank(),classified.klass,classified.function};
    };
    for(const auto& part:model.insts) if(part.sheet.rfind("som_j",0)==0)
        for(const auto& [pin,net]:part.pad_nets) {
            (void)pin;if(!net.second.empty()&&pcb_classify_net(net.second)=="SIGNAL") add(net.second);
        }
    for(const auto& violation:v1.violations) add(violation.net);
    const auto rendered=render_pcb(model,pcb_emit_policy(input.floorplan.project));
    const PcbEmittedBoard emitted{"in-memory-current-board",rendered.document};
    const auto stitch=check_return_stitch(check,v1,triage,input.interface_bytes,&emitted);
    require(stitch.ok,stitch.summary());
    require(pcb_escape_file_parity(emitted,model.copper)=="ok","escape copper and ground plane emitted intact");
}
} // namespace placement_requirements_test
