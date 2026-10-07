#pragma once
#include "schgen/board_schematic.hpp"
#include "schgen/quantize.hpp"
#include "schgen/turn.hpp"
#include <cmath>
#include <queue>

// Test-only oracle. No experiment measurement, ratsnest, floorplan Engine or
// production MST routine is called here. Parsed immutable pads, the generated
// zone offsets/selected plan and checkpoint poses are the measurement inputs.
namespace experiment_metric_contracts {
using namespace schgen;
struct Pad { double x, y; std::string sheet; int side = 0; };
using Nets = std::map<std::string, std::vector<Pad>>;

template<class Visit> void tree(const std::vector<Pad>& pads, Visit visit) {
    if (pads.empty()) return;
    // A heap of directed cut edges is independent of production's dense Prim
    // distance/update arrays. Target index breaks equal frontier distances;
    // earlier source admission wins equal edges to the same target.
    using Edge = std::tuple<double, std::size_t, std::size_t, std::size_t>;
    std::priority_queue<Edge, std::vector<Edge>, std::greater<Edge>> cut;
    std::vector<bool> admitted(pads.size());
    auto admit = [&](std::size_t source, std::size_t rank) {
        admitted[source] = true;
        for (std::size_t target = 0; target < pads.size(); ++target)
            if (!admitted[target]) cut.emplace(
                std::abs(pads[source].x-pads[target].x)+std::abs(pads[source].y-pads[target].y),
                target, rank, source);
    };
    admit(0, 0);
    for (std::size_t rank = 1; rank < pads.size(); ++rank) {
        while (admitted[std::get<1>(cut.top())]) cut.pop();
        const auto [distance, target, source_rank, source] = cut.top(); cut.pop();
        (void)distance; (void)source_rank;
        visit(pads[source], pads[target]);
        admit(target, rank);
    }
}
inline ExperimentLengths lengths(const std::vector<PcbCheckInstance>& instances) {
    Nets nets;
    for (const auto& inst : instances) {
        if (!inst.mod) throw std::runtime_error("metric oracle: unresolved " + inst.ref);
        for (const auto& [pin, type, x, y, angle, w, h] : inst.mod->pads) {
            (void)type; (void)angle; (void)w; (void)h;
            const auto net = inst.pad_nets.find(pin);
            if (net == inst.pad_nets.end() || net->second.second.empty() ||
                net->second.second.rfind("unconnected-", 0) == 0) continue;
            const auto p = turn_point(x, y, inst.rotation);
            nets[net->second.second].push_back(
                {py_round(inst.x+p.first, 3), py_round(inst.y+p.second, 3), inst.sheet});
        }
    }
    ExperimentLengths result;
    for (const auto& [name, pads] : nets) {
        (void)name;
        tree(pads, [&](const Pad& a, const Pad& b) {
            const auto distance = std::hypot(a.x-b.x, a.y-b.y);
            result.total += distance;
            if (a.sheet != b.sheet) { result.cross += distance; ++result.n_cross; }
        });
    }
    result.cross = py_round(result.cross, 1); result.total = py_round(result.total, 1);
    return result;
}
struct Part { std::string sheet; const CircuitPartIr* authored; };
inline std::map<std::string, Part> parts(const FloorplanInput& input) {
    std::map<std::string, Part> result;
    const std::map<std::string, int> bands(input.sheet_index.begin(), input.sheet_index.end());
    for (std::size_t i=0; i<input.sheets.size(); ++i) {
        const auto& sheet = input.sheets[i];
        const auto band = bands.count(sheet.name) ? bands.at(sheet.name) : static_cast<int>(i+1);
        for (const auto& part : sheet.parts)
            result.emplace(board_renamed_ref(part.ref, band, sheet.name), Part{sheet.name, &part});
    }
    return result;
}

inline double estimate(const FloorplanInput& input, const FloorplanPlan& plan) {
    const auto& g = input.geometry;
    const auto authored = parts(input);
    std::map<std::string, const FloorplanBlock*> blocks;
    std::set<std::string> bottom;
    for (const auto* list : {&plan.edge_blocks, &plan.interior_blocks})
        for (const auto& b : *list) {
            blocks.emplace(b.name, &b);
            if (b.shape_idx && g.shapes.at(b.name).at(b.shape_idx).side == "bottom") bottom.insert(b.name);
        }
    std::map<std::string, PcbCheckFootprintPtr> mods;
    for (const auto& [key, fp] : input.footprints)
        mods.emplace(key, pcb_check_footprint(fp.source, "", fp.document));
    auto rotation = [&](const std::string& ref) {
        return (g.conn_rot.count(ref) ? g.conn_rot.at(ref) : 0.) +
               (g.zone_extra_rot.count(ref) ? g.zone_extra_rot.at(ref) : 0.);
    };
    std::map<std::string, std::map<std::string, std::vector<Pad>>> placed;
    auto place = [&](const std::string& ref, const std::string& key, double rot,
                     FloorplanPoint xy, int side, bool local_round) {
        for (const auto& [pin, type, x, y, angle, w, h] : mods.at(key)->pads) {
            (void)type; (void)angle; (void)w; (void)h;
            auto p = turn_point(x, y, rot);
            if (local_round) { p.first=py_round(p.first,3); p.second=py_round(p.second,3); }
            placed[ref][pin].push_back({py_round(xy.first+p.first,3), py_round(xy.second+p.second,3),
                                       authored.at(ref).sheet, side});
        }
    };
    for (const auto& [sheet, size] : g.zone_box) {
        (void)size;
        const auto block = blocks.find(sheet);
        if (block == blocks.end()) continue;
        const auto& b = *block->second;
        const auto* shape = b.shape_idx ? &g.shapes.at(sheet).at(b.shape_idx) : nullptr;
        FloorplanOffsets offsets;
        for (const auto* map : {&g.top_off, &g.bot_off})
            if (map->count(sheet)) for (const auto& [ref, xy] : map->at(sheet)) offsets[ref]=xy;
        for (const auto& [ref, base] : offsets) {
            const auto key = g.resolvable.at(ref);
            auto selected_key = key;
            auto xy = base;
            double rot = rotation(ref);
            int side = g.side_of.count(ref) && g.side_of.at(ref) != "top" ? 1 : 0;
            if (shape) {
                xy = shape->bot_off.count(ref) ? shape->bot_off.at(ref) : shape->top_off.at(ref);
                rot = shape->extra_rot.count(ref) ?
                    (g.conn_rot.count(ref) ? g.conn_rot.at(ref) : 0.)+shape->extra_rot.at(ref) : 0.;
                if (shape->mirror.count(ref)) selected_key=shape->mirror.at(ref);
                if (bottom.count(sheet)) side = shape->top_off.count(ref) ? 1 : 0;
            }
            xy = {py_round(py_round(input.origin.first+b.x,4)+xy.first,4),
                  py_round(py_round(input.origin.second+b.y,4)+xy.second,4)};
            if (g.conn_edge.count(ref)) {
                // Edge seating uses the incumbent pad union even when the
                // selected shape has a different orientation or mirror.
                std::vector<std::tuple<std::string,double,double,double,double,double>> rows;
                for (const auto& [pin,type,x,y,angle,w,h] : mods.at(key)->pads) {
                    (void)pin; rows.emplace_back(type,x,y,angle,w,h);
                }
                std::optional<Box4> box;
                for (const auto& [type,x0,y0,x1,y1] : pad_boxes_local(rows,rotation(ref))) {
                    (void)type;
                    if (!box) box=Box4{x0,y0,x1,y1};
                    else { box->x0=std::min(box->x0,x0); box->y0=std::min(box->y0,y0);
                           box->x1=std::max(box->x1,x1); box->y1=std::max(box->y1,y1); }
                }
                if (box) {
                    const auto& edge=g.conn_edge.at(ref);
                    if (edge=="N") xy.second=py_round(input.origin.second+.4-box->y0,4);
                    if (edge=="S") xy.second=py_round(input.origin.second+plan.board_h-.4-box->y1,4);
                    if (edge=="W") xy.first=py_round(input.origin.first+.4-box->x0,4);
                    if (edge=="E") xy.first=py_round(input.origin.first+plan.board_w-.4-box->x1,4);
                }
            }
            place(ref,selected_key,rot,xy,side,true);
        }
    }
    std::vector<std::string> decoupling;
    for (const auto& [ref, p] : authored) if (p.sheet=="som_decoupling") decoupling.push_back(ref);
    const double rw=std::max(1.,plan.som.w-12.), rh=std::max(1.,plan.som.h-12.);
    const int cols=plan.dec_count ? std::max(1,static_cast<int>(std::min(
        static_cast<double>(plan.dec_count),py_round(std::sqrt(plan.dec_count*rw/rh),0)))) : 1;
    for (const auto& [ref, p] : authored) {
        auto key=input.footprint_of.find(p.authored->footprint);
        if (key==input.footprint_of.end()) continue;
        if (p.sheet.rfind("som_j",0)==0 && ref.rfind("J",0)==0) {
            for (const auto& jack : plan.som.js) if (jack.ref=="J"+p.sheet.substr(5))
                place(ref,key->second,jack.w<jack.h ? 90 : 0,
                      {fixed_part_grid(input.origin.first+plan.som_x+jack.x),
                       fixed_part_grid(input.origin.second+plan.som_y+jack.y)},0,true);
        } else if (p.sheet=="som_decoupling") {
            const auto k=std::find(decoupling.begin(),decoupling.end(),ref)-decoupling.begin();
            const auto rows=std::max(1,(plan.dec_count+cols-1)/cols);
            place(ref,key->second,rotation(ref),
                  {py_round(input.origin.first+plan.som_x+6+rw*(k%cols+.5)/cols,4),
                   py_round(input.origin.second+plan.som_y+6+rh*(k/cols+.5)/rows,4)},1,true);
        } else if (p.authored->lib_id.rfind("Mechanical:MountingHole",0)==0) {
            const auto found=std::find(g.mh_refs.begin(),g.mh_refs.end(),ref);
            if (found==g.mh_refs.end()) continue;
            const auto corner=(found-g.mh_refs.begin())%4;
            place(ref,key->second,rotation(ref),
                  {fixed_part_grid(input.origin.first+(corner==1||corner==2 ? plan.board_w-5 : 5)),
                   fixed_part_grid(input.origin.second+(corner>=2 ? plan.board_h-5 : 5))},0,true);
        }
    }
    // Retain sheet/net/pin order (and duplicate physical pads) independently of
    // production's CrossPart indexing. Only multi-sheet nets enter estimation.
    Nets nets;
    for (std::size_t i=0; i<input.sheets.size(); ++i) {
        const auto& sheet=input.sheets[i];
        std::vector<const CircuitNetIr*> sorted;
        for (const auto& net : sheet.nets) sorted.push_back(&net);
        std::sort(sorted.begin(),sorted.end(),[](const auto* a,const auto* b){return a->name<b->name;});
        for (const auto* net : sorted) for (const auto& pin : net->pins) {
            if (pin.ref.rfind("#",0)==0) continue;
            const std::map<std::string,int> bands(input.sheet_index.begin(),input.sheet_index.end());
            const auto ref=board_renamed_ref(pin.ref,bands.count(sheet.name) ? bands.at(sheet.name) : static_cast<int>(i+1),sheet.name);
            if (placed.count(ref) && placed.at(ref).count(pin.pin)) {
                const auto& pads=placed.at(ref).at(pin.pin);
                nets[net->name].insert(nets[net->name].end(),pads.begin(),pads.end());
            }
        }
    }
    double result=0;
    for (const auto& [name,pads] : nets) {
        std::set<std::string> sheets;
        for (const auto& pad : pads) sheets.insert(pad.sheet);
        if (sheets.size()<2) continue;
        double cost=0;
        const auto via=input.impedance_net_classes.count(name) ? quantization_policy::kViaImpedanceMm :
            input.experiment && input.experiment->ordinary_via_mm ? *input.experiment->ordinary_via_mm : quantization_policy::kViaOrdinaryMm;
        tree(pads,[&](const Pad& a,const Pad& b) {
            if (a.sheet==b.sheet) return;
            cost+=std::sqrt((a.x-b.x)*(a.x-b.x)+(a.y-b.y)*(a.y-b.y));
            if ((bottom.count(a.sheet)||bottom.count(b.sheet)) && a.side!=b.side) cost+=via;
        });
        result+=cost;
    }
    return py_round(result,1);
}

template<class Require> void identity(const PcbPlacementInput& input,
    const std::vector<PcbCheckInstance>& instances, Require require, bool final=false) {
    const auto authored=parts(input.floorplan);
    std::map<std::string,int> net_ids;
    for (const auto& [name,pins] : input.netlist) {
        (void)pins;
        if (!name.empty() && name.rfind("unconnected-",0)!=0) net_ids.emplace(name,0);
    }
    int id=1; for (auto& [name,n] : net_ids) { (void)name; n=id++; }
    std::map<std::pair<std::string,std::string>,std::pair<int,std::string>> pin_nets;
    for (const auto& [name,pins] : input.netlist) if (name.rfind("unconnected-",0)!=0)
        for (const auto& pin : pins) pin_nets[{pin.ref,pin.pin}]={net_ids.count(name) ? net_ids.at(name) : 0,name};
    std::set<std::string> seen;
    for (const auto& inst : instances) {
        require(seen.insert(inst.ref).second,"unique checkpoint reference "+inst.ref);
        require(inst.mod!=nullptr && std::isfinite(inst.x) && std::isfinite(inst.y) &&
                std::isfinite(inst.rotation) && (inst.side=="top"||inst.side=="bottom"),"resolved finite pose "+inst.ref);
        if (final && !authored.count(inst.ref) && inst.sheet=="mechanical" && inst.ref.rfind("FID",0)==0) {
            require(inst.footprint=="Fiducial:Fiducial_1mm_Mask2mm" && inst.value=="Fiducial" &&
                    inst.side=="top" && inst.pad_nets.empty(),"synthetic fiducial identity");
            continue;
        }
        require(authored.count(inst.ref)!=0,"authored checkpoint reference "+inst.ref);
        const auto& part=authored.at(inst.ref);
        require(inst.sheet==part.sheet && inst.value==part.authored->value &&
                inst.footprint==part.authored->footprint,"authored part identity "+inst.ref);
        const auto key=input.floorplan.footprint_of.find(part.authored->footprint);
        require(key!=input.floorplan.footprint_of.end() && input.footprints.count(key->second),
                "authoritative footprint resolved "+inst.ref);
        const auto& source=*input.footprints.at(key->second);
        std::multiset<std::string> required_pads,actual_pads;
        for (const auto& pad : source.pads) required_pads.insert(std::get<0>(pad));
        for (const auto& pad : inst.mod->pads) actual_pads.insert(std::get<0>(pad));
        // Mirroring changes geometry, never physical pin IDs or multiplicity.
        require(actual_pads==required_pads,"authoritative physical pad membership "+inst.ref);
        std::map<std::string,std::pair<int,std::string>> expected;
        for (const auto& [pin,type,x,y,angle,w,h] : source.pads) {
            (void)type; (void)x; (void)y; (void)angle; (void)w; (void)h;
            if (pin.empty()) continue;
            const auto found=pin_nets.find({inst.ref,pin});
            expected[pin]=found==pin_nets.end() ? std::make_pair(0,std::string{}) : found->second;
        }
        require(inst.pad_nets==expected,"independent net/pin identity "+inst.ref);
    }
    for (const auto& [ref,part] : authored) {
        const auto key=input.floorplan.footprint_of.find(part.authored->footprint);
        if (key!=input.floorplan.footprint_of.end() && input.footprints.count(key->second))
            require(seen.count(ref)!=0,"resolved authored part retained "+ref);
    }
}
} // namespace experiment_metric_contracts
