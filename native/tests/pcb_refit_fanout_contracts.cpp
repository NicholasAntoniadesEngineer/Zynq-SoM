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
        std::cout << "11 refit fanout policies and accounted emission projection PASS\n";
        return 0;
    } catch (const std::exception &e) { std::cerr << e.what() << '\n'; return 1; }
}
