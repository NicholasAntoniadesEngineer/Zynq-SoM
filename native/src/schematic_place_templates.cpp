#include "schematic_place_internal.hpp"

#include "schgen/occupancy.hpp"
#include "schgen/pcb_scan.hpp"
#include "schgen/place_geom.hpp"

#include <cctype>
#include <limits>
#include <sstream>

#if defined(__clang__)
#pragma clang fp contract(off)
#endif

namespace schgen::schematic_place {
namespace {

double r3(double v) { return py_round(v, 3); }
bool rail(const CircuitNetIr& n) { return n.net_class == "power" || n.net_class == "ground"; }
bool driver(const std::string& type) { return type == "power_out" || type == "output"; }

template<class T> T take(OrderedMap<T>& map, const std::string& key) {
    const auto it = map.find(key);
    if (it == map.end()) return {};
    auto value = std::move(it->second);
    map.erase(key);
    return value;
}
template<class T> const T& get(const OrderedMap<T>& map, const std::string& key) {
    static const T empty{};
    const auto it = map.find(key);
    return it == map.end() ? empty : it->second;
}
template<class T> const T& first(const std::vector<T>& values, const std::string& where) {
    if (values.empty()) throw SchematicPlaceError(where + ": expected a nonempty component list");
    return values.front();
}
template<class T> std::vector<T> unique_sorted(std::vector<T> values) {
    std::sort(values.begin(), values.end());
    values.erase(std::unique(values.begin(), values.end()), values.end());
    return values;
}
void horizontal(SchematicPlacement& pl, const std::string& net, std::vector<double> nodes, double y) {
    nodes = unique_sorted(std::move(nodes));
    for (std::size_t i = 1; i < nodes.size(); ++i) pl.plan(net, {{nodes[i-1], y}, {nodes[i], y}});
}
std::string quoted(const std::string& value) {
    const char quote = value.find('\'') != std::string::npos && value.find('"') == std::string::npos ? '"' : '\'';
    std::string out(1, quote);
    for (char ch : value) {
        if (ch == quote || ch == '\\') out += '\\';
        if (ch == '\n') out += "\\n";
        else if (ch == '\r') out += "\\r";
        else if (ch == '\t') out += "\\t";
        else out += ch;
    }
    return out + quote;
}
std::string refmap_repr(const RefMap& map) {
    std::string out = "{";
    bool comma = false;
    for (const auto& [name, refs] : map) {
        if (comma) out += ", ";
        comma = true; out += quoted(name) + ": [";
        for (std::size_t i = 0; i < refs.size(); ++i) { if (i) out += ", "; out += quoted(refs[i]); }
        out += ']';
    }
    return out + '}';
}
VisualBox box(const Box4& b, const std::string& kind, const std::string& owner) {
    return {b.x0, b.y0, b.x1, b.y1, kind, owner};
}
PinPositions positions(const SymbolDef& symbol, double ay) {
    PinPositions result;
    for (const auto& p : symbol.pins) result[p.number] = pin_page_position(p, 0, ay, 0);
    return result;
}
void erase_chain(Engine& e, const ChainPtr& chain) {
    const auto it = std::find(e.float_chains.begin(), e.float_chains.end(), chain);
    if (it == e.float_chains.end()) throw SchematicPlaceError("placement chain disappeared during template mutation");
    e.float_chains.erase(it);
}

std::optional<std::string> stage_in_rail(Engine& e, const std::string& ref) {
    for (const auto& p : e.lib.get(e.part(ref).lib_id).pins) {
        if (p.etype != "power_in" || p.rotation != 0) continue;
        const auto* n = e.net_of(ref, p.number);
        if (n && n->net_class == "power") return n->name;
    }
    return std::nullopt;
}
bool is_fb_pin(const Engine& e, const SymbolPin& p, const std::string& net, const std::string& out) {
    std::string name;
    for (const auto ch : p.name) if (ch != '/' && ch != '_')
        name += static_cast<char>(std::toupper(static_cast<unsigned char>(ch)));
    static const std::set<std::string> other{"BIAS", "VCC", "RT", "PGOOD", "SS", "COMP", "ENSYNC", "EN"};
    static const std::set<std::string> feedback{"FB", "FEEDBACK", "VFB", "VSENSE", "FBVSENSE"};
    if (other.count(name)) return false;
    if (feedback.count(name)) return true;
    for (const auto& [ref, rail_name] : get(e.pull, net))
        if (rail_name == out && e.part(ref).lib_id == "Device:R") return true;
    return false;
}
std::optional<std::string> stage_fb_net(Engine& e, const std::string& ref, const Stage& stage) {
    for (const auto& p : e.lib.get(e.part(ref).lib_id).pins) {
        const auto* n = e.net_of(ref, p.number);
        if (n && n->net_class == "signal" && (e.pull.contains(n->name) || e.hang.contains(n->name)) &&
            is_fb_pin(e, p, n->name, stage.out)) return n->name;
    }
    return std::nullopt;
}
bool stage_has_left_input(Engine& e, const std::string& ref) {
    // _stage_in_rail already requires this exact power-in/left-pin predicate.
    return stage_in_rail(e, ref).has_value();
}
std::string stage_in_rail_box(Engine& e, const std::string& ref) {
    const auto& symbol = e.lib.get(e.part(ref).lib_id);
    const auto stage = e._detect_buck_topology(ref, symbol);
    for (const auto& p : symbol.pins) {
        const auto* n = e.net_of(ref, p.number);
        if (n && n->net_class == "power" && n->name.rfind("GND", 0) != 0 && (!stage || n->name != stage->out))
            return n->name;
    }
    throw SchematicPlaceError(ref + ": box buck stage with no input rail");
}

}  // namespace

void Engine::_decoupling_cluster(double ax, double ay, const VisualBox& body) {
    double col_x = ax - sp.cluster_dx;
    std::size_t count = 0;
    for (const auto& [_, caps] : cluster) count += caps.size();
    if (!count) return;
    const double span = static_cast<double>(count - 1) * sp.cap_pitch;
    double farm_left, row_step, cy, max_right;
    if (count > 5) {
        const auto extent = _extent();
        std::tie(col_x, farm_left, row_step, cy) = farm_cluster_origin(extent.x0, extent.y1, U,
            static_cast<int>(_n_box_bucks));
        max_right = farm_row_right_bound(extent.x0, extent.x1, A3_CENTER.first,
            A3_TITLEBLOCK_LEFT, TITLEBLOCK_MARGIN, sp.cap_pitch);
    } else {
        col_x = std::min(col_x, gfloor(body.x0 - span - 4 * sp.hang_stub));
        cy = std::max(ay + sp.cluster_dy, gceil(body.y1 + 3 * sp.hang_stub));
        const double floor = _cell_floor(col_x - 2 * sp.cap_pitch, col_x + span + 2 * sp.cap_pitch);
        cy = std::max(cy, gceil(floor + 4 * sp.hang_stub));
        farm_left = col_x; row_step = 0; max_right = std::numeric_limits<double>::infinity();
    }
    std::optional<double> previous_width;
    for (const auto& [name, caps] : cluster) {
        const auto width = text_wh(name).first;
        if (previous_width) col_x = next_rail_col(col_x, sp.cap_pitch, *previous_width, width, U, 1.27);
        previous_width = width;
        std::vector<std::pair<double, std::vector<double>>> runs;
        std::vector<double> current;
        for (const auto& ref : caps) {
            const auto wrap = farm_wrap_advance(col_x, max_right, !current.empty(), farm_left, cy, row_step, U);
            if (wrap.wrapped) {
                runs.emplace_back(cy, std::move(current)); current.clear();
                col_x = wrap.col_x; cy = wrap.cy;
            }
            _cluster_cap(ref, col_x, cy);
            current.push_back(col_x); col_x += sp.cap_pitch;
        }
        if (!current.empty()) runs.emplace_back(cy, std::move(current));
        for (const auto& [run_y, tops] : runs) {
            const double y = run_y - 3.81;
            if (tops.size() == 1) power(name, tops.front(), y);
            else {
                const double middle = gsnap((tops.front() + tops.back()) / 2);
                auto nodes = tops; nodes.push_back(middle);
                horizontal(pl, name, std::move(nodes), y);
                pl.plan(name, {{middle, y}, {middle, y - 2.54}});
                power(name, middle, y - 2.54);
            }
        }
    }
    cluster.clear();
}

void Engine::_cluster_cap(const std::string& ref, double x, double cy) {
    for (const auto& number : lib.pin_numbers(part(ref).lib_id)) {
        const auto* n = net_of(ref, number);
        if (!n || n->net_class != "power") continue;
        const auto [far_pt, far] = _vertical_2pin(ref, x, cy - 3.81, n->name, true);
        power(far, far_pt.first, far_pt.second, _power_rot(far, true));
        return;
    }
    throw SchematicPlaceError(ref + ": decoupling capacitor has no POWER pin");
}

void Engine::_flags_row() {
    // One ordered symbol traversal/index for the whole row, preserving duplicate
    // pin last-wins behavior without rescanning every part for each rail.
    std::map<PinKey, std::string> etypes;
    for (const auto& p : c.parts)
        for (const auto& pin : lib.get(p.lib_id).pins) etypes[{p.ref, pin.number}] = pin.etype;
    std::vector<const CircuitNetIr*> rails;
    for (const auto& n : c.nets) {
        if (!rail(n)) continue;
        bool driven = false;
        for (const auto& pr : n.pins) {
            const auto it = etypes.find({pr.ref, pr.pin});
            if (it != etypes.end() && driver(it->second)) { driven = true; break; }
        }
        if (!driven) rails.push_back(&n);
    }
    if (rails.empty()) return;
    const auto extent = _extent();
    auto [x, y] = flags_row_origin(extent.x0, extent.y1, U);
    std::optional<double> previous_width;
    for (const auto* n : rails) {
        const auto width = text_wh(n->name).first;
        if (previous_width) x = next_flag_x(x, sp.flag_pitch, *previous_width, width, U, 2.54);
        power(n->name, x, y);
        const auto end = y + (n->net_class == "ground" ? -2.54 : 2.54);
        pl.plan(n->name, {{x, y}, {x, end}});
        flag(n->name, x, end, n->net_class == "ground" ? 0 : 180);
        previous_width = width;
    }
}

double Engine::_glabel_len(const std::string& name) { return text_wh(name).first + GLABEL_PAD_LEN * TEXT_SIZE; }

void Engine::_power_at(const std::string& name, double x, double y, int rotation, std::optional<Point> value) {
    const auto id = _power_lib(name);
    const auto& symbol = lib.get(id);
    const auto serial = std::to_string(++_pwr);
    const auto ref = "#PWR" + (serial.size() < 2 ? "0" : std::string{}) + serial;
    SchematicPlacedPower power;
    power.lib_id = id; power.value = name; power.ref = ref;
    power.x = x; power.y = y; power.rotation = rotation; power.net = name;
    power.show_value = value.has_value();
    if (value) power.val_pos = SchematicTextPosition{value->first, value->second,
        rotation == 90 || rotation == 270 ? 90 : 0};
    pl.powers.push_back(std::move(power));
    pl.boxes.push_back(body_box_page(symbol, x, y, rotation, "body", ref));
    // The legacy horizontal-strip value box intentionally uses unrotated text.
    if (value) pl.boxes.push_back(box(centered_box(name, value->first, value->second), "value", ref));
}

SchematicPlacement Engine::_connector_template(const std::string& ref) {
    const auto& original = part(ref);
    const auto& symbol = lib.get(original.lib_id);
    const auto body = body_box_page(symbol, 0, 0, 0, "body", ref);
    SchematicPlacedPart placed;
    placed.ref = ref; placed.lib_id = original.lib_id; placed.value = original.value;
    placed.footprint = original.footprint;
    placed.ref_pos = SchematicTextPosition{0, body.y0 - 1.27, 0};
    placed.val_pos = SchematicTextPosition{0, 0, 90};
    pl.parts.push_back(placed); pl.boxes.push_back(body);
    pl.boxes.push_back(box(centered_box(ref, 0, body.y0 - 1.27), "reference", ref));
    pl.boxes.push_back(box(centered_box(original.value, 0, 0, true), "value", ref));
    const auto texts = pin_text_boxes(symbol, placed);
    pl.boxes.insert(pl.boxes.end(), texts.begin(), texts.end()); _done.insert(ref);
    using Tap = std::pair<double, double>; // y, x (stable top-to-bottom order)
    for (const auto [rotation, sign] : {std::pair{0, -1}, std::pair{180, 1}}) {
        std::vector<PinAt> rows;
        for (const auto& pin : symbol.pins) if (pin.rotation == rotation)
            rows.push_back({&pin, pin_page_position(pin, 0, 0, 0)});
        std::stable_sort(rows.begin(), rows.end(), [](const auto& a, const auto& b) { return a.point.second < b.point.second; });
        std::vector<std::tuple<double, double, std::string>> ports;
        OrderedMap<std::vector<Tap>> rails;
        for (const auto& row : rows) {
            const auto* n = net_of(ref, row.pin->number);
            const auto [x, y] = row.point;
            if (!n) pl.no_connects.push_back({x, y});
            else if (n->net_class == "port") ports.emplace_back(y, x, n->name);
            else rails[n->name].emplace_back(y, x);
        }
        const double inner = sign * (5.08 + CONN_RUN);
        std::vector<double> ys;
        for (const auto& port : ports) ys.push_back(std::get<0>(port));
        const auto columns = conn_port_columns(ys, CONN_ROW, 1e-6);
        double inner_length = 0, outer_length = 0;
        for (std::size_t i = 0; i < ports.size(); ++i) {
            auto& length = columns[i] == "inner" ? inner_length : outer_length;
            length = std::max(length, _glabel_len(std::get<2>(ports[i])));
        }
        const double outer = conn_signed_ceil(sign, std::abs(inner) + inner_length + CONN_COL_GAP, U);
        for (std::size_t i = 0; i < ports.size(); ++i) {
            const auto& [y, x, name] = ports[i];
            const double end = columns[i] == "inner" ? inner : outer;
            pl.plan(name, {{x, y}, {end, y}}); label(name, end, y, sign < 0 ? 180 : 0);
        }
        const double label_edge = std::max(std::abs(outer) + outer_length, std::abs(inner) + inner_length);
        const double ylo = ys.empty() ? std::numeric_limits<double>::infinity() : *std::min_element(ys.begin(), ys.end());
        const double yhi = ys.empty() ? -std::numeric_limits<double>::infinity() : *std::max_element(ys.begin(), ys.end());
        const double mid = conn_signed_ceil(sign, label_edge + CONN_MID_GAP, U);
        double strip_reach = 0;
        OrderedMap<std::vector<Tap>> grounds;
        const auto trunk = [&](const std::string& name, const std::vector<Tap>& taps, double x) {
            for (const auto& [y, pin_x] : taps) pl.plan(name, {{pin_x, y}, {x, y}});
            for (std::size_t i = 1; i < taps.size(); ++i) pl.plan(name, {{x, taps[i-1].first}, {x, taps[i].first}});
        };
        for (const auto& [name, taps] : rails) {
            if (net(name).net_class == "ground") { grounds[name] = taps; continue; }
            std::vector<double> tap_ys;
            for (const auto& tap : taps) tap_ys.push_back(tap.first);
            for (const auto& group : conn_cluster_groups(tap_ys, CONN_ROW, 1e-6)) {
                std::vector<Tap> cluster_taps;
                for (const auto index : group) cluster_taps.push_back(taps.at(static_cast<std::size_t>(index)));
                const auto top = cluster_taps.front().first, bottom = cluster_taps.back().first;
                for (const auto& [other, foreign] : rails) if (other != name)
                    for (const auto& tap : foreign) if (top < tap.first && tap.first < bottom)
                        throw SchematicPlaceError(name + ": foreign rail row inside cluster span on side " +
                            std::to_string(sign) + " — extend the engine");
                if (bottom < ylo) {
                    trunk(name, cluster_taps, inner);
                    pl.plan(name, {{inner, top}, {inner, top - CONN_EXT}});
                    power(name, inner, top - CONN_EXT, 0);
                } else if (top > yhi) {
                    trunk(name, cluster_taps, inner);
                    pl.plan(name, {{inner, bottom}, {inner, bottom + CONN_EXT}});
                    power(name, inner, bottom + CONN_EXT, 180);
                } else {
                    trunk(name, cluster_taps, mid);
                    const Point anchor{mid + sign * CONN_STRIP_STUB, top};
                    pl.plan(name, {{mid, top}, anchor});
                    const double width = text_wh(name).first;
                    const double vx = anchor.first + sign * (CONN_STRIP_BAR + 0.42 + width / 2);
                    _power_at(name, anchor.first, anchor.second, sign < 0 ? 90 : 270, Point{vx, top});
                    strip_reach = std::max(strip_reach, CONN_STRIP_STUB + CONN_STRIP_BAR + 0.42 + width + 0.5);
                }
            }
        }
        const double ground_x = conn_gnd_x(sign, label_edge, mid, strip_reach, 5.08, U);
        for (const auto& [name, taps] : grounds) {
            trunk(name, taps, ground_x);
            const double bottom = taps.back().first;
            pl.plan(name, {{ground_x, bottom}, {ground_x, bottom + CONN_EXT}});
            power(name, ground_x, bottom + CONN_EXT, 0);
        }
    }
    Refs rails;
    for (const auto& n : c.nets) if (rail(n)) rails.push_back(n.name);
    std::sort(rails.begin(), rails.end());
    const double y = conn_flag_y(_extent().y1, U);
    double x = conn_flag_x0(sp.flag_pitch, static_cast<int>(rails.size()), U);
    for (const auto& name : rails) {
        power(name, x, y);
        const bool ground = net(name).net_class == "ground";
        const double end = y + (ground ? -2.54 : 2.54);
        pl.plan(name, {{x, y}, {x, end}}); flag(name, x, end, ground ? 0 : 180);
        x += sp.flag_pitch;
    }
    return pl;
}

StageMap Engine::_detect_stages() {
    StageMap stages;
    for (const auto& ref : multi) {
        const auto& symbol = lib.get(part(ref).lib_id);
        for (const auto& p : symbol.pins) {
            if (!driver(p.etype)) continue;
            const auto* n = net_of(ref, p.number);
            if (!n) continue;
            if (n->net_class == "power" && p.etype == "power_out") {
                stages[ref] = {"ldo", n->name, "", ""}; break;
            }
            if (n->net_class == "signal") {
                for (const auto& [r, out] : get(pull, n->name)) if (part(r).lib_id == "Device:L") {
                    stages[ref] = {"buck", out, n->name, r}; break;
                }
                if (stages.contains(ref)) break;
            }
        }
        if (!stages.contains(ref)) if (auto st = _detect_buck_topology(ref, symbol)) stages[ref] = *st;
    }
    return stages;
}

std::optional<Stage> Engine::_detect_buck_topology(const std::string& ref, const SymbolDef& symbol) {
    for (const auto& p : symbol.pins) {
        const auto* n = net_of(ref, p.number);
        if (!n || n->net_class != "signal") continue;
        for (const auto& [r, out] : get(pull, n->name))
            if (part(r).lib_id == "Device:L") return Stage{"buck", out, n->name, r};
        for (const auto& leg : series) {
            if ((n->name != leg.a && n->name != leg.b) || part(leg.ref).lib_id != "Device:L") continue;
            const auto& far = leg.a == n->name ? leg.b : leg.a;
            if (net(far).net_class == "power") return Stage{"buck", far, n->name, leg.ref};
        }
    }
    return std::nullopt;
}

std::optional<std::string> Engine::_stage_in_rail(const std::string& ref) { return stage_in_rail(*this, ref); }
bool Engine::_is_fb_pin(const SymbolPin& pin, const std::string& name, const std::string& out) const {
    return is_fb_pin(*this, pin, name, out);
}
std::optional<std::string> Engine::_stage_fb_net(const std::string& ref, const Stage& stage) {
    return stage_fb_net(*this, ref, stage);
}
bool Engine::_stage_has_left_input(const std::string& ref) { return stage_has_left_input(*this, ref); }
std::string Engine::_stage_in_rail_box(const std::string& ref) { return stage_in_rail_box(*this, ref); }
std::optional<std::string> Engine::_stages_out(const std::string& ref) {
    const auto stage = _detect_buck_topology(ref, lib.get(part(ref).lib_id));
    return stage ? std::optional<std::string>{stage->out} : std::nullopt;
}
double Engine::_farm_row_right_bound(double ex0, double ex1_flow) const {
    return farm_row_right_bound(ex0, ex1_flow, A3_CENTER.first, A3_TITLEBLOCK_LEFT, TITLEBLOCK_MARGIN, sp.cap_pitch);
}
bool Engine::_needs_flag(const std::string& name) {
    const auto& n = net(name);
    std::set<std::string> refs;
    for (const auto& p : n.pins) refs.insert(p.ref);
    std::map<PinKey, std::string> etypes;
    // Only symbols connected to this rail matter; preserve source pin order so
    // duplicate pin numbers still select the final electrical type.
    for (const auto& p : c.parts) if (refs.count(p.ref))
        for (const auto& pin : lib.get(p.lib_id).pins) etypes[{p.ref, pin.number}] = pin.etype;
    bool power_in = false;
    for (const auto& p : n.pins) {
        const auto it = etypes.find({p.ref, p.pin});
        if (it == etypes.end()) continue;
        if (driver(it->second)) return false;
        if (it->second == "power_in") power_in = true;
    }
    return power_in;
}

namespace {

void box_right_pin_islet(Engine& e, const std::string& name, Point pt) {
    double x = r3(pt.first + e.sp.port_run);
    for (int k = 0; k < 8; ++k) {
        if (e._spot_free(llabel_box(name, x, pt.second, 0)) &&
            e._corridor_free(pt.second, pt.first + 0.01, x, {name})) {
            e.pl.plan(name, {pt, {x, pt.second}}); e.llabel(name, x, pt.second, 0); e._bridge(name); return;
        }
        x = gceil(x + 2 * U);
    }
    throw SchematicPlaceError("box-buck right pin " + name + ": no clear islet escape");
}

void box_left_pin_islet(Engine& e, const std::string& name, Point pt, const VisualBox& body) {
    double x = r3(pt.first - e.sp.port_run);
    for (int k = 0; k < 6; ++k) {
        if (e._spot_free(llabel_box(name, x, pt.second, 180)) &&
            e._corridor_free(pt.second, pt.first - 0.01, x, {name})) {
            e.pl.plan(name, {pt, {x, pt.second}}); e.llabel(name, x, pt.second, 180); e._bridge(name); return;
        }
        x = gfloor(x - 2 * U);
    }
    x = pt.first;
    const auto try_label = [&](double xv, double y, bool jog) {
        const Point label{r3(xv + e.sp.port_run), y};
        const auto [low, high] = std::minmax(pt.second, y);
        if (!e._spot_free(llabel_box(name, label.first, label.second, 0)) ||
            !e._spot_free({xv - 0.15, low + 0.2, xv + 0.15, high - 0.2}, 0) ||
            !e._corridor_free(y, xv - 0.01, label.first, {name})) return false;
        if (jog) e.pl.plan(name, {pt, {xv, pt.second}, {xv, y}, label});
        else e.pl.plan(name, {pt, {xv, y}, label});
        e.llabel(name, label.first, label.second, 0); e._bridge(name); return true;
    };
    for (const bool down : {true, false}) {
        const auto edge = down ? body.y1 : body.y0;
        const auto far = down ? gceil(edge + 28 * U) : gfloor(edge - 28 * U);
        const auto step = down ? 2 * U : -2 * U;
        if (!e._vband_stem_free(x, std::min(pt.second, far), std::max(pt.second, far), {name})) continue;
        double y = down ? gceil(edge + 4 * U) : gfloor(edge - 4 * U);
        for (int k = 0; k < 28; ++k) { if (try_label(x, y, false)) return; y = r3(y + step); }
    }
    const bool prefer_up = pt.second < (body.y0 + body.y1) / 2;
    for (const bool up : {prefer_up, !prefer_up}) {
        x = gfloor(pt.first - 2 * U);
        const double edge = up ? body.y0 : body.y1;
        const double low = up ? edge - 24 * U : edge + U;
        const double high = up ? edge - U : edge + 24 * U;
        for (int k = 0; k < 8; ++k) {
            if (e._vband_stem_free(x, low, high, {name}) && e._corridor_free(pt.second, pt.first - 0.01, x, {name})) break;
            x = gfloor(x - 2 * U);
        }
        const auto step = up ? -2 * U : 2 * U;
        double y = up ? gfloor(edge - 4 * U) : gceil(edge + 4 * U);
        for (int k = 0; k < 24; ++k) { if (try_label(x, y, true)) return; y = r3(y + step); }
    }
    throw SchematicPlaceError("box-buck left pin " + name + ": no clear islet escape");
}

std::vector<ChainPtr> feedback_chains(const Engine& e, const std::string& feedback, const std::string& out) {
    std::vector<ChainPtr> result;
    for (const auto& ch : e.float_chains)
        if (ch->kind == "trunk" && ch->root == feedback && ch->legs.size() == 2 && ch->legs.back().b == out)
            result.push_back(ch);
    return result;
}

void fb_left_network(Engine& e, Point p_fb, const std::string& fb_net, const std::string& out) {
    const double x = gfloor(p_fb.first - e.sp.port_run - 4 * U), top = r3(p_fb.second - 4 * U);
    e.power(out, x, top, e._power_rot(out, false));
    const auto pulls = take(e.pull, fb_net);
    const auto rt = first(pulls, "feedback " + fb_net).first;
    const auto mid = e._vertical_2pin(rt, x, top, out, true).first.second;
    const auto rb = first(take(e.hang, fb_net), "feedback " + fb_net);
    const auto [foot, far] = e._vertical_2pin(rb, x, mid, fb_net, true);
    e.power(far, foot.first, foot.second, e._power_rot(far, true));
    const double xv = r3(p_fb.first - 2 * U);
    e.pl.plan(fb_net, {p_fb, {xv, p_fb.second}, {xv, mid}, {x, mid}});
    double column = gfloor(x - e.sp.cap_pitch);
    for (std::size_t i = 1; i < pulls.size(); ++i) {
        e.power(out, column, top, e._power_rot(out, false));
        const auto ff = e._vertical_2pin(pulls[i].first, column, top, out, true).first;
        e.pl.plan(fb_net, {{x, mid}, {column, mid}, {column, ff.second}});
        column = gfloor(column - e.sp.cap_pitch);
    }
    for (const auto& ch : feedback_chains(e, fb_net, out)) {
        const auto& rff = ch->legs[0]; const auto& cff = ch->legs[1];
        constexpr double half = 3.81;
        const double xr = column;
        e._horizontal_2pin(rff.ref, xr, mid, rff.b);
        e.pl.plan(fb_net, {{x, mid}, {xr + half, mid}});
        const double xf = gfloor(xr - e.sp.cap_pitch);
        e.power(out, xf, top, e._power_rot(out, false));
        const auto ff = e._vertical_2pin(cff.ref, xf, top, out, true).first;
        const double jog = gsnap((xr - half + xf) / 2);
        e.pl.plan(rff.b, {{xr - half, mid}, {jog, mid}, {jog, ff.second}, {xf, ff.second}});
        erase_chain(e, ch); column = gfloor(xf - e.sp.cap_pitch);
    }
}

}  // namespace

void Engine::_box_right_pin_islet(const std::string& name, Point pt) { box_right_pin_islet(*this, name, pt); }
void Engine::_box_left_pin_islet(const std::string& name, Point pt, const VisualBox& body) {
    box_left_pin_islet(*this, name, pt, body);
}
void Engine::_fb_left_network(const std::string&, const Stage&, Point pt,
        const std::string& feedback, const std::string& out) {
    fb_left_network(*this, pt, feedback, out);
}

SchematicPlacement Engine::_regulator_template(StageMap stages) {
    OrderedMap<std::string> produced, consumed;
    for (const auto& [ref, stage] : stages) produced[stage.out] = ref;
    for (const auto& ref : multi) {
        if (!stages.contains(ref)) continue;
        for (const auto& p : lib.get(part(ref).lib_id).pins) {
            const auto* n = net_of(ref, p.number);
            if (n && n->net_class == "power" && n->name.rfind("GND", 0) != 0 && n->name != stages.at(ref).out &&
                !consumed.contains(n->name)) consumed[n->name] = ref;
        }
    }
    RefMap in_caps, out_caps;
    // Snapshot key order before erasing; OrderedMap references invalidate.
    Refs assigned;
    for (const auto& [name, caps] : cluster) {
        const bool prod = produced.contains(name), cons = consumed.contains(name);
        if (prod && cons) {
            const auto split = (caps.size() + 1) / 2;
            out_caps[name] = Refs(caps.begin(), caps.begin() + static_cast<std::ptrdiff_t>(split));
            in_caps[name] = Refs(caps.begin() + static_cast<std::ptrdiff_t>(split), caps.end());
        } else if (prod) out_caps[name] = caps;
        else if (cons) in_caps[name] = caps;
        else continue;
        assigned.push_back(name);
    }
    for (const auto& name : assigned) cluster.erase(name);
    std::set<std::string> available;
    for (const auto& [name, _] : consumed) if (!produced.contains(name)) available.insert(name);
    Refs pool, order, auxiliary;
    for (const auto& ref : multi) (stages.contains(ref) ? pool : auxiliary).push_back(ref);
    // Resolve the same immutable input-rail property once per stage, rather
    // than rescan symbol pins on every dependency-order pass.
    std::map<std::string, std::optional<std::string>> inputs;
    for (const auto& ref : pool) inputs.emplace(ref, stage_in_rail(*this, ref));
    while (!pool.empty()) {
        auto it = std::find_if(pool.begin(), pool.end(), [&](const auto& ref) {
            const auto& input = inputs.at(ref); return !input || available.count(*input);
        });
        if (it != pool.end()) { order.push_back(*it); available.insert(stages.at(*it).out); pool.erase(it); }
        else { order.push_back(pool.front()); pool.erase(pool.begin()); } // Cycles retain Python fallback ordering.
    }
    std::set<std::string> boxes;
    for (const auto& [ref, stage] : stages)
        if (stage.kind == "buck" && !stage_has_left_input(*this, ref)) boxes.insert(ref);
    _n_box_bucks = boxes.size();
    double ay = 0;
    for (std::size_t i = 0; i < order.size(); ++i) {
        const auto& ref = order[i];
        _stage_row(ref, stages.at(ref), ay, in_caps, out_caps);
        ay = gceil(_extent().y1 + (boxes.count(ref) && i + 1 < order.size() ? 28 * U : 10 * U));
    }
    Handled handled;
    for (const auto& ref : auxiliary) {
        const auto& symbol = lib.get(part(ref).lib_id);
        double reach = 0;
        for (const auto& p : symbol.pins) {
            if (p.rotation != 270) continue;
            const auto* n = net_of(ref, p.number);
            if (!n) continue;
            for (const auto& ch : float_chains) if (ch->kind == "pin" && ch->root == n->name)
                reach = std::max(reach, static_cast<double>(ch->legs.size()) * 7.62 + 10 * U - p.y - symbol.body[3]);
        }
        const auto body = body_box_page(symbol, 0, 0, get(orient, ref), "body", ref);
        const auto extent = _extent();
        const double y = gceil(std::max(ay + reach, extent.y1 + 4 * U - body.y0));
        double pending = (!pull.empty() || !hang.empty()) ? 24 * U : 0;
        if (!float_chains.empty()) pending += 24 * U;
        TrunkMap jobs;
        if (y + body.y1 - extent.y0 > PAPER_H_BUDGET - pending && extent.x1 > extent.x0)
            _cell(ref, gceil(extent.x1 + _side_reach(ref, "left") + 4 * U), gceil(extent.y0 - body.y0), handled, jobs);
        else _cell(ref, 0, y, handled, jobs);
        ay = gceil(_extent().y1 + 10 * U);
    }
    _leftover_chains_columns(); _port_strap_columns(); _pull_rank_columns();
    if (!cluster.empty()) {
        const auto first_stage = std::find_if(multi.begin(), multi.end(), [&](const auto& ref) { return stages.contains(ref); });
        if (first_stage != multi.end()) {
            const auto first_part = std::find_if(pl.parts.begin(), pl.parts.end(), [&](const auto& p) { return p.ref == *first_stage; });
            if (first_part == pl.parts.end()) throw SchematicPlaceError("regulator template: stage was not placed: " + *first_stage);
            const auto body = body_box_page(lib.get(first_part->lib_id), first_part->x, first_part->y,
                first_part->rotation, "body", *first_stage);
            // Copy coordinates before the cluster appends to pl.parts.
            const double x = first_part->x, y = first_part->y;
            _decoupling_cluster(x, y, body);
        }
    }
    if (!cluster.empty()) throw SchematicPlaceError("regulator template: unassigned decoupling caps " + refmap_repr(cluster));
    _flags_row(); return pl;
}

void Engine::_buck_box_stage(const std::string& ref, const Stage& stage, double ay, RefMap& in_caps, RefMap& out_caps) {
    const auto input = stage_in_rail_box(*this, ref);
    const auto placed = _place_body(ref, 0, ay);
    const auto& symbol = *placed.symbol;
    const auto pins = positions(symbol, ay);
    std::vector<PinAt> top;
    for (const auto& p : symbol.pins) if (p.rotation == 270) top.push_back({&p, pins.at(p.number)});
    std::stable_sort(top.begin(), top.end(), [](const auto& a, const auto& b) { return a.point.first < b.point.first; });
    std::vector<Point> inputs;
    for (const auto& p : top) {
        const auto* n = net_of(ref, p.pin->number);
        if (n && n->name == input) inputs.push_back(p.point);
    }
    if (inputs.size() > 1) _rail_bus(input, inputs, "top");
    else if (!inputs.empty()) _rail_stub(input, inputs.front(), "top");
    for (const auto& p : top) {
        const auto* n = net_of(ref, p.pin->number);
        if (!n) { pl.no_connects.push_back({p.point.first, p.point.second}); continue; }
        if (n->name == input || rail(*n)) continue;
        if (const auto chain = _local_drop_chain(n->name, ref)) {
            const auto side = !inputs.empty() && p.point.first < inputs.front().first ? "left" : "right";
            _stack_from_pin(*chain, p.point, "top", side);
            for (const auto& leg : chain->legs) { (void)leg; hang.erase(n->name); pull.erase(n->name); }
        } else _signal_islet_drop(n->name, p.point, "top");
    }
    const auto caps = take(in_caps, input);
    if (!caps.empty()) {
        auto& target = cluster[input]; target.insert(target.end(), caps.begin(), caps.end());
    }
    OrderedMap<std::vector<Point>> grounds;
    for (const auto& p : symbol.pins) if (p.rotation == 90) {
        const auto* n = net_of(ref, p.number);
        const auto& pt = pins.at(p.number);
        if (!n) pl.no_connects.push_back({pt.first, pt.second});
        else if (n->net_class == "ground") grounds[n->name].push_back(pt);
    }
    for (const auto& [name, points] : grounds) {
        auto sorted = points;
        std::stable_sort(sorted.begin(), sorted.end(), [](const auto& a, const auto& b) { return a.first < b.first; });
        if (sorted.size() > 1) _rail_bus(name, sorted, "bottom"); else _rail_stub(name, sorted.front(), "bottom");
    }
    const auto feedback = stage_fb_net(*this, ref, stage);
    _buck_right(ref, stage, ay, pins, symbol, out_caps);
    for (const auto& p : symbol.pins) if (p.rotation == 180) {
        const auto* n = net_of(ref, p.number);
        if (!n || (feedback && n->name == *feedback)) continue;
        const auto pt = pins.at(p.number);
        if (n->net_class == "port") {
            const double x = r3(pt.first + sp.port_run);
            pl.plan(n->name, {pt, {x, pt.second}});
            label(n->name, x, pt.second, 0, p.etype == "input" || p.etype == "output" ? p.etype : "bidirectional");
        } else if (n->net_class == "signal" && (pull.contains(n->name) || hang.contains(n->name)))
            box_right_pin_islet(*this, n->name, pt);
    }
    std::vector<PinAt> left;
    for (const auto& p : symbol.pins) if (p.rotation == 0) left.push_back({&p, pins.at(p.number)});
    std::stable_sort(left.begin(), left.end(), [](const auto& a, const auto& b) { return a.point.second > b.point.second; });
    for (const auto& p : left) {
        const auto* n = net_of(ref, p.pin->number);
        if (!n) { pl.no_connects.push_back({p.point.first, p.point.second}); continue; }
        if (feedback && n->name == *feedback) continue;
        box_left_pin_islet(*this, n->name, p.point, placed.body);
    }
    _part_texts(placed.part_index, placed.body);
}

void Engine::_stage_row(const std::string& ref, const Stage& stage, double ay, RefMap& in_caps, RefMap& out_caps) {
    if (stage.kind == "buck" && !stage_has_left_input(*this, ref)) {
        _buck_box_stage(ref, stage, ay, in_caps, out_caps); return;
    }
    const auto placed = _place_body(ref, 0, ay);
    const auto& symbol = *placed.symbol;
    const auto pins = positions(symbol, ay);
    using NamedPoint = std::pair<Point, std::string>;
    std::optional<NamedPoint> input, ground, uvlo;
    std::optional<std::tuple<Point, std::string, std::string>> enable;
    std::vector<NamedPoint> auxiliary, biased;
    std::vector<Point> grounds;
    const auto input_rail = stage_in_rail(*this, ref);
    for (const auto& p : symbol.pins) {
        const auto* n = net_of(ref, p.number);
        if (!n) continue;
        const auto pt = pins.at(p.number);
        if (p.rotation == 0 && p.etype == "power_in" && n->net_class == "power") input = {pt, n->name};
        else if (p.rotation == 0 && n->net_class == "port") enable = {pt, n->name, p.etype};
        else if (p.rotation == 0 && p.etype == "power_out" && n->net_class == "signal" && _local_drop_chain(n->name, ref))
            auxiliary.emplace_back(pt, n->name);
        else if (p.rotation == 0 && n->net_class == "signal" && get(pull, n->name).size() == 1 &&
            get(hang, n->name).size() == 1 && (!input_rail || get(pull, n->name).front().second != *input_rail))
            biased.emplace_back(pt, n->name);
        else if (p.rotation == 0 && n->net_class == "signal" && pull.contains(n->name) && hang.contains(n->name)) uvlo = {pt, n->name};
        else if (p.rotation == 90 && n->net_class == "ground") { ground = {pt, n->name}; grounds.push_back(pt); }
    }
    if (!input || !ground) throw SchematicPlaceError(ref + ": regulator stage without VIN/GND pins");
    if (enable) {
        const auto& [pt, name, type] = *enable;
        const double x = pt.first - sp.port_run;
        pl.plan(name, {pt, {x, pt.second}}); label(name, x, pt.second, 180, type == "input" ? "input" : "bidirectional");
    }
    const auto [pv, in_rail] = *input;
    std::vector<std::pair<double, Point>> straps;
    for (const auto& p : symbol.pins) {
        const auto* n = net_of(ref, p.number);
        if (!n || n->name != in_rail || p.rotation != 0 || pins.at(p.number) == pv) continue;
        straps.emplace_back(r3(pv.first - 2 * U * static_cast<double>(straps.size() + 1)), pins.at(p.number));
    }
    const auto caps = take(in_caps, in_rail);
    std::vector<double> columns;
    for (std::size_t i = 0; i < caps.size(); ++i) columns.push_back(gfloor(pv.first - sp.cluster_dx + static_cast<double>(i) * -sp.cap_pitch));
    std::optional<double> uvlo_column;
    Refs uvlo_ground;
    if (uvlo) {
        const auto& [r, name] = first(get(pull, uvlo->second), "UVLO " + uvlo->second);
        if (name != in_rail) throw SchematicPlaceError(ref + ": EN-UVLO top " + r + " sits on " + quoted(name) +
            ", not the input rail " + quoted(in_rail) + " — unhandled topology, extend the engine");
        uvlo_ground = get(hang, uvlo->second); std::sort(uvlo_ground.begin(), uvlo_ground.end());
        uvlo_column = gfloor(pv.first - sp.cluster_dx + static_cast<double>(caps.size()) * -sp.cap_pitch);
        columns.push_back(*uvlo_column);
    }
    auto nodes = columns; nodes.insert(nodes.begin(), pv.first);
    for (const auto& [x, _] : straps) nodes.push_back(x);
    horizontal(pl, in_rail, std::move(nodes), pv.second);
    for (const auto& [x, pt] : straps) pl.plan(in_rail, {{x, pv.second}, {x, pt.second}, pt});
    const double rail_x = columns.empty() ? pv.first : columns.back();
    pl.plan(in_rail, {{rail_x, pv.second}, {rail_x, pv.second - 5.08}}); power(in_rail, rail_x, pv.second - 5.08);
    for (std::size_t i = 0; i < caps.size(); ++i) {
        const auto [pt, far] = _vertical_2pin(caps[i], columns[i], pv.second, in_rail, true); power(far, pt.first, pt.second);
    }
    if (uvlo && uvlo_column) {
        const auto [pe, name] = *uvlo;
        const auto rt = first(take(pull, name), "UVLO " + name).first;
        const double mid = _vertical_2pin(rt, *uvlo_column, pv.second, in_rail, true).first.second;
        hang.erase(name);
        const double xv = r3(pe.first - 2.54);
        double floor = mid;
        for (const auto& b : pl.boxes) if (b.kind == "body" && b.owner.rfind("#PWR", 0) == 0 &&
            *uvlo_column < b.x0 && b.x1 < xv && b.y0 > pv.second) floor = std::max(floor, b.y1);
        const double tie = floor <= mid ? mid : gceil(floor + 2 * U);
        if (tie > mid) pl.plan(name, {{*uvlo_column, mid}, {*uvlo_column, tie}});
        std::vector<double> mid_xs{*uvlo_column};
        for (std::size_t i = 0; i < uvlo_ground.size(); ++i) {
            const double x = i == 0 ? *uvlo_column : gfloor(*uvlo_column - (static_cast<double>(i) * sp.cap_pitch));
            if (i) mid_xs.push_back(x);
            const auto [pt, far] = _vertical_2pin(uvlo_ground[i], x, tie, name, true); power(far, pt.first, pt.second);
        }
        mid_xs.push_back(xv); horizontal(pl, name, std::move(mid_xs), tie);
        pl.plan(name, {pe, {xv, pe.second}, {xv, tie}});
    }
    for (const auto& pt : unique_sorted(grounds)) power(ground->second, pt.first, pt.second);
    const auto by_y = [](const auto& a, const auto& b) { return a.first.second < b.first.second; };
    std::stable_sort(auxiliary.begin(), auxiliary.end(), by_y);
    for (std::size_t rank = 0; rank < auxiliary.size(); ++rank) {
        const auto& [pt, name] = auxiliary[rank];
        const auto r = hang.contains(name) ? first(hang.at(name), "auxiliary " + name) : first(get(pull, name), "auxiliary " + name).first;
        const double x = gfloor(pt.first - sp.cluster_dx - static_cast<double>(auxiliary.size() - 1 - rank) * sp.cap_pitch);
        const auto [foot, far] = _vertical_2pin(r, x, pt.second, name, true); power(far, foot.first, foot.second);
        hang.erase(name); pull.erase(name); pl.plan(name, {pt, {x, pt.second}});
    }
    std::stable_sort(biased.begin(), biased.end(), by_y);
    for (const auto& [pt, name] : biased) {
        double x = r3(pt.first - sp.port_run);
        for (const auto& b : pl.boxes) if (b.kind == "label" && b.x1 <= pt.first &&
            b.y0 - 2 * U <= pt.second && pt.second <= b.y1 + 2 * U) x = std::min(x, gfloor(b.x0 - 2 * U));
        pl.plan(name, {pt, {x, pt.second}}); llabel(name, x, pt.second, 180);
    }
    for (const auto& p : symbol.pins) if (!net_of(ref, p.number) && p.etype != "no_connect") {
        const auto& pt = pins.at(p.number); pl.no_connects.push_back({pt.first, pt.second});
    }
    if (stage.kind == "buck") _buck_right(ref, stage, ay, pins, symbol, out_caps);
    else _ldo_right(ref, stage, ay, pins, symbol, out_caps);
    _part_texts(placed.part_index, placed.body);
}

void Engine::_buck_right(const std::string& ref, const Stage& stage, double ay,
        const PinPositions&, const SymbolDef& symbol, RefMap& out_caps) {
    const auto& sw = stage.sw; const auto& out = stage.out;
    std::optional<Point> p_sw, p_boot, p_fb;
    std::optional<std::string> boot_net, fb_net, boot_cap;
    bool fb_left = false;
    for (const auto& p : symbol.pins) {
        if (p.rotation != 0 && p.rotation != 180) continue;
        const auto* n = net_of(ref, p.number);
        if (!n) continue;
        if (n->name == sw && p.rotation == 180) p_sw = pin_page_position(p, 0, ay, 0);
        else if (n->net_class == "signal") {
            const auto boot = std::find_if(series.begin(), series.end(), [&](const auto& leg) {
                return (n->name == leg.a || n->name == leg.b) && (sw == leg.a || sw == leg.b);
            });
            if (boot != series.end() && p.rotation == 180) {
                p_boot = pin_page_position(p, 0, ay, 0); boot_net = n->name; boot_cap = boot->ref;
            } else if ((pull.contains(n->name) || hang.contains(n->name)) && (!boot_net || n->name != *boot_net) &&
                is_fb_pin(*this, p, n->name, out) && !p_fb) {
                p_fb = pin_page_position(p, 0, ay, 0); fb_net = n->name; fb_left = p.rotation == 0;
            }
        }
    }
    if (!p_sw) throw SchematicPlaceError(ref + ": buck stage without SW pin");
    const double x0 = p_sw->first, y = p_sw->second, xl = r3(x0 + 26.67);
    double slot = gceil(xl + 9 * U);
    std::vector<Point> extra;
    for (const auto& p : symbol.pins) if (p.rotation == 180 && p_boot) {
        const auto* n = net_of(ref, p.number);
        if (n && n->name == *boot_net) {
            const auto pt = pin_page_position(p, 0, ay, 0); if (pt != *p_boot) extra.push_back(pt);
        }
    }
    if (p_boot && boot_cap) {
        const double xv = r3(x0 + 2.54), xc = r3(x0 + 10.16), xj = r3(x0 + 20.32);
        std::vector<Point> boots{*p_boot}; boots.insert(boots.end(), extra.begin(), extra.end());
        double low = p_boot->second, high = low;
        for (const auto& pt : extra) { low = std::min(low, pt.second); high = std::max(high, pt.second); }
        const bool above = low > y + 1e-6;
        const double yb = r3(above ? high + 5.08 : low - 5.08), riser = above ? low : high;
        for (const auto& pt : boots) pl.plan(*boot_net, {pt, {xv, pt.second}});
        pl.plan(*boot_net, {{xv, riser}, {xv, yb}, {xc - 3.81, yb}});
        _horizontal_2pin(*boot_cap, xc, yb, *boot_net);
        pl.plan(sw, {{xc + 3.81, yb}, {xj, yb}, {xj, y}});
        series.erase(std::remove_if(series.begin(), series.end(), [&](const auto& leg) { return leg.ref == *boot_cap; }), series.end());
        pl.plan(sw, {*p_sw, {xj, y}}); pl.plan(sw, {{xj, y}, {x0 + 26.67 - 3.81, y}});
    } else pl.plan(sw, {*p_sw, {x0 + 26.67 - 3.81, y}});
    _horizontal_2pin(stage.inductor, xl, y, sw);
    if (pull.contains(sw)) {
        auto& list = pull.at(sw);
        if (!list.empty()) {
            const auto it = std::find(list.begin(), list.end(), std::pair{stage.inductor, out});
            if (it == list.end()) throw SchematicPlaceError(ref + ": inductor is absent from switching-node pull list");
            list.erase(it);
        }
        if (list.empty()) pull.erase(sw);
    }
    std::vector<double> nodes{r3(xl + 3.81)};
    for (const auto& cap : take(out_caps, out)) {
        nodes.push_back(slot);
        const auto [pt, far] = _vertical_2pin(cap, slot, y, out, true); power(far, pt.first, pt.second);
        slot = gceil(slot + sp.cap_pitch);
    }
    if (p_fb && fb_net && fb_left) { fb_left_network(*this, *p_fb, *fb_net, out); p_fb.reset(); }
    if (p_fb && fb_net) {
        const auto& name = *fb_net;
        const double divider = slot; slot = gceil(slot + sp.cap_pitch); nodes.push_back(divider);
        pl.plan(out, {{divider, y}, {divider, y + 5.08}});
        const auto pulls = take(pull, name);
        const auto rt = first(pulls, "feedback " + name).first;
        const double mid = _vertical_2pin(rt, divider, y + 5.08, out, true).first.second;
        const auto rb = first(take(hang, name), "feedback " + name);
        const auto [foot, far] = _vertical_2pin(rb, divider, mid, name, true); power(far, foot.first, foot.second);
        const double xv = r3(x0 + 2.54);
        pl.plan(name, {*p_fb, {xv, p_fb->second}, {xv, mid}, {divider, mid}});
        for (std::size_t i = 1; i < pulls.size(); ++i) {
            const double x = slot; nodes.push_back(x); slot = gceil(slot + sp.cap_pitch);
            pl.plan(out, {{x, y}, {x, y + 5.08}});
            const auto pt = _vertical_2pin(pulls[i].first, x, y + 5.08, out, true).first;
            pl.plan(name, {{divider, mid}, {x, mid}, {x, pt.second}});
        }
        for (const auto& ch : feedback_chains(*this, name, out)) {
            const auto& rff = ch->legs[0]; const auto& cff = ch->legs[1];
            constexpr double half = 3.81;
            const double xr = slot; nodes.push_back(xr);
            _horizontal_2pin(rff.ref, xr, mid, name); pl.plan(name, {{divider, mid}, {xr - half, mid}});
            const double xf = gceil(xr + sp.cap_pitch); nodes.push_back(xf); slot = gceil(xf + sp.cap_pitch);
            pl.plan(out, {{xf, y}, {xf, y + 5.08}});
            const auto pt = _vertical_2pin(cff.ref, xf, y + 5.08, out, true).first;
            const double jog = gsnap((xr + half + xf) / 2);
            pl.plan(rff.b, {{xr + half, mid}, {jog, mid}, {jog, pt.second}, {xf, pt.second}});
            erase_chain(*this, ch);
        }
    }
    std::vector<ChainPtr> chains;
    for (const auto& ch : float_chains) if (ch->kind == "rail" && ch->root == out) chains.push_back(ch);
    for (const auto& ch : chains) {
        nodes.push_back(slot); Point current{slot, y}; std::string current_net = out;
        for (const auto& leg : ch->legs) {
            const auto& near = leg.a == current_net ? leg.a : leg.b;
            std::tie(current, current_net) = _vertical_2pin(leg.ref, slot, current.second, near, true);
        }
        if (rail(net(current_net))) power(current_net, current.first, current.second);
        erase_chain(*this, ch); slot = gceil(slot + sp.cap_pitch);
    }
    const double right = gsnap(slot - sp.cap_pitch / 2); nodes.push_back(right);
    horizontal(pl, out, std::move(nodes), y);
    pl.plan(out, {{right, y}, {right, y - 5.08}}); power(out, right, y - 5.08);
}

void Engine::_ldo_right(const std::string& ref, const Stage& stage, double ay,
        const PinPositions&, const SymbolDef& symbol, RefMap& out_caps) {
    std::optional<Point> output;
    for (const auto& pin : symbol.pins) if (pin.rotation == 180 && pin.etype == "power_out") output = pin_page_position(pin, 0, ay, 0);
    if (!output) throw SchematicPlaceError(ref + ": LDO stage without right-facing power output pin");
    const double y = output->second;
    double slot = gceil(output->first + 2 * U + 5.08);
    std::vector<double> nodes{output->first};
    for (const auto& cap : take(out_caps, stage.out)) {
        nodes.push_back(slot);
        const auto [pt, far] = _vertical_2pin(cap, slot, y, stage.out, true); power(far, pt.first, pt.second);
        slot = gceil(slot + sp.cap_pitch);
    }
    const double right = gsnap(slot - sp.cap_pitch / 2); nodes.push_back(right);
    horizontal(pl, stage.out, std::move(nodes), y);
    pl.plan(stage.out, {{right, y}, {right, y - 5.08}}); power(stage.out, right, y - 5.08);
}

}  // namespace schgen::schematic_place
