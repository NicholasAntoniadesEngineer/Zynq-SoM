#include "pcb_emit_internal.hpp"
#include "schgen/embed_fp.hpp"

namespace schgen::pcb_emission {
Box4 courtyard(const PcbFootprintInst &i) {
    if (!i.mod || !i.mod->bbox)
        throw PcbEmissionError(i.ref + ": missing footprint courtyard geometry");
    auto b = inst_placed_box(*i.mod->bbox, i.x, i.y, i.rotation, 4);
    for (double v : {b.x0, b.y0, b.x1, b.y1})
        if (!std::isfinite(v))
            throw PcbEmissionError(i.ref + ": nonfinite footprint courtyard");
    return b;
}
Sexpr embed(const PcbFootprintInst &i, const PcbEmitPolicy &p, const Uid &uid) {
    if (!i.mod)
        throw PcbEmissionError(i.ref + ": unresolved footprint");
    if (!tag(i.mod->document, "footprint"))
        throw PcbEmissionError(i.ref + ": footprint root required");
    if (!mirror_assert_ok(i.mirror, i.side,
                          std::filesystem::path(i.mod->source).parent_path().filename() ==
                              ".mirrored_fp"))
        throw PcbEmissionError(
            i.ref + ": mirror=True demands side=bottom + a .mirrored_fp document (got side='" +
            i.side + "', mod=" + i.mod->source +
            ") — a mirrored instance emitted any other way is chiral-wrong copper");
    Sexpr doc = i.mod->document;
    auto &root = std::get<SexprList>(doc.v);
    if (root.size() < 2)
        throw PcbEmissionError(i.ref + ": footprint name required");
    for (const auto& override : p.model_overrides) {
        if (i.value != override.value || i.footprint != override.footprint) continue;
        if (i.mirror) throw PcbEmissionError(i.ref + ": model override requires unmirrored source geometry");
        if (override.path.empty() || !std::isfinite(override.rotation_z))
            throw PcbEmissionError(i.ref + ": invalid model override");
        auto replacement = node("model", {str(override.path), node("offset", {node("xyz", {num(0),num(0),num(0)})}),
            node("scale", {node("xyz", {num(1),num(1),num(1)})}),
            node("rotate", {node("xyz", {num(0),num(0),num(override.rotation_z)})})});
        auto first = std::find_if(root.begin(), root.end(), [](const auto& n) { return tag(n,"model"); });
        if (first == root.end()) root.push_back(std::move(replacement));
        else {
            *first = std::move(replacement);
            root.erase(std::remove_if(first + 1, root.end(), [](const auto& n) { return tag(n,"model"); }), root.end());
        }
        break;
    }
    root[1] = str(footprint_alias(i.footprint, p.footprint_aliases));
    doc = embed_footprint_body(std::move(doc), i.x, i.y, i.rotation, i.side, uid("fp:" + i.ref));
    std::unordered_map<std::string, std::pair<int, std::string>> nets(i.pad_nets.begin(),
                                                                      i.pad_nets.end());
    std::unordered_map<int, std::pair<int, std::string>> inherited;
    for (const auto &[seq, n, name] : thermal_via_scan(doc, nets))
        inherited[seq] = {n, name};
    bool hide = lookup(p.connector_mating_faces, i.value) || lookup(p.header_descriptions, i.ref) ||
                lookup(p.switch_descriptions, i.ref) ||
                i.footprint.find("TestPoint") != std::string::npos;
    return embed_footprint_decorate(std::move(doc), i.ref, i.value, i.rotation, hide, nets,
                                    inherited, uid);
}

ThermalNodes thermal_nodes(const PcbModel &m, const PcbEmitPolicy &p, const Uid &uid,
                           PcbEmissionResult &result) {
    ThermalNodes out;
    auto g = m.net_numbers.find("GND");
    if (g == m.net_numbers.end() || !g->second)
        return out;
    std::map<int, std::string> net_names;
    for (const auto &[name, n] : m.net_numbers)
        net_names[n] = name;
    // Scan each immutable source once per render, never cache by a mutable path.
    using Pads = decltype(scan_mod_pads(Sexpr{}));
    std::map<const PcbCheckFootprint *, Pads> scans;
    std::vector<Points> polygons;
    std::vector<std::string> layers;
    Points placed;
    ViaSiteSpec rule{m.origin_x,          m.origin_y,           m.board_w,
                     m.board_h,           p.thermal_via_edge,   p.thermal_via_size,
                     p.thermal_via_drill, p.thermal_via_clear,  p.hole_samenet_pad,
                     p.thermal_via_h2h,   p.thermal_via_spacing};
    for (const auto &i : m.insts) {
        auto match = std::find_if(p.thermal_copper.begin(), p.thermal_copper.end(),
                                  [&](const auto &s) { return starts(i.value, s.first); });
        if (match == p.thermal_copper.end())
            continue;
        auto spec = match->second;
        if (spec.via_sites.empty())
            throw PcbEmissionError(i.ref + ": thermal copper requires preferred via sites");
        if (i.mirror) {
            spec.pour = {spec.pour.x0, 0.0 - spec.pour.y1, spec.pour.x1, 0.0 - spec.pour.y0};
            for (auto &xy : spec.via_sites)
                xy.second = 0.0 - xy.second;
        }
        if (i.side == "bottom")
            for (auto &l : spec.pour_layers) {
                if (l == "F.Cu")
                    l = "B.Cu";
                else if (l == "B.Cu")
                    l = "F.Cu";
                else
                    throw PcbEmissionError("unknown thermal copper layer: " + l);
            }
        auto corners = corners_rot(
            spec.pour, i.rotation, i.x, i.y, m.origin_x + p.gnd_plane_edge_back,
            m.origin_y + p.gnd_plane_edge_back, m.origin_x + m.board_w - p.gnd_plane_edge_back,
            m.origin_y + m.board_h - p.gnd_plane_edge_back, 3);
        for (const auto &l : spec.pour_layers) {
            out.zones.push_back(emit_fill_zone(
                g->second, "GND", "thermal_pour_" + i.ref + "_" + l.substr(0, l.find('.')), l,
                corners, uid("thpour:" + i.ref + ":" + l), p.pour_clearance, true,
                p.zone_min_thickness));
            polygons.push_back(corners);
            layers.push_back(l);
        }
        double reach = 0;
        for (auto [x, y] : spec.via_sites)
            reach = std::max({reach, std::abs(x), std::abs(y)});
        reach += 20;
        std::vector<ViaObstacle> obstacles;
        for (const auto &other : m.insts)
            if (within_reach(other.x, other.y, i.x, i.y, reach)) {
                if (!other.mod)
                    throw PcbEmissionError(other.ref + ": unresolved thermal via obstacle");
                auto found = scans.find(other.mod.get());
                if (found == scans.end())
                    found =
                        scans.emplace(other.mod.get(), scan_mod_pads(other.mod->document)).first;
                for (const auto &[name, x, y, rot, w, h, drill] : found->second) {
                    auto [wx, wy] = world_turned_point(other.x, other.y, x, y, other.rotation, 4);
                    auto [hx, hy] = pad_half_extent(w, h, other.rotation + rot);
                    auto net = other.pad_nets.find(name);
                    obstacles.push_back({wx, wy, hx, hy,
                                         net == other.pad_nets.end() ? "" : net->second.second,
                                         drill, other.ref + "." + name});
                }
            }
        for (const auto &c : m.copper)
            if (c.kind == "via" && within_reach(c.x, c.y, i.x, i.y, reach)) {
                auto [x, y] = round_xy(c.x, c.y, 4);
                double radius = c.size / 2;
                obstacles.push_back(
                    {x, y, radius, radius, net_names[c.net], c.drill,
                     "escape via @(" + fmt(c.x, 3, true) + "," + fmt(c.y, 3, true) + ")"});
            }
        Points chosen, candidates = spec.via_sites;
        auto lattice = fallback_via_sites(spec.pour.x0, spec.pour.y0, spec.pour.x1, spec.pour.y1,
                                          p.thermal_via_size, p.thermal_lattice_pitch);
        candidates.insert(candidates.end(), lattice.begin(), lattice.end());
        int n_lattice = 0;
        std::map<std::string, int> vetoes;
        Points occupied = placed;
        for (std::size_t ci = 0; ci < candidates.size() && chosen.size() < spec.max_vias; ++ci) {
            auto [x, y] = world_turned_point(i.x, i.y, candidates[ci].first, candidates[ci].second,
                                             i.rotation, 3);
            auto hit = via_site_blocker(x, y, rule, obstacles, occupied);
            if (!hit.blocked) {
                chosen.emplace_back(x, y);
                occupied.emplace_back(x, y);
                if (ci >= spec.via_sites.size()) {
                    ++n_lattice;
                    result.fallback_events.push_back("thermal_via_lattice");
                }
            } else {
                std::string label;
                if (hit.kind == "edge")
                    label = "Edge.Cuts keep-back";
                else if (hit.kind == "thermal")
                    label =
                        "thermal via @(" + fmt(hit.x, 3, true) + "," + fmt(hit.y, 3, true) + ")";
                else
                    label = hit.label + " [" + (hit.nname.empty() ? "no-net" : hit.nname) + "] @(" +
                            fmt(hit.x, 3, true) + "," + fmt(hit.y, 3, true) + ")";
                ++vetoes[label];
            }
        }
        if (n_lattice)
            result.diagnostics.push_back(
                "THERMAL VIA LATTICE: " + i.ref + " (" + i.value + ") seated " +
                std::to_string(n_lattice) + "/" + std::to_string(chosen.size()) +
                " via(s) from the exhaustive lattice — curated preferred site(s) blocked "
                "(registered fallback; drift from datasheet-preferred via geometry)");
        const ThermalPourNeed *need = nullptr;
        for (const auto &n : p.thermal_credit_needs)
            if (starts(i.value, n.value_prefix) &&
                (!need ||
                 std::tie(n.min_vias, n.radius_mm) > std::tie(need->min_vias, need->radius_mm)))
                need = &n;
        if (need) {
            int count = count_within_reach(i.x, i.y, chosen, need->radius_mm);
            if (count < need->min_vias) {
                std::vector<std::pair<std::string, int>> top(vetoes.begin(), vetoes.end());
                std::stable_sort(top.begin(), top.end(),
                                 [](const auto &a, const auto &b) { return a.second > b.second; });
                std::string blockers;
                for (std::size_t n = 0; n < std::min<std::size_t>(4, top.size()); ++n) {
                    if (n)
                        blockers += "; ";
                    blockers += top[n].first + " x" + std::to_string(top[n].second);
                }
                result.diagnostics.push_back(
                    "THERMAL VIA SHORTFALL: " + i.ref + " (" + i.value + ") at (" +
                    fmt(i.x, 3, true) + "," + fmt(i.y, 3, true) + ") rot " + fmt(i.rotation) +
                    " seated " + std::to_string(count) + "/" + std::to_string(need->min_vias) +
                    " GND vias within " + fmt(need->radius_mm) + " mm; " +
                    std::to_string(candidates.size()) +
                    " candidate seats searched (curated + lattice), every other one blocked. Worst "
                    "blockers: " +
                    blockers +
                    ". MOVE those parts (or this one): the thermal gate WITHHOLDS the pour credit "
                    "on a short field.");
            }
        }
        placed.insert(placed.end(), chosen.begin(), chosen.end());
        for (std::size_t n = 0; n < chosen.size(); ++n)
            out.vias.push_back(emit_via(chosen[n].first, chosen[n].second, p.thermal_via_size,
                                        p.thermal_via_drill, g->second,
                                        uid("thvia:" + i.ref + ":" + std::to_string(n)), false));
    }
    std::map<std::string, std::vector<std::size_t>> groups;
    for (std::size_t n = 0; n < layers.size(); ++n)
        groups[layers[n]].push_back(n);
    for (const auto &[_, indices] : groups) {
        std::vector<Points> shapes;
        for (auto n : indices)
            shapes.push_back(polygons[n]);
        auto ranks = stagger_overlap_ranks(shapes);
        for (std::size_t k = 0; k < indices.size(); ++k)
            if (ranks[k]) {
                auto &zone = std::get<SexprList>(out.zones[indices[k]].v);
                auto hatch = std::find_if(zone.begin(), zone.end(),
                                          [](const auto &n) { return tag(n, "hatch"); });
                zone.insert(hatch + 1, node("priority", {num(ranks[k])}));
            }
    }
    return out;
}
} // namespace schgen::pcb_emission
