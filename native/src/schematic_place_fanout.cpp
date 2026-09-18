#include "schematic_place_internal.hpp"

#include "schgen/occupancy.hpp"
#include "schgen/place_search.hpp"
#include "schgen/turn.hpp"

#include <charconv>
#include <cmath>
#include <limits>

#if defined(__clang__)
#pragma clang fp contract(off)
#endif

namespace schgen::schematic_place {
namespace {
bool rail(const CircuitNetIr& n) { return n.net_class == "power" || n.net_class == "ground"; }
bool signal(const CircuitNetIr& n) { return n.net_class == "signal" || n.net_class == "port"; }
bool has(const Refs& refs, const std::string& ref) { return std::find(refs.begin(), refs.end(), ref) != refs.end(); }
bool touches(const Leg& leg, const std::string& name) { return leg.a == name || leg.b == name; }
template <typename T> T get(const OrderedMap<T>& map, const std::string& key) {
    const auto it = map.find(key);
    return it == map.end() ? T{} : it->second;
}
template <typename T> T take(OrderedMap<T>& map, const std::string& key) {
    auto result = get(map, key); map.erase(key); return result;
}
void require(bool value, const std::string& message) {
    if (!value) throw SchematicPlaceError(message);
}
const CircuitNetIr& required_net(const CircuitNetIr* value, const std::string& ref) {
    if (!value) throw SchematicPlaceError(ref + ": expected a connected pin");
    return *value;
}
std::string number_text(double value) {
    char buffer[512];
    const double magnitude = std::fabs(value);
    const auto format = magnitude == 0 || (magnitude >= 1e-4 && magnitude < 1e16)
        ? std::chars_format::fixed : std::chars_format::scientific;
    const auto result = std::to_chars(buffer, buffer + sizeof(buffer), value, format);
    require(result.ec == std::errc{}, "cannot format placement coordinate");
    std::string out(buffer, result.ptr);
    if (out.find_first_of(".e") == std::string::npos) out += ".0";
    return out;
}
std::string point_text(Point p) { return "(" + number_text(p.first) + ", " + number_text(p.second) + ")"; }
VisualBox visual(const Box4& b, const std::string& kind, const std::string& owner) {
    return {b.x0, b.y0, b.x1, b.y1, kind, owner};
}
std::vector<std::string> attachments(const Line& line) {
    if (line.attach) return {*line.attach};
    if (line.attach_div) return {line.attach_div->first, line.attach_div->second};
    return {};
}
std::string label_shape(const std::string& etype) {
    if (etype == "input" || etype == "output" || etype == "tri_state") return etype;
    if (etype == "open_collector" || etype == "open_emitter") return "output";
    return "bidirectional";
}
}  // namespace

std::pair<Point, std::string> Engine::_vertical_2pin(const std::string& ref, double x, double y,
        const std::string& attach_net, bool downward, const std::string& text_side) {
    const auto& symbol = lib.get(part(ref).lib_id);
    const auto attached = _pin_of_net(ref, attach_net);
    const auto& far = required_net(net_of(ref, other_pin(ref, attached)), ref);
    const auto& p = pin(symbol, attached);
    double off;
    int rot;
    if (std::fabs(p.y) > 1e-6) {
        off = std::fabs(p.y);
        const bool up = p.y > 0;
        rot = downward ? (up ? 0 : 180) : (up ? 180 : 0);
    } else {
        off = std::fabs(p.x);
        const bool right = p.x > 0;
        rot = downward ? (right ? 90 : 270) : (right ? 270 : 90);
    }
    const double anchor_y = downward ? y + off : y - off;
    passive(ref, x, anchor_y, rot, text_side);
    return {{x, py_round(downward ? anchor_y + off : anchor_y - off, 3)}, far.name};
}
void Engine::_horizontal_2pin(const std::string& ref, double x, double y,
        const std::string& left_net, const std::string& text_side) {
    const auto& p = pin(lib.get(part(ref).lib_id), _pin_of_net(ref, left_net));
    const int rot = std::fabs(p.y) > 1e-6 ? (p.y > 0 ? 90 : 270) : (p.x < 0 ? 0 : 180);
    passive(ref, x, y, rot, text_side);
}
PlacedBody Engine::_place_body(const std::string& ref, double ax, double ay) {
    const auto& p = part(ref);
    const int rot = get(orient, ref);
    const auto& symbol = lib.get(p.lib_id);
    const auto body = body_box_page(symbol, ax, ay, rot, "body", ref);
    const std::size_t index = pl.parts.size();
    pl.parts.push_back({ref, p.lib_id, p.value, ax, ay, rot, p.footprint, std::nullopt, std::nullopt});
    pl.boxes.push_back(body);
    const auto text = pin_text_boxes(symbol, pl.parts[index]);
    pl.boxes.insert(pl.boxes.end(), text.begin(), text.end());
    OrderedMap<std::vector<PinAt>> sides;
    for (const std::string side : {"left", "right", "top", "bottom"}) sides[side] = {};
    std::set<Point> seen;
    for (const auto& ppin : symbol.pins) {
        if (ppin.hidden) continue;
        const auto pt = pin_page_position(ppin, ax, ay, rot);
        if (!seen.insert(pt).second) continue;
        sides[side_of_rotation(ppin.rotation + rot)].push_back({&ppin, pt});
    }
    _done.insert(ref);
    return {index, &symbol, body, std::move(sides)};
}
void Engine::_part_texts(std::size_t index, const VisualBox& body) {
    require(index < pl.parts.size(), "part text index is out of range");
    auto& placed = pl.parts[index];
    for (const std::string kind : {"reference", "value"}) {
        const auto& text = kind == "reference" ? placed.ref : placed.value;
        const double width = text_wh(text).first;
        const double above = body.y0 - 1.905, below = body.y1 + 2.03, ax = placed.x;
        const std::vector<double> xs{body.x1 - 2.54, ax + 7.62, body.x0 + 2.54,
                                    ax, ax - 7.62, ax + 12.7, ax - 12.7};
        std::vector<Point> candidates;
        for (int side = 0; side < 2; ++side) {
            const bool up = kind == "reference" ? side == 0 : side == 1;
            for (int row = 0; row < 6; ++row)
                for (const auto x : xs) candidates.emplace_back(x, up ? above - row * 2.54 : below + row * 2.54);
        }
        for (int row = 0; row < 3; ++row) {
            candidates.emplace_back(body.x1 + 0.8 + width / 2, placed.y + row * 2.54);
            candidates.emplace_back(body.x0 - 0.8 - width / 2, placed.y + row * 2.54);
        }
        Point position{ax, below + 18 * 2.54};
        for (const auto& candidate : candidates)
            if (_spot_free(centered_box(text, candidate.first, candidate.second))) { position = candidate; break; }
        const SchematicTextPosition pos{position.first, position.second, 0};
        if (kind == "reference") placed.ref_pos = pos;
        else placed.val_pos = pos;
        pl.boxes.push_back(visual(centered_box(text, pos.x, pos.y), kind, placed.ref));
    }
}
void Engine::_bridge(const std::string& name) { pl.label_bridged.insert(name); }
bool Engine::_net_shared(const std::string& name, const std::string& ref) const {
    for (const auto& p : net(name).pins) if (p.ref != ref && has(multi, p.ref)) return true;
    return false;
}
std::optional<Leg> Engine::_series_of(const std::string& name) const {
    std::optional<Leg> result;
    for (const auto& leg : series) if (touches(leg, name)) {
        if (result) return std::nullopt;
        result = leg;
    }
    if (!result) return std::nullopt;
    const auto& far = result->a == name ? result->b : result->a;
    if (trunks.contains(far) || (!multi_nets.count(far) && net(far).net_class != "port")) return std::nullopt;
    return result;
}
std::pair<double, Box4> Engine::_series_inline(const Leg& leg, const std::string& name,
        Point tap, int sign, std::optional<Box4> avoid) {
    // Callers may pass a series-vector element; removing it later invalidates it.
    const Leg item = leg;
    const auto& far = item.a == name ? item.b : item.a;
    const auto& near = pin(lib.get(part(item.ref).lib_id), _pin_of_net(item.ref, name));
    const double off = std::fabs(near.y) > 1e-6 ? std::fabs(near.y) : std::fabs(near.x);
    double shift = 0;
    if (avoid && std::fabs(tap.second - (avoid->y0 + avoid->y1) / 2) < GLABEL_H * TEXT_SIZE + 1.0) {
        const double len = net(far).net_class == "port" ? _glabel_len(far) : text_wh(far).first + 0.7;
        const double lx0 = tap.first + sign * (2 * U + 2 * off + 2 * U);
        const double b0 = sign < 0 ? lx0 - len : lx0, b1 = sign < 0 ? lx0 : lx0 + len;
        if (b0 - 0.5 < avoid->x1 && b1 + 0.5 > avoid->x0) {
            const double want = (sign < 0 ? avoid->x0 : avoid->x1) + sign * (sp.stagger_extra + sp.label_tap_gap);
            shift = gceil(std::max(0.0, (want - lx0) * sign));
        }
    }
    const double ax = tap.first + sign * (2 * U + shift + off);
    _horizontal_2pin(item.ref, ax, tap.second, sign < 0 ? far : name, sign < 0 ? "right" : "left");
    const Point near_tip{py_round(tap.first + sign * 2 * U, 3), tap.second};
    const Point far_tip{py_round(ax + sign * off, 3), tap.second};
    pl.plan(name, {tap, near_tip});
    const double lx = py_round(far_tip.first + sign * 2 * U, 3);
    pl.plan(far, {far_tip, {lx, tap.second}});
    const int rot = sign < 0 ? 180 : 0;
    Box4 box;
    if (net(far).net_class == "port") {
        label(far, lx, tap.second, rot); box = glabel_box(far, lx, tap.second, rot);
    } else {
        llabel(far, lx, tap.second, rot); _bridge(far); box = llabel_box(far, lx, tap.second, rot);
    }
    const auto found = std::find_if(series.begin(), series.end(), [&](const Leg& s) {
        return s.ref == item.ref && s.a == item.a && s.b == item.b;
    });
    require(found != series.end(), item.ref + ": series leg no longer exists");
    series.erase(found);
    return {sign < 0 ? box.x0 : box.x1, box};
}
double Engine::_attach_halfw(const Line& line) {
    double width = 0;
    for (const auto& ref : attachments(line)) {
        const auto* far = net_of(ref, other_pin(ref, _pin_of_net(ref, line.net)));
        if (far) width = std::max(width, text_wh(far->name).first);
    }
    return width / 2 + 0.7;
}
std::pair<double, double> Engine::_attach_band(const Line& line) {
    const double base = _attach_halfw(line);
    double text_width = 0, half = 0;
    for (const auto& ref : attachments(line)) {
        const auto& p = part(ref);
        for (const auto v : lib.get(p.lib_id).body) half = std::max(half, std::fabs(v));
        text_width = std::max({text_width, text_wh(ref).first, text_wh(p.value).first});
    }
    return {std::max(base, half), std::max(base, half + 0.42 + text_width)};
}
double Engine::_attach_column(const Line& line, Point tap, double rank_y, bool downward) {
    require(line.attach.has_value(), line.net + ": attachment is missing");
    pl.plan(line.net, {tap, {tap.first, rank_y}});
    const auto [far_pt, far] = _vertical_2pin(*line.attach, tap.first, rank_y, line.net, downward);
    power(far, far_pt.first, far_pt.second, _power_rot(far, downward));
    return _attach_halfw(line);
}
double Engine::_divider(const Line& line, Point tap) {
    require(line.attach_div.has_value(), line.net + ": divider is missing");
    for (const auto& [ref, downward] : std::vector<std::pair<std::string, bool>>{
            {line.attach_div->first, false}, {line.attach_div->second, true}}) {
        const auto [far_pt, far] = _vertical_2pin(ref, tap.first, tap.second, line.net, downward);
        power(far, far_pt.first, far_pt.second, _power_rot(far, downward));
    }
    return _attach_halfw(line);
}
int Engine::_power_rot(const std::string& name, bool downward) const {
    return (net(name).net_class == "ground") == downward ? 0 : 180;
}
int Engine::_rail_rot(const std::string& name, const std::string& side) const {
    return (net(name).net_class == "ground") == (side == "bottom") ? 0 : 180;
}
void Engine::_rail_stub(const std::string& name, Point pt, const std::string& side) {
    const double dy = side == "top" ? -2.54 : 2.54;
    const auto& symbol = lib.get(_power_lib(name));
    const int rot = _rail_rot(name, side);
    for (const int k : {1, 2, 3, 4, 5, 6, 8})
        for (const double dx : {0.0, 5.08, -5.08, 10.16, -10.16, 15.24, -15.24, 20.32, -20.32, 25.4, -25.4}) {
            const Point end{py_round(pt.first + dx, 3), py_round(pt.second + dy * k, 3)};
            const auto vp = value_anchor(symbol, end.first, end.second, rot);
            const auto body = body_box_page(symbol, end.first, end.second, rot, "body", "?");
            const double lo = std::min(pt.second, end.second), hi = std::max(pt.second, end.second);
            bool ok = _spot_free(centered_box(name, vp.first, vp.second)) && _spot_free(body.bounds())
                && _vband_stem_free(pt.first, lo + 0.2, hi - 0.2, {name})
                && _spot_free({pt.first - 0.15, lo + 0.2, pt.first + 0.15, hi - 0.2}, 0.0);
            if (ok && dx != 0) ok = _spot_free({std::min(pt.first, end.first), end.second - 0.5,
                                               std::max(pt.first, end.first), end.second + 0.5}, 0.0);
            if (!ok) continue;
            if (dx == 0) pl.plan(name, {pt, end});
            else pl.plan(name, {pt, {pt.first, end.second}, end});
            power(name, end.first, end.second, rot);
            return;
        }
    throw SchematicPlaceError(name + ": no clear rail-stub spot off " + point_text(pt));
}
void Engine::_rail_bus(const std::string& name, const std::vector<Point>& points, const std::string& side) {
    require(!points.empty(), name + ": empty rail bus");
    const double y = py_round(points.front().second + (side == "top" ? -2.54 : 2.54), 3);
    std::vector<double> xs;
    for (const auto& p : points) { pl.plan(name, {p, {p.first, y}}); xs.push_back(p.first); }
    std::sort(xs.begin(), xs.end());
    for (std::size_t i = 1; i < xs.size(); ++i) pl.plan(name, {{xs[i - 1], y}, {xs[i], y}});
    power(name, xs[xs.size() / 2], y, _rail_rot(name, side));
}

bool Engine::_foreign_rows_clear(const Box4& box, const std::string& name, const std::set<double>& own) const {
    std::vector<double> foreign;
    for (const auto& [row, row_net] : _rail_row_net) if (row_net != name && !own.count(row)) foreign.push_back(row);
    for (const auto row : _sig_rows) if (!own.count(row)) foreign.push_back(row);
    return foreign_rows_clear(box, foreign, 1e-6);
}
void Engine::_fan_rail_run(const std::vector<RailPin>& run, int sign, const std::vector<Point>& rows) {
    require(!run.empty() && run.front().pin && run.front().net, "empty or invalid rail run");
    const auto& n = *run.front().net;
    const double jx = run.front().point.first + sign * std::max(3.81,
        gceil(text_wh(n.name).first / 2 + 0.7 - run.front().pin->length));
    const auto& symbol = lib.get(_power_lib(n.name));
    if (run.size() == 1) {
        const auto pt = run.front().point;
        bool above = false, below = false;
        for (const auto& p : rows) if (p != pt) {
            above |= p.second < pt.second - 1e-6; below |= p.second > pt.second + 1e-6;
        }
        double jxc = jx;
        if (above && below) {
            int rot = sign < 0 ? 90 : 270;
            auto body = body_box_page(symbol, jx, pt.second, rot, "body", "?");
            if ((sign < 0 && body.x1 > jx + 0.01) || (sign > 0 && body.x0 < jx - 0.01)) rot = (rot + 180) % 360;
            const double width = text_wh(n.name).first;
            double vx = 0;
            for (int k = 0; k < 40; ++k) {
                jxc = py_round(jx + sign * k * 2 * U, 3);
                body = body_box_page(symbol, jxc, pt.second, rot, "body", "?");
                vx = sign < 0 ? body.x0 - 0.42 - width / 2 : body.x1 + 0.42 + width / 2;
                if (_spot_free(body.bounds()) && _spot_free(centered_box(n.name, vx, pt.second))
                    && _corridor_free(pt.second, pt.first + sign * 0.01, jxc, {n.name})) break;
            }
            pl.plan(n.name, {pt, {jxc, pt.second}});
            _power_at(n.name, jxc, pt.second, rot, Point{vx, pt.second});
            return;
        }
        bool up = n.net_class == "power";
        if (up && above && !below) up = false;
        else if (!up && below && !above) up = true;
        const double dy = up ? -5.08 : 5.08;
        const int rot = (n.net_class == "ground") != up ? 0 : 180;
        Point end;
        for (int k = 0; k < 40; ++k) {
            jxc = py_round(jx + sign * k * 2 * U, 3);
            end = {jxc, pt.second + dy};
            const auto vp = value_anchor(symbol, end.first, end.second, rot);
            const auto body = body_box_page(symbol, end.first, end.second, rot, "body", "?");
            const double lo = std::min(pt.second, end.second), hi = std::max(pt.second, end.second);
            if (_spot_free(centered_box(n.name, vp.first, vp.second)) && _spot_free(body.bounds())
                && _spot_free({jxc - 0.1, lo + 0.2, jxc + 0.1, hi - 0.2}, 0.0)
                && _corridor_free(pt.second, pt.first + sign * 0.01, jxc, {n.name})) break;
        }
        pl.plan(n.name, {pt, {jxc, pt.second}, end});
        power(n.name, end.first, end.second, rot);
        return;
    }
    std::vector<double> ys;
    std::set<double> own;
    for (const auto& item : run) { ys.push_back(item.point.second); own.insert(py_round(item.point.second, 3)); }
    struct Candidate { bool clear; double end_y; int rotation; double x; };
    std::optional<Candidate> best, fallback;
    const bool ground = n.net_class == "ground";
    for (const bool top : {!ground, ground}) {
        const double end_y = top ? ys.front() : ys.back();
        const int rot = ground != top ? 0 : 180;
        bool seated = false;
        double jxc = jx;
        for (int k = 0; k < 40; ++k) {
            jxc = py_round(jx + sign * k * 2 * U, 3);
            const auto vp = value_anchor(symbol, jxc, end_y, rot);
            const auto vbox = centered_box(n.name, vp.first, vp.second);
            const auto body = body_box_page(symbol, jxc, end_y, rot, "body", "?").bounds();
            bool rows_clear = true;
            for (const auto row : _sig_rows)
                if (!own.count(row) && ((vbox.y0 - 1e-6 < row && row < vbox.y1 + 1e-6)
                                       || (body.y0 - 1e-6 < row && row < body.y1 + 1e-6))) rows_clear = false;
            bool ok = _spot_free(vbox) && _spot_free(body) && rows_clear
                && _spot_free({jxc - 0.1, ys.front() + 0.1, jxc + 0.1, ys.back() - 0.1}, 0.0);
            if (ok) for (const auto y : ys)
                if (!_corridor_free(y, run.front().point.first + sign * 0.01, jxc, {n.name})) { ok = false; break; }
            if (!ok) continue;
            const bool clear = _foreign_rows_clear(body, n.name, own) && _foreign_rows_clear(vbox, n.name, own);
            if (!best || (clear && !best->clear)) best = Candidate{clear, end_y, rot, jxc};
            seated = true; break;
        }
        if (!seated) fallback = Candidate{false, end_y, rot, jxc};
        if (best && best->clear) break;
    }
    // The original bounded search retains its last candidate on exhaustion;
    // downstream visual/routing gates still reject an obstructed placement.
    const auto choice = best ? *best : *fallback;
    for (const auto& item : run) pl.plan(n.name, {item.point, {choice.x, item.point.second}});
    for (std::size_t i = 1; i < ys.size(); ++i) pl.plan(n.name, {{choice.x, ys[i - 1]}, {choice.x, ys[i]}});
    power(n.name, choice.x, choice.end_y, choice.rotation);
}
void Engine::_fan_rail_comb(const std::string& name, const std::vector<Point>& input, int sign,
        std::size_t box_mark, const OrderedMap<std::size_t>& plan_marks) {
    require(!input.empty(), name + ": empty rail comb");
    auto points = input;
    std::stable_sort(points.begin(), points.end(), [](const auto& a, const auto& b) { return a.second < b.second; });
    std::set<double> unique;
    for (const auto& pt : points) unique.insert(pt.second);
    const std::vector<double> ys(unique.begin(), unique.end());
    const double y0 = ys.front() - 2 * U, y1 = ys.back() + 2 * U;
    double edge = points.front().first + sign * 4 * U;
    for (std::size_t i = box_mark; i < pl.boxes.size(); ++i) {
        const auto& box = pl.boxes[i];
        if (box.y0 < y1 && box.y1 > y0) edge = sign < 0 ? std::min(edge, box.x0) : std::max(edge, box.x1);
    }
    for (const auto& [plan_net, paths] : pl.plans)
        for (std::size_t i = get(plan_marks, plan_net); i < paths.size(); ++i)
            for (std::size_t j = 1; j < paths[i].size(); ++j) {
                const auto& a = paths[i][j - 1]; const auto& b = paths[i][j];
                if (std::min(a.second, b.second) < y1 && std::max(a.second, b.second) > y0)
                    edge = sign < 0 ? std::min({edge, a.first, b.first}) : std::max({edge, a.first, b.first});
            }
    const double bar_x = sign < 0 ? gfloor(edge - 2 * U) : gceil(edge + 2 * U);
    for (const auto& pt : points) pl.plan(name, {pt, {bar_x, pt.second}});
    for (std::size_t i = 1; i < ys.size(); ++i) pl.plan(name, {{bar_x, ys[i - 1]}, {bar_x, ys[i]}});
    const bool ground = net(name).net_class == "ground";
    const Point end{bar_x, py_round(ground ? ys.back() + 2 * U : ys.front() - 2 * U, 3)};
    pl.plan(name, {{bar_x, ground ? ys.back() : ys.front()}, end});
    power(name, end.first, end.second, 0);
}

void Engine::_fan_side(const std::string& ref, const std::string& side, const std::vector<PinAt>& items, Handled& handled) {
    const int sign = side == "left" ? -1 : 1;
    const auto box_mark = pl.boxes.size();
    OrderedMap<std::size_t> plan_marks;
    for (const auto& [name, paths] : pl.plans) plan_marks[name] = paths.size();
    std::vector<Point> rows;
    std::vector<double> handled_rows;
    std::vector<PinAt> unhandled;
    std::set<double> signal_rows;
    for (const auto& item : items) {
        require(item.pin != nullptr, "null fanout pin");
        rows.push_back(item.point);
        if (handled.count({ref, item.pin->number, side})) {
            handled_rows.push_back(item.point.second);
            const auto* n = net_of(ref, item.pin->number);
            if (n && signal(*n)) signal_rows.insert(py_round(item.point.second, 3));
        } else unhandled.push_back(item);
    }
    std::stable_sort(unhandled.begin(), unhandled.end(), [](const auto& a, const auto& b) { return a.point.second < b.point.second; });
    std::vector<std::vector<RailPin>> runs;
    for (const auto& item : unhandled) {
        const auto* n = net_of(ref, item.pin->number);
        const auto* previous = runs.empty() ? nullptr : runs.back().back().net;
        const bool adjacent = !runs.empty() && std::fabs(item.point.second - runs.back().back().point.second - 2.54) < 1e-6;
        if (n && previous && n->name == previous->name && (rail(*n) || adjacent))
            runs.back().push_back({item.pin, item.point, n});
        else runs.push_back({{item.pin, item.point, n}});
    }
    std::map<std::string, int> rail_counts;
    for (const auto& run : runs) if (run.front().net && rail(*run.front().net)) ++rail_counts[run.front().net->name];
    std::optional<std::string> comb;
    int best_count = 5;
    for (const auto& [name, count] : rail_counts) if (count > best_count) { comb = name; best_count = count; }
    _rail_row_net.clear();
    for (const auto& run : runs) for (const auto& item : run) if (item.net) {
        if (signal(*item.net)) signal_rows.insert(py_round(item.point.second, 3));
        else if (rail(*item.net)) _rail_row_net[py_round(item.point.second, 3)] = item.net->name;
    }
    _sig_rows.assign(signal_rows.begin(), signal_rows.end());
    std::vector<Point> comb_points;
    std::vector<std::vector<RailPin>> rail_jobs;
    std::vector<Line> lines;
    for (const auto& run : runs) {
        const auto* n = run.front().net;
        if (!n) { for (const auto& item : run) pl.no_connects.push_back({item.point.first, item.point.second}); continue; }
        if (rail(*n)) {
            if (comb && n->name == *comb) for (const auto& item : run) comb_points.push_back(item.point);
            else if (comb) rail_jobs.push_back(run);
            else _fan_rail_run(run, sign, rows);
            continue;
        }
        for (std::size_t i = 1; i < run.size(); ++i) pl.plan(n->name, {run[i - 1].point, run[i].point});
        if (n->net_class == "signal" && run.size() > 1) {
            std::set<PinKey> members;
            for (const auto& item : run) members.emplace(ref, item.pin->number);
            if (std::all_of(n->pins.begin(), n->pins.end(), [&](const auto& p) { return members.count({p.ref, p.pin}) != 0; })) continue;
        }
        auto pulls = get(pull, n->name); auto hangs = get(hang, n->name);
        if (n->net_class == "signal" && _net_shared(n->name, ref) && (!trunks.contains(n->name) || has(shunts, ref))) pulls.clear();
        Line line;
        line.net = n->name; line.pin_pt = run.front().point; line.net_class = n->net_class; line.pin_etype = run.front().pin->etype;
        if (comb && (!pulls.empty() || !hangs.empty())) { pulls.clear(); hangs.clear(); line.force_label = true; }
        if (!pulls.empty() && !hangs.empty()) {
            require(pulls.size() <= 1 && hangs.size() <= 1, "net " + n->name + ": multi-element divider — extend the engine");
            line.attach_div = {pulls.front().first, hangs.front()}; pull.erase(n->name); hang.erase(n->name);
        } else if (!pulls.empty()) {
            require(pulls.size() <= 1, "net " + n->name + ": multiple pull-ups — extend the engine");
            line.attach = pulls.front().first; pull.erase(n->name);
        } else if (!hangs.empty()) {
            require(hangs.size() <= 1, "net " + n->name + ": multiple filter caps — extend the engine");
            line.attach = hangs.front(); hang.erase(n->name);
        }
        lines.push_back(std::move(line));
    }
    const auto finish_rails = [&] {
        for (const auto& run : rail_jobs) _fan_rail_run(run, sign, rows);
        if (!comb_points.empty()) _fan_rail_comb(*comb, comb_points, sign, box_mark, plan_marks);
    };
    if (lines.empty()) { finish_rails(); return; }
    int hang_sign = side == "left" ? -1 : 1;
    std::vector<double> attach_rows, side_rows;
    for (const auto& line : lines) if (line.attach) attach_rows.push_back(line.pin_pt.second);
    for (const auto& pt : rows) side_rows.push_back(pt.second);
    if (!attach_rows.empty() && side_rows.size() > 1) {
        const double first = *std::min_element(attach_rows.begin(), attach_rows.end());
        const double last = *std::max_element(attach_rows.begin(), attach_rows.end());
        const bool veto_up = std::any_of(handled_rows.begin(), handled_rows.end(), [&](double y) { return y < first - 1e-6; });
        const bool veto_down = std::any_of(handled_rows.begin(), handled_rows.end(), [&](double y) { return y > last + 1e-6; });
        const auto a = std::make_tuple(veto_up, first - *std::min_element(side_rows.begin(), side_rows.end()), -1);
        const auto b = std::make_tuple(veto_down, *std::max_element(side_rows.begin(), side_rows.end()) - last, 1);
        hang_sign = std::get<2>(std::min(a, b));
    }
    std::stable_sort(lines.begin(), lines.end(), [&](const auto& a, const auto& b) {
        return hang_sign > 0 ? a.pin_pt.second > b.pin_pt.second : a.pin_pt.second < b.pin_pt.second;
    });
    const double rank_row = attach_rows.empty() ? lines.front().pin_pt.second
        : hang_sign < 0 ? *std::min_element(attach_rows.begin(), attach_rows.end()) : *std::max_element(attach_rows.begin(), attach_rows.end());
    const double rank_y = rank_row + hang_sign * sp.hang_stub;
    const auto label_length = [&](const Line& line) { return line.net_class == "port" ? _glabel_len(line.net) : text_wh(line.net).first + 0.7; };
    const auto labeled = [&](const Line& line) {
        return line.force_label || line.net_class == "port" || (line.net_class == "signal" && _net_shared(line.net, ref)
            && (!trunks.contains(line.net) || has(shunts, ref)) && !_series_of(line.net));
    };
    std::map<std::size_t, bool> outer;
    std::optional<double> previous_y;
    bool previous_outer = false;
    double inner_length = 0;
    for (std::size_t i = 0; i < lines.size(); ++i) {
        const auto& line = lines[i];
        if (!labeled(line) || line.attach || line.attach_div) { previous_y.reset(); continue; }
        const bool out = previous_y && std::fabs(line.pin_pt.second - *previous_y) < GLABEL_H * TEXT_SIZE + 0.5 && !previous_outer;
        outer[i] = out; previous_outer = out; previous_y = line.pin_pt.second;
        if (!out) inner_length = std::max(inner_length, label_length(line));
    }
    std::optional<Box4> previous_box;
    for (std::size_t i = 0; i < lines.size(); ++i) {
        const auto& line = lines[i]; const auto [px, py] = line.pin_pt;
        double lx = px + sign * sp.port_run;
        if (outer.count(i) && outer.at(i)) lx += sign * gceil(inner_length + 1.27);
        if (previous_box) {
            const double len = label_length(line);
            const Box4 box{sign < 0 ? lx - len : lx, py - 1.45, sign < 0 ? lx : lx + len, py + 1.45};
            if (box.x0 - 0.5 < previous_box->x1 && box.x1 + 0.5 > previous_box->x0
                && box.y0 - 0.5 < previous_box->y1 && box.y1 + 0.5 > previous_box->y0) {
                const double want = (sign < 0 ? previous_box->x0 : previous_box->x1) + sign * (sp.stagger_extra + sp.label_tap_gap);
                lx = sign < 0 ? std::min(lx, gfloor(want)) : std::max(lx, gceil(want));
            }
        }
        const bool is_labeled = labeled(line);
        Point tap{lx, py};
        if (line.attach || line.attach_div) {
            const auto [left, right] = _attach_band(line);
            const double depth = 12 * U;
            const double b0 = line.attach_div ? py - depth : hang_sign < 0 ? rank_y - depth : std::min(py, rank_y);
            const double b1 = line.attach_div ? py + depth : hang_sign < 0 ? std::max(py, rank_y) : rank_y + depth;
            double tx = is_labeled ? lx - sign * sp.label_tap_gap : lx;
            for (int k = 0; k < 60; ++k) {
                if (_spot_free({tx - left, b0, tx + right, b1}, 0.0) && _vband_stem_free(tx, b0, b1, {line.net})
                    && _corridor_free(py, px + sign * 0.01, tx, {line.net})) break;
                tx = py_round(tx + sign * 2 * U, 3);
            }
            tap = {tx, py};
            if (is_labeled) lx = tx + sign * sp.label_tap_gap;
        }
        for (const auto& [a, b] : _escape_run_legs(line.net, px, py, tap.first)) pl.plan(line.net, {a, b});
        if (line.attach_div) _divider(line, tap);
        else if (line.attach) _attach_column(line, tap, rank_y, hang_sign > 0);
        if (!is_labeled) {
            const auto leg = line.net_class == "signal" ? _series_of(line.net) : std::nullopt;
            if (leg) previous_box = _series_inline(*leg, line.net, tap, sign, previous_box).second;
            continue;
        }
        if (tap != Point{lx, py}) pl.plan(line.net, {tap, {lx, py}});
        const int rot = side == "left" ? 180 : 0;
        if (line.net_class == "port") {
            label(line.net, lx, py, rot, label_shape(line.pin_etype)); previous_box = glabel_box(line.net, lx, py, rot);
        } else {
            llabel(line.net, lx, py, rot); _bridge(line.net); previous_box = llabel_box(line.net, lx, py, rot);
        }
        // Python's lane_edge accumulation is unused; it has no observable state.
    }
    finish_rails();
}

std::optional<FloatChain> Engine::_local_drop_chain(const std::string& name, const std::string& ref) {
    const auto& n = net(name);
    std::vector<CircuitPinRefIr> multi_pins;
    std::set<std::string> passive_refs;
    for (const auto& p : n.pins) {
        if (has(multi, p.ref)) multi_pins.push_back(p);
        else passive_refs.insert(p.ref);
    }
    if (multi_pins.size() != 1 || multi_pins.front().ref != ref) return std::nullopt;
    auto locals = get(hang, name);
    for (const auto& p : get(pull, name)) locals.push_back(p.first);
    if (locals.size() != 1 || passive_refs != std::set<std::string>(locals.begin(), locals.end())) return std::nullopt;
    const auto& local = locals.front();
    const auto& far = required_net(net_of(local, other_pin(local, _pin_of_net(local, name))), local);
    return FloatChain{"pin", name, {{local, name, far.name}}, {}};
}
void Engine::_signal_islet_drop(const std::string& name, Point pt, const std::string& side) {
    const Point end{pt.first, py_round(pt.second + (side == "top" ? -1 : 1) * sp.port_run, 3)};
    pl.plan(name, {pt, end}); llabel(name, end.first, end.second, 0); _bridge(name);
    const auto count = std::count_if(series.begin(), series.end(), [&](const auto& leg) { return touches(leg, name); });
    if (count == 1 && get(hang, name).size() + get(pull, name).size() == 1) _pin_islets.insert(name);
}
void Engine::_stack_from_pin(const FloatChain& chain, Point pt, const std::string& side, const std::string& text_side) {
    const bool down = side == "bottom";
    auto cur = pt;
    std::string current = chain.root;
    for (const auto& leg : chain.legs) {
        const auto next = _vertical_2pin(leg.ref, pt.first, cur.second, leg.a == current ? leg.a : leg.b, down, text_side);
        cur = next.first; current = next.second;
        _chain_mid_features(chain, current, cur);
    }
    const auto& n = net(current);
    if (rail(n)) power(current, cur.first, cur.second, (n.net_class == "power") != down ? 0 : 180);
}
void Engine::_chain_mid_features(const FloatChain& chain, const std::string& name, Point at) {
    const auto& n = net(name);
    if (rail(n)) return;
    std::vector<double> nodes{at.first};
    const auto refs = get(chain.hangs, name);
    for (std::size_t i = 0; i < refs.size(); ++i) {
        const double x = gceil(at.first + sp.cap_pitch * (i + 1)); nodes.push_back(x);
        const auto [pt, far] = _vertical_2pin(refs[i], x, at.second, name, true);
        power(far, pt.first, pt.second);
    }
    if (n.net_class == "port") {
        const double x = gceil(nodes.back() + (nodes.size() > 1 ? 5.08 : 2.54)); nodes.push_back(x);
        label(name, x, at.second, 0);
    } else if (nodes.size() == 1) return;
    for (std::size_t i = 1; i < nodes.size(); ++i) pl.plan(name, {{nodes[i - 1], at.second}, {nodes[i], at.second}});
}
void Engine::_chain_mid_features_left(const FloatChain& chain, const std::string& name, Point at) {
    const auto& n = net(name);
    if (rail(n)) return;
    std::vector<double> nodes{at.first};
    const auto refs = get(chain.hangs, name);
    for (std::size_t i = 0; i < refs.size(); ++i) {
        const double x = gfloor(at.first - sp.cap_pitch * (i + 1)); nodes.push_back(x);
        const auto [pt, far] = _vertical_2pin(refs[i], x, at.second, name, true);
        power(far, pt.first, pt.second);
    }
    if (n.net_class == "port") {
        const double x = gfloor(*std::min_element(nodes.begin(), nodes.end()) - 2.54); nodes.push_back(x);
        label(name, x, at.second, 180);
    } else if (nodes.size() == 1) return;
    std::sort(nodes.begin(), nodes.end());
    for (std::size_t i = 1; i < nodes.size(); ++i) pl.plan(name, {{nodes[i - 1], at.second}, {nodes[i], at.second}});
}
std::shared_ptr<Trunk> Engine::_rung_of(const std::string& name, const TrunkMap& jobs) const {
    for (const auto& [key, trunk] : jobs) {
        (void)key;
        require(bool(trunk), "null trunk job");
        for (const auto& leg : series)
            if (std::set<std::string>{leg.a, leg.b} == std::set<std::string>{name, trunk->net}) return trunk;
    }
    return {};
}
double Engine::_cell_floor(double x0, double x1) const { return cell_floor(x0, x1, _boxes(), _plan_seg_boxes()); }
void Engine::_cell(const std::string& ref, double ax, double ay, Handled& handled, TrunkMap& jobs,
                   bool defer_texts, int drop_dir) {
    const auto placed = _place_body(ref, ax, ay);
    OrderedMap<ChainPtr> pin_stacks;
    for (const auto& chain : float_chains) if (chain && chain->kind == "pin") pin_stacks[chain->root] = chain;
    for (const std::string side : {"left", "right"}) _fan_side(ref, side, placed.sides.at(side), handled);
    std::vector<PinAt> ports;
    std::vector<std::pair<PinAt, std::shared_ptr<Trunk>>> rungs;
    for (const std::string side : {"top", "bottom"}) {
        std::vector<std::pair<std::string, std::vector<Point>>> rails;
        auto pins = placed.sides.at(side);
        std::stable_sort(pins.begin(), pins.end(), [](const auto& a, const auto& b) { return a.point.first < b.point.first; });
        for (const auto& item : pins) {
            const auto& number = item.pin->number; const auto pt = item.point;
            if (handled.count({ref, number, side})) continue;
            const auto* n = net_of(ref, number);
            if (!n) { pl.no_connects.push_back({pt.first, pt.second}); continue; }
            if (jobs.contains(n->name)) { jobs.at(n->name)->direct.push_back({pt, side}); continue; }
            if (auto rung = _rung_of(n->name, jobs)) { rungs.push_back({item, rung}); continue; }
            if (rail(*n)) {
                if (!rails.empty() && rails.back().first == n->name) rails.back().second.push_back(pt);
                else rails.push_back({n->name, {pt}});
                continue;
            }
            if (pin_stacks.contains(n->name)) { const auto chain = take(pin_stacks, n->name); _stack_from_pin(*chain, pt, side); continue; }
            if (n->net_class == "port") { ports.push_back(item); continue; }
            if (const auto local = _local_drop_chain(n->name, ref)) { _stack_from_pin(*local, pt, side); continue; }
            if (n->net_class == "signal") { _signal_islet_drop(n->name, pt, side); continue; }
            throw SchematicPlaceError(ref + "." + number + " (" + n->name + ") on the " + side + " edge: no engine pattern applies");
        }
        for (const auto& [name, points] : rails) if (points.size() > 1) _rail_bus(name, points, side);
        for (const auto& [name, points] : rails) if (points.size() == 1) _rail_stub(name, points.front(), side);
    }
    if (!ports.empty() || !rungs.empty()) {
        double row = gceil(_cell_floor(placed.body.x0 - 15.0, placed.body.x1 + 15.0) + 4 * U);
        for (const auto& item : ports) { _bottom_port_drop(ref, *item.pin, item.point, row, drop_dir); row = gceil(row + 4 * U); }
        for (const auto& [item, trunk] : rungs) {
            const auto& n = required_net(net_of(ref, item.pin->number), ref);
            Refs legs;
            for (const auto& leg : series) if (touches(leg, trunk->net) && touches(leg, n.name)) legs.push_back(leg.ref);
            trunk->rungs.push_back({n.name, item.point, "bottom_far", legs, row});
            row = gceil(row + 4 * U);
        }
    }
    if (defer_texts) _deferred_texts.emplace_back(placed.part_index, placed.body);
    else _part_texts(placed.part_index, placed.body);
}
void Engine::_bottom_port_drop(const std::string& ref, const SymbolPin& ppin, Point pt, double row, int direction) {
    const auto& name = required_net(net_of(ref, ppin.number), ref).name;
    const auto extent = _extent();
    double lx = direction < 0 ? gfloor(extent.x0 - 2 * U) : gceil(extent.x1 + 2 * U);
    pl.plan(name, {pt, {pt.first, row}});
    const auto pulls = take(pull, name); const auto hangs = take(hang, name);
    require(pulls.size() <= 1 && hangs.empty(), "net " + name + ": bottom-drop attachments beyond one pull-up — extend the engine");
    if (!pulls.empty()) {
        const double start = direction < 0 ? lx : std::max(lx, pt.first + 2 * U);
        const double tx = _lane_x(direction, row - 12 * U, row - 0.1, start);
        const Point tap{tx, row}; lx = tx + direction * sp.label_tap_gap;
        pl.plan(name, {{pt.first, row}, tap}); pl.plan(name, {tap, {lx, row}});
        const Point knee{tx, row - sp.hang_stub}; pl.plan(name, {tap, knee});
        const auto [far_pt, far] = _vertical_2pin(pulls.front().first, tx, knee.second, name, false);
        power(far, far_pt.first, far_pt.second);
    } else pl.plan(name, {{pt.first, row}, {lx, row}});
    label(name, lx, row, direction < 0 ? 180 : 0,
          ppin.etype == "input" || ppin.etype == "output" ? ppin.etype : "bidirectional");
}

void Engine::_build_trunk(Trunk& trunk) {
    int votes = 0;
    for (const auto& d : trunk.direct) votes += d.side == "top" ? 1 : d.side == "bottom" ? -1 : 0;
    for (const auto& r : trunk.rungs) if (r.kind == "bottom_far") --votes;
    trunk.zone = votes > 0 ? "above" : "below";
    const auto extent = _extent();
    double ty = trunk.zone == "above" ? gfloor(extent.y0 - 4 * U) : gceil(extent.y1 + 4 * U);
    if (trunk.zone == "below" && !trunk.rungs.empty()) {
        std::size_t max_legs = 0; double max_y = -std::numeric_limits<double>::infinity();
        for (const auto& r : trunk.rungs) { max_legs = std::max(max_legs, r.legs.size()); max_y = std::max(max_y, r.pin_pt.second); }
        const double bar = gceil(max_y + 4 * U);
        ty = std::max(ty, py_round(bar + 7.62 * max_legs, 3));
    }
    trunk.y = ty;
    std::vector<double> nodes;
    struct Job { std::string kind; Point pt; int sign; std::string far; Refs legs; };
    std::vector<Job> jobs;
    for (const auto& d : trunk.direct) {
        if (d.side == "top" || d.side == "bottom") {
            if (_corridor_clear_vert(d.pin_pt.first, d.pin_pt.second, ty, trunk.net)) {
                pl.plan(trunk.net, {d.pin_pt, {d.pin_pt.first, ty}}); nodes.push_back(d.pin_pt.first);
            } else {
                const auto way = _escape_path(1, d.pin_pt, ty, trunk.net);
                pl.plan(trunk.net, way); nodes.push_back(way.back().first);
            }
        } else jobs.push_back({"direct", d.pin_pt, d.side == "left" ? -1 : 1, {}, {}});
    }
    for (const auto& r : trunk.rungs) {
        if (r.kind == "left" || r.kind == "right") {
            jobs.push_back({r.legs.size() == 1 ? "rung" : "ladder", r.pin_pt, r.kind == "left" ? -1 : 1, r.net, r.legs});
        } else if (trunk.zone == "below") {
            const auto cols = _ladder_rung(trunk, r.net, r.pin_pt, r.legs, gceil(_rung_bar_y(trunk)));
            nodes.insert(nodes.end(), cols.begin(), cols.end());
        } else {
            const double fx = _lane_x(-1, ty, r.row + 2 * U, r.pin_pt.first - 3 * U);
            pl.plan(r.net, {r.pin_pt, {r.pin_pt.first, r.row}});
            pl.plan(r.net, {{r.pin_pt.first, r.row}, {fx, r.row}});
            require(r.legs.size() == 1, trunk.net + ": flank rung with " + std::to_string(r.legs.size()) + " legs — extend the engine");
            if (pl.label_bridged.count(r.net)) llabel(r.net, py_round(r.pin_pt.first - 2 * U, 3), r.row, 180);
            const auto [pt, far] = _vertical_2pin(r.legs.front(), fx, r.row, r.net, false, "left");
            require(far == trunk.net, r.legs.front() + ": rung does not reach trunk " + trunk.net);
            pl.plan(trunk.net, {pt, {fx, ty}}); nodes.push_back(fx);
        }
    }
    std::stable_sort(jobs.begin(), jobs.end(), [&](const auto& a, const auto& b) {
        return std::fabs(a.pt.second - ty) < std::fabs(b.pt.second - ty);
    });
    for (const auto& j : jobs) {
        if (j.kind == "direct") {
            const auto way = _escape_path(j.sign, j.pt, ty, trunk.net); pl.plan(trunk.net, way); nodes.push_back(way.back().first);
        } else if (j.kind == "ladder") {
            const auto cols = _side_ladder_rung(trunk, j.far, j.pt, j.sign, j.legs, ty);
            nodes.insert(nodes.end(), cols.begin(), cols.end());
        } else {
            double fx;
            try { fx = _escape_lane(j.sign, j.pt, ty, j.far); }
            catch (const SchematicPlaceError&) {
                _rung_islet_drop(j.far, j.pt, j.sign); _rung_islets.push_back({trunk.net, j.far, j.legs.front()}); continue;
            }
            pl.plan(j.far, {j.pt, {fx, j.pt.second}});
            const auto [pt, far] = _vertical_2pin(j.legs.front(), fx, j.pt.second, j.far, !(ty < j.pt.second),
                                                 j.sign < 0 ? "left" : "right");
            require(far == trunk.net, j.legs.front() + ": rung does not reach trunk " + trunk.net);
            pl.plan(trunk.net, {pt, {fx, ty}}); nodes.push_back(fx);
        }
    }
    for (const auto& chain : trunk.chains) {
        require(bool(chain), "null trunk chain");
        const auto extent_b = _extent();
        const double edge = _band_edge(ty - 2, ty + 24.0, -1, extent_b.x0), x = gfloor(edge - 4 * U);
        nodes.push_back(x); Point cur{x, ty}; std::string name = trunk.net;
        for (const auto& leg : chain->legs) {
            const auto next = _vertical_2pin(leg.ref, x, cur.second, leg.a == name ? leg.a : leg.b, true, "right");
            cur = next.first; name = next.second; _chain_mid_features_left(*chain, name, cur);
        }
        if (rail(net(name))) {
            const Point end{cur.first, py_round(cur.second + 2 * U, 3)}; pl.plan(name, {cur, end});
            power(name, end.first, end.second, _power_rot(name, true));
        }
    }
    for (const auto& ref : take(hang, trunk.net)) {
        const auto ext = _extent();
        const double right = gceil(_band_edge(ty - 2 * U, ty + 10 * U, 1,
            nodes.empty() ? 0.0 : *std::max_element(nodes.begin(), nodes.end())) + 4 * U);
        const double left = gfloor(_band_edge(ty - 2 * U, ty + 10 * U, -1,
            nodes.empty() ? 0.0 : *std::min_element(nodes.begin(), nodes.end())) - 4 * U);
        const double grow_r = std::max(0.0, right + 2 * U - ext.x1), grow_l = std::max(0.0, ext.x0 - (left - 2 * U));
        const double x = grow_l < grow_r ? left : right; nodes.push_back(x);
        const auto [pt, far] = _vertical_2pin(ref, x, ty, trunk.net, true); power(far, pt.first, pt.second);
    }
    std::set<double> unique;
    for (const double x : nodes) unique.insert(py_round(x, 3));
    nodes.assign(unique.begin(), unique.end());
    require(nodes.size() >= 2, "trunk " + trunk.net + ": fewer than 2 taps after build");
    if (_needs_flag(trunk.net)) {
        std::size_t widest = 1;
        for (std::size_t i = 2; i < nodes.size(); ++i)
            if (nodes[i] - nodes[i - 1] >= nodes[widest] - nodes[widest - 1]) widest = i;
        const double fx = gsnap((nodes[widest - 1] + nodes[widest]) / 2);
        const double dy = trunk.zone == "above" ? -2.54 : 2.54;
        pl.plan(trunk.net, {{fx, ty}, {fx, ty + dy}}); flag(trunk.net, fx, ty + dy, trunk.zone == "above" ? 0 : 180);
        unique.insert(fx); nodes.assign(unique.begin(), unique.end());
    }
    for (std::size_t i = 1; i < nodes.size(); ++i) pl.plan(trunk.net, {{nodes[i - 1], ty}, {nodes[i], ty}});
    if (net(trunk.net).net_class == "port") {
        const auto ext = _extent(); const double width = _glabel_len(trunk.net);
        const double grow_r = std::max(0.0, nodes.back() + 2 * U + width - ext.x1);
        const double grow_l = std::max(0.0, ext.x0 - (nodes.front() - 2 * U - width));
        std::vector<std::pair<double, int>> ends{{nodes.back(), 0}, {nodes.front(), 180}};
        if (grow_l < grow_r) std::reverse(ends.begin(), ends.end());
        double nx = 0, lx = 0; int rot = 0; bool found = false;
        for (int k = 1; k < 12 && !found; ++k) for (const auto& end : ends) {
            nx = end.first; rot = end.second; lx = py_round(nx + (rot == 0 ? 2 * U * k : -2 * U * k), 3);
            if (_spot_free(glabel_box(trunk.net, lx, ty, rot), 0.25)
                && _corridor_free(ty, nx + (rot == 0 ? 1 : -1) * 0.01, lx, {trunk.net})) { found = true; break; }
        }
        pl.plan(trunk.net, {{nx, ty}, {lx, ty}}); label(trunk.net, lx, ty, rot); return;
    }
    for (const auto& [x, rot] : std::vector<std::pair<double, int>>{{nodes.back(), 0}, {nodes.front(), 180}, {nodes.front() + 1.27, 0}})
        if (_spot_free(llabel_box(trunk.net, x, ty, rot), 0.1)) { llabel(trunk.net, x, ty, rot); return; }
    llabel(trunk.net, nodes.back(), ty, 0);
}

double Engine::_rung_bar_y(const Trunk& trunk) const {
    std::optional<double> row;
    for (const auto& rung : trunk.rungs) if (rung.kind == "bottom_far") row = row ? std::max(*row, rung.pin_pt.second) : rung.pin_pt.second;
    require(row.has_value(), trunk.net + ": no bottom_far rung for ladder bar");
    return gceil(*row + 4 * U);
}
std::vector<double> Engine::_ladder_rung(Trunk& trunk, const std::string& far_net, Point pt, Refs legs, double bar) {
    const auto capacitor = [&](const std::string& ref) {
        const auto& id = part(ref).lib_id; return id.size() >= 2 && id.compare(id.size() - 2, 2, ":C") == 0;
    };
    std::stable_sort(legs.begin(), legs.end(), [&](const auto& a, const auto& b) { return capacitor(a) < capacitor(b); });
    std::vector<double> cols;
    for (std::size_t i = 0; i < legs.size(); ++i) cols.push_back(py_round(pt.first + i * 6 * U, 3));
    pl.plan(far_net, {pt, {pt.first, bar}});
    for (std::size_t i = 1; i < cols.size(); ++i) pl.plan(far_net, {{cols[i - 1], bar}, {cols[i], bar}});
    llabel(far_net, pt.first + 1.27, bar);
    for (std::size_t i = 0; i < legs.size(); ++i) {
        const double y = py_round(bar + i * 6 * U, 3);
        if (y != bar) pl.plan(far_net, {{cols[i], bar}, {cols[i], y}});
        const auto [far_pt, far] = _vertical_2pin(legs[i], cols[i], y, far_net, true, i % 2 == 0 ? "left" : "right");
        require(far == trunk.net, legs[i] + ": rung does not reach trunk " + trunk.net);
        pl.plan(trunk.net, {far_pt, {cols[i], trunk.y}});
    }
    return cols;
}
std::vector<double> Engine::_side_ladder_rung(Trunk& trunk, const std::string& far_net, Point pt, int sign, Refs legs, double ty) {
    const auto capacitor = [&](const std::string& ref) {
        const auto& id = part(ref).lib_id; return id.size() >= 2 && id.compare(id.size() - 2, 2, ":C") == 0;
    };
    std::stable_sort(legs.begin(), legs.end(), [&](const auto& a, const auto& b) { return capacitor(a) < capacitor(b); });
    const double pitch = gceil(sp.cap_pitch);
    const std::string text_side = sign > 0 ? "right" : "left";
    std::vector<double> cols; auto from = pt;
    for (std::size_t i = 0; i < legs.size(); ++i) {
        const double y = py_round(pt.second + i * pitch, 3);
        const double start = from.first + sign * (cols.empty() ? 3 * U : pitch);
        const double x = _free_drop_col(sign, start, y, ty, legs[i], far_net, text_side);
        pl.plan(far_net, {from, {x, pt.second}});
        if (y != pt.second) pl.plan(far_net, {{x, pt.second}, {x, y}});
        const auto [far_pt, far] = _vertical_2pin(legs[i], x, y, far_net, true, text_side);
        require(far == trunk.net, legs[i] + ": rung does not reach trunk " + trunk.net);
        pl.plan(trunk.net, {far_pt, {x, ty}}); cols.push_back(x); from = {x, pt.second};
    }
    llabel(far_net, py_round(pt.first + sign * 2 * U, 3), pt.second, sign > 0 ? 0 : 180);
    return cols;
}
double Engine::_free_drop_col(int sign, double start, double attach_y, double ty,
        const std::string& ref, const std::string& name, const std::string& text_side) {
    const auto& p = part(ref); const auto& symbol = lib.get(p.lib_id);
    const auto& attached = pin(symbol, _pin_of_net(ref, name));
    const double off = attached.y != 0 ? std::fabs(attached.y) : std::fabs(attached.x);
    const double anchor_y = attach_y + off;
    double x = sign > 0 ? gceil(start) : gfloor(start);
    for (int i = 0; i < 160; ++i) {
        const SchematicPlacedPart placed{ref, p.lib_id, p.value, x, anchor_y, 0, p.footprint, std::nullopt, std::nullopt};
        std::vector<VisualBox> boxes{body_box_page(symbol, x, anchor_y, 0, "body", ref)};
        const auto pin_boxes = pin_text_boxes(symbol, placed); boxes.insert(boxes.end(), pin_boxes.begin(), pin_boxes.end());
        const auto [w, h] = text_wh(p.value);
        boxes.push_back(text_side == "right" ? VisualBox{x + 0.7, anchor_y - h / 2, x + 0.7 + w, anchor_y + h / 2, "value", ref}
                                               : VisualBox{x - 0.7 - w, anchor_y - h / 2, x - 0.7, anchor_y + h / 2, "value", ref});
        if (std::all_of(boxes.begin(), boxes.end(), [&](const auto& b) { return _spot_free(b.bounds(), 0.3); })
            && _spot_free({x - 0.4, attach_y, x + 0.4, ty}, 0.0)
            && _corridor_free(attach_y, x + sign * 0.01, x - sign * 0.4, {name})) return x;
        x = py_round(x + sign * 2 * U, 3);
    }
    throw SchematicPlaceError(name + ": no free ladder column from " + number_text(start));
}
double Engine::_lane_x(int sign, double y0, double y1, double start) const {
    const auto result = lane_x(sign, y0, y1, start, U, 0.7, 0.3, 0.0, _boxes(), _plan_seg_boxes(), _nc_boxes());
    if (!result) throw SchematicPlaceError("no free lane found");
    return *result;
}
std::vector<Seg2> Engine::_plan_raw_segs(const std::set<std::string>& skip) const {
    std::vector<Seg2> segments;
    for (const auto& [name, paths] : pl.plans) if (!skip.count(name))
        for (const auto& path : paths) for (std::size_t i = 1; i < path.size(); ++i)
            segments.push_back({path[i - 1].first, path[i - 1].second, path[i].first, path[i].second});
    return segments;
}
std::vector<Seg2> Engine::_stem_segs(const std::set<std::string>& skip) {
    std::vector<Seg2> segments;
    for (const auto& placed : pl.parts) for (const auto& p : lib.get(placed.lib_id).pins) {
        if (p.hidden) continue;
        const auto* n = net_of(placed.ref, p.number);
        if (n && skip.count(n->name)) continue;
        const auto tip = pin_page_position(p, placed.x, placed.y, placed.rotation);
        const auto [dx, dy] = stem_dir(p.rotation, placed.rotation);
        segments.push_back({tip.first, tip.second, py_round(tip.first + dx * p.length, 3), py_round(tip.second + dy * p.length, 3)});
    }
    return segments;
}
bool Engine::_corridor_free(double y, double xa, double xb, const std::set<std::string>& skip) {
    auto segments = _plan_raw_segs(skip); const auto stems = _stem_segs(skip);
    segments.insert(segments.end(), stems.begin(), stems.end());
    return corridor_free(y, xa, xb, _boxes(), segments, 0.3);
}
bool Engine::_vband_stem_free(double x, double y0, double y1, const std::set<std::string>& skip) {
    std::vector<Box4> boxes;
    for (const auto& s : _stem_segs(skip)) boxes.push_back({s.x0, s.y0, s.x1, s.y1});
    return vband_stem_free(x, y0, y1, boxes, 0.3);
}
bool Engine::_corridor_clear_vert(double x, double pin_y, double ty, const std::string& name) const {
    return corridor_clear_vert(x, pin_y, ty, _boxes(), _plan_raw_segs({name}), 0.2);
}
bool Engine::_cell_free(double x, double y, const std::string& name) {
    auto segments = _plan_raw_segs({name}); const auto stems = _stem_segs({name});
    segments.insert(segments.end(), stems.begin(), stems.end());
    return cell_free_point(x, y, _boxes(), segments, 0.3);
}
std::vector<std::pair<Point, Point>> Engine::_escape_run_legs(const std::string& name, double px, double py, double tx) {
    std::vector<OwnedBox> owned;
    for (const auto& box : pl.boxes) owned.push_back({box.bounds(), box.owner, box.kind});
    const auto parts = _boxes(); auto corridor = _plan_raw_segs({name}); const auto stems = _stem_segs({name});
    corridor.insert(corridor.end(), stems.begin(), stems.end());
    std::vector<Box4> stem_boxes;
    for (const auto& s : stems) stem_boxes.push_back({s.x0, s.y0, s.x1, s.y1});
    return escape_run_legs(px, py, tx, U, 0.127, owned, parts, _plan_seg_boxes(), _nc_boxes(),
                           parts, corridor, stem_boxes, 0.0, 0.3, 0.3);
}
std::optional<double> Engine::_lane_in_dir(int sign, Point pt, double ty, const std::string& name) {
    const auto parts = _boxes(); auto corridor = _plan_raw_segs({name}); const auto stems = _stem_segs({name});
    corridor.insert(corridor.end(), stems.begin(), stems.end());
    return lane_in_dir(sign, pt.first, pt.second, ty, U, 0.7, 0.3, 0.0, 0.3, 0.01,
                        parts, _plan_seg_boxes(), _nc_boxes(), parts, corridor);
}
double Engine::_escape_lane(int sign, Point pt, double ty, const std::string& name) {
    for (const int direction : {sign, -sign}) if (const auto result = _lane_in_dir(direction, pt, ty, name)) return *result;
    throw SchematicPlaceError(name + ": no free escape lane from " + point_text(pt));
}
std::vector<Point> Engine::_escape_path(int sign, Point pt, double ty, const std::string& name) {
    for (const int direction : {sign, -sign}) if (const auto result = _lane_in_dir(direction, pt, ty, name))
        return {pt, {*result, pt.second}, {*result, ty}};
    return _bfs_escape(pt, ty, name);
}
std::vector<Point> Engine::_bfs_escape(Point pt, double ty, const std::string& name) {
    const auto extent = _extent(); auto segments = _plan_raw_segs({name}); const auto stems = _stem_segs({name});
    segments.insert(segments.end(), stems.begin(), stems.end());
    const auto result = bfs_escape(pt.first, pt.second, ty, U, extent.x0, extent.y0, extent.x1, extent.y1, 16.0, _boxes(), segments, 0.3);
    if (!result) throw SchematicPlaceError(name + ": no free escape lane from " + point_text(pt));
    return *result;
}
void Engine::_collect_trunk_pins(const std::string& ref, double ax, double ay, TrunkMap& jobs, const Handled& rung_keys) {
    for (const auto& [name, trunk] : jobs) {
        (void)name; require(bool(trunk), "null trunk job");
        for (const auto& tip : _side_tips(ref)) if (_on_net(ref, tip.number, trunk->net))
            trunk->direct.push_back({{py_round(ax + tip.point.first, 3), py_round(ay + tip.point.second, 3)}, tip.side});
    }
    for (const auto& tip : _side_tips(ref)) {
        if (!rung_keys.count({ref, tip.number, tip.side})) continue;
        const auto& n = required_net(net_of(ref, tip.number), ref);
        const auto trunk = _rung_of(n.name, jobs);
        require(bool(trunk), n.name + ": no trunk for rung");
        Refs legs;
        for (const auto& leg : series) if (touches(leg, trunk->net) && touches(leg, n.name)) legs.push_back(leg.ref);
        trunk->rungs.push_back({n.name, {py_round(ax + tip.point.first, 3), py_round(ay + tip.point.second, 3)}, tip.side, legs, 0.0});
    }
}

}  // namespace schgen::schematic_place
