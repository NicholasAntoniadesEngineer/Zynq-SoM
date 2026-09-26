#include "pcb_placement_internal.hpp"

namespace schgen::pcb_placement {
namespace {
FloorplanTermIndex term_index(const Context &ctx) {
    using Key = std::tuple<std::string, std::string, std::string>;
    std::map<Key, FloorplanTerm> merged;
    auto add = [&](FloorplanTerm t) {
        auto [p, fresh] = merged.emplace(Key{t.kind, t.subject, t.target_raw}, t);
        if (fresh)
            return;
        auto &old = p->second;
        if (t.bound && (!old.bound || *t.bound < *old.bound))
            old.bound = t.bound;
        old.enforced = old.enforced || t.enforced;
        if (old.output_roles.empty())
            old.output_roles = t.output_roles;
        if (old.out_refs.empty())
            old.out_refs = t.out_refs;
    };
    const std::set<std::string> known{"flow", "downstream", "output_roles",
                                      "far",  "near_max",   "media_faces_near_max"};
    std::set<std::string> names;
    for (const auto &sc : ctx.in.floorplan.sheets)
        names.insert(sc.name);
    for (const auto &sheet : names) {
        auto found = ctx.in.contracts.find(sheet);
        if (found == ctx.in.contracts.end())
            continue;
        const auto &contract = found->second;
        const auto &ext = optional(contract, "external");
        for (const auto &[key, value] : ext.object_value) {
            (void)value;
            if (!known.count(key))
                throw PcbZoneInfeasible("placement contract " + sheet +
                                        ": unsupported external term kind " + key);
        }
        auto make = [&](const std::string &kind, const std::string &subject,
                        const std::string &target, const std::string &basis) {
            FloorplanTerm t;
            t.kind = kind;
            t.sheet = sheet;
            t.subject = subject;
            t.target_raw = target;
            t.basis = basis;
            t.enforced = ctx.wired.count(sheet);
            return t;
        };
        const auto basis = text(contract, "contract", "?");
        const auto flow = strings(ext, "flow");
        for (std::size_t k = 1; k < flow.size(); ++k)
            add(make("flow_hop", flow[k - 1], flow[k], "flow chain [" + basis + "]"));
        for (const auto &n : optional(ext, "near_max").array_value) {
            auto t = make("near_max", sheet, text(n, "other", "?"), text(n, "basis"));
            t.bound = number(n, "max_mm");
            add(t);
        }
        for (const auto &n : optional(ext, "far").array_value) {
            auto t = make("far_min", sheet, text(n, "what", "?"), text(n, "basis"));
            t.bound = number(n, "min_mm");
            add(t);
        }
        auto downstream = text(ext, "downstream");
        auto roles = strings(ext, "output_roles");
        if (!downstream.empty() && !roles.empty()) {
            auto t = make("facing", sheet, downstream, "facing/output_roles [" + basis + "]");
            t.output_roles = roles;
            std::set<std::string> refs;
            for (const auto &[ref, role] : optional(contract, "roles").object_value)
                if (std::find(roles.begin(), roles.end(), role.string_value) != roles.end())
                    refs.insert(ref);
            const auto &map = ctx.board_refs.at(sheet);
            for (const auto &r : refs)
                if (map.count(r))
                    t.out_refs.push_back(map.at(r));
            add(t);
        }
    }
    if (ctx.in.floorplan.spec) {
        std::set<std::pair<std::string, std::string>> near;
        for (const auto &[key, t] : merged) {
            (void)key;
            if (t.kind == "near_max")
                near.insert({t.subject, t.target()});
        }
        for (const auto &[name, a] : ctx.in.floorplan.spec->interior)
            if (a.near && !a.near->empty() && !near.count({name, *a.near})) {
                FloorplanTerm t;
                t.kind = "near_intent";
                t.sheet = name;
                t.subject = name;
                t.target_raw = *a.near;
                t.basis = "carrier/floorplan.json near-intent (advisory)";
                add(t);
            }
    }
    FloorplanTermIndex index;
    for (const auto &[key, t] : merged) {
        (void)key;
        bool missing = false;
        for (const auto &n : {t.subject, t.target()})
            missing |= n != "@som" && !names.count(n);
        (missing ? index.na : t.enforced ? index.hard : index.soft).push_back(t);
    }
    return index;
}
FloorplanLocalMetrics metrics(const PcbZoneResult &zones, const Offsets &top, const Offsets &bottom,
                              const Rotations &extra, FloorplanPoint wh,
                              const std::map<std::string, std::string> &mirrors = {}) {
    FloorplanLocalMetrics result;
    result.zone_wh = wh;
    Offsets both = top;
    for (const auto &[r, xy] : bottom)
        both[r] = xy;
    PcbStageInput empty;
    Engine geometry(empty);
    for (const auto &[ref, xy] : both) {
        result.offsets.emplace_back(ref, xy.first, xy.second);
        auto source = mirrors.find(ref);
        std::string key;
        if (source != mirrors.end())
            key = source->second;
        else {
            auto p = zones.geometry.resolvable.find(ref);
            if (p == zones.geometry.resolvable.end())
                continue;
            key = p->second;
        }
        auto c = zones.geometry.conn_rot.find(ref), e = extra.find(ref);
        const auto boxes =
            values(geometry.pads(zones.footprints.at(key),
                                 normalize((c == zones.geometry.conn_rot.end() ? 0 : c->second) +
                                           (e == extra.end() ? 0 : e->second))));
        auto bounds = boxes_union(boxes);
        if (bounds)
            result.pad_union.emplace_back(ref, bounds->x0 + xy.first, bounds->y0 + xy.second,
                                          bounds->x1 + xy.first, bounds->y1 + xy.second);
    }
    return result;
}
} // namespace
} // namespace schgen::pcb_placement

namespace schgen {
FloorplanInput prepare_pcb_floorplan(const PcbPlacementInput &input, const PcbZoneResult &zones) {
    using namespace pcb_placement;
    if (input.floorplan.origin != FloorplanPoint{25, 25})
        throw PcbZoneInfeasible("PCB placement requires the 25 mm emission origin");
    Context ctx(input);
    FloorplanInput result = input.floorplan;
    result.geometry = zones.geometry;
    for (const auto &[key, fp] : zones.footprints) {
        if (!fp)
            throw PcbZoneInfeasible("null footprint: " + key);
        result.footprints[key] = {fp->source, fp->document};
    }
    result.impedance_net_classes.clear();
    for (const auto &[net, c] : ctx.netclass_of)
        if (ctx.classes.at(c))
            result.impedance_net_classes[net] = c;
    FloorplanComposeInput compose;
    compose.corridors = result.compose.corridors;
    compose.index = term_index(ctx);
    compose.wired_participants = ctx.l4_exempt;
    std::set<std::string> sheets;
    for (const auto *all : {&result.geometry.top_off, &result.geometry.bot_off})
        for (const auto &[sheet, offset] : *all) {
            (void)offset;
            sheets.insert(sheet);
        }
    for (const auto &sheet : sheets)
        compose.metrics[sheet] =
            metrics(zones, result.geometry.top_off[sheet], result.geometry.bot_off[sheet],
                    result.geometry.zone_extra_rot, result.geometry.zone_box[sheet]);
    for (const auto &[sheet, shapes] : result.geometry.shapes)
        for (std::size_t k = 1; k < shapes.size(); ++k) {
            const auto &s = shapes[k];
            compose.shape_metrics[{sheet, static_cast<int>(k)}] =
                metrics(zones, s.top_off, s.bot_off, s.extra_rot, {s.w, s.h}, s.mirror);
        }
    std::map<std::string, std::set<std::string>> net_sheets;
    for (const auto &sheet : result.sheets)
        for (const auto &n : sheet.nets) {
            if (sheet.name.rfind("som_j", 0) == 0) {
                bool auxiliary = false;
                for (const auto &p : n.pins)
                    for (const auto &part : sheet.parts)
                        if (p.ref == part.ref && part.ref.rfind("J", 0) != 0 &&
                            part.footprint.find("MountingHole") == std::string::npos)
                            auxiliary = true;
                if (!auxiliary)
                    continue;
            }
            net_sheets[n.name].insert(sheet.name);
        }
    for (const auto &[net, members] : net_sheets) {
        (void)net;
        if (members.size() == 2)
            ++compose.channel_demand[{*members.begin(), *members.rbegin()}];
    }
    result.compose = std::move(compose);
    result.accounting.fallback_events.insert(result.accounting.fallback_events.end(),
                                             zones.fallback_events.begin(),
                                             zones.fallback_events.end());
    checked_quantization_merge(result.accounting.quantization_engagements, zones.quantization_engagements);
    return result;
}
PcbPlacementResult build_pcb_model(const PcbPlacementInput &input) {
    auto zones = build_pcb_zone_geometry(input);
    // The authored floorplan sizes against the normal two-face offers even
    // when the caller requests the legacy top-preferred emission option.
    // Placement then binds that solve to its independently constructed zones.
    // Keeping these inputs distinct preserves build_model(two_side=False).
    auto planning = input;
    planning.two_side = true;
    auto planning_zones = input.two_side ? zones : build_pcb_zone_geometry(planning);
    auto floorplan = generate_floorplan(prepare_pcb_floorplan(planning, planning_zones));
    return place_pcb_model_accounted(input, zones, floorplan, input.two_side
        ? PcbZoneAccountingOwnership::IncludedInFloorplan
        : PcbZoneAccountingOwnership::SeparateFromFloorplan);
}
} // namespace schgen
