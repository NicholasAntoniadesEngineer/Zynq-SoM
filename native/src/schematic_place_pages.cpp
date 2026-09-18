#include "schematic_place_internal.hpp"

#include "schgen/occupancy.hpp"

#include <iomanip>
#include <locale>
#include <sstream>

#if defined(__clang__)
#pragma clang fp contract(off)
#endif

namespace schgen::schematic_place {
namespace {
constexpr double TALL_SHEET_MM = 244.0, GROUND_CELL_LIFT = 2 * U;
bool auxiliary(const CircuitPartIr& p) {
    return p.lib_id == "Connector:TestPoint" || p.lib_id == "Mechanical:MountingHole_Pad";
}
bool rail(const CircuitNetIr& n) { return n.net_class == "power" || n.net_class == "ground"; }
std::string repr(const std::string& s) {
    const char quote = s.find('\'') != std::string::npos && s.find('"') == std::string::npos ? '"' : '\'';
    std::string out(1, quote);
    constexpr char hex[] = "0123456789abcdef";
    for (unsigned char ch : s) {
        if (ch == quote || ch == '\\') out += '\\';
        if (ch == '\n') out += "\\n";
        else if (ch == '\r') out += "\\r";
        else if (ch == '\t') out += "\\t";
        else if (ch < 32 || ch == 127) { out += "\\x"; out += hex[ch >> 4]; out += hex[ch & 15]; }
        else out += static_cast<char>(ch);
    }
    return out + quote;
}
template <typename Range> std::string repr_list(const Range& values) {
    std::string out = "[";
    for (const auto& s : values) { if (out.size() > 1) out += ", "; out += repr(s); }
    return out + "]";
}
VisualBox visual(const Box4& b, const std::string& kind, const std::string& owner) {
    return {b.x0, b.y0, b.x1, b.y1, kind, owner};
}
struct Bounds {
    bool present = false;
    double x0 = 0, y0 = 0, x1 = 0, y1 = 0;
    void add(double x, double y) {
        if (!present) { x0 = x1 = x; y0 = y1 = y; present = true; }
        else { x0 = std::min(x0, x); x1 = std::max(x1, x); y0 = std::min(y0, y); y1 = std::max(y1, y); }
    }
    void boxes(const std::vector<VisualBox>& boxes) {
        for (const auto& b : boxes) { add(b.x0, b.y0); add(b.x1, b.y1); }
    }
};
void translate_route(SchematicRoutedSheet& r, double dx, double dy) {
    for (auto& s : r.segs) {
        s.x0 = py_round(s.x0 + dx, 3); s.y0 = py_round(s.y0 + dy, 3);
        s.x1 = py_round(s.x1 + dx, 3); s.y1 = py_round(s.y1 + dy, 3);
    }
    for (auto& p : r.junctions) { p.x = py_round(p.x + dx, 3); p.y = py_round(p.y + dy, 3); }
}
std::string oversized(double w, double h) {
    std::ostringstream out;
    out.imbue(std::locale::classic());
    out << "sheet " << std::fixed << std::setprecision(0) << py_round(w, 0) << 'x'
        << py_round(h, 0) << " mm exceeds even A3 (390x265)";
    return out.str();
}
}  // namespace

std::pair<CircuitSheetIr, Refs> split_auxiliary(const CircuitSheetIr& c) {
    Refs refs;
    for (const auto& p : c.parts) if (auxiliary(p)) refs.push_back(p.ref);
    std::sort(refs.begin(), refs.end(), [](const auto& a, const auto& b) {
        return std::make_pair(a.size(), a) < std::make_pair(b.size(), b);
    });
    CircuitSheetIr core = c;
    if (refs.empty()) return {std::move(core), std::move(refs)};
    const std::set<std::string> excluded(refs.begin(), refs.end());
    core.parts.erase(std::remove_if(core.parts.begin(), core.parts.end(),
        [&](const auto& p) { return excluded.count(p.ref); }), core.parts.end());
    for (auto& n : core.nets) n.pins.erase(std::remove_if(n.pins.begin(), n.pins.end(),
        [&](const auto& p) { return excluded.count(p.ref); }), n.pins.end());
    // Preserve empty nets, NC records, port metadata, loads and waivers exactly
    // as Python split(); this is an intermediate Engine snapshot, not a new IR.
    return {std::move(core), std::move(refs)};
}

void add_probe_row(Engine& eng, const CircuitSheetIr& c, const Refs& refs) {
    if (refs.empty()) return;
    auto& pl = eng.pl;
    const auto ex = eng._extent();
    const bool vertical = ex.y1 - ex.y0 > TALL_SHEET_MM;
    double fx = vertical ? gceil(ex.x1 + 8 * U) : gsnap(ex.x0 + 4 * U);
    double row_y = vertical ? gsnap(ex.y0 + 4 * U) : gceil(ex.y1 + 6 * U);
    const double row_x0 = fx;
    const double wrap_at = std::min(ex.x0 + std::max(140.0, 0.5 * (ex.x1 - ex.x0)),
                                    (ex.x0 + ex.x1) / 2 + 20.0);
    std::map<std::string, const CircuitPartIr*> parts;
    std::map<std::string, const CircuitNetIr*> net_by_ref;
    for (const auto& p : c.parts) parts.emplace(p.ref, &p);
    for (const auto& n : c.nets) for (const auto& p : n.pins) net_by_ref.emplace(p.ref, &n);
    auto net_of = [&](const std::string& ref) -> const CircuitNetIr& {
        const auto it = net_by_ref.find(ref);
        // Do not retry an unnetted auxiliary as if it were geometric congestion.
        if (it == net_by_ref.end()) throw std::invalid_argument(ref + ": test point carries no net");
        return *it->second;
    };
    for (std::size_t i = 0; i < refs.size(); ++i) {
        const auto& ref = refs[i];
        const auto& n = net_of(ref);
        const auto found = parts.find(ref);
        if (found == parts.end()) throw std::invalid_argument("unknown auxiliary part " + repr(ref));
        const auto& p = *found->second;
        const bool ground_after_high = n.net_class != "ground" && i + 1 < refs.size()
            && net_of(refs[i + 1]).net_class == "ground";
        const auto rw = text_wh(ref).first, vw = text_wh(p.value).first;
        if (!vertical) {
            const auto cell_right = std::max(0.76 + 0.42 + std::max(rw, vw), text_wh(n.name).first + 1.0);
            if (fx > row_x0 && fx + cell_right > wrap_at) { fx = row_x0; row_y = gceil(row_y + 13 * U); }
        }
        Point tp;
        int rotation;
        if (n.net_class == "ground") {
            tp = {fx, row_y}; rotation = 0;
            pl.plan(n.name, {{fx, row_y}, {fx, row_y + 2 * U}});
            eng.power(n.name, fx, row_y + 2 * U, 0);  // Ground symbol, downward.
        } else if (n.net_class == "power") {
            eng.power(n.name, fx, row_y, 0, false);
            pl.plan(n.name, {{fx, row_y}, {fx, row_y + 2 * U}});
            tp = {fx, row_y + 2 * U}; rotation = 180;
        } else {
            const bool exported = std::any_of(pl.hlabels.begin(), pl.hlabels.end(),
                [&](const auto& h) { return h.name == n.name; });
            double stub = 2 * U;
            if (n.net_class == "port" && !exported) {
                // A local label alone disconnects probe-only PORTs in hierarchy.
                eng.label(n.name, fx, row_y, 0); stub = 4 * U;
            } else eng.llabel(n.name, fx, row_y, 0);
            pl.plan(n.name, {{fx, row_y}, {fx, row_y + stub}});
            tp = {fx, row_y + stub}; rotation = 180;
        }
        const auto& symbol = eng.lib.get(p.lib_id);
        const auto body = body_box_page(symbol, tp.first, tp.second, rotation, "body", ref);
        const auto cy = (body.y0 + body.y1) / 2;
        const SchematicTextPosition rp{body.x1 + 0.42 + rw / 2, cy - 1.27, 0};
        const SchematicTextPosition vp{body.x1 + 0.42 + vw / 2, cy + 1.27, 0};
        pl.parts.push_back({ref, p.lib_id, p.value, tp.first, tp.second, rotation, p.footprint, rp, vp});
        pl.boxes.push_back(body);
        pl.boxes.push_back(visual(centered_box(ref, rp.x, rp.y), "reference", ref));
        pl.boxes.push_back(visual(centered_box(p.value, vp.x, vp.y), "value", ref));
        eng._done.insert(ref);
        if (vertical) row_y = gceil(row_y + 2 * U + 4.064 + 4 * U + (ground_after_high ? GROUND_CELL_LIFT : 0.0));
        else {
            const double right = std::max({body.x1 + 0.42 + rw, body.x1 + 0.42 + vw, fx + text_wh(n.name).first + 1.0});
            fx = gceil(right + std::max(eng.sp.flag_pitch - 6 * U, 2 * U) + 2 * U);
        }
    }
}

void translate(SchematicPlacement& pl, double dx, double dy) {
    auto move = [&](double& x, double& y) { x = py_round(x + dx, 3); y = py_round(y + dy, 3); };
    auto text = [&](std::optional<SchematicTextPosition>& p) { if (p) move(p->x, p->y); };
    for (auto& p : pl.parts) { move(p.x, p.y); text(p.ref_pos); text(p.val_pos); }
    for (auto& p : pl.powers) { move(p.x, p.y); text(p.val_pos); }
    for (auto& p : pl.hlabels) move(p.x, p.y);
    for (auto& p : pl.llabels) move(p.x, p.y);
    for (auto& p : pl.no_connects) move(p.x, p.y);
    for (auto& entry : pl.plans) for (auto& path : entry.second) for (auto& p : path) move(p.first, p.second);
    for (auto& b : pl.boxes) { move(b.x0, b.y0); move(b.x1, b.y1); }
}
void center_on_sheet(SchematicPlacement& pl) {
    Bounds b; b.boxes(pl.boxes);
    for (const auto& entry : pl.plans) for (const auto& path : entry.second) for (const auto& p : path) b.add(p.first, p.second);
    if (!b.present) throw SchematicPlaceError("cannot center placement without boxes or planned points");
    const double cx = (b.x0 + b.x1) / 2, cy = (b.y0 + b.y1) / 2;
    translate(pl, gsnap(A4_CENTER.first - cx), gsnap(A4_CENTER.second - cy));
}

bool is_congestion(const std::string& message) {
    if (message.find("placement infeasible after") == std::string::npos) return false;
    for (const std::string marker : {"no engine pattern applies", "no power symbol mapped",
            "regulator stage without", "multi-element divider", "neither a multi-pin part nor",
            "unsupported extra leg", "single-ended chain tops out", "bottom-drop attachments beyond"})
        if (message.find(marker) != std::string::npos) return false;
    return true;
}

std::vector<std::set<std::string>> signal_blobs(const CircuitSheetIr& c, SymbolLibrary& lib) {
    std::map<std::string, std::string> parents;
    for (const auto& p : c.parts) parents.emplace(p.ref, p.ref);
    auto find = [&](std::string x) {
        while (parents.at(x) != x) { parents.at(x) = parents.at(parents.at(x)); x = parents.at(x); }
        return x;
    };
    for (const auto& n : c.nets) if (n.net_class == "signal") {
        std::optional<std::string> first;
        for (const auto& p : n.pins) if (parents.count(p.ref)) {
            if (!first) { first = p.ref; continue; }
            const auto a = find(*first), b = find(p.ref);
            if (a != b) parents.at(std::max(a, b)) = std::min(a, b);
        }
    }
    OrderedMap<std::set<std::string>> groups;
    std::map<std::string, std::string> group_of;
    std::set<std::string> multi;
    for (const auto& p : c.parts) {
        const auto root = find(p.ref);
        groups[root].insert(p.ref); group_of.emplace(p.ref, root);
        if (lib.pin_numbers(p.lib_id).size() > 2) multi.insert(p.ref);
    }
    std::map<std::string, std::set<std::string>> rail_groups;
    for (const auto& n : c.nets) if (rail(n)) {
        std::set<std::string> roots;
        for (const auto& p : n.pins) if (multi.count(p.ref)) roots.insert(group_of.at(p.ref));
        if (!roots.empty()) rail_groups.emplace(n.name, std::move(roots));
    }
    Refs roots;
    for (const auto& entry : groups) roots.push_back(entry.first);
    for (const auto& root : roots) {
        if (!groups.contains(root) || groups.at(root).size() != 1) continue;
        const auto ref = *groups.at(root).begin();
        if (multi.count(ref)) continue;
        std::vector<const CircuitNetIr*> rails;
        for (const auto& n : c.nets) if (rail(n) && std::any_of(n.pins.begin(), n.pins.end(),
                [&](const auto& p) { return p.ref == ref; })) rails.push_back(&n);
        std::stable_sort(rails.begin(), rails.end(), [](const auto* a, const auto* b) {
            return std::make_pair(a->net_class == "ground", a->name) < std::make_pair(b->net_class == "ground", b->name);
        });
        for (const auto* r : rails) {
            const auto found = rail_groups.find(r->name);
            if (found == rail_groups.end()) continue;
            const auto candidate = std::find_if(found->second.begin(), found->second.end(),
                [&](const auto& g) { return g != root; });
            if (candidate == found->second.end()) continue;
            const auto refs = groups.at(root);  // Do not retain vector-map refs across erase.
            groups.at(*candidate).insert(refs.begin(), refs.end());
            groups.erase(root); break;
        }
    }
    std::vector<std::set<std::string>> out;
    for (const auto& entry : groups) out.push_back(entry.second);
    std::sort(out.begin(), out.end(), [](const auto& a, const auto& b) {
        return a.size() == b.size() ? *a.begin() < *b.begin() : a.size() > b.size();
    });
    return out;
}

CircuitSheetIr subset_page(const CircuitSheetIr& c, const std::set<std::string>& refs, int page) {
    CircuitSheetIr out;
    out.schema = c.schema; out.name = c.name + "." + std::to_string(page); out.title = c.title;
    for (const auto& ref : refs) {
        const auto p = std::find_if(c.parts.begin(), c.parts.end(), [&](const auto& p) { return p.ref == ref; });
        if (p == c.parts.end()) throw std::invalid_argument("unknown page part " + repr(ref));
        out.parts.push_back(*p);
    }
    for (const auto& p : c.nc) if (refs.count(p.ref)) out.nc.push_back(p);
    std::set<std::string> nets;
    for (const auto& n : c.nets) {
        CircuitNetIr kept{n.name, n.net_class, {}};
        for (const auto& p : n.pins) if (refs.count(p.ref)) kept.pins.push_back(p);
        if (kept.pins.empty()) continue;
        if (kept.pins.size() != n.pins.size() && n.net_class == "signal") {
            Refs pins;
            for (const auto& p : n.pins) pins.push_back(p.ref + "." + p.pin);
            std::sort(pins.begin(), pins.end());
            // Partitioning is structural, not a retryable placement failure.
            throw std::invalid_argument("SIGNAL net " + repr(n.name) + " would be CUT across pages — OPEN. pins "
                + repr_list(pins) + " split by page refs " + repr_list(refs)
                + "; partition_pages must keep SIGNAL-connected parts on one page.");
        }
        nets.insert(n.name); out.nets.push_back(std::move(kept));
        if (n.net_class == "port") for (const auto& p : c.port_types) if (p.net == n.name) out.port_types.push_back(p);
        for (const auto& h : c.hints) if (h.net == n.name) out.hints.push_back(h);
    }
    for (const auto& l : c.loads) if (nets.count(l.rail)) out.loads.push_back(l);
    for (const auto& w : c.waivers)
        if (refs.count(w.key.substr(0, w.key.find('.'))) || nets.count(w.key)) out.waivers.push_back(w);
    return out;
}

std::vector<CircuitSheetIr> partition_pages_with_fit(const CircuitSheetIr& c, SymbolLibrary& lib,
        const std::function<bool(const CircuitSheetIr&)>& fits) {
    const auto blobs = signal_blobs(c, lib);
    if (blobs.size() < 2) return {c};
    std::vector<std::set<std::string>> bins;
    for (const auto& blob : blobs) {
        bool placed = false;
        for (auto& bin : bins) {
            auto combined = bin; combined.insert(blob.begin(), blob.end());
            if (fits(subset_page(c, combined, 0))) { bin = std::move(combined); placed = true; break; }
        }
        if (!placed) bins.push_back(blob);
    }
    if (bins.size() < 2) return {c};
    std::vector<CircuitSheetIr> out;
    for (std::size_t i = 0; i < bins.size(); ++i) out.push_back(subset_page(c, bins[i], static_cast<int>(i + 1)));
    return out;
}

SchematicPlacedPage place_and_route_with(const CircuitSheetIr& c, SymbolLibrary& lib,
        const SchematicSpacing& initial, int max_attempts, const PageOperations& ops) {
    auto spacing = initial;
    std::string last = "?";
    for (int attempt = 0; attempt < max_attempts; ++attempt) {
        SchematicPlacement pl;
        SchematicRoutedSheet routed;
        try { pl = ops.build(c, lib, spacing); routed = ops.route(c, pl, lib); }
        catch (const SchematicRouteError& e) { last = "route: " + std::string(e.what()); spacing = spacing.expanded(); continue; }
        catch (const SchematicPlaceError& e) { last = "route: " + std::string(e.what()); spacing = spacing.expanded(); continue; }
        auto geometry = schematic_route_geometry(pl, routed);
        const auto result = ops.check_visual(geometry);
        if (result.ok) {
            Bounds b; b.boxes(pl.boxes);
            for (const auto& s : routed.segs) { b.add(s.x0, s.y0); b.add(s.x1, s.y1); }
            if (!b.present) throw SchematicPlaceError("cannot size placement without boxes or routed segments");
            const double w = b.x1 - b.x0, h = b.y1 - b.y0;
            if (w <= 272.0 && h <= 180.0) return {c, std::move(pl), std::move(routed), std::move(geometry)};
            if (w <= 390.0 && h <= 265.0) {
                const double dx = gsnap(A3_CENTER.first - A4_CENTER.first), dy = gsnap(A3_CENTER.second - A4_CENTER.second);
                translate(pl, dx, dy); translate_route(routed, dx, dy);
                geometry = schematic_route_geometry(pl, routed); pl.paper = "A3";
                return {c, std::move(pl), std::move(routed), std::move(geometry)};
            }
            last = oversized(w, h);
        } else last = result.summary();
        spacing = spacing.expanded();
    }
    throw SchematicPlaceError("placement infeasible after " + std::to_string(max_attempts) + " expansions; last failure:\n" + last);
}

std::vector<SchematicPlacedPage> paginate_and_route_with(const CircuitSheetIr& c, SymbolLibrary& lib,
        const SchematicSpacing& initial, int attempts, const PageOperations& ops) {
    try { return {place_and_route_with(c, lib, initial, attempts, ops)}; }
    catch (const SchematicPlaceError& e) {
        if (!is_congestion(e.what())) throw;
        const auto pages = partition_pages_with_fit(c, lib, [&](const auto& candidate) {
            try { place_and_route_with(candidate, lib, initial, 2, ops); return true; }
            catch (const SchematicPlaceError&) { return false; }
        });
        if (pages.size() < 2) throw;
        std::vector<SchematicPlacedPage> out;
        for (const auto& page : pages) out.push_back(place_and_route_with(page, lib, initial, attempts, ops));
        return out;
    }
}
std::vector<CircuitSheetIr> partition_pages(const CircuitSheetIr& c, SymbolLibrary& lib) {
    return partition_pages_with_fit(c, lib, [&](const auto& candidate) {
        try { place_and_route_schematic(candidate, lib, {}, 2); return true; }
        catch (const SchematicPlaceError&) { return false; }
    });
}
}  // namespace schgen::schematic_place

namespace schgen {
std::vector<CircuitSheetIr> partition_schematic_pages(const CircuitSheetIr& c, SymbolLibrary& lib) {
    return schematic_place::partition_pages(c, lib);
}
namespace {
schematic_place::PageOperations native_page_operations() {
    return {build_schematic_placement,
        [](const auto& c, const auto& pl, auto& lib) { return route_schematic(c, pl, lib); },
        [](const auto& geometry) { return check_visual_geometry(geometry); }};
}
}  // namespace
SchematicPlacement build_schematic_placement(const CircuitSheetIr& c, SymbolLibrary& lib, const SchematicSpacing& spacing) {
    auto split = schematic_place::split_auxiliary(c);
    schematic_place::Engine engine(split.first, lib, spacing);
    engine.pl = engine.run();
    schematic_place::add_probe_row(engine, c, split.second);
    schematic_place::center_on_sheet(engine.pl);
    return std::move(engine.pl);
}
SchematicPlacedPage place_and_route_schematic(const CircuitSheetIr& c, SymbolLibrary& lib,
        const SchematicSpacing& spacing, int attempts) {
    return schematic_place::place_and_route_with(c, lib, spacing, attempts, native_page_operations());
}
std::vector<SchematicPlacedPage> paginate_and_route_schematic(const CircuitSheetIr& c, SymbolLibrary& lib,
        const SchematicSpacing& spacing, int attempts) {
    return schematic_place::paginate_and_route_with(c, lib, spacing, attempts, native_page_operations());
}
}  // namespace schgen
