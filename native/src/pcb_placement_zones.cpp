#include "pcb_placement_internal.hpp"
#include "pcb_placement_orientations.hpp"
#include "schgen/board_decision_policy.hpp"

namespace schgen {
PcbZoneResult pcb_placement::build_zones_for_search(const PcbPlacementInput &in, bool vertical_compaction,
                                                  ExecutionFailureReceipt* failure) {
    using namespace pcb_placement;
    vertical_compaction=vertical_compaction||(in.floorplan.experiment&&in.floorplan.experiment->vertical_compaction);
    Context ctx(in);
    PcbZoneResult out;
    ExecutionFailureReceipt child;
    try {
    if(vertical_compaction&&(!in.floorplan.compact_search||!in.floorplan.experiment||
                            in.floorplan.experiment->contract_group_face_sheets.empty()))
        throw std::invalid_argument("vertical compaction requires compact mode and explicit contract-group sheets");
    if(in.floorplan.experiment)for(const auto& selected:in.floorplan.experiment->contract_group_face_sheets) {
        if(!in.floorplan.compact_search||!ctx.board_refs.count(selected))
            throw PcbZoneInfeasible("contract-group face candidates require compact mode and a known sheet: "+selected);
    }
    auto &g = out.geometry;
    std::set<std::string> edges;
    std::map<std::string, std::set<std::string>> faces;
    std::map<std::string, std::string> connector_class;
    std::map<std::string, Rotations> conn_rot;
    std::map<std::string, std::string> sheet_outer;
    auto sheet_edges =
        in.floorplan.spec ? in.floorplan.spec->edge_of() : std::map<std::string, std::string>{};
    auto layers =
        in.floorplan.spec ? in.floorplan.spec->layer_of() : std::map<std::string, std::string>{};
    std::map<std::string, std::set<std::string>> decoupling;
    for (const auto &sheet : in.floorplan.sheets) {
        std::vector<std::tuple<std::string, std::vector<std::string>>> nets;
        for (const auto &n : sheet.nets) {
            std::vector<std::string> refs;
            for (const auto &p : n.pins)
                refs.push_back(!p.ref.empty() && p.ref[0] == '#'
                                   ? p.ref
                                   : ctx.board_refs.at(sheet.name).at(p.ref));
            nets.emplace_back(n.name, refs);
        }
        auto caps = decoupling_caps(nets);
        decoupling[sheet.name] = {caps.begin(), caps.end()};
    }
    for (const auto &p : ctx.parts) {
        if (p.sheet == "som_decoupling" ||
            (p.sheet.rfind("som_j", 0) == 0 && p.ref.rfind("J", 0) == 0))
            continue;
        if (edge_family(p.value))
            edges.insert(p.sheet);
        if (p.lib_id.rfind("Mechanical:MountingHole", 0) == 0) {
            g.mh_refs.push_back(p.ref);
            continue;
        }
        auto fp = ctx.resolve(p.footprint);
        if (!fp) {
            g.deferred.push_back(p.ref + " (" + p.sheet + "): footprint '" + p.footprint +
                                 "' not found");
            continue;
        }
        auto bb = footprint_bbox(fp->document, 3);
        g.resolvable[p.ref] = ctx.key(p.footprint);
        g.bbox_of[p.ref] = bb;
        g.side_of[p.ref] =
            classify_side(p.ref, p.lib_id, bb, decoupling[p.sheet].count(p.ref), in.two_side, 12,
                          {"DF40C", "MountingHole", "Mechanical:", "TestPoint", "PinHeader",
                           "PinSocket", "Connector", "Conn_"});
        g.refs_by_sheet[p.sheet].push_back(p.ref);
        if (face_top(p))
            faces[p.sheet].insert(p.ref);
        else if (!connector_class.count(p.sheet)) {
            bool conn = connector_value(p.value);
            for (const auto &token : {"PinHeader", "PinSocket", "Conn", "DF40"})
                conn |= p.lib_id.find(token) != std::string::npos ||
                        p.footprint.find(token) != std::string::npos;
            for (const auto &[r, desc] : in.floorplan.project.header_desc) {
                (void)desc;
                conn |= r == p.ref;
            }
            if (conn)
                connector_class[p.sheet] = p.ref;
        }
        if (connector_value(p.value) && sheet_edges.count(p.sheet)) {
            double rot = connector_rotation(p.value, sheet_edges.at(p.sheet), ctx.quantization);
            g.conn_rot[p.ref] = rot;
            g.conn_edge[p.ref] = sheet_edges.at(p.sheet);
            conn_rot[p.sheet][p.ref] = rot;
            sheet_outer[p.sheet] = sheet_edges.at(p.sheet);
        }
    }
    std::sort(g.mh_refs.begin(), g.mh_refs.end());
    for (const auto &[sheet, layer] : layers)
        if (layer == "bottom" || layer == "either") {
            if (!g.refs_by_sheet.count(sheet))
                throw PcbZoneInfeasible("floorplan.json: " + sheet + " declares copper-face " +
                                        layer + " but it has no packable zone");
            if (edges.count(sheet) || conn_rot.count(sheet) || sheet_edges.count(sheet))
                throw PcbZoneInfeasible("floorplan.json: " + sheet +
                                        " carries a seated off-board connector; top required");
            if (connector_class.count(sheet))
                throw PcbZoneInfeasible("floorplan.json: " + sheet +
                                        " contains connector-class part " +
                                        connector_class.at(sheet) + "; top required");
            for (const auto &sc : in.floorplan.sheets)
                if (sc.name == sheet)
                    for (const auto &n : sc.nets) {
                        auto c = ctx.netclass_of.find(n.name);
                        if (c != ctx.netclass_of.end() && ctx.classes.at(c->second))
                            throw PcbZoneInfeasible("floorplan.json: " + sheet +
                                                    " carries impedance-controlled net class " +
                                                    c->second +
                                                    "; B.Cu has no emitted reference plane");
                    }
        }
    auto shape = [](const PcbStageResult &p, const std::string &tag) {
        Shape s;
        s.w = p.w;
        s.h = p.h;
        s.top_off = p.top;
        s.bot_off = p.bottom;
        s.extra_rot = p.rotations;
        s.tag = tag;
        return s;
    };
    for (const auto &[sheet, refs] : g.refs_by_sheet) {
        bool edge = edges.count(sheet),
             eligible = layers[sheet] == "bottom" || layers[sheet] == "either";
        PcbStageResult p;
        bool templated = ctx.wired.count(sheet) && in.contracts.count(sheet);
        std::set<std::string> members;
        if (templated) {
            auto st = ctx.stage_input(sheet, g);
            members = pcb_contract_members(st);
            for (const auto &r : members) {
                g.side_of[r] = "top";
                st.side_of[r] = "top";
            }
            st.outer_dir = sheet_outer.count(sheet) ? sheet_outer.at(sheet) : "";
            p = build_pcb_stage_zone(st,&child);
            out.fallback_events.insert(out.fallback_events.end(), p.fallback_events.begin(),
                                       p.fallback_events.end());
            merge_execution_counts(out.quantization_engagements, p.quantization_engagements,&child);
            auto ab = shape(p, "asbuilt"), tn = turned(ab, &ctx.quantization), t2 = turned(tn, &ctx.quantization), t3 = turned(t2, &ctx.quantization);
            tn.tag = "turned";
            t2.tag = "t180";
            t3.tag = "t270";
            bool turn_now = !edge && p.h > board_decision_policy::interior_band_target && p.w <= board_decision_policy::interior_band_target && p.w < p.h;
            if (turn_now) {
                p.top = tn.top_off;
                p.bottom = tn.bot_off;
                p.w = tn.w;
                p.h = tn.h;
                p.rotations = tn.extra_rot;
            }
            if (!edge && !conn_rot.count(sheet)) {
                std::vector<Shape> variants = turn_now ? std::vector<Shape>{tn, ab, t2, t3}
                                                       : std::vector<Shape>{ab, tn, t2, t3},
                                   unique;
                for (const auto &s : variants)
                    if (std::none_of(unique.begin(), unique.end(), [&](const auto &u) {
                            return s.w == u.w && s.h == u.h && s.top_off == u.top_off &&
                                   s.bot_off == u.bot_off && s.extra_rot == u.extra_rot;
                        }))
                        unique.push_back(s);
                if (eligible) {
                    auto bottom =
                        bottom_shapes(ctx, g, sheet, faces[sheet], p, members, out.fallback_events);
                    unique.insert(unique.end(), bottom.begin(), bottom.end());
                }
                if (unique.size() >= 2)
                    g.shapes[sheet] = std::move(unique);
            } else if (conn_rot.count(sheet)) {
                auto mirror = member_mirror(ctx, g, sheet, p, conn_rot.at(sheet));
                if (mirror)
                    g.shapes[sheet] = {shape(p, "asbuilt"), *mirror};
            }
        } else {
            p = pack_zone(ctx, g, refs, edge ? board_decision_policy::edge_zone_aspect : 1.,
                          conn_rot.count(sheet) ? conn_rot.at(sheet) : Rotations{},
                          sheet_outer.count(sheet) ? sheet_outer.at(sheet) : "");
            if (!edge && p.h > board_decision_policy::interior_band_target) {
                auto alternative = pack_zone(ctx, g, refs, board_decision_policy::interior_zone_aspect);
                if (alternative.h <= board_decision_policy::interior_band_target && alternative.h < p.h)
                    p = alternative;
                else if (p.w <= board_decision_policy::interior_band_target && p.w < p.h) {
                    auto t = turned(shape(p, ""), &ctx.quantization);
                    p.top = t.top_off;
                    p.bottom = t.bot_off;
                    p.w = t.w;
                    p.h = t.h;
                    p.rotations = t.extra_rot;
                }
            }
            if (!edge && !conn_rot.count(sheet)) {
                std::set<FloorplanPoint> seen{{placement_shape_key_precision4dp(p.w, &ctx.quantization), placement_shape_key_precision4dp(p.h, &ctx.quantization)}};
                std::vector<Shape> variants;
                std::vector<Shape> same_box_alternatives;
                for (double aspect : {2.2, 1., .45}) {
                    auto v = pack_zone(ctx, g, refs, aspect);
                    const bool new_box=seen.insert({placement_shape_key_precision4dp(v.w, &ctx.quantization), placement_shape_key_precision4dp(v.h, &ctx.quantization)}).second;
                    if(!new_box&&!in.floorplan.compact_search)continue;
                    auto candidate=shape(v, aspect == 2.2 ? "a2.2"
                                                    : aspect == 1 ? "a1"
                                                                  : "a0.45");
                    if (new_box)
                        variants.push_back(std::move(candidate));
                    else if(in.floorplan.compact_search)
                        same_box_alternatives.push_back(std::move(candidate));
                }
                if (eligible) {
                    auto bottom = bottom_shapes(ctx, g, sheet, faces[sheet], std::nullopt, {},
                                                out.fallback_events);
                    variants.insert(variants.end(), bottom.begin(), bottom.end());
                }
                // Preserve legacy unrotated offers/indices; append newly retained
                // arrangements instead of inserting them ahead of incumbents.
                if(!same_box_alternatives.empty())
                    append_distinct_zone_shapes(shape(p,"base"),variants,same_box_alternatives);
                if (!variants.empty()) {
                    variants.insert(variants.begin(), shape(p, "base"));
                    g.shapes[sheet] = std::move(variants);
                }
            } else if (conn_rot.count(sheet)) {
                auto mirror = member_mirror(ctx, g, sheet, p, conn_rot.at(sheet));
                if (mirror)
                    g.shapes[sheet] = {shape(p, "asbuilt"), *mirror};
            }
        }
        if (in.floorplan.compact_search && !edge && !conn_rot.count(sheet) &&
            !sheet_edges.count(sheet) && !connector_class.count(sheet))
            append_rigid_zone_orientations(ctx, g, sheet, shape(p, "base"));
        if (in.floorplan.compact_search)
            append_owned_group_zone_shapes(ctx, out, sheet, shape(p, "base"),
                !templated && !edge && !conn_rot.count(sheet) &&
                !sheet_edges.count(sheet) && !connector_class.count(sheet), &child);
        if(in.floorplan.experiment&&in.floorplan.experiment->contract_group_face_sheets.count(sheet))
            append_contract_group_faces(ctx,g,sheet,shape(p,"base"),in.floorplan.experiment->contract_group_rotations,
                                        vertical_compaction);
        if(in.floorplan.experiment&&in.floorplan.experiment->owned_face_cohesion)
            append_owned_face_zone_shapes(ctx,out,sheet,shape(p,"base"),
                !templated&&!edge&&!conn_rot.count(sheet)&&!sheet_edges.count(sheet)&&!connector_class.count(sheet),
                layers[sheet]!="bottom",eligible,faces[sheet],&child);
        g.top_off[sheet] = p.top;
        g.bot_off[sheet] = p.bottom;
        g.zone_box[sheet] = {p.w, p.h};
        g.zone_extra_rot.insert(p.rotations.begin(), p.rotations.end());
    }
    merge_execution_counts(out.quantization_engagements, ctx.quantization,&child);
    out.footprints = std::move(ctx.pool);
    return out;
    } catch (...) {
        ExecutionAccounting prefix{out.quantization_engagements,out.fallback_events};
        append_execution_accounting(prefix,{ctx.quantization,{}},failure);
        capture_execution_failure(failure,std::move(prefix),&child);
        throw;
    }
}
PcbZoneResult build_pcb_zone_geometry(const PcbPlacementInput &in,ExecutionFailureReceipt* failure) {
    return pcb_placement::build_zones_for_search(in,false,failure);
}
FloorplanZoneGeometry bind_pcb_zone_shapes(const PcbZoneResult &zones,
                                           const std::map<std::string, int> &chosen) {
    using namespace pcb_placement;
    auto g = zones.geometry;
    for (const auto &[sheet, index] : chosen) {
        if (!index)
            continue;
        auto variants = g.shapes.find(sheet);
        if (index < 0 || variants == g.shapes.end() ||
            static_cast<std::size_t>(index) >= variants->second.size())
            throw PcbZoneInfeasible("apply_chosen_shapes: " + sheet + " chose unregistered shape " +
                                    std::to_string(index));
        const auto &s = variants->second[index];
        if(s.side!="top"&&s.side!="bottom")throw PcbZoneInfeasible("apply_chosen_shapes: invalid primary face");
        for (const auto *offsets : {&g.top_off[sheet], &g.bot_off[sheet]})
            for (const auto &[r, p] : *offsets) {
                (void)p;
                g.zone_extra_rot.erase(r);
            }
        g.zone_box[sheet] = {s.w, s.h};
        g.top_off[sheet] = s.top_off;
        g.bot_off[sheet] = s.bot_off;
        g.zone_extra_rot.insert(s.extra_rot.begin(), s.extra_rot.end());
        if(s.side=="top") {
            // A selected shape may carry an explicitly different soft side
            // assignment. Bind its physical faces, not the original heuristic.
            for(const auto& [r,p]:s.top_off){(void)p;g.side_of[r]="top";}
            for(const auto& [r,p]:s.bot_off){(void)p;g.side_of[r]="bottom";}
        }
        if (s.side == "bottom") {
            if (s.mirror.size() != s.top_off.size())
                throw PcbZoneInfeasible("bottom primary pack and mirror map disagree");
            for (const auto &[r, p] : s.top_off) {
                (void)p;
                if (!s.mirror.count(r))
                    throw PcbZoneInfeasible("bottom primary member has no mirrored document: " + r);
                g.side_of[r] = "bottom";
            }
            for (const auto &[r, p] : s.bot_off) {
                (void)p;
                g.side_of[r] = "top";
            }
        }
        // Mixed-face top-primary variants also carry mirrored bottom members.
        // Bind the selected document independently of the primary pack face.
        for (const auto &[r, key] : s.mirror) {
            if(g.side_of.at(r)!="bottom"||(!s.top_off.count(r)&&!s.bot_off.count(r)))
                throw PcbZoneInfeasible("mirrored member is not a selected bottom-side part: "+r);
            g.resolvable[r] = key;
            g.bbox_of[r] = footprint_bbox(zones.footprints.at(key)->document, 3);
            g.mirror_refs.insert(r);
        }
    }
    return g;
}
} // namespace schgen
