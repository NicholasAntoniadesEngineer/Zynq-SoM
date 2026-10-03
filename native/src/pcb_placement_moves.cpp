#include "pcb_placement_internal.hpp"

namespace schgen::pcb_placement {
namespace {
bool hit(Box4 b, const std::vector<Box4> &boxes) {
    return std::any_of(boxes.begin(), boxes.end(),
                       [&](Box4 other) { return rects_intersect_open(b, other); });
}
using SubjectMap = std::map<std::string, std::pair<std::string, Box4>>;
std::set<std::string> independently_locked_owned_members(const Placer &placer) {
    std::set<std::string> members, caps;
    if (!placer.ctx.in.floorplan.compact_search) return members;
    for (const auto &[sheet, evidence] : placer.ctx.in.owned_groups) {
        if (!evidence)
            throw std::runtime_error("placement moves: null trusted ownership for " + sheet);
        for (const auto &row : owned_group_placements(*evidence)) {
            if (!placer.pos.count(row.owner) && !placer.pos.count(row.cap)) continue;
            if (!placer.pos.count(row.owner) || !placer.pos.count(row.cap) ||
                placer.ctx.by_ref.at(row.owner).sheet != sheet ||
                placer.ctx.by_ref.at(row.cap).sheet != sheet ||
                row.owner == row.cap || !caps.insert(row.cap).second)
                throw std::runtime_error("placement moves: incomplete or inconsistent owned group in " + sheet);
            // Both bypass and output bulk retain their declared relationship.
            // These independent move/swap stages offer neither a rigid owned
            // group trial nor a named-pad nonincrease proof, so grant no new
            // movement permission to either endpoint. Other parts stay eligible.
            members.insert(row.owner);
            members.insert(row.cap);
        }
    }
    return members;
}
PcbCheckInput refit_fanout_geometry(const Placer &placer, const PcbStageRefitPoses *trial) {
    PcbCheckModel model;
    model.origin_x = model.origin_y = 25;
    model.board_w = placer.width;
    model.board_h = placer.height;
    for (const auto &[ref, xy] : placer.pos) {
        if (!placer.geometry.resolvable.count(ref)) continue;
        const auto &source = placer.ctx.by_ref.at(ref);
        PcbCheckInstance part;
        part.ref = ref;
        part.sheet = source.sheet;
        part.footprint = source.footprint;
        part.value = source.value;
        part.side = placer.fixed.count(ref) ? "top" : placer.side(ref);
        part.mod = placer.mod(ref);
        part.mirror = placer.geometry.mirror_refs.count(ref);
        part.x = xy.first;
        part.y = xy.second;
        part.rotation = placer.rot(ref);
        if (trial && trial->count(ref)) {
            const auto &pose = trial->at(ref);
            part.x = std::get<0>(pose);
            part.y = std::get<1>(pose);
            part.rotation = std::get<2>(pose);
        }
        for (const auto &pad : pad_names_from_text(part.mod->bytes)) {
            const auto net = placer.pin_net.find({ref, pad});
            part.pad_nets[pad] = net == placer.pin_net.end()
                ? std::pair<int, std::string>{0, ""} : net->second;
        }
        // Evaluate the coordinates that instantiate() will actually emit.
        // Count these real trial projections even if the move is rejected.
        if (placer.grid_placed.count(ref)) {
            part.x = placement_emission_pose_precision4dp(25 + part.x, &placer.ctx.quantization);
            part.y = placement_emission_pose_precision4dp(25 + part.y, &placer.ctx.quantization);
        } else {
            part.x = placer.ctx.fixed_grid(25 + part.x);
            part.y = placer.ctx.fixed_grid(25 + part.y);
        }
        model.insts.push_back(std::move(part));
    }
    return PcbCheckInput(std::move(model));
}
bool refit_preserves_fanout(const PcbCheckInput &incumbent, const PcbCheckInput &trial) {
    const auto before = check_fanout(incumbent, 0);
    const auto after = check_fanout(trial, 0);
    if (before.records.size() != after.records.size()) return false;
    std::map<std::string, PcbFanoutRecord> prior;
    for (const auto &record : before.records) prior.emplace(record.ref, record);
    // Compare subjects, not the total ratchet count: one repaired subject may
    // not pay for newly starving another. Existing starvation may not worsen.
    for (const auto &record : after.records) {
        const auto found = prior.find(record.ref);
        if (found == prior.end()) return false;
        const auto &old = found->second;
        if (record.starved() && (!old.starved() || record.clearance < old.clearance))
            return false;
    }
    return true;
}

using EvictRows = std::vector<OwnedCapPlacement>;
using EvictIndex = std::map<std::string, std::size_t>;
EvictIndex evict_index(const PcbCheckInput &input) {
    EvictIndex index;
    for (std::size_t i = 0; i < input.model().insts.size(); ++i)
        index.emplace(input.model().insts[i].ref, i);
    return index;
}
Box4 evict_box(const PcbCheckInput &input, std::size_t i) {
    const auto &part=input.model().insts.at(i);
    if (!part.mod || !part.mod->bbox)
        throw PcbZoneInfeasible("compact eviction: missing actual footprint bbox");
    const auto &g = input.geometry_at(i);
    if (!g.courtyard || !g.pad_bbox)
        throw PcbZoneInfeasible("compact eviction: missing actual courtyard/pads");
    const auto a = *g.courtyard, b = *g.pad_bbox;
    Box4 result{std::min(a.x0,b.x0), std::min(a.y0,b.y0),
                std::max(a.x1,b.x1), std::max(a.y1,b.y1)};
    const auto unite=[&](Box4 other) {
        result={std::min(result.x0,other.x0),std::min(result.y0,other.y0),
                std::max(result.x1,other.x1),std::max(result.y1,other.y1)};
    };
    // Gate reporting boxes round extents too. Keep the unrounded transformed
    // courtyard/named-pad extents at the emitted pose as well: a rounded box
    // must not hide an internal or THT separation loss.
    unite(offset_turned_box(*part.mod->bbox,part.rotation,part.x,part.y));
    for (const auto &[name,pad] : g.pad_boxes) { (void)name; unite(pad); }
    return {result.x0-25,result.y0-25,result.x1-25,result.y1-25};
}
double evict_gap(const PcbCheckInput &input, const EvictIndex &index, const OwnedCapPlacement &row) {
    const auto a = input.geometry_at(index.at(row.owner)).pad_boxes.at(row.owner_pin);
    const auto b = input.geometry_at(index.at(row.cap)).pad_boxes.at(row.cap_pin);
    return std::hypot(std::max({0.,a.x0-b.x1,b.x0-a.x1}),
                      std::max({0.,a.y0-b.y1,b.y0-a.y1}));
}
bool evict_movable(const Placer &p, const std::string &r) {
    if (!p.grid_placed.count(r) || p.fixed.count(r) || p.som_refs.count(r) ||
        !p.geometry.resolvable.count(r) || !p.geometry.bbox_of.count(r) ||
        p.geometry.conn_edge.count(r) || p.contract_members.count(r) ||
        std::find(p.geometry.mh_refs.begin(),p.geometry.mh_refs.end(),r)!=p.geometry.mh_refs.end())
        return false;
    const auto &part = p.ctx.by_ref.at(r);
    // Context builds l4_exempt from wired sheets and external zone targets,
    // not board references. Match l4_pull's sheet-keyed eligibility.
    return !p.ctx.l4_exempt.count(part.sheet) &&
        part.sheet.rfind("som_j",0)!=0 && part.sheet!="som_decoupling" &&
        part.footprint.find("Fiducial")==std::string::npos &&
        !(p.ctx.wired.count(part.sheet) && p.ctx.in.contracts.count(part.sheet));
}
bool evict_allocated(const Placer &p, const std::string &ref, Box4 b) {
    // No new leash radius: the existing allocated block is the authority.
    const auto &sheet = p.ctx.by_ref.at(ref).sheet;
    for (const auto *blocks : {&p.plan.edge_blocks,&p.plan.interior_blocks})
        for (const auto &block : *blocks) if (block.name==sheet)
            return b.x0>=block.x && b.y0>=block.y &&
                   b.x1<=block.x+block.w && b.y1<=block.y+block.h;
    return false; // Cannot prove an absent allocation.
}
bool evict_legal(const Placer &p, const PcbCheckInput &before, const PcbCheckInput &after,
                 const std::set<std::string> &members, const EvictRows &rows,
                 const std::vector<Box4> &corridors, bool rigid) {
    const auto prior=evict_index(before), next=evict_index(after);
    if (next.size()!=p.pos.size()) return false; // No invisible external obstacles.
    for (const auto &row : rows)
        if ((members.count(row.owner)||members.count(row.cap)) &&
            evict_gap(after,next,row)>evict_gap(before,prior,row))
            return false;
    const auto separation=[](Box4 a,Box4 b) {
        return std::max({a.x0-b.x1,b.x0-a.x1,a.y0-b.y1,b.y0-a.y1});
    };
    for (const auto &r : members) {
        if (!evict_movable(p,r)) return false;
        const auto &part=after.model().insts.at(next.at(r));
        const auto b=evict_box(after,next.at(r));
        const bool tht=has_thru_pads_from_text(part.mod->bytes);
        if (b.x0<.6 || b.y0<.6 || b.x1>p.width-.6 || b.y1>p.height-.6 ||
            !evict_allocated(p,r,b) || ((part.side=="bottom" || tht) && hit(b,corridors)) ||
            (part.side=="top" && rects_intersect_open(b,p.keepout)))
            return false;
        for (const auto &[s,i] : next) {
            if (r==s) continue;
            const auto &other=after.model().insts[i];
            if (part.side!=other.side && !tht && !has_thru_pads_from_text(other.mod->bytes))
                continue;
            if (separation(b,evict_box(after,i))<p.ctx.clearance) return false;
        }
    }
    if (!refit_preserves_fanout(before,after)) return false;
    if (rigid)
        for (const auto &record : check_fanout(after,0).records)
            if (record.starved()) return false;
    return true;
}
bool evict_bottom_shadow(const Placer &p, const std::string &ref) {
    return p.side(ref)=="bottom" || (p.geometry.resolvable.count(ref) &&
        has_thru_pads_from_text(p.mod(ref)->bytes));
}
void compact_evict(Placer &p) {
    // Validate trusted rows before any movement. Ownership does not grant
    // permission to move a fixed/contracted member.
    independently_locked_owned_members(p);
    EvictRows rows;
    for (const auto &[sheet,evidence] : p.ctx.in.owned_groups) {
        (void)sheet;
        for (const auto &row : owned_group_placements(*evidence))
            if (p.pos.count(row.owner)) rows.push_back(row);
    }
    std::vector<Box4> corridors;
    for (const auto &[r,j] : p.som_refs) {
        (void)j;
        if (p.pos.count(r) && p.geometry.resolvable.count(r))
            corridors.push_back(pcb_escape_corridor_board(*p.mod(r),
                p.ctx.corridor_grid(25,p.pos.at(r).first),
                p.ctx.corridor_grid(25,p.pos.at(r).second),p.rot(r),&p.ctx.quantization));
    }
    if (corridors.empty()) return;
    const auto entry=p.pos;
    auto event=[&](const std::string &s) {
        p.out.fallback_events.push_back(s);
        p.out.placement_accounting.fallback_events.push_back(s);
    };
    try {
        for (const auto &[ref,xy] : entry) {
            (void)xy;
            if (!evict_bottom_shadow(p,ref)) continue;
            const auto before=refit_fanout_geometry(p,nullptr);
            const auto index=evict_index(before);
            if (!index.count(ref))
                throw PcbZoneInfeasible("compact eviction: unresolved bottom-shadow member "+ref);
            const auto b=evict_box(before,index.at(ref));
            if (!hit(b,corridors)) continue;
            std::vector<std::tuple<double,double,double>> exits;
            for (const auto &c : corridors) if (rects_intersect_open(b,c)) {
                const double m=p.ctx.clearance/2;
                exits.emplace_back(c.x1-b.x0+m,c.x1-b.x0+m,0);
                exits.emplace_back(b.x1-c.x0+m,-(b.x1-c.x0+m),0);
                exits.emplace_back(c.y1-b.y0+m,0,c.y1-b.y0+m);
                exits.emplace_back(b.y1-c.y0+m,0,-(b.y1-c.y0+m));
            }
            std::sort(exits.begin(),exits.end());
            std::set<std::string> group{ref};
            bool added;
            do {
                added=false;
                for (const auto &row : rows) if (group.count(row.owner)||group.count(row.cap)) {
                    added|=group.insert(row.owner).second;
                    added|=group.insert(row.cap).second;
                }
            } while (added);
            bool moved=false;
            // Same finite exits/steps as the existing eviction; no extra
            // hardware limit or unbounded repair search. Independent first.
            for (bool rigid : {false,true}) {
                if (rigid && group.size()==1) break;
                const std::set<std::string> members=rigid?group:std::set<std::string>{ref};
                if (!std::all_of(members.begin(),members.end(),
                    [&](const auto &r){return evict_movable(p,r);})) continue;
                for (const auto &[distance,ex,ey] : exits) {
                    (void)distance;
                    for (int k=0;k<9;++k) {
                        const double dx=ex+(ex>0?k:ex<0?-k:0);
                        const double dy=ey+(ey>0?k:ey<0?-k:0);
                        PcbStageRefitPoses trial;
                        for (const auto &r : members) {
                            const auto old=p.pos.at(r);
                            trial[r]={placement_evict_trial_precision4dp(old.first+dx,&p.ctx.quantization),
                                      placement_evict_trial_precision4dp(old.second+dy,&p.ctx.quantization),p.rot(r)};
                        }
                        const auto after=refit_fanout_geometry(p,&trial);
                        if (!evict_legal(p,before,after,members,rows,corridors,rigid)) continue;
                        for (const auto &[r,pose] : trial) {
                            const FloorplanPoint next{std::get<0>(pose),std::get<1>(pose)};
                            if (p.pos.at(r)!=next) event("corridor_evict_moved");
                            p.pos[r]=next;
                        }
                        moved=true;
                        break;
                    }
                    if (moved) break;
                }
                if (moved) break;
            }
            if (!moved) {
                event("corridor_stray_unmovable");
                throw PcbZoneInfeasible("compact eviction: no legal ownership-preserving corridor exit for "+ref);
            }
        }
        // Do not silently accept another obstruction, including after a group
        // moved a member already visited by the loop.
        const auto final=refit_fanout_geometry(p,nullptr);
        for (const auto &[r,i] : evict_index(final))
            if (evict_bottom_shadow(p,r) && hit(evict_box(final,i),corridors)) {
                event("corridor_stray_unmovable");
                throw PcbZoneInfeasible("compact eviction: corridor remains obstructed by "+r);
            }
    } catch (...) {
        p.pos=entry; // Atomic geometry rollback, never rollback actual work.
        throw;
    }
}
} // namespace
void Placer::l4_pull() {
    const auto owned = independently_locked_owned_members(*this);
    double pc = ctx.clearance;
    auto center = FloorplanPoint{plan.som_x + plan.som.w / 2, plan.som_y + plan.som.h / 2};
    std::vector<Box4> through, corridors;
    std::map<std::string, Box4> bottom;
    SubjectMap subjects;
    for (const auto &[r, p] : pos) {
        if (side(r) == "top" && geometry.resolvable.count(r) &&
            has_thru_pads_from_text(mod(r)->bytes))
            through.push_back(grow_rect(box(r, p), pc));
        if (side(r) == "bottom" && geometry.bbox_of.count(r)) {
            bottom[r] = grow_rect(box(r, p), pc / 2);
            if (geometry.resolvable.count(r) && ctx.by_ref.count(r) && pins(r) >= 3)
                subjects[r] = {
                    ctx.by_ref.at(r).sheet,
                    grow_rect(box(r, p), std::max(0., ctx.credit(need(pins(r))) - pc / 2))};
        }
    }
    auto offset = ctx.in.floorplan.module_offset.value_or(FloorplanPoint{
        ctx.in.floorplan.project.module_offset[0], ctx.in.floorplan.project.module_offset[1]});
    if (pc > .5 || offset.first || offset.second)
        for (const auto &[r, j] : som_refs) {
            (void)j;
            if (geometry.resolvable.count(r) && pos.count(r))
                corridors.push_back(
                    pcb_escape_corridor_board(*mod(r), pos.at(r).first, pos.at(r).second, rot(r), &ctx.quantization));
        }
    for (const auto &[sheet, origin] : origins) {
        (void)origin;
        if (ctx.l4_exempt.count(sheet))
            continue;
        std::vector<std::string> movers;
        for (const auto &[r, p] : geometry.bot_off[sheet]) {
            (void)p;
            if (!owned.count(r) && side(r) == "bottom" && pos.count(r) && !r.empty() &&
                (r[0] == 'R' || r[0] == 'C' || r[0] == 'L') && r.rfind("RJ", 0) != 0 &&
                r.rfind("LED", 0) != 0)
                movers.push_back(r);
        }
        if (movers.size() < 2)
            continue;
        std::vector<FloorplanPoint> points;
        for (const auto &r : movers)
            points.push_back(pos.at(r));
        auto c = points_centroid(points);
        double vx = center.first - c.first, vy = center.second - c.second,
               dist = hypot_xy(0, 0, vx, vy);
        if (dist < 1)
            continue;
        double ux = vx / dist, uy = vy / dist;
        std::set<std::string> moving(movers.begin(), movers.end());
        std::vector<Box4> others;
        for (const auto &[r, b] : bottom)
            if (!moving.count(r))
                others.push_back(b);
        others.insert(others.end(), corridors.begin(), corridors.end());
        for (const auto &[r, s] : subjects)
            if (s.first != sheet && !moving.count(r))
                others.push_back(s.second);
        std::vector<std::string> all;
        double area = 0;
        for (const auto *offsets : {&geometry.top_off[sheet], &geometry.bot_off[sheet]})
            for (const auto &[r, p] : *offsets) {
                (void)p;
                if (pos.count(r) && geometry.bbox_of.count(r)) {
                    all.push_back(r);
                    auto b = box(r, {0, 0});
                    area += (b.x1 - b.x0) * (b.y1 - b.y0);
                }
            }
        if (!area)
            area = 1;
        double chosen = 0;
        for (int k = placement_l4_distance_trunc(std::min(dist, 40.), &ctx.quantization); k > 0; --k) {
            double shift = k;
            Offsets shifted;
            bool okay = true;
            for (const auto &r : movers) {
                auto old = pos.at(r);
                FloorplanPoint p{old.first + ux * shift, old.second + uy * shift};
                auto b = box(r, p);
                if (b.x0 < .6 || b.y0 < .6 || b.x1 > width - .6 || b.y1 > height - .6 ||
                    hit(grow_rect(b, pc / 2), others) || hit(grow_rect(b, pc / 2), through)) {
                    okay = false;
                    break;
                }
                shifted[r] = p;
            }
            if (!okay)
                continue;
            std::vector<Box4> boxes;
            for (const auto &r : all)
                boxes.push_back(box(r, shifted.count(r) ? shifted.at(r) : pos.at(r)));
            auto b = boxes_union(boxes);
            if (!b)
                continue;
            if ((b->x1 - b->x0) * (b->y1 - b->y0) / area > 5)
                continue;
            chosen = shift;
            break;
        }
        if (chosen > 0)
            for (const auto &r : movers) {
                auto p = pos.at(r);
                p = {placement_l4_pose_precision4dp(p.first + ux * chosen, &ctx.quantization), placement_l4_pose_precision4dp(p.second + uy * chosen, &ctx.quantization)};
                pos[r] = p;
                bottom[r] = grow_rect(box(r, p), pc / 2);
                auto s = subjects.find(r);
                if (s != subjects.end()) {
                    auto z = box(r, {0, 0});
                    double grow = (s->second.second.x1 - s->second.second.x0 - (z.x1 - z.x0)) / 2;
                    s->second.second = grow_rect(box(r, p), grow);
                }
            }
    }
}
void Placer::edge_seat() {
    for (const auto &[r, edge] : geometry.conn_edge) {
        if (!geometry.resolvable.count(r) || !pos.count(r))
            continue;
        std::vector<std::tuple<std::string, double, double, double, double, double>> rows;
        for (const auto &[name, type, x, y, rotation, w, h] : mod(r)->pads) {
            (void)name;
            rows.emplace_back(type, x, y, rotation, w, h);
        }
        std::vector<Box4> boxes;
        for (const auto &[type, x0, y0, x1, y1] : pad_boxes_local(rows, rot(r))) {
            (void)type;
            boxes.push_back({x0, y0, x1, y1});
        }
        auto b = boxes_union(boxes);
        if (!b)
            continue;
        auto p = pos.at(r);
        if (edge == "N")
            p.second = .4 - b->y0;
        else if (edge == "S")
            p.second = height - .4 - b->y1;
        else if (edge == "W")
            p.first = .4 - b->x0;
        else if (edge == "E")
            p.first = width - .4 - b->x1;
        pos[r] = {placement_edge_seat_precision4dp(p.first, &ctx.quantization), placement_edge_seat_precision4dp(p.second, &ctx.quantization)};
        grid_placed.insert(r);
    }
}
void Placer::refit(ExecutionFailureReceipt* failure) {
    std::map<std::string, std::vector<std::pair<std::string, std::string>>> net_pins;
    for (const auto &[key, n] : pin_net)
        if (!n.second.empty() && n.second.rfind("unconnected-", 0) != 0)
            net_pins[n.second].push_back(key);
    for (auto &[n, pins] : net_pins) {
        (void)n;
        std::sort(pins.begin(), pins.end());
    }
    PcbStageInput all;
    for (const auto &[r, key] : geometry.resolvable)
        all.footprints[r] = ctx.pool.at(key);
    Engine geometry_engine(all);
    for (const auto &[sheet, origin] : origins) {
        (void)origin;
        if (!ctx.wired.count(sheet) || !ctx.in.contracts.count(sheet))
            continue;
        const auto &contract = ctx.in.contracts.at(sheet);
        auto downstream = text(optional(contract, "external"), "downstream");
        if (downstream.empty())
            continue;
        std::vector<std::string> refs, down;
        for (const auto &r : geometry.refs_by_sheet[sheet])
            if (pos.count(r))
                refs.push_back(r);
        std::sort(refs.begin(), refs.end());
        for (const auto &r : geometry.refs_by_sheet[downstream])
            if (pos.count(r))
                down.push_back(r);
        // @som is a virtual target, not a sheet with component members.
        // Keep the frozen default pipeline unchanged; compact trials must use
        // the same physical target as the final facing gate.
        const bool som_target = ctx.in.floorplan.compact_search && downstream == "@som";
        if (refs.empty() || (!som_target && down.empty()) ||
            std::any_of(refs.begin(), refs.end(),
                        [&](const auto &r) { return geometry.conn_rot.count(r); }))
            continue;
        std::vector<FloorplanPoint> dp;
        for (const auto &r : down)
            dp.push_back(pos.at(r));
        auto centroid = som_target
            ? FloorplanPoint{plan.som_x + plan.som.w / 2, plan.som_y + plan.som.h / 2}
            : points_centroid(dp);
        std::set<std::string> own(refs.begin(), refs.end());
        std::map<std::string, std::vector<std::pair<std::string, std::string>>> own_pins;
        std::map<std::string, std::vector<std::tuple<double, double, std::string>>> foreign;
        for (const auto &[net, pins] : net_pins) {
            std::vector<std::pair<std::string, std::string>> own_net;
            for (const auto &p : pins)
                if (own.count(p.first))
                    own_net.push_back(p);
            if (own_net.empty())
                continue;
            own_pins[net] = own_net;
            auto &ext = foreign[net];
            for (const auto &[r, pin] : pins) {
                if (own.count(r) || !pos.count(r) || !geometry.resolvable.count(r))
                    continue;
                const auto &pb = geometry_engine.pads(mod(r), normalize(rot(r)));
                auto b = std::find_if(pb.begin(), pb.end(),
                                      [name = pin](const auto &p) { return p.first == name; });
                if (b == pb.end())
                    continue;
                auto p = pos.at(r);
                ext.emplace_back(placement_foreign_pad_precision3dp(p.first + (b->second.x0 + b->second.x1) / 2, &ctx.quantization),
                                 placement_foreign_pad_precision3dp(p.second + (b->second.y0 + b->second.y1) / 2, &ctx.quantization),
                                 ctx.by_ref.at(r).sheet);
            }
        }
        Offsets xy;
        for (const auto &r : refs)
            xy[r] = pos.at(r);
        auto result = refit_pcb_stage_facing_accounted(ctx.stage_input(sheet, geometry), xy, rotations,
                                             centroid, own_pins, foreign, failure);
        merge_execution_counts(ctx.quantization, result.quantization_engagements,failure);
        out.placement_accounting.fallback_events.insert(out.placement_accounting.fallback_events.end(),
            result.fallback_events.begin(), result.fallback_events.end());
        out.fallback_events.insert(out.fallback_events.end(), result.fallback_events.begin(), result.fallback_events.end());
        if (som_target && result.poses) {
            // The legacy refit pivots about the pad span. With asymmetric
            // courtyards that can move the reservation even for a half turn.
            // Translate this new compact trial rigidly back onto its original
            // courtyard envelope; do not move or resize the allocated zone.
            auto courtyard_center = [&](bool trial) {
                PcbCheckModel model;
                model.origin_x = 0;
                model.origin_y = 0;
                for (const auto &r : refs) {
                    PcbCheckInstance part;
                    part.ref = r;
                    part.mod = mod(r);
                    part.side = side(r);
                    const auto pose = trial ? result.poses->at(r)
                        : std::make_tuple(pos.at(r).first, pos.at(r).second, rot(r));
                    part.x = std::get<0>(pose);
                    part.y = std::get<1>(pose);
                    part.rotation = std::get<2>(pose);
                    model.insts.push_back(std::move(part));
                }
                PcbCheckInput checked(std::move(model));
                std::vector<Box4> boxes;
                for (std::size_t k = 0; k < refs.size(); ++k)
                    boxes.push_back(checked.courtyard_at(k));
                return boxes_span_center(boxes);
            };
            const auto before = courtyard_center(false), after = courtyard_center(true);
            for (auto &[r, pose] : *result.poses) {
                (void)r;
                std::get<0>(pose) += before.first - after.first;
                std::get<1>(pose) += before.second - after.second;
            }
            const auto input = ctx.stage_input(sheet, geometry);
            const Engine engine(input);
            const auto outputs = engine.output_refs();
            std::vector<FloorplanPoint> all_points, output_points;
            for (const auto &[r, pose] : *result.poses) {
                const FloorplanPoint point{std::get<0>(pose), std::get<1>(pose)};
                all_points.push_back(point);
                if (outputs.count(r)) output_points.push_back(point);
            }
            if (output_points.empty()) continue;
            const auto zone = points_centroid(all_points), output = points_centroid(output_points);
            if (!(facing_align_dot(zone.first, zone.second, output.first, output.second,
                                  centroid.first - zone.first, centroid.second - zone.second) > 0))
                continue;
        }
        // The compact refit must not buy a facing/airwire improvement by
        // starving another group. Preserve all trial receipts above, and
        // leave the incumbent poses intact when the trial fails this check.
        if (ctx.in.floorplan.compact_search && result.poses &&
            !refit_preserves_fanout(refit_fanout_geometry(*this, nullptr),
                                   refit_fanout_geometry(*this, &*result.poses)))
            continue;
        if (result.poses)
            for (const auto &[r, p] : *result.poses) {
                pos[r] = {std::get<0>(p), std::get<1>(p)};
                rotations[r] = std::get<2>(p);
            }
    }
}
void Placer::reorder() {
    const auto owned = independently_locked_owned_members(*this);
    std::vector<ReorderPos> poses;
    std::vector<std::tuple<std::string, std::vector<std::string>>> sheets, pad_names;
    std::vector<std::tuple<std::string, std::vector<std::tuple<std::string, double, double>>>>
        local;
    std::vector<std::tuple<std::string, std::string, std::string, double, bool>> members;
    std::vector<std::tuple<std::string, double, double, double, double>> boxes;
    std::vector<std::tuple<std::string, std::string, std::string>> pn;
    std::vector<std::tuple<std::string, std::vector<std::pair<std::string, std::string>>>> nets;
    std::vector<std::string> resolved, skip, conn;
    for (const auto &[r, p] : pos) {
        poses.emplace_back(r, p.first, p.second);
        if (!geometry.resolvable.count(r))
            continue;
        auto names = pad_names_from_text(mod(r)->bytes);
        pad_names.emplace_back(r, names);
        std::vector<std::tuple<std::string, double, double>> pads;
        for (const auto &[name, type, x, y, angle, w, h] : mod(r)->pads) {
            (void)type;
            (void)angle;
            (void)w;
            (void)h;
            pads.emplace_back(name, x, y);
        }
        auto xy = inst_pad_xy(pads, 0, 0, rot(r), 3);
        std::vector<std::tuple<std::string, double, double>> unique;
        for (const auto &p : xy) {
            auto found = std::find_if(unique.begin(), unique.end(), [&](const auto &q) {
                return std::get<0>(q) == std::get<0>(p);
            });
            if (found == unique.end())
                unique.push_back(p);
            else
                *found = p;
        }
        local.emplace_back(r, unique);
    }
    for (const auto &[sheet, refs] : geometry.refs_by_sheet) {
        sheets.emplace_back(sheet, refs);
        for (const auto &r : refs)
            if (!owned.count(r) && pos.count(r) && geometry.resolvable.count(r))
                members.emplace_back(
                    r, side(r), mod(r)->source, rot(r),
                    is_cluster_passive(r, pins(r), {"RS", "RJ", "RN", "LED"}, {"R", "C", "L"}));
    }
    for (const auto &[r, b] : geometry.bbox_of)
        boxes.emplace_back(r, b.x0, b.y0, b.x1, b.y1);
    for (const auto &[k, n] : pin_net)
        pn.emplace_back(k.first, k.second, n.second);
    for (const auto &[name, pins] : ctx.in.netlist) {
        std::vector<std::pair<std::string, std::string>> rows;
        for (const auto &p : pins)
            rows.emplace_back(p.ref, p.pin);
        nets.emplace_back(name, rows);
    }
    for (const auto &[r, k] : geometry.resolvable) {
        (void)k;
        resolved.push_back(r);
    }
    for (const auto &[r, v] : geometry.conn_rot) {
        (void)v;
        conn.push_back(r);
    }
    for (const auto &[s, p] : origins) {
        (void)p;
        if (ctx.wired.count(s) && ctx.in.contracts.count(s))
            skip.push_back(s);
    }
    auto result = reorder_interchangeable(poses, sheets, skip, conn, members, boxes, pad_names,
                                          local, pn, nets, resolved);
    for (const auto &[r, x, y] : std::get<0>(result))
        pos[r] = {x, y};
}
void Placer::evict() {
    if (ctx.in.floorplan.compact_search) {
        compact_evict(*this);
        return;
    }
    std::vector<Box4> corridors, through;
    std::map<std::string, Box4> bottom;
    SubjectMap subjects;
    double pc = ctx.clearance;
    for (const auto &[r, j] : som_refs) {
        (void)j;
        if (pos.count(r) && geometry.resolvable.count(r))
            corridors.push_back(
                pcb_escape_corridor_board(*mod(r), ctx.corridor_grid(25, pos.at(r).first),
                                          ctx.corridor_grid(25, pos.at(r).second), rot(r), &ctx.quantization));
    }
    for (const auto &[r, p] : pos) {
        if (!geometry.bbox_of.count(r))
            continue;
        if (side(r) == "bottom")
            bottom[r] = box(r, p);
        else if (geometry.resolvable.count(r) && has_thru_pads_from_text(mod(r)->bytes))
            through.push_back(box(r, p));
    }
    for (const auto &[r, b] : bottom)
        if (geometry.resolvable.count(r) && ctx.by_ref.count(r) && pins(r) >= 3)
            subjects[r] = {ctx.by_ref.at(r).sheet,
                           grow_rect(b, std::max(0., ctx.credit(need(pins(r))) - pc))};
    for (auto &[ref, b] : bottom) {
        if (!hit(b, corridors))
            continue;
        std::vector<std::tuple<double, double, double>> exits;
        double m = pc / 2;
        for (const auto &c : corridors)
            if (rects_intersect_open(b, c)) {
                exits.emplace_back(c.x1 - b.x0 + m, c.x1 - b.x0 + m, 0);
                exits.emplace_back(b.x1 - c.x0 + m, -(b.x1 - c.x0 + m), 0);
                exits.emplace_back(c.y1 - b.y0 + m, 0, c.y1 - b.y0 + m);
                exits.emplace_back(b.y1 - c.y0 + m, 0, -(b.y1 - c.y0 + m));
            }
        std::sort(exits.begin(), exits.end());
        bool moved = false;
        for (const auto &[d, ex, ey] : exits) {
            (void)d;
            for (int k = 0; k < 9; ++k) {
                double sx = ex + (ex > 0   ? k
                                  : ex < 0 ? -k
                                           : 0),
                       sy = ey + (ey > 0   ? k
                                  : ey < 0 ? -k
                                           : 0);
                auto old = pos.at(ref);
                FloorplanPoint p{placement_evict_trial_precision4dp(old.first + sx, &ctx.quantization), placement_evict_trial_precision4dp(old.second + sy, &ctx.quantization)};
                auto next = box(ref, p);
                if (next.x0 < .6 || next.y0 < .6 || next.x1 > width - .6 || next.y1 > height - .6 ||
                    hit(next, corridors))
                    continue;
                auto grown = grow_rect(next, pc);
                bool blocked = hit(grown, through);
                for (const auto &[r, other] : bottom)
                    if (r != ref && rects_intersect_open(grown, other))
                        blocked = true;
                for (const auto &[r, s] : subjects)
                    if (r != ref && s.first != ctx.by_ref.at(ref).sheet &&
                        rects_intersect_open(grown, s.second))
                        blocked = true;
                if (blocked)
                    continue;
                pos[ref] = p;
                b = next;
                moved = true;
                break;
            }
            if (moved)
                break;
        }
        out.fallback_events.push_back(moved ? "corridor_evict_moved" : "corridor_stray_unmovable");
        out.placement_accounting.fallback_events.push_back(out.fallback_events.back());
    }
}
} // namespace schgen::pcb_placement
