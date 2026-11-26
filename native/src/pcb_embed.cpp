#include "pcb_emit_internal.hpp"
#include "schgen/embed_fp.hpp"
#include "schgen/thermal_via_planning.hpp"

namespace schgen::pcb_emission {
bool interface_label_part(const PcbFootprintInst& i,const PcbEmitPolicy& p) {
    if(connector_fact(p.connectors,i.value)||lookup(p.header_descriptions,i.ref)||
       lookup(p.switch_descriptions,i.ref))return true;
    const auto digit=i.ref.find_first_of("0123456789");
    const auto prefix=i.ref.substr(0,digit);
    for(const auto* name:{"J","P","TP","SW","JP","BT","LED","FID","H"})
        if(prefix==name)return true;
    for(const auto* family:{"Connector","TestPoint","Button_Switch","Switch","Jumper", "LED_","Display","Battery","Fuse","MountingHole","Fiducial"})
        if(i.footprint.find(family)!=std::string::npos)return true;
    return false;
}
Box4 courtyard(const PcbFootprintInst &i) {
    if (!i.mod || !i.mod->bbox)
        throw PcbEmissionError(i.ref + ": missing footprint courtyard geometry");
    auto b = inst_placed_box(*i.mod->bbox, i.x, i.y, i.rotation, 4);
    for (double v : {b.x0, b.y0, b.x1, b.y1})
        if (!std::isfinite(v))
            throw PcbEmissionError(i.ref + ": nonfinite footprint courtyard");
    return b;
}
Box4 body_box(const PcbFootprintInst &i) {
    if (!i.mod || !i.mod->body)
        throw PcbEmissionError(i.ref + ": missing footprint body geometry");
    auto b = inst_placed_box(*i.mod->body, i.x, i.y, i.rotation, 4);
    for (double v : {b.x0, b.y0, b.x1, b.y1})
        if (!std::isfinite(v))
            throw PcbEmissionError(i.ref + ": nonfinite footprint body");
    return b;
}
namespace {
const std::string silk_layer_suffix = ".SilkS";
const std::vector<std::string> silk_text_tags{"fp_text", "property"};
const std::vector<std::string> silk_line_tags{"fp_line", "fp_arc", "fp_rect", "fp_circle", "fp_poly", "fp_curve"};
bool on_silk(Sexpr &n) {
    Sexpr *layer = child(n, "layer");
    if (!layer) return false;
    const auto &a = std::get<SexprList>(layer->v);
    if (a.size() < 2 || !std::holds_alternative<std::string>(a[1].v)) return false;
    const std::string &name = std::get<std::string>(a[1].v);
    return name.size() >= silk_layer_suffix.size() &&
           name.compare(name.size() - silk_layer_suffix.size(), silk_layer_suffix.size(), silk_layer_suffix) == 0;
}
bool raise_number(Sexpr *holder, std::size_t at, double floor) {
    if (!holder) return false;
    auto &a = std::get<SexprList>(holder->v);
    if (a.size() <= at || !std::holds_alternative<double>(a[at].v)) return false;
    const double value = std::get<double>(a[at].v);
    if (value <= 0.0 || value >= floor) return false;
    a[at] = num(floor);
    return true;
}
bool unfilled(Sexpr &n) {
    Sexpr *fill = child(n, "fill");
    if (!fill) return true;
    const auto &a = std::get<SexprList>(fill->v);
    if (a.size() < 2 || !std::holds_alternative<Sexpr::Sym>(a[1].v)) return true;
    const std::string &mode = std::get<Sexpr::Sym>(a[1].v).name;
    return mode == "none" || mode == "no";
}
void raise_silk(Sexpr &doc, const DrcFloors &floors) {
    for (auto &n : std::get<SexprList>(doc.v)) {
        if (!std::holds_alternative<SexprList>(n.v) || !on_silk(n)) continue;
        const auto is = [&](const std::vector<std::string> &tags) {
            return std::any_of(tags.begin(), tags.end(), [&](const std::string &t) { return tag(n, t); });
        };
        if (is(silk_text_tags)) {
            Sexpr *effects = child(n, "effects");
            Sexpr *font = effects ? child(*effects, "font") : nullptr;
            if (!font) continue;
            Sexpr *size = child(*font, "size");
            if (size) {
                auto &a = std::get<SexprList>(size->v);
                if (a.size() > 2 && std::holds_alternative<double>(a[1].v) && std::holds_alternative<double>(a[2].v)) {
                    const double width = std::get<double>(a[1].v), height = std::get<double>(a[2].v);
                    if (height > 0.0 && height < floors.text_height) {
                        a[1] = num(width * floors.text_height / height);
                        a[2] = num(floors.text_height);
                    }
                }
            }
            raise_number(child(*font, "thickness"), 1, floors.text_thickness);
        } else if (is(silk_line_tags) && unfilled(n)) {
            if (Sexpr *stroke = child(n, "stroke")) raise_number(child(*stroke, "width"), 1, floors.text_thickness);
        }
    }
}
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
    if (const ModelOverrideFact* found = part_fact_for(p.model_overrides, i.value, i.footprint); found && found->footprint == i.footprint) {
        const ModelOverrideFact& override = *found;
        if (i.mirror) throw PcbEmissionError(i.ref + ": model override requires unmirrored source geometry");
        if (override.path.empty() || !std::isfinite(override.rotation_z_deg))
            throw PcbEmissionError(i.ref + ": invalid model override");
        auto replacement = node("model", {str(override.path), node("offset", {node("xyz", {num(0),num(0),num(0)})}),
            node("scale", {node("xyz", {num(1),num(1),num(1)})}),
            node("rotate", {node("xyz", {num(0),num(0),num(override.rotation_z_deg)})})});
        auto first = std::find_if(root.begin(), root.end(), [](const auto& n) { return tag(n,"model"); });
        if (first == root.end()) root.push_back(std::move(replacement));
        else {
            *first = std::move(replacement);
            root.erase(std::remove_if(first + 1, root.end(), [](const auto& n) { return tag(n,"model"); }), root.end());
        }
    }
    const FootprintAliasFact* alias = part_fact(p.footprint_aliases, i.footprint);
    root[1] = str(alias ? alias->footprint : i.footprint);
    doc = embed_footprint_body(std::move(doc), i.x, i.y, i.rotation, i.side, uid("fp:" + i.ref));
    std::unordered_map<std::string, std::pair<int, std::string>> nets(i.pad_nets.begin(),
                                                                      i.pad_nets.end());
    std::unordered_map<int, std::pair<int, std::string>> inherited;
    for (const auto &[seq, n, name] : thermal_via_scan(doc, nets))
        inherited[seq] = {n, name};
    bool hide = connector_fact(p.connectors, i.value) || lookup(p.header_descriptions, i.ref) ||
                lookup(p.switch_descriptions, i.ref) ||
                i.footprint.find("TestPoint") != std::string::npos;
    if(p.interface_reference_labels_only)hide=!interface_label_part(i,p);
    if(!p.labels)hide=true;
    Sexpr out = embed_footprint_decorate(std::move(doc), i.ref, i.value, i.rotation, hide, nets,
                                         inherited, uid);
    if (p.silk_to_floor) {
        if (!p.drc_floors) throw PcbEmissionError(i.ref + ": raising silk to the fabricator minimum needs the fabricator floors");
        raise_silk(out, *p.drc_floors);
    }
    return out;
}

std::vector<ViaObstacle> thermal_obstacles(const PcbCheckModel &m, QuantizationCounts* counts) {
    std::map<int, std::string> net_names;
    for (const auto &[name, n] : m.net_numbers)
        net_names[n] = name;
    // Scan each immutable source once per render, never cache by a mutable path.
    using Pads = decltype(scan_mod_pads(Sexpr{}));
    std::map<const PcbCheckFootprint *, Pads> scans;
    // Through-vias must clear pads on both faces. Footprint origins do not
    // bound pad extent: connectors and offset-origin footprints can reach far
    // beyond them. Prepare actual world geometry once, shared by all subjects.
    std::vector<ViaObstacle> obstacles;
    for (const auto &other : m.insts) {
        if (!other.mod)
            throw PcbEmissionError(other.ref + ": unresolved thermal via obstacle");
        auto found = scans.find(other.mod.get());
        if (found == scans.end())
            found = scans.emplace(other.mod.get(), scan_mod_pads(other.mod->document)).first;
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
        if (c.kind == "via") {
            auto [x, y] = round_xy(c.x, c.y, 4, counts);
            double radius = c.size / 2;
            obstacles.push_back({x, y, radius, radius, net_names[c.net], c.drill,
                "escape via @(" + fmt(c.x, 3, true) + "," + fmt(c.y, 3, true) + ")"});
        }
    return obstacles;
}
ViaSiteSpec thermal_rule(const PcbCheckModel &m, const PcbEmitPolicy &p) {
    return {m.origin_x, m.origin_y, m.board_w, m.board_h, p.thermal_via_edge,
            p.thermal_via_size, p.thermal_via_drill, p.thermal_via_clear,
            p.hole_samenet_pad, p.thermal_via_h2h, p.thermal_via_spacing};
}
bool has_thermal_subjects(const PcbCheckModel& m, const PcbEmitPolicy& p) {
    return std::any_of(m.insts.begin(), m.insts.end(), [&](const auto &i) {
        return thermal_field_for(p.thermal_copper, p.regulators, i.value) != nullptr;
    });
}
ThermalNodes thermal_nodes(const PcbModel &m, const PcbEmitPolicy &p, const Uid &uid,
                           PcbEmissionResult &result, QuantizationCounts* counts) {
    ThermalNodes out;
    auto g = m.net_numbers.find("GND");
    if (g == m.net_numbers.end() || !g->second || !has_thermal_subjects(m, p))
        return out;
    const auto obstacles = thermal_obstacles(m, counts);
    const auto rule = thermal_rule(m, p);
    std::vector<Points> polygons;
    std::vector<std::string> layers;
    Points placed;
    for (const auto &i : m.insts) {
        auto found = thermal_copper_spec(p, i.value);
        if (!found)
            continue;
        auto spec = std::move(*found);
        if (spec.via_sites.empty())
            throw PcbEmissionError(i.ref + ": thermal copper requires preferred via sites");
        spec.pour = thermal_pour_local(spec.pour, i.mirror);
        if (i.mirror)
            for (auto &xy : spec.via_sites)
                xy.second = 0.0 - xy.second;
        if (i.side == "bottom")
            for (auto &l : spec.pour_layers) {
                if (l == "F.Cu")
                    l = "B.Cu";
                else if (l == "B.Cu")
                    l = "F.Cu";
                else
                    throw PcbEmissionError("unknown thermal copper layer: " + l);
            }
        auto corners = thermal_pour_corners(
            spec.pour, i.rotation, i.x, i.y,
            ground_plane_box(m.origin_x, m.origin_y, m.board_w, m.board_h, p.gnd_plane_edge_back));
        for (const auto &l : spec.pour_layers) {
            out.zones.push_back(emit_fill_zone(
                g->second, "GND", "thermal_pour_" + i.ref + "_" + l.substr(0, l.find('.')), l,
                corners, uid("thpour:" + i.ref + ":" + l), p.pour_clearance, true,
                p.zone_min_thickness));
            polygons.push_back(corners);
            layers.push_back(l);
        }
        auto selection = select_via_sites(i.x, i.y, i.rotation, spec.via_sites, spec.pour,
            spec.max_vias, p.thermal_lattice_pitch, true, rule, obstacles, placed, counts);
        const auto& chosen = selection.chosen;
        const auto n_lattice = selection.lattice_chosen;
        result.fallback_events.insert(result.fallback_events.end(), n_lattice, "thermal_via_lattice");
        std::map<std::string, int> vetoes;
        std::map<std::string, int> preferred_vetoes;
        for (const auto& rejection : selection.rejected) {
            const auto& hit = rejection.blocker;
            std::string label;
            if (hit.kind == "edge")
                label = "Edge.Cuts keep-back";
            else if (hit.kind == "thermal")
                label = "thermal via @(" + fmt(hit.x, 3, true) + "," + fmt(hit.y, 3, true) + ")";
            else
                label = hit.label + " [" + (hit.nname.empty() ? "no-net" : hit.nname) + "] @(" +
                        fmt(hit.x, 3, true) + "," + fmt(hit.y, 3, true) + ")";
            ++vetoes[label];
            if (rejection.preferred) ++preferred_vetoes[label];
        }
        if (n_lattice) {
            std::string preferred_blockers;
            for(const auto& [label,count]:preferred_vetoes) {
                if(!preferred_blockers.empty())preferred_blockers+="; ";
                preferred_blockers+=label+" x"+std::to_string(count);
            }
            result.diagnostics.push_back(
                "THERMAL VIA LATTICE: " + i.ref + " (" + i.value + ") seated " +
                std::to_string(n_lattice) + "/" + std::to_string(chosen.size()) +
                " via(s) from the exhaustive lattice — curated preferred site(s) blocked "
                "(registered fallback; alternative to authored preferred via geometry). Preferred-site blockers: "+preferred_blockers);
        }
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
                    std::to_string(selection.preferred_examined + selection.lattice_examined) +
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

namespace schgen {
const char* thermal_ground_net() { return "GND"; }
std::vector<PreferredThermalField> plan_preferred_thermal_vias(
    const PcbCheckModel& m, const PcbEmitPolicy& p, QuantizationCounts* counts) {
    using namespace pcb_emission;
    std::vector<PreferredThermalField> result;
    if (!has_thermal_subjects(m,p)) return result;
    const auto ground = m.net_numbers.find("GND");
    if (ground == m.net_numbers.end() || !ground->second)
        throw PcbEmissionError("thermal planning requires a resolved GND net");
    const auto obstacles = thermal_obstacles(m,counts);
    const auto rule = thermal_rule(m,p);
    Points occupied;
    for (const auto& i : m.insts) {
        auto found = thermal_copper_spec(p,i.value);
        if (!found) continue;
        auto spec = std::move(*found);
        if (spec.via_sites.empty()) throw PcbEmissionError(i.ref+": thermal copper requires preferred via sites");
        if (i.mirror) {
            for (auto& xy : spec.via_sites) xy.second = -xy.second;
            spec.pour = {spec.pour.x0,-spec.pour.y1,spec.pour.x1,-spec.pour.y0};
        }
        auto sites = select_via_sites(i.x,i.y,i.rotation,spec.via_sites,spec.pour,
            spec.max_vias,p.thermal_lattice_pitch,false,rule,obstacles,occupied,counts);
        occupied.insert(occupied.end(),sites.chosen.begin(),sites.chosen.end());
        result.push_back({i.ref,spec.max_vias,std::move(sites)});
    }
    return result;
}
std::vector<ThermalPadMove> thermal_pad_move_candidates(
    const PcbCheckModel& model, const PcbEmitPolicy& policy,
    const std::vector<PreferredThermalField>& fields, QuantizationCounts* counts) {
    if (std::none_of(fields.begin(),fields.end(),[](const auto& field) {
            return field.sites.chosen.size()<field.requested;
        })) return {};
    const auto obstacles=pcb_emission::thermal_obstacles(model,counts);
    const auto rule=pcb_emission::thermal_rule(model,policy);
    std::map<std::string,std::set<std::string>> owners;
    for (const auto& part : model.insts)
        for (const auto& pad : scan_mod_pads(part.mod->document))
            owners[part.ref+"."+std::get<0>(pad)].insert(part.ref);
    std::set<std::tuple<std::string,double,double>> seen;
    std::vector<ThermalPadMove> result;
    std::vector<ThermalPadMove> subject_moves;
    std::set<std::tuple<std::string,double,double>> subject_seen;
    for (const auto& field : fields) {
        if (field.sites.chosen.size()>=field.requested) continue;
        for (const auto& rejected : field.sites.rejected) {
            if (!rejected.preferred || rejected.blocker.kind!="obs") continue;
            const auto found=owners.find(rejected.blocker.label);
            if (found==owners.end() || found->second.size()!=1) continue;
            const auto& ref=*found->second.begin();
            if (ref==field.ref) continue; // Moving the subject also moves its sites.
            for (const auto& obstacle : obstacles) {
                if (obstacle.label!=rejected.blocker.label) continue;
                for (const auto& [x,y] : via_obstacle_axis_exits(
                        rejected.candidate.first,rejected.candidate.second,rule,obstacle)) {
                    const double dx=x-obstacle.cx, dy=y-obstacle.cy;
                    if (seen.emplace(ref,dx,dy).second) result.push_back({ref,dx,dy});
                    // Equivalent relative displacement with the obstacle held
                    // still. The caller must move the subject's complete group
                    // when required and recheck all fields and hardware gates.
                    if (subject_seen.emplace(field.ref,-dx,-dy).second)
                        subject_moves.push_back({field.ref,-dx,-dy});
                }
            }
        }
    }
    std::stable_sort(result.begin(),result.end(),[](const auto& a,const auto& b) {
        return std::hypot(a.dx,a.dy)<std::hypot(b.dx,b.dy);
    });
    std::stable_sort(subject_moves.begin(),subject_moves.end(),[](const auto& a,const auto& b) {
        return std::hypot(a.dx,a.dy)<std::hypot(b.dx,b.dy);
    });
    for(const auto& move:subject_moves)
        if(seen.emplace(move.ref,move.dx,move.dy).second)result.push_back(move);
    return result;
}
bool preserves_preferred_thermal_vias(const std::vector<PreferredThermalField>& before,
                                      const std::vector<PreferredThermalField>& after) {
    if (before.size()!=after.size()) return false;
    std::map<std::string,const PreferredThermalField*> prior;
    for (const auto& field : before)
        if (!prior.emplace(field.ref,&field).second) return false;
    for (const auto& field : after) {
        const auto old = prior.find(field.ref);
        if (old==prior.end() || field.requested!=old->second->requested ||
            field.sites.chosen.size()<old->second->sites.chosen.size()) return false;
        prior.erase(old);
    }
    return prior.empty();
}
}
