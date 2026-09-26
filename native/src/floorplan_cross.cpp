#include "floorplan_internal.hpp"
#include "schgen/board_schematic.hpp"

#include <algorithm>
#include <cmath>
#include <numeric>

namespace schgen::floorplan_detail {
namespace {
double rotated(double value) { double r = std::fmod(value,360.0); return r < 0 ? r+360 : r; }
template<class Map> typename Map::mapped_type get(const Map& m, const typename Map::key_type& k) {
    const auto i = m.find(k); return i == m.end() ? typename Map::mapped_type{} : i->second;
}
}  // namespace

void Engine::prepare_cross() {
    const auto& zg = in.geometry;
    auto rotations = zg.conn_rot;
    for (const auto& [ref, extra] : zg.zone_extra_rot) rotations[ref] = rotated(rotations[ref]+extra);
    std::map<std::string,CrossPart> owned;
    std::map<std::string,int> bands;
    for (const auto& [sheet,band] : in.sheet_index) bands[sheet]=band;
    for (const auto& [sheet,wh] : zg.zone_box) {
        (void)wh;
        for (const auto* map : {&zg.top_off,&zg.bot_off}) {
            const auto off = map->find(sheet);
            if (off == map->end()) continue;
            for (const auto& [ref,xy] : off->second) {
                CrossPart part{};
                part.owner=CrossPart::Owner::Zone; part.ref=ref; part.sheet=sheet;
                part.key=sheet; part.offset=xy;
                const auto mod=zg.resolvable.find(ref);
                if (mod==zg.resolvable.end()) throw FloorplanError("floorplan: zone offset has no resolved footprint for "+ref);
                part.footprint=mod->second;
                part.base_side = zg.side_of.count(ref) ? zg.side_of.at(ref) : "top";
                owned[ref]=std::move(part);
            }
        }
    }
    std::map<std::string,const SomJGeom*> jacks;
    for (const auto& j : plan.som.js) jacks[j.ref]=&j;
    std::vector<std::string> dec_refs;
    for (std::size_t i=0; i<in.sheets.size(); ++i) {
        const auto& sc=in.sheets[i];
        const int band=bands.count(sc.name) ? bands.at(sc.name) : static_cast<int>(i+1);
        std::vector<const CircuitPartIr*> parts;
        for (const auto& p:sc.parts) parts.push_back(&p);
        std::sort(parts.begin(),parts.end(),[](const auto* a,const auto* b){return a->ref<b->ref;});
        for (const auto* p:parts) {
            const std::string ref=board_renamed_ref(p->ref,band,sc.name);
            const auto mod=resolved(*p);
            if (!mod) continue;
            CrossPart part{};
            part.ref=ref; part.sheet=sc.name; part.footprint=*mod; part.base_side="top";
            if (starts(sc.name,"som_j")) {
                const auto jack="J"+sc.name.substr(5);
                if (!starts(ref,"J") || !jacks.count(jack)) continue;
                part.owner=CrossPart::Owner::SomJack; part.key=jack;
                const auto* j=jacks.at(jack); part.offset={j->x,j->y};
                rotations[ref]=j->w<j->h ? 90 : 0;
            } else if (sc.name=="som_decoupling") {
                part.owner=CrossPart::Owner::Decoupling; part.base_side="bottom";
                dec_refs.push_back(ref);
            } else if (starts(p->lib_id,"Mechanical:MountingHole")) {
                const auto at=std::find(zg.mh_refs.begin(),zg.mh_refs.end(),ref);
                if (at==zg.mh_refs.end()) continue;
                part.owner=CrossPart::Owner::MountingHole;
                part.owner_index=static_cast<int>(at-zg.mh_refs.begin())%4;
            } else continue;
            owned[ref]=std::move(part);
        }
    }
    std::sort(dec_refs.begin(),dec_refs.end());
    for (std::size_t k=0; k<dec_refs.size(); ++k) owned.at(dec_refs[k]).owner_index=static_cast<int>(k);
    auto pads_at=[&](const std::string& key,double rot) {
        std::vector<std::tuple<std::string,double,double>> local;
        for (const auto& row:footprint(key).pads) local.emplace_back(std::get<0>(row),std::get<2>(row),std::get<3>(row));
        std::map<std::string,std::vector<FloorplanPoint>> result;
        for (const auto& [name,x,y]:inst_pad_xy(local,0,0,rot,3)) result[name].emplace_back(x,y);
        return result;
    };
    std::map<std::string,std::size_t> part_index;
    for (auto& [ref,part]:owned) {
        part.pad_positions[0]=pads_at(part.footprint,get(rotations,ref));
        const auto shapes=zg.shapes.find(part.sheet);
        if (shapes!=zg.shapes.end()) for (std::size_t k=1;k<shapes->second.size();++k) {
            if (part.owner!=CrossPart::Owner::Zone) { part.pad_positions[static_cast<int>(k)]=part.pad_positions.at(0); continue; }
            const auto& s=shapes->second[k];
            if (s.bot_off.count(ref)) part.shape_offsets[static_cast<int>(k)]=s.bot_off.at(ref);
            else if (s.top_off.count(ref)) part.shape_offsets[static_cast<int>(k)]=s.top_off.at(ref);
            else throw FloorplanError("floorplan: shape "+std::to_string(k)+" of "+part.sheet+" omits "+ref);
            const auto extra=s.extra_rot.find(ref);
            const double rot=extra==s.extra_rot.end() ? 0 : rotated(get(zg.conn_rot,ref)+extra->second);
            const auto mirror=s.mirror.find(ref);
            if (mirror==s.mirror.end() && rot==get(rotations,ref)) part.pad_positions[static_cast<int>(k)]=part.pad_positions.at(0);
            else part.pad_positions[static_cast<int>(k)]=pads_at(mirror==s.mirror.end() ? part.footprint : mirror->second,rot);
        }
        part_index[ref]=cross_parts.size(); cross_parts.push_back(std::move(part));
    }
    std::map<std::string,std::vector<CrossNetPin>> by_net;
    for (std::size_t i=0;i<in.sheets.size();++i) {
        const auto& sc=in.sheets[i];
        const int band=bands.count(sc.name) ? bands.at(sc.name) : static_cast<int>(i+1);
        std::vector<const CircuitNetIr*> nets;
        for (const auto& n:sc.nets) nets.push_back(&n);
        std::sort(nets.begin(),nets.end(),[](const auto* a,const auto* b){return a->name<b->name;});
        for (const auto* n:nets) for (const auto& pin:n->pins) {
            if (starts(pin.ref,"#")) continue;
            const auto ref=board_renamed_ref(pin.ref,band,sc.name);
            const auto hit=part_index.find(ref);
            if (hit==part_index.end()) continue;
            const auto& base=cross_parts[hit->second].pad_positions.at(0);
            if (!base.count(pin.pin) || base.at(pin.pin).empty()) continue;
            by_net[n->name].push_back({hit->second,pin.pin});
        }
    }
    std::set<std::string> classes;
    for (auto& [name,pins]:by_net) {
        std::set<std::string> members;
        for (const auto& p:pins) members.insert(cross_parts[p.part].sheet);
        if (members.size()<2) continue;
        const auto cls=in.impedance_net_classes.find(name);
        const bool impedance=cls!=in.impedance_net_classes.end();
        if (impedance) { ++n_impedance; classes.insert(cls->second); }
        checked_quantization_add(plan.accounting.quantization_engagements, "est_via_cost");
        for (const auto& sheet:members) nets_by_sheet[sheet].push_back(cross_nets.size());
        cross_nets.push_back({name,std::move(pins),floorplan_experiment_via_cost(
            in.experiment.get(), impedance, est_via_cost(impedance))});
    }
    for (const auto& cls:classes) { if (!impedance_classes.empty()) impedance_classes+=","; impedance_classes+=cls; }
    for (const auto& [ref,edge]:zg.conn_edge) {
        (void)edge;
        const auto p=part_index.find(ref);
        if (p==part_index.end()) continue;
        const auto box=boxes_union(pad_boxes(cross_parts[p->second].footprint,get(rotations,ref)));
        if (box) connector_pad_boxes[ref]=*box;
    }
}

double Engine::estimate(const std::vector<const FloorplanBlock*>& blocks, const std::string& only_sheet) {
    std::map<std::string,const FloorplanBlock*> by_name;
    std::map<std::string,int> selected, bottom;
    for (const auto* b:blocks) {
        by_name[b->name]=b;
        if (b->shape_idx && in.geometry.shapes.count(b->name)) {
            const auto& variants=in.geometry.shapes.at(b->name);
            if (b->shape_idx<0 || static_cast<std::size_t>(b->shape_idx)>=variants.size()) throw FloorplanError("floorplan: shape index out of range for "+b->name);
            selected[b->name]=b->shape_idx;
            if (variants[b->shape_idx].side=="bottom") bottom[b->name]=b->shape_idx;
        }
    }
    const std::array<FloorplanPoint,4> corners{{{mh_inset,mh_inset},{plan.board_w-mh_inset,mh_inset},
        {plan.board_w-mh_inset,plan.board_h-mh_inset},{mh_inset,plan.board_h-mh_inset}}};
    const auto [rw,rh,cols,rows]=som_decoupling_grid(plan.som.w,plan.som.h,plan.dec_count,dec_inset);
    std::vector<std::optional<FloorplanPoint>> positions(cross_parts.size());
    for (std::size_t i=0;i<cross_parts.size();++i) {
        const auto& part=cross_parts[i];
        double x=0,y=0;
        if (part.owner==CrossPart::Owner::Zone) {
            const auto block=by_name.find(part.key);
            if (block==by_name.end()) continue;
            const int k=get(selected,part.key);
            const auto d=k ? part.shape_offsets.at(k) : part.offset;
            x=py_round(py_round(in.origin.first+block->second->x,4)+d.first,4);
            y=py_round(py_round(in.origin.second+block->second->y,4)+d.second,4);
        } else if (part.owner==CrossPart::Owner::SomJack) {
            x=quantize("fixed_part_grid",in.origin.first+plan.som_x+part.offset.first);
            y=quantize("fixed_part_grid",in.origin.second+plan.som_y+part.offset.second);
        } else if (part.owner==CrossPart::Owner::Decoupling) {
            x=py_round(in.origin.first+plan.som_x+dec_inset+rw*(part.owner_index%cols+.5)/cols,4);
            y=py_round(in.origin.second+plan.som_y+dec_inset+rh*(part.owner_index/cols+.5)/rows,4);
        } else {
            x=quantize("fixed_part_grid",in.origin.first+corners[part.owner_index].first);
            y=quantize("fixed_part_grid",in.origin.second+corners[part.owner_index].second);
        }
        const auto pb=connector_pad_boxes.find(part.ref);
        if (pb!=connector_pad_boxes.end()) {
            const auto& e=in.geometry.conn_edge.at(part.ref);
            if (e=="N") y=py_round(in.origin.second+edge_pad_clear-pb->second.y0,4);
            else if (e=="S") y=py_round(in.origin.second+plan.board_h-edge_pad_clear-pb->second.y1,4);
            else if (e=="W") x=py_round(in.origin.first+edge_pad_clear-pb->second.x0,4);
            else if (e=="E") x=py_round(in.origin.first+plan.board_w-edge_pad_clear-pb->second.x1,4);
        }
        positions[i]={{x,y}};
    }
    std::vector<std::size_t> net_indices;
    if (only_sheet.empty()) { net_indices.resize(cross_nets.size()); std::iota(net_indices.begin(),net_indices.end(),0); }
    else net_indices=get(nets_by_sheet,only_sheet);
    double cross=0;
    for (const auto index:net_indices) {
        const auto& net=cross_nets[index];
        std::map<std::string,int> sheet_ids;
        std::vector<std::uint8_t> flags;
        std::vector<std::tuple<double,double,int,int>> points;
        for (const auto& pin:net.pins) {
            if (!positions[pin.part]) continue;
            const auto& p=cross_parts[pin.part];
            const auto& pad_by_name=p.pad_positions.at(get(selected,p.sheet));
            const auto pad=pad_by_name.find(pin.pin);
            if (pad==pad_by_name.end()) continue;
            const auto added=sheet_ids.emplace(p.sheet,static_cast<int>(sheet_ids.size()));
            if (added.second) flags.push_back(bottom.count(p.sheet) ? 1:0);
            int side=p.base_side=="top" ? 0:1;
            if (bottom.count(p.sheet)) side=in.geometry.shapes.at(p.sheet)[bottom.at(p.sheet)].top_off.count(p.ref) ? 1:0;
            for (const auto& [rx,ry]:pad->second) points.emplace_back(py_round(positions[pin.part]->first+rx,3),
                py_round(positions[pin.part]->second+ry,3),added.first->second,side);
        }
        cross+=cross_net_cost(points,net.via_cost,flags);
    }
    observe_floorplan_experiment_estimate(in.experiment.get(), cross, only_sheet.empty());
    return cross;
}
double Engine::estimate() {
    std::vector<const FloorplanBlock*> all;
    for (const auto* b:blocks()) all.push_back(b);
    return estimate(all);
}
}  // namespace schgen::floorplan_detail
