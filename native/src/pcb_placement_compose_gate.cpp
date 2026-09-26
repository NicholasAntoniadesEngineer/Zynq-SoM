#include "pcb_placement_gates_internal.hpp"

namespace schgen {
using namespace placement_gates;
FloorplanTermIndex pcb_final_compose_index(const PcbPlacementInput &authored,
                                           const PcbCheckModel &model) {
    auto scoped = authored;
    std::set<std::string> placed;
    for (const auto &i : model.insts)
        placed.insert(i.sheet);
    std::set<std::string> bands;
    for (const auto &[name, band] : scoped.floorplan.sheet_index) {
        (void)band;
        bands.insert(name);
    }
    // Preserve fallback reference bands before narrowing discovery scope.
    for (std::size_t k = 0; k < authored.floorplan.sheets.size(); ++k) {
        const auto &s = authored.floorplan.sheets[k];
        if (!bands.count(s.name))
            scoped.floorplan.sheet_index.emplace_back(s.name, static_cast<int>(k + 1));
    }
    auto &sheets = scoped.floorplan.sheets;
    sheets.erase(std::remove_if(sheets.begin(), sheets.end(),
                                [&](const auto &s) { return !placed.count(s.name); }),
                 sheets.end());
    std::set<std::string> included;
    for (const auto &s : sheets)
        included.insert(s.name);
    for (const auto &name : placed)
        if (!included.count(name)) {
            decltype(scoped.floorplan.sheets)::value_type sheet;
            sheet.name = name;
            sheets.push_back(std::move(sheet));
        }
    // Empty zone geometry requests only the term-index portion of preparation.
    // That portion depends on authored policy and refs, not placement metrics.
    return prepare_pcb_floorplan(scoped, PcbZoneResult{}).compose.index;
}
PcbComposeEvidence pcb_compose_evidence(const JsonNode &sidecar, FloorplanPoint origin) {
    PcbComposeEvidence out;
    if (sidecar.kind == JsonKind::Null)
        return out;
    kind(sidecar, JsonKind::Object);
    if (!std::isfinite(origin.first) || !std::isfinite(origin.second))
        throw std::invalid_argument("compose evidence: nonfinite origin");
    std::map<std::string, Box4> sorted;
    const auto &corridors = opt(opt(sidecar, "t1_constraints"), "corridors");
    if (corridors.kind != JsonKind::Null)
        for (const auto &[name, c] : kind(corridors, JsonKind::Object).object_value) {
            const auto &r = kind(required(c, "rect"), JsonKind::Array).array_value;
            if (r.size() != 4)
                throw std::invalid_argument("compose evidence: four corridor coordinates required");
            Box4 box{jnum(r[0]) - origin.first, jnum(r[1]) - origin.second,
                     jnum(r[2]) - origin.first, jnum(r[3]) - origin.second};
            if (box.x0 > box.x1 || box.y0 > box.y1)
                throw std::invalid_argument("compose evidence: inverted corridor");
            sorted["escape:" + name] = box;
        }
    out.corridors.assign(sorted.begin(), sorted.end());
    for (const auto &c : array(opt(opt(sidecar, "escape_meta"), "coexistence")))
        out.coexistence.push_back({str(c, "ref"), str(c, "sheet"), str(c, "verdict", "?")});
    return out;
}
PcbComposeEvidence pcb_compose_evidence(const PcbModel &model) {
    JsonNode sidecar;
    if (model.escape_plan_record)
        sidecar = *model.escape_plan_record;
    else
        sidecar.kind = JsonKind::Object;
    kind(sidecar, JsonKind::Object);
    bool replaced = false;
    for (auto &[k, v] : sidecar.object_value)
        if (k == "escape_meta") {
            v = model.escape_meta;
            replaced = true;
        }
    if (!replaced)
        sidecar.object_value.emplace_back("escape_meta", model.escape_meta);
    return pcb_compose_evidence(sidecar, {model.origin_x, model.origin_y});
}
std::vector<FloorplanTermEval> measure_pcb_compose_terms(const PcbCheckInput &in,
                                                         const FloorplanTermIndex &index,
                                                         const PcbPlacementGatePolicy &policy) {
    FinalGeometry geom(in);
    const auto &model = in.model();
    auto budget = flow_budget(model.board_w, model.board_h, model.som_core);
    const double inf = std::numeric_limits<double>::infinity();
    std::vector<FloorplanTermEval> out;
    for (const auto *terms : {&index.hard, &index.soft})
        for (const auto &t : *terms) {
            double bound = t.bound.value_or(0.);
            auto target = t.target();
            if (t.kind == "flow_hop") {
                auto a = geom.centroid(t.subject), b = geom.centroid(target);
                if (!a || !b) {
                    out.push_back({t, inf, py_round(budget, 4), -inf, false, "UNRESOLVED"});
                    continue;
                }
                auto d = hypot_xy(a->first, a->second, b->first, b->second);
                out.push_back(
                    {t, d, py_round(budget, 4), py_round(budget - d, 4), d <= budget, ""});
            } else if (t.kind == "near_max" || t.kind == "near_intent") {
                auto a = geom.bbox(t.subject), b = geom.bbox(target);
                if (!a || !b) {
                    out.push_back({t, inf, bound, -inf, t.kind == "near_intent", "UNRESOLVED"});
                    continue;
                }
                auto d = box_gap(*a, *b);
                if (t.kind == "near_intent")
                    out.push_back({t, d, 0, 0, true, "advisory"});
                else
                    out.push_back({t, d, bound, py_round(bound - d, 4), d <= bound, ""});
            } else if (t.kind == "far_min") {
                auto a = geom.centroid(t.subject), b = geom.centroid(target);
                if (!a || !b) {
                    out.push_back({t, inf, bound, -inf, false, "UNRESOLVED"});
                    continue;
                }
                auto d = hypot_xy(a->first, a->second, b->first, b->second);
                out.push_back({t, d, bound, py_round(d - bound, 4), d >= bound, ""});
            } else if (t.kind == "facing") {
                std::set<std::string> members(t.out_refs.begin(), t.out_refs.end());
                if (members.empty()) {
                    const auto &map = refs(policy, t.subject);
                    for (const auto &r : t.output_roles) {
                        auto p = map.find(r);
                        if (p != map.end())
                            members.insert(p->second);
                    }
                }
                auto a = geom.centroid(t.subject), b = geom.centroid(target),
                     o = geom.members(t.subject, members);
                if (!a || !b || !o) {
                    out.push_back({t, 180, 90, -90, false, "UNRESOLVED"});
                    continue;
                }
                auto [dot, angle] =
                    facing_dot(a->first, a->second, o->first, o->second, b->first, b->second);
                out.push_back(
                    {t, angle, 90, py_round(90 - angle, 4), dot > 0, "dot=" + sign(dot, 2)});
            } else
                throw std::invalid_argument("compose measurement: unsupported term kind " +
                                            repr(t.kind));
        }
    return out;
}
PcbCrossAirwires pcb_cross_airwires_by_pair(const PcbCheckModel &model,
                                            const RatsnestNets *supplied_nets,
                                            const RatsnestEdges *supplied_edges) {
    const auto owned = supplied_nets ? RatsnestNets{} : ratsnest_net_pad_positions(model);
    const auto &nets = supplied_nets ? *supplied_nets : owned;
    const auto made = supplied_edges ? RatsnestEdges{} : ratsnest_mst(nets);
    const auto &edges = supplied_edges ? *supplied_edges : made;
    PcbCrossAirwires out;
    for (const auto &[net, pts] : nets) {
        auto es = edges.find(net);
        if (es == edges.end())
            throw std::invalid_argument("compose cross-airwires: missing MST for " + net);
        for (const auto &[a, b] : es->second) {
            if (a < 0 || b < 0 || static_cast<std::size_t>(a) >= pts.size() ||
                static_cast<std::size_t>(b) >= pts.size())
                throw std::invalid_argument("compose cross-airwires: invalid MST endpoint");
            const auto &[x, y, ra, sa] = pts[static_cast<std::size_t>(a)];
            const auto &[u, v, rb, sb] = pts[static_cast<std::size_t>(b)];
            (void)ra;
            (void)rb;
            if (sa == sb)
                continue;
            auto &pair = out[sa < sb ? std::make_pair(sa, sb) : std::make_pair(sb, sa)];
            ++pair.first;
            pair.second += hypot_xy(x, y, u, v);
        }
    }
    for (auto &[key, value] : out) {
        (void)key;
        value.second = py_round(value.second, 1);
    }
    return out;
}
PcbComposeReport report_pcb_composition(const PcbCheckInput &in, const FloorplanTermIndex &index,
                                        const PcbPlacementGatePolicy &policy,
                                        const PcbComposeEvidence &evidence,
                                        const RatsnestNets *nets, const RatsnestEdges *edges) {
    PcbComposeReport out;
    out.index = index;
    out.evaluations = measure_pcb_compose_terms(in, index, policy);
    out.n_corridors = evidence.corridors.size();
    std::optional<double> minimum;
    double sum = 0;
    for (const auto &e : out.evaluations) {
        if (!e.ok)
            ++(e.term.enforced ? out.hard_red : out.soft_red);
        if (e.term.enforced && std::isfinite(e.margin)) {
            sum += e.margin;
            if (!minimum || e.margin < *minimum)
                minimum = e.margin;
        }
    }
    out.hard_margin_sum = py_round(sum, 2);
    out.hard_margin_min = minimum ? py_round(*minimum, 2) : 0;
    const auto &model = in.model();
    std::map<std::pair<std::string, std::string>, std::string> managed;
    for (const auto &c : evidence.coexistence)
        managed[{c.ref, c.sheet}] = c.verdict;
    for (std::size_t k = 0; k < model.insts.size(); ++k) {
        const auto &i = model.insts[k];
        if (starts(i.sheet, "som_j") || !i.mod)
            continue;
        const auto &boxes = in.geometry_at(k).pad_boxes;
        std::optional<std::string> hit;
        std::set<std::string> seen;
        // Preserve original named-pad insertion order for first-hit reporting.
        for (const auto &row : i.mod->pads) {
            const auto &name = std::get<0>(row);
            if (!seen.insert(name).second)
                continue;
            auto p = boxes.find(name);
            if (p == boxes.end())
                continue;
            const auto b = p->second;
            for (const auto &[label, rect] : evidence.corridors) {
                auto c = translated(rect, model.origin_x, model.origin_y);
                if (b.x0 < c.x1 && b.x1 > c.x0 && b.y0 < c.y1 && b.y1 > c.y0) {
                    hit = label;
                    break;
                }
            }
            if (hit)
                break;
        }
        if (!hit)
            continue;
        auto line = i.ref + " (" + i.sheet + ") in " + *hit;
        auto verdict = managed.find({i.ref, i.sheet});
        if (verdict == managed.end())
            out.unmanaged.push_back(line);
        else
            out.managed.push_back(line + " [T2 " + verdict->second + "]");
    }
    std::sort(out.unmanaged.begin(), out.unmanaged.end());
    std::sort(out.managed.begin(), out.managed.end());
    out.cross_airwires = pcb_cross_airwires_by_pair(model, nets, edges);
    return out;
}
std::string PcbComposeReport::text() const {
    std::vector<std::string> lines{
        "FLOORPLAN COMPOSITION (T1): " + std::to_string(index.hard.size()) + " hard / " +
            std::to_string(index.soft.size()) + " soft terms; hard RED " +
            std::to_string(hard_red) + ", soft RED " + std::to_string(soft_red) + " (advisory)",
        "  aggregate hard margin: sum " + pyfloat(hard_margin_sum) + " mm, min " +
            pyfloat(hard_margin_min) + " mm (informational)"};
    std::vector<FloorplanTermEval> hard, soft;
    for (const auto &e : evaluations)
        (e.term.enforced ? hard : soft).push_back(e);
    auto key = [](const FloorplanTerm &t) {
        return std::make_tuple(t.kind, t.subject, t.target_raw);
    };
    auto append = [&](std::vector<FloorplanTermEval> &es) {
        std::sort(es.begin(), es.end(),
                  [&](const auto &a, const auto &b) { return key(a.term) < key(b.term); });
        for (const auto &e : es) {
            const auto &t = e.term;
            lines.push_back("    " + std::string(t.enforced ? "HARD" : "soft") + " " + t.kind +
                            " " + t.subject + "->" + t.target_raw + ": " + f(e.measured, 2) +
                            " vs " + f(e.bound, 2) + " (margin " + sign(e.margin, 2) + ") " +
                            (e.ok ? "ok" : "RED") + " [" + t.basis + "]" +
                            (e.note.empty() ? "" : " " + e.note));
        }
    };
    lines.push_back("  hard terms:");
    append(hard);
    lines.push_back("  soft terms (advisory ledger — repair triggers, never gates):");
    append(soft);
    if (!index.na.empty()) {
        lines.push_back("  n/a terms (endpoint subsystem not instantiated by this project — "
                        "project-scoped resolution):");
        auto terms = index.na;
        std::sort(terms.begin(), terms.end(),
                  [&](const auto &a, const auto &b) { return key(a) < key(b); });
        for (const auto &t : terms)
            lines.push_back("    n/a " + t.kind + " " + t.subject + "->" + t.target_raw + " [" +
                            t.basis + "]");
    }
    lines.push_back("  T2 escape corridors (D13 never-close): " + std::to_string(n_corridors) +
                    " loaded, " + std::to_string(unmanaged.size()) +
                    " UNMANAGED part intrusion(s), " + std::to_string(managed.size()) +
                    " T2-coexistence-managed");
    for (const auto &s : unmanaged)
        lines.push_back("    UNMANAGED INTRUSION " + s);
    for (const auto &s : managed)
        lines.push_back("    managed " + s);
    lines.push_back("  D13 channel hotspots (>= 6 cross-airwires; corridor = 2 + 0.2/net mm):");
    using Row = std::pair<std::pair<std::string, std::string>, std::pair<int, double>>;
    std::vector<Row> pairs;
    for (const auto &entry : cross_airwires)
        if (channel_demand_mm(entry.second.first, 6, 2, .2) > 0 &&
            !starts(entry.first.first, "som_j") && !starts(entry.first.second, "som_j"))
            pairs.push_back(entry);
    std::sort(pairs.begin(), pairs.end(), [](const auto &a, const auto &b) {
        return a.second.first != b.second.first ? a.second.first > b.second.first
                                                : a.first < b.first;
    });
    for (const auto &[pair, value] : pairs)
        lines.push_back("    " + pair.first + " | " + pair.second + ": " +
                        std::to_string(value.first) + " airwires (" + f(value.second, 1) +
                        " mm) -> corridor >= " + f(channel_demand_mm(value.first, 6, 2, .2), 1) +
                        " mm");
    return join(lines);
}
PcbPlacementGatesResult
check_pcb_placement_gates(const PcbCheckInput &input, const PcbPlacementGatePolicy &policy,
                          const FloorplanTermIndex &index, const PcbComposeEvidence &evidence,
                          const RatsnestNets *nets, const RatsnestEdges *edges) {
    validate_pcb_contract_pins(policy);
    PcbPlacementGatesResult out;
    out.placement_contract = check_pcb_wired_contracts(input, policy);
    out.placement_flow = check_pcb_placement_flow(input, policy);
    out.coverage = pcb_contract_coverage(input, policy);
    out.coverage_report = render_pcb_contract_coverage(out.coverage, policy.wired_sheets);
    out.composition = report_pcb_composition(input, index, policy, evidence, nets, edges);
    return out;
}
PcbPlacementGatesResult check_pcb_placement_gates(const PcbPlacementInput &authored,
                                                  const PcbModel &model) {
    return check_pcb_placement_gates(PcbCheckInput(model), pcb_placement_gate_policy(authored),
                                     pcb_final_compose_index(authored, model),
                                     pcb_compose_evidence(model));
}
} // namespace schgen
