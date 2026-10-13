#include "pcb_placement_internal.hpp"
#include "pcb_placement_orientations.hpp"
#include "schgen/pcb_placement_gates.hpp"
#include "contract_rigid_groups_internal.hpp"

namespace schgen::pcb_placement {
double bottom_contact_shift(double value,QuantizationCounts* counts) {
    if(!std::isfinite(value))throw std::invalid_argument("nonfinite bottom contact shift");
    auto rounded=placement_bottom_pose_precision4dp(value,counts);
    const auto inward=[&]{return value>0?rounded<value:rounded>value;};
    if(inward())rounded=placement_bottom_pose_precision4dp(rounded+std::copysign(.0001,value),counts);
    if(!std::isfinite(rounded)||inward())throw std::overflow_error("bottom contact shift exceeds output precision");
    return rounded;
}
bool same_zone_shape_geometry(const Shape& a, const Shape& b) {
    if (a.w != b.w || a.h != b.h || a.top_off != b.top_off ||
        a.bot_off != b.bot_off || a.side != b.side || a.mirror != b.mirror) return false;
    // Missing rotations already mean zero to the consumer. Compare their
    // meaning without filling/rewriting either original rotation map.
    const auto agrees = [](const Rotations& x, const Rotations& y) {
        for (const auto& [ref, angle] : x) {
            const auto found = y.find(ref);
            if (angle != (found == y.end() ? 0 : found->second)) return false;
        }
        return true;
    };
    return agrees(a.extra_rot, b.extra_rot) && agrees(b.extra_rot, a.extra_rot);
}
void append_distinct_zone_shapes(Shape incumbent,std::vector<Shape>& existing,
                                const std::vector<Shape>& candidates) {
    for(const auto& candidate:candidates)
        if(!same_zone_shape_geometry(incumbent,candidate)&&
           std::none_of(existing.begin(),existing.end(),[&](const auto& prior){return same_zone_shape_geometry(prior,candidate);}))
            existing.push_back(candidate);
}
namespace {
Shape enclose_courtyards(Context& ctx,const Geometry& g,const Shape& source) {
    auto enclosed=source;
    double left=0,top=0,right=source.w,bottom=source.h;
    for(const auto* offsets:{&source.top_off,&source.bot_off})for(const auto& [ref,xy]:*offsets) {
        const auto key=source.mirror.count(ref)?source.mirror.at(ref):g.resolvable.at(ref);
        const auto& mod=ctx.pool.at(key);
        if(!mod->bbox)throw PcbZoneInfeasible("template has no courtyard: "+ref);
        const auto box=offset_turned_box(*mod->bbox,source.extra_rot.count(ref)?source.extra_rot.at(ref):0,xy.first,xy.second);
        left=std::min(left,box.x0);top=std::min(top,box.y0);
        right=std::max(right,box.x1);bottom=std::max(bottom,box.y1);
    }
    // Keep the rigid arrangement; enclose measured geometry rather than
    // weakening boundary checks when the stage envelope omitted a margin.
    const double dx=bottom_contact_shift(-left,&ctx.quantization),dy=bottom_contact_shift(-top,&ctx.quantization);
    for(auto* offsets:{&enclosed.top_off,&enclosed.bot_off})for(auto& [ref,xy]:*offsets) {
        (void)ref;xy.first=placement_bottom_pose_precision4dp(xy.first+dx,&ctx.quantization);
        xy.second=placement_bottom_pose_precision4dp(xy.second+dy,&ctx.quantization);
    }
    enclosed.w=bottom_contact_shift(right+dx,&ctx.quantization);
    enclosed.h=bottom_contact_shift(bottom+dy,&ctx.quantization);
    return enclosed;
}
bool orientation_eligible(const Context& ctx, const Geometry& g, const std::string& sheet,
                          bool board_checked_external=false) {
    if (!ctx.in.floorplan.compact_search) return false;
    if (ctx.in.floorplan.spec && ctx.in.floorplan.spec->edge_of().count(sheet)) return false;
    // External direction/near/flow targets require board-level reasoning.
    // Do not invent a local proxy or weaken those authored constraints.
    auto contract = ctx.in.contracts.find(sheet);
    if (contract != ctx.in.contracts.end()) {
        const auto& external = optional(contract->second, "external");
        if (external.kind != JsonKind::Null &&
            !(external.kind == JsonKind::Object && external.object_value.empty())) {
            // Only explicit face-group exploration may defer these terms to
            // the board-level compose/final gates, and only for wired sheets.
            // Ordinary orientation expansion retains its local-only policy.
            const auto& schema=optional(contract->second,"contract");
            if(!board_checked_external||!ctx.wired.count(sheet)||schema.kind!=JsonKind::String||
               schema.string_value!="placement/v2"||external.kind!=JsonKind::Object)return false;
            const std::set<std::string> supported{"flow","downstream","output_roles","far","near_max","media_faces_near_max"};
            for(const auto& [key,value]:external.object_value){(void)value;if(!supported.count(key))return false;}
        }
    }
    for (const auto& ref : g.refs_by_sheet.at(sheet)) {
        const auto& part = ctx.by_ref.at(ref);
        // This exact authored stock pad is a probe target, not a mating
        // connector. Keep all other connector tests and top-access checks.
        const bool probe_pad = part.lib_id == "Connector:TestPoint" &&
            part.footprint == "TestPoint:TestPoint_Pad_D1.5mm";
        if (g.conn_rot.count(ref) || g.conn_edge.count(ref) ||
            edge_family(part.value) || connector_value(part.value) || ref_prefix(ref) == "J" ||
            (part.lib_id.find("Connector") != std::string::npos && !probe_pad) ||
            part.footprint.find("PinHeader") != std::string::npos ||
            part.footprint.find("PinSocket") != std::string::npos ||
            part.footprint.find("DF40") != std::string::npos) return false;
    }
    return true;
}
bool orientation_holds(const Context& ctx, const Geometry& g, const std::string& sheet,
                       const Shape& shape) {
    if (!std::isfinite(shape.w) || !std::isfinite(shape.h) || shape.w <= 0 || shape.h <= 0 ||
        (shape.side != "top" && shape.side != "bottom")) return false;
    PcbCheckModel model; model.board_w = shape.w; model.board_h = shape.h;
    model.origin_x = 0; model.origin_y = 0;
    std::set<std::string> seen;
    for (const auto* offsets : {&shape.top_off, &shape.bot_off})
        for (const auto& [ref, xy] : *offsets) {
            if (!seen.insert(ref).second || !g.resolvable.count(ref)) return false;
            const auto& part = ctx.by_ref.at(ref);
            PcbCheckInstance inst; inst.ref = ref; inst.sheet = sheet;
            inst.value = part.value; inst.footprint = part.footprint;
            const bool primary = offsets == &shape.top_off;
            inst.side = primary ? shape.side : (shape.side == "top" ? "bottom" : "top");
            if (face_top(part) && inst.side != "top") return false;
            auto mirrored = shape.mirror.find(ref);
            inst.mod = ctx.pool.at(mirrored == shape.mirror.end()
                ? g.resolvable.at(ref) : mirrored->second);
            inst.mirror = mirrored != shape.mirror.end();
            inst.x = xy.first; inst.y = xy.second;
            auto rotation = shape.extra_rot.find(ref);
            inst.rotation = rotation == shape.extra_rot.end() ? 0 : rotation->second;
            model.insts.push_back(std::move(inst));
        }
    if (seen != std::set<std::string>(g.refs_by_sheet.at(sheet).begin(),
                                      g.refs_by_sheet.at(sheet).end())) return false;
    const PcbCheckInput checked(std::move(model));
    for (std::size_t i = 0; i < checked.model().insts.size(); ++i) {
        const auto b = checked.courtyard_at(i);
        if (b.x0 < 0 || b.y0 < 0 || b.x1 > shape.w || b.y1 > shape.h) return false;
    }
    auto contract = ctx.in.contracts.find(sheet);
    if (contract != ctx.in.contracts.end() &&
        !check_pcb_placement_contract(checked, sheet, &contract->second,
                                      ctx.board_refs.at(sheet)).ok) return false;
    return true;
}
}
void append_rigid_zone_orientations(Context& ctx, Geometry& g, const std::string& sheet,
                                    const Shape& incumbent, std::size_t first_original) {
    if (!orientation_eligible(ctx, g, sheet)) return;
    const auto found = g.shapes.find(sheet);
    const std::vector<Shape> originals = found == g.shapes.end()
        ? std::vector<Shape>{incumbent} : found->second;
    auto variants = originals;
    if(first_original>originals.size())throw PcbZoneInfeasible("orientation suffix starts beyond registered shapes");
    for (std::size_t index=first_original;index<originals.size();++index) {
        const auto& original=originals[index];
        if (!orientation_holds(ctx, g, sheet, original)) continue;
        auto next = original;
        for (const auto* suffix : {"/r90", "/r180", "/r270"}) {
            // Existing registered scalars account for each actual trial,
            // including rejected or duplicate alternatives.
            next = turned(next, &ctx.quantization);
            next.tag = original.tag + suffix;
            if (orientation_holds(ctx, g, sheet, next) &&
                std::none_of(variants.begin(), variants.end(),
                    [&](const auto& prior) { return same_zone_shape_geometry(prior, next); }))
                variants.push_back(next);
        }
    }
    if (variants.size() > originals.size()) g.shapes[sheet] = std::move(variants);
}
void append_contract_group_faces(Context& ctx,Geometry& g,const std::string& sheet,const Shape& original,
                                 bool group_rotations) {
    // Local geometry candidates, not hardware qualification. Preserve the
    // incumbent and explore four deterministic alignments per eligible
    // contract-connected group/orientation. Final board gates remain authoritative.
    if(!orientation_eligible(ctx,g,sheet,true)||original.side!="top")return;
    const auto contract=ctx.in.contracts.find(sheet);
    if(contract==ctx.in.contracts.end())return;
    const auto& schema=optional(contract->second,"contract");
    const auto seed=schema.kind==JsonKind::String&&schema.string_value=="placement/v2"
        ?enclose_courtyards(ctx,g,original):original;
    if(!orientation_holds(ctx,g,sheet,seed))return;
    std::set<std::string> pinned;
    for(const auto& ref:g.refs_by_sheet.at(sheet))
        if(face_top(ctx.by_ref.at(ref))||has_thru_pads_from_text(ctx.pool.at(g.resolvable.at(ref))->bytes))pinned.insert(ref);
    for(const auto& sc:ctx.in.floorplan.sheets)if(sc.name==sheet)
        for(const auto& net:sc.nets) {
            const auto nc=ctx.netclass_of.find(net.name);
            if(nc==ctx.netclass_of.end()||!ctx.classes.at(nc->second))continue;
            for(const auto& pin:net.pins)if(!pin.ref.empty()&&pin.ref.front()!='#')
                pinned.insert(ctx.board_refs.at(sheet).at(pin.ref));
        }
    const auto stage=ctx.stage_input(sheet,g);
    const auto groups=contract_rigid_groups(contract->second,ctx.board_refs.at(sheet),pinned,true,&stage.pad_nets);
    if(!groups)return;
    std::map<std::string,decltype(PcbCheckInstance::pad_nets)> pad_nets;
    // Match final emission: unconnected physical pads still count toward the
    // fanout tier. An empty map would silently skip every multi-pin subject.
    for(const auto& ref:g.refs_by_sheet.at(sheet))
        for(const auto& pin:pad_names_from_text(ctx.pool.at(g.resolvable.at(ref))->bytes)) {
            const auto net=stage.pad_nets.find({ref,pin});
            pad_nets[ref].emplace(pin,std::make_pair(0,net==stage.pad_nets.end()?std::string{}:net->second));
        }
    const auto model=[&](const Shape& s) {
        PcbCheckModel m;m.board_w=s.w;m.board_h=s.h;m.origin_x=0;m.origin_y=0;
        for(const auto* offsets:{&s.top_off,&s.bot_off})for(const auto& [ref,xy]:*offsets) {
            const auto& p=ctx.by_ref.at(ref);PcbCheckInstance i;
            i.ref=ref;i.sheet=sheet;i.value=p.value;i.footprint=p.footprint;
            if(const auto pins=pad_nets.find(ref);pins!=pad_nets.end())i.pad_nets=pins->second;
            i.x=xy.first;i.y=xy.second;i.rotation=s.extra_rot.count(ref)?s.extra_rot.at(ref):0;
            i.side=offsets==&s.top_off?"top":"bottom";i.mirror=s.mirror.count(ref);
            i.mod=ctx.pool.at(i.mirror?s.mirror.at(ref):g.resolvable.at(ref));m.insts.push_back(std::move(i));
        }
        return PcbCheckInput(std::move(m));
    };
    const auto before=model(seed);
    std::map<std::string,Box4> boxes;
    double old_right=0,old_bottom=0;
    for(std::size_t i=0;i<before.model().insts.size();++i) {
        const auto box=before.courtyard_at(i);boxes.emplace(before.model().insts[i].ref,box);
        old_right=std::max(old_right,box.x1);old_bottom=std::max(old_bottom,box.y1);
    }
    const auto qualify=[&](Shape& candidate) {
        const auto checked=model(candidate);double right=0,bottom=0;bool physical=true;
        for(std::size_t i=0;i<checked.model().insts.size();++i) {
            const auto a=checked.courtyard_at(i);right=std::max(right,a.x1);bottom=std::max(bottom,a.y1);
            physical&=a.x0>=0&&a.y0>=0;
            for(std::size_t j=0;j<i;++j) {
                const auto& pi=checked.model().insts[i];const auto& pj=checked.model().insts[j];
                if(pi.side!=pj.side&&!has_thru_pads_from_text(pi.mod->bytes)&&!has_thru_pads_from_text(pj.mod->bytes))continue;
                const auto b=checked.courtyard_at(j);
                if(a.x0<b.x1+ctx.clearance&&a.x1+ctx.clearance>b.x0&&
                   a.y0<b.y1+ctx.clearance&&a.y1+ctx.clearance>b.y0)physical=false;
            }
        }
        if(!physical)return false;
        candidate.w=placement_variant_dimension_precision4dp(right+seed.w-old_right,&ctx.quantization);
        candidate.h=placement_variant_dimension_precision4dp(bottom+seed.h-old_bottom,&ctx.quantization);
        // Face assignments may help global packing without reducing local area.
        if(!orientation_holds(ctx,g,sheet,candidate)||!check_fanout(model(candidate),0).ok)return false;
        return true;
    };
    const auto append_checked=[&](Shape candidate) {
        if(!qualify(candidate))return false;
        auto found=g.shapes.find(sheet);
        if(found==g.shapes.end())found=g.shapes.emplace(sheet,std::vector<Shape>{original}).first;
        if(std::none_of(found->second.begin(),found->second.end(),[&](const auto& old){return same_zone_shape_geometry(old,candidate);}))
            found->second.push_back(std::move(candidate));
        return true;
    };
    std::vector<Shape> single_group;
    // Keep every original offer in its original index before appending turns.
    for(int turn=0;turn<(group_rotations?4:1);++turn) {
    std::vector<Shape> contact_pairs;
    const auto previous_singles=single_group.size();
    for(const auto& group:*groups) {
        if(group.refs.size()<2||!group.required_top_refs.empty())continue;
        bool eligible=true;
        std::vector<Box4> moved_boxes,remaining_boxes;
        for(const auto& ref:group.refs) {
            eligible&=seed.top_off.count(ref)&&!seed.mirror.count(ref);
            moved_boxes.push_back(boxes.at(ref));
        }
        if(!eligible)continue;
        for(const auto& [ref,box]:boxes)
            if(!std::binary_search(group.refs.begin(),group.refs.end(),ref))remaining_boxes.push_back(box);
        const auto moving=boxes_union(moved_boxes),remaining=boxes_union(remaining_boxes);
        if(!moving||!remaining)continue;
        try {
            for(const auto& ref:group.refs) {
                const auto key=g.resolvable.at(ref),mk="@mirror/"+key;
                if(ctx.pool.count(mk))continue;
                const auto fp=ctx.pool.at(key);const auto document=mirrored_footprint(fp->document);
                auto parent=std::filesystem::path(fp->source).parent_path().filename().string();
                if(parent.size()>=7&&parent.compare(parent.size()-7,7,".pretty")==0)parent.resize(parent.size()-7);
                const auto path=(std::filesystem::path(".mirrored_fp")/(parent+"__"+
                    std::filesystem::path(fp->source).stem().string()+".kicad_mod")).string();
                ctx.pool.emplace(mk,pcb_check_footprint(path,sexpr_dumps(document)+"\n",document));
            }
        } catch(const MirrorUnsupported&) {continue;}
        const double original_width=moving->x1-moving->x0,original_height=moving->y1-moving->y0;
        const double width=turn%2?original_height:original_width;
        const double height=turn%2?original_width:original_height;
        for(const auto target:std::vector<FloorplanPoint>{{remaining->x0,remaining->y0},
                {remaining->x1-width,remaining->y0},{remaining->x0,remaining->y1-height},
                {remaining->x1-width,remaining->y1-height}}) {
            Shape candidate=seed;
            candidate.tag="contract-bottom/"+group.refs.front()+"/"+std::to_string(target.first)+"/"+std::to_string(target.second);
            if(turn)candidate.tag+="/group-r"+std::to_string(90*turn);
            for(const auto& ref:group.refs) {
                const auto xy=seed.top_off.at(ref);candidate.top_off.erase(ref);
                FloorplanPoint local{moving->x1-xy.first,xy.second-moving->y0};
                double w=original_width,h=original_height;
                for(int t=0;t<turn;++t){local={local.second,w-local.first};std::swap(w,h);}
                candidate.bot_off[ref]={placement_bottom_pose_precision4dp(local.first+target.first,&ctx.quantization),
                    placement_bottom_pose_precision4dp(local.second+target.second,&ctx.quantization)};
                candidate.extra_rot[ref]=normalize(180-(seed.extra_rot.count(ref)?seed.extra_rot.at(ref):0)+90*turn);
                const auto key=g.resolvable.at(ref),mk="@mirror/"+key;
                candidate.mirror[ref]=mk;
            }
            if(append_checked(candidate))single_group.push_back(std::move(candidate));
        }
    }
    // Combine disjoint connected groups, not arbitrary individual components.
    // Singles stay first; every combination is independently checked because
    // two legal moves can collide or jointly starve a fanout corridor.
    for(std::size_t i=0;i<single_group.size();++i)for(std::size_t j=i+1;j<single_group.size();++j) {
        if(j<previous_singles)continue; // earlier orientations already combined these
        const auto& a=single_group[i];const auto& b=single_group[j];
        bool disjoint=true;
        for(const auto& [ref,xy]:b.bot_off) {
            (void)xy;
            if(seed.top_off.count(ref)&&!a.top_off.count(ref))disjoint=false;
        }
        if(!disjoint)continue;
        Shape candidate=a;
        candidate.tag="contract-bottom-pair/"+a.tag+"+"+b.tag;
        for(const auto& [ref,xy]:b.bot_off)if(seed.top_off.count(ref)) {
            candidate.top_off.erase(ref);candidate.bot_off[ref]=xy;
            candidate.extra_rot[ref]=b.extra_rot.at(ref);candidate.mirror[ref]=b.mirror.at(ref);
        }
        if(append_checked(candidate))continue;
        // Corner-aligned singles can overlap when combined. Derive rigid
        // translations from actual colliding courtyards, not a sampling grid.
        const auto placed=model(candidate);
        std::set<FloorplanPoint> shifts;
        const auto moved=[&](const std::string& ref){return seed.top_off.count(ref)&&b.bot_off.count(ref);};
        for(std::size_t bi=0;bi<placed.model().insts.size();++bi) {
            if(!moved(placed.model().insts[bi].ref))continue;
            const auto box=placed.courtyard_at(bi);
            for(std::size_t oi=0;oi<placed.model().insts.size();++oi) {
                const auto& obstacle=placed.model().insts[oi];
                if(moved(obstacle.ref)||(obstacle.side!="bottom"&&!has_thru_pads_from_text(obstacle.mod->bytes)))continue;
                const auto other=placed.courtyard_at(oi);
                if(box.x0>=other.x1+ctx.clearance||box.x1+ctx.clearance<=other.x0||
                   box.y0>=other.y1+ctx.clearance||box.y1+ctx.clearance<=other.y0)continue;
                shifts.emplace(other.x1+ctx.clearance-box.x0,0);
                shifts.emplace(other.x0-ctx.clearance-box.x1,0);
                shifts.emplace(0,other.y1+ctx.clearance-box.y0);
                shifts.emplace(0,other.y0-ctx.clearance-box.y1);
            }
        }
        for(const auto& raw:shifts) {
            const FloorplanPoint shift{bottom_contact_shift(raw.first,&ctx.quantization),
                                      bottom_contact_shift(raw.second,&ctx.quantization)};
            Shape translated=candidate;
            translated.tag+="/contact/"+std::to_string(shift.first)+"/"+std::to_string(shift.second);
            for(auto& [ref,xy]:translated.bot_off)if(moved(ref)) {
                xy.first=placement_bottom_pose_precision4dp(xy.first+shift.first,&ctx.quantization);
                xy.second=placement_bottom_pose_precision4dp(xy.second+shift.second,&ctx.quantization);
            }
            contact_pairs.push_back(std::move(translated));
        }
    }
    // Keep each orientation's existing offers ahead of its checked repairs.
    for(auto& candidate:contact_pairs)append_checked(std::move(candidate));
    }
    // Reuse vacated space for unconstrained singleton leftovers. Preserve their
    // face and orientation (notably service LEDs); every contact move goes
    // through the same physical, local-contract and fanout gates as new offers.
    // This is a finite coordinate descent over existing courtyard contacts,
    // not a sampled grid or a claim of optimal packing.
    if(schema.kind==JsonKind::String&&schema.string_value=="placement/v2") {
        const auto found=g.shapes.find(sheet);
        if(found==g.shapes.end())return;
        const auto offers=found->second;
        for(const auto& offer:offers) {
            if(offer.tag.rfind("contract-bottom",0)!=0)continue;
            auto compact=offer;
            std::vector<std::string> leftovers;
            for(const auto& group:*groups)if(group.refs.size()==1)leftovers.push_back(group.refs.front());
            std::sort(leftovers.begin(),leftovers.end(),[&](const auto& a,const auto& b){
                const auto position=[&](const auto& ref){return compact.top_off.count(ref)?compact.top_off.at(ref):compact.bot_off.at(ref);};
                return std::make_pair(-position(a).first,a)<std::make_pair(-position(b).first,b);
            });
            for(const auto& ref:leftovers) {
                const bool top=compact.top_off.count(ref);
                const auto measured=model(compact);
                std::size_t index=0;
                while(measured.model().insts.at(index).ref!=ref)++index;
                const auto bounds=measured.courtyard_at(index);
                std::set<double> shifts{-bounds.x0};
                for(std::size_t i=0;i<measured.model().insts.size();++i)if(i!=index) {
                    const auto& obstacle=measured.model().insts[i];
                    if((obstacle.side=="top")!=top&&!has_thru_pads_from_text(obstacle.mod->bytes))continue;
                    const auto box=measured.courtyard_at(i);
                    shifts.insert(box.x1+ctx.clearance-bounds.x0);
                }
                for(const auto raw:shifts) {
                    if(raw>=0)continue;
                    auto moved=compact;
                    auto& xy=(top?moved.top_off:moved.bot_off).at(ref);
                    // Round toward the obstacle-free side of a left contact.
                    xy.first=placement_bottom_pose_precision4dp(
                        bottom_contact_shift(xy.first+raw,&ctx.quantization),&ctx.quantization);
                    if(qualify(moved)&&moved.w*moved.h<=compact.w*compact.h) {
                        compact=std::move(moved);break;
                    }
                }
            }
            if(compact.w*compact.h<offer.w*offer.h) {
                compact.tag=offer.tag+"/leftover-contact";
                append_checked(std::move(compact));
            }
        }
    }
}

bool mirror_holds(const Context &ctx, const Geometry &g, const std::string &sheet,
                  const Shape &shape) {
    if (!ctx.in.contracts.count(sheet))
        return true;
    auto input = ctx.stage_input(sheet, g);
    Engine engine(input);
    Offsets offsets = shape.top_off;
    offsets.insert(shape.bot_off.begin(), shape.bot_off.end());
    auto pads = [&](const std::string &lib) -> NamedBoxes {
        auto br = input.board_refs.find(lib);
        if (br == input.board_refs.end())
            return {};
        const auto &r = br->second;
        auto p = offsets.find(r);
        if (p == offsets.end())
            return {};
        auto fp = input.footprints.find(r);
        if (fp == input.footprints.end())
            return {};
        auto mirror = shape.mirror.find(r);
        auto mod = mirror == shape.mirror.end() ? fp->second : ctx.pool.at(mirror->second);
        double rot = 0;
        auto base = g.conn_rot.find(r);
        if (base != g.conn_rot.end())
            rot = base->second;
        auto extra = shape.extra_rot.find(r);
        if (extra != shape.extra_rot.end())
            rot += extra->second;
        return engine.pads({r, mod, normalize(rot), p->second.first, p->second.second});
    };
    for (const auto &s : optional(input.contract, "structures").array_value)
        if (text(s, "type") == "proximity") {
            auto a = pads(text(s, "anchor"));
            if (a.empty())
                continue;
            for (const auto &lib : strings(s, "members")) {
                auto m = pads(lib);
                if (m.empty())
                    continue;
                if (distance(a, m, strings(s, "anchor_pins")) > number(s, "max_mm"))
                    return false;
                for (const auto &mf : optional(s, "min_from").array_value) {
                    auto b = pads(text(mf, "part"));
                    if (b.empty())
                        continue;
                    auto pin = text(mf, "pin");
                    if (distance(b, m,
                                 pin.empty()
                                     ? std::vector<std::string>{}
                                     : std::vector<std::string>{pin}) < number(mf, "min_mm"))
                        return false;
                }
            }
        }
    return true;
}
std::optional<Shape> member_mirror(const Context &ctx, const Geometry &g, const std::string &sheet,
                                   const PcbStageResult &p, const Rotations &connectors) {
    Shape s;
    s.w = placement_variant_dimension_precision4dp(p.w, &ctx.quantization);
    s.h = placement_variant_dimension_precision4dp(p.h, &ctx.quantization);
    s.top_off = p.top;
    s.bot_off = p.bottom;
    s.tag = "mirror";
    std::vector<std::pair<std::string, Box4>> members;
    std::vector<Box4> boxes, conn_boxes;
    for (const auto *offsets : {&p.top, &p.bottom})
        for (const auto &[r, xy] : *offsets) {
            auto rot = p.rotations.find(r);
            auto b = offset_turned_box(g.bbox_of.at(r), rot == p.rotations.end() ? 0 : rot->second,
                                       xy.first, xy.second);
            if (!connectors.count(r)) {
                members.push_back({r, b});
                boxes.push_back(b);
            } else {
                conn_boxes.push_back(
                    offset_turned_box(g.bbox_of.at(r), connectors.at(r), xy.first, xy.second));
                s.extra_rot[r] = 0;
            }
        }
    if (members.empty())
        return {};
    auto center = rect_center(*boxes_union(boxes));
    for (const auto &[r, b] : members) {
        Box4 next{placement_member_box_precision4dp(2 * center.first - b.x1, &ctx.quantization), placement_member_box_precision4dp(2 * center.second - b.y1, &ctx.quantization),
                  placement_member_box_precision4dp(2 * center.first - b.x0, &ctx.quantization), placement_member_box_precision4dp(2 * center.second - b.y0, &ctx.quantization)};
        if (next.x0 < -1e-6 || next.y0 < -1e-6 || next.x1 > p.w + 1e-6 || next.y1 > p.h + 1e-6)
            return {};
        for (const auto &c : conn_boxes)
            if (boxes_overlap(next, c, ctx.clearance))
                return {};
        auto &xy = s.top_off.count(r) ? s.top_off.at(r) : s.bot_off.at(r);
        xy = {placement_member_pose_precision4dp(2 * center.first - xy.first, &ctx.quantization), placement_member_pose_precision4dp(2 * center.second - xy.second, &ctx.quantization)};
        auto rot = p.rotations.find(r);
        s.extra_rot[r] = normalize((rot == p.rotations.end() ? 0 : rot->second) + 180);
    }
    if (!mirror_holds(ctx, g, sheet, s))
        return {};
    return s;
}
std::vector<Shape> bottom_shapes(Context &ctx, const Geometry &g, const std::string &sheet,
                                 const std::set<std::string> &face,
                                 const std::optional<PcbStageResult> &tmpl,
                                 const std::set<std::string> &members,
                                 std::vector<std::string> &events) {
    auto mirror = [&](PcbStageResult p, const std::string &tag) {
        Shape s;
        s.w = p.w;
        s.h = p.h;
        s.tag = tag;
        s.side = "bottom";
        for (const auto &[r, xy] : p.top) {
            if (face.count(r))
                throw PcbZoneInfeasible(
                    "bottom eligibility retained a face-top part in its primary pack: " + r);
            s.top_off[r] = {placement_bottom_pose_precision4dp(p.w - xy.first, &ctx.quantization), xy.second};
            double rot = p.rotations.count(r) ? p.rotations.at(r) : 0;
            s.extra_rot[r] = normalize(180 - rot);
            auto key = g.resolvable.at(r), mk = "@mirror/" + key;
            auto fp = ctx.pool.at(key);
            auto doc = mirrored_footprint(fp->document);
            auto parent = std::filesystem::path(fp->source).parent_path().filename().string();
            if (parent.size() >= 7 && parent.compare(parent.size() - 7, 7, ".pretty") == 0)
                parent.resize(parent.size() - 7);
            auto path =
                (std::filesystem::path(".mirrored_fp") /
                 (parent + "__" + std::filesystem::path(fp->source).stem().string() + ".kicad_mod"))
                    .string();
            ctx.pool[mk] = pcb_check_footprint(path, sexpr_dumps(doc) + "\n", doc);
            s.mirror[r] = mk;
        }
        for (const auto &[r, xy] : p.bottom) {
            double rot = p.rotations.count(r) ? p.rotations.at(r) : 0;
            auto cb = turn_box(g.bbox_of.at(r), rot);
            s.bot_off[r] = mirror_offset_x(xy.first, xy.second, cb, p.w, &ctx.quantization);
            if (p.rotations.count(r))
                s.extra_rot[r] = rot;
        }
        return s;
    };
    if (tmpl) {
        auto p = *tmpl;
        std::vector<std::string> lifted;
        for (const auto &[r, xy] : p.top) {
            (void)xy;
            if (face.count(r)) {
                if (members.count(r)) {
                    events.push_back("bottom_variant_contract_reject");
                    return {};
                }
                lifted.push_back(r);
            }
        }
        if (!lifted.empty()) {
            std::vector<ShelfOcc> blockers;
            auto halo = [&](const std::string &r, FloorplanPoint xy) {
                return grow_rect(offset_turned_box(g.bbox_of.at(r),
                                                   p.rotations.count(r) ? p.rotations.at(r) : 0,
                                                   xy.first, xy.second),
                                 ctx.clearance / 2);
            };
            auto meta = [&](const std::string &r) {
                int n = static_cast<int>(
                    pad_names_from_text(ctx.pool.at(g.resolvable.at(r))->bytes).size());
                double floor = n >= 3 ? need(n) : ctx.clearance;
                return std::make_pair(
                    floor > ctx.clearance ? std::max(0., ctx.credit(floor) - ctx.clearance) : 0.,
                    passive(r, n));
            };
            for (const auto &r : lifted)
                p.top.erase(r);
            for (const auto &[r, xy] : p.top)
                if (has_thru_pads_from_text(ctx.pool.at(g.resolvable.at(r))->bytes))
                    blockers.push_back({halo(r, xy), 0, false});
            for (const auto &[r, xy] : p.bottom) {
                auto [extra, cp] = meta(r);
                blockers.push_back({halo(r, xy), extra, cp});
            }
            std::vector<ShelfItem> items;
            for (const auto &r : lifted) {
                auto [extra, cp] = meta(r);
                items.push_back({r, halo(r, {0, 0}), extra, cp});
            }
            auto pack = shelf_pack(items, std::max(0., p.w - 2 * zone_pad), blockers, zone_pad,
                                   &ctx.quantization);
            for (const auto &[r, x, y] : pack.placed)
                p.bottom[r] = {x, y};
            double mx = 0, my = 0;
            for (const auto &[r, xy] : p.bottom) {
                auto b = halo(r, xy);
                mx = std::max(mx, b.x1);
                my = std::max(my, b.y1);
            }
            p.w = placement_lift_extent_precision4dp(std::max(p.w, mx + zone_pad), &ctx.quantization);
            p.h = placement_lift_extent_precision4dp(std::max(p.h, my + zone_pad), &ctx.quantization);
        }
        auto shape = mirror(p, "bottom");
        if (mirror_holds(ctx, g, sheet, shape)) {
            std::vector<Shape> result{shape};
            // Templated top offers already include all quarter turns. Give an
            // eligible bottom template the same directional freedom, retaining
            // its original offer first. Local contracts are checked here;
            // external facing/flow remains a board-level acceptance condition.
            if(ctx.in.floorplan.compact_search) {
                auto next=shape;
                for(const auto* suffix:{"/r90","/r180","/r270"}) {
                    next=turned(next,&ctx.quantization);next.tag=shape.tag+suffix;
                    auto enclosed=enclose_courtyards(ctx,g,next);
                    if(orientation_holds(ctx,g,sheet,enclosed)&&std::none_of(result.begin(),result.end(),
                        [&](const auto& old){return same_zone_shape_geometry(old,enclosed);}))result.push_back(std::move(enclosed));
                }
            }
            return result;
        }
        events.push_back("bottom_variant_contract_reject");
        return {};
    }
    std::vector<Shape> result;
    auto all_top = g.side_of;
    for (const auto &r : g.refs_by_sheet.at(sheet))
        all_top[r] = "top";
    for (bool split : {false, true})
        for (double aspect : {1., 2.2, .45}) {
            auto p = pack_zone(ctx, g, g.refs_by_sheet.at(sheet), aspect, {}, "", face,
                               split ? nullptr : &all_top);
            std::string a = aspect == 1 ? "1" : aspect == 2.2 ? "2.2" : "0.45";
            auto candidate=mirror(p, (split ? "bottom-split-a" : "bottom-a") + a);
            // Equal envelopes need not occupy the same space on each face or
            // place the same pins. Retain distinct physical arrangements.
            if(std::none_of(result.begin(),result.end(),[&](const auto& prior) {
                return same_zone_shape_geometry(prior,candidate);
            })) result.push_back(std::move(candidate));
        }
    return result;
}
} // namespace schgen::pcb_placement
