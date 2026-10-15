// Standalone test TU includes the owned implementation to exercise private policy helpers.
// Link schgen_core; do not also compile pcb_placement_moves.cpp into this executable.
#include "../src/pcb_placement_moves.cpp"
#include "pcb_placement_fixture.hpp"
#include <iostream>
#include <stdexcept>

namespace {
using namespace schgen;
using namespace schgen::pcb_placement;
void require(bool value, const char *message) {
    if (!value) throw std::runtime_error(message);
}
PcbCheckInput model(double a_gap, double b_gap, bool opposite = false,
                    bool same_sheet_passive = false, bool rename = false, int pins = 3) {
    const auto fp = pcb_check_footprint("unit.kicad_mod",
        "(footprint unit (layer F.Cu)"
        " (fp_rect (start -1 -1) (end 1 1) (stroke (width 0.05) (type default)) (layer F.CrtYd))"
        " (pad 1 smd rect (at 0 0) (size 1 1) (layers F.Cu F.Paste F.Mask)))");
    PcbCheckModel m;
    m.origin_x = m.origin_y = 0;
    for (int k = 0; k < 2; ++k) {
        PcbCheckInstance subject;
        subject.ref = k == 0 ? (rename ? "UNKNOWN" : "SW1") : "SW2";
        subject.sheet = k == 0 ? "a" : "b";
        subject.mod = fp;
        subject.x = k == 0 ? 0 : 100;
        subject.pad_nets = {{"1",{1,"a"}}, {"2",{2,"b"}}, {"3",{3,"c"}}};
        for(int pin = 4; pin <= pins; ++pin) subject.pad_nets[std::to_string(pin)] = {pin,"signal"};
        m.insts.push_back(subject);
        PcbCheckInstance passive;
        passive.ref = k == 0 ? "C1" : "D2";
        passive.sheet = same_sheet_passive ? subject.sheet : "other";
        passive.mod = fp;
        passive.x = subject.x + 2 + (k == 0 ? a_gap : b_gap);
        passive.side = opposite ? "bottom" : "top";
        passive.pad_nets = {{"1",{1,"a"}}, {"2",{2,"b"}}};
        m.insts.push_back(passive);
    }
    return PcbCheckInput(std::move(m));
}
void projection(const std::filesystem::path& root) {
    auto f = placement_fixture::load(root,"carrier");
    const auto zones = build_pcb_zone_geometry(f.input);
    std::vector<PcbCheckInstance> observed;
    auto observer = std::make_shared<PcbPlacementExperiment>();
    observer->checkpoint = [&](const auto& row) { observed = row.instances; };
    f.input.experiment = observer;
    Placer p(f.input,zones,f.stage);
    p.seed();
    const auto old_pos = p.pos;
    const auto old_rot = p.rotations;
    const auto old_nets = p.pin_net;
    const auto old_sides = p.geometry.side_of;
    PcbStageRefitPoses trial;
    for(const auto& [ref,xy] : p.pos)
        trial[ref] = {xy.first + .000049, xy.second - .000049, p.rot(ref)};
    const auto before = p.ctx.quantization;
    const auto checked = refit_fanout_geometry(p,&trial);
    require(checked.model().net_numbers==p.net_numbers,
            "refit projection retains net identities for thermal planning");
    require(p.pos==old_pos && p.rotations==old_rot && p.pin_net==old_nets && p.geometry.side_of==old_sides,
            "trial projection is atomic and preserves identities");
    std::map<std::string,std::size_t> expected;
    for(const auto& i : checked.model().insts)
        expected[p.grid_placed.count(i.ref) ? "placement_emission_pose_precision4dp" : "fixed_part_grid"] += 2;
    for(const auto& [key,count] : expected) {
        const auto prior = before.find(key);
        require(p.ctx.quantization.at(key)-(prior==before.end()?0:prior->second)==count,
                "each projected coordinate has a measured work receipt");
    }
    for(const auto& [ref,pose] : trial) p.pos[ref]={std::get<0>(pose),std::get<1>(pose)};
    p.observe_checkpoint("projection-test");
    require(observed.size()==checked.model().insts.size(),"projection subject set matches emission observer");
    for(std::size_t k=0;k<observed.size();++k) {
        const auto& a = observed[k]; const auto& b = checked.model().insts[k];
        require(a.ref==b.ref && a.x==b.x && a.y==b.y && a.rotation==b.rotation &&
                a.side==b.side && a.mirror==b.mirror && a.pad_nets==b.pad_nets,
                "trial geometry matches independently projected emission geometry");
    }
}
void noncompact_refit_contract(const std::filesystem::path& root) {
    auto f=placement_fixture::load(root,"carrier");
    auto mode=std::make_shared<FloorplanExperiment>();mode->multiscale_outline=true;
    f.input.floorplan.experiment=mode;
    const auto zones=build_pcb_zone_geometry(f.input);
    auto prepared=prepare_pcb_floorplan(f.input,zones);
    // Exercise the deferred-facing boundary. Whether a particular refit is
    // unsafe depends on current geometry, not a frozen component pose.
    for(auto& term:prepared.compose.index.hard)term.require_positive_facing=false;
    const auto stage=generate_floorplan(prepared);
    std::map<std::string,std::vector<PcbCheckInstance>> frames;
    auto observer=std::make_shared<PcbPlacementExperiment>();
    observer->checkpoint=[&](const auto& row){
        if(row.stage=="breathe"||row.stage=="refit_facing")frames[row.stage]=row.instances;
    };
    f.input.experiment=observer;
    const auto placed=place_pcb_model(f.input,zones,stage);
    const auto fanout=check_fanout(PcbCheckInput(placed.model),0);
    require(fanout.ok,"noncompact adapter accepted a refit that newly starves a foreign subject");
    auto before_model=placed.model,after_model=placed.model;
    before_model.insts=frames.at("breathe");after_model.insts=frames.at("refit_facing");
    const PcbCheckInput before(before_model),after(after_model);
    const auto before_fanout=check_fanout(before,0),after_fanout=check_fanout(after,0);
    require(!before_fanout.records.empty()&&before_fanout.records.size()==after_fanout.records.size(),
            "actual refit must preserve a nonempty fanout subject population");
    std::map<std::string,PcbFanoutRecord> prior;
    for(const auto& row:before_fanout.records)prior.emplace(row.ref,row);
    for(const auto& row:after_fanout.records){
        const auto& old=prior.at(row.ref);
        require(!row.starved()||(old.starved()&&row.clearance>=old.clearance),
                "actual refit must not create or worsen starvation for any subject");
    }
    const auto policy=pcb_emit_policy(f.input.floorplan.project);
    require(preserves_preferred_thermal_vias(plan_preferred_thermal_vias(before_model,policy),
                                           plan_preferred_thermal_vias(after_model,policy)),
            "actual refit must preserve preferred thermal capacity");
    // Controlled negative case on the real checkpoint geometry: place the
    // diode on a healthy foreign subject, rather than assuming the optimiser
    // will forever offer the same unsafe pose from an old layout.
    auto crowded=after_model;
    auto diode=std::find_if(crowded.insts.begin(),crowded.insts.end(),[](const auto& i){return i.ref=="D20001";});
    require(diode!=crowded.insts.end(),"real diode mutation subject exists");
    bool witnessed=false;
    for(const auto& row:after_fanout.records){
        if(row.starved())continue;
        const auto subject=std::find_if(crowded.insts.begin(),crowded.insts.end(),[&](const auto& i){return i.ref==row.ref;});
        if(subject==crowded.insts.end()||subject->sheet==diode->sheet||subject->side!=diode->side)continue;
        diode->x=subject->x;diode->y=subject->y;
        const PcbCheckInput trial(crowded);
        const auto mutated=check_fanout(trial,0);
        const auto harmed=std::find_if(mutated.records.begin(),mutated.records.end(),[&](const auto& r){return r.ref==row.ref;});
        if(harmed==mutated.records.end()||!harmed->starved())continue;
        require(!refit_preserves_fanout(after,trial),"real-board newly starved subject must reject refit");
        witnessed=true;break;
    }
    require(witnessed,"controlled real-board starvation mutation must execute");
}
void thermal_pull(const std::filesystem::path& root) {
    auto f=placement_fixture::load(root,"carrier");
    const auto zones=build_pcb_zone_geometry(f.input);
    Placer p(f.input,zones,f.stage);
    p.seed();
    const auto policy=pcb_emit_policy(f.input.floorplan.project);
    const auto before=plan_preferred_thermal_vias(refit_fanout_geometry(p,nullptr).model(),policy);
    require(!before.empty(),"carrier pull test must exercise actual thermal subjects");
    p.l4_pull();
    const auto after=plan_preferred_thermal_vias(refit_fanout_geometry(p,nullptr).model(),policy);
    require(preserves_preferred_thermal_vias(before,after),
            "passive pull cannot consume another subject's preferred through-via capacity");
}
}
int main(int argc, char** argv) {
    try {
        if(argc!=2) return 2;
        require(refit_preserves_fanout(model(2,2), model(1.5,2)), "exact floor accepted");
        require(!refit_preserves_fanout(model(2,2), model(1.485,2)), "new starvation rejected");
        require(!refit_preserves_fanout(model(1,2), model(2,1)), "count-neutral starvation swap rejected");
        require(!refit_preserves_fanout(model(1,2), model(.9,2)), "existing starvation cannot worsen");
        require(refit_preserves_fanout(model(1,2), model(1,1.5)), "unchanged unrelated failure does not waive another subject");
        require(refit_preserves_fanout(model(1,2), model(1.25,2)), "improvement accepted");
        require(refit_preserves_fanout(model(2,2,true), model(0,2,true)), "opposite-face crowding follows final gate");
        require(refit_preserves_fanout(model(2,2,false,true), model(0,2,false,true)), "same-sheet C passive follows final gate");
        require(!refit_preserves_fanout(model(2,2), model(2,2,false,false,true)), "unknown subject cannot replace original");
        require(!refit_preserves_fanout(model(2.9263,3,false,false,false,14), model(1.87,3,false,false,false,14)), "USB JTAG 14-pin floor cannot regress");
        require(refit_preserves_fanout(model(3,3,false,false,false,14), model(2,3,false,false,false,14)), "14-pin exact floor accepted");
        projection(argv[1]);
        noncompact_refit_contract(argv[1]);
        thermal_pull(argv[1]);
        std::cout << "11 refit fanout policies and accounted emission projection PASS\n";
        return 0;
    } catch (const std::exception &e) { std::cerr << e.what() << '\n'; return 1; }
}
