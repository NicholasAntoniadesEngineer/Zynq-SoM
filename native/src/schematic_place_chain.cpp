#include "schematic_place_internal.hpp"
#include "schgen/occupancy.hpp"

#include <charconv>
#include <cmath>
#include <limits>

#if defined(__clang__)
#pragma clang fp contract(off)
#endif

namespace schgen::schematic_place {
namespace {
double r3(double value) { return py_round(value, 3); }
bool rail(const CircuitNetIr& net) { return net.net_class == "power" || net.net_class == "ground"; }
bool signal(const CircuitNetIr& net) { return net.net_class == "signal" || net.net_class == "port"; }
bool has(const Refs& refs, const std::string& ref) { return std::find(refs.begin(), refs.end(), ref) != refs.end(); }
bool touches(const Leg& leg, const std::string& net) { return leg.a == net || leg.b == net; }
void require(bool value, const std::string& message = "") {
    if (!value) throw SchematicPlaceError(message);
}
template<class T> T get(const OrderedMap<T>& map, const std::string& key) {
    const auto it = map.find(key);
    return it == map.end() ? T{} : it->second;
}
template<class T> T take(OrderedMap<T>& map, const std::string& key) {
    T out = get(map, key); map.erase(key); return out;
}
template<class T> Refs keys(const OrderedMap<T>& map) {
    Refs out; for (const auto& entry : map) out.push_back(entry.first);
    return out;
}
template<class T> Refs sorted_keys(const OrderedMap<T>& map) {
    auto out = keys(map); std::sort(out.begin(), out.end()); return out;
}
std::string py_quote(const std::string& s) {
    const char quote = s.find('\'') != std::string::npos && s.find('"') == std::string::npos ? '"' : '\'';
    constexpr char hex[] = "0123456789abcdef";
    std::string out(1, quote);
    for (const unsigned char ch : s) {
        if (ch == quote || ch == '\\') out += '\\';
        if (ch == '\n') out += "\\n";
        else if (ch == '\r') out += "\\r";
        else if (ch == '\t') out += "\\t";
        else if (ch < 32 || ch == 127) { out += "\\x"; out += hex[ch >> 4]; out += hex[ch & 15]; }
        else out += static_cast<char>(ch);
    }
    return out + quote;
}
std::string ref_list(const Refs& refs) {
    std::string out = "[";
    for (std::size_t i = 0; i < refs.size(); ++i) { if (i) out += ", "; out += py_quote(refs[i]); }
    return out + "]";
}
std::string number_text(double value) {
    char buffer[512];
    const double mag = std::fabs(value);
    const auto result = std::to_chars(buffer, buffer + sizeof(buffer), value,
        mag == 0 || (mag >= 1e-4 && mag < 1e16) ? std::chars_format::fixed : std::chars_format::scientific);
    require(result.ec == std::errc{}, "cannot format placement coordinate");
    std::string out(buffer, result.ptr);
    if (out.find_first_of(".e") == std::string::npos) out += ".0";
    return out;
}
void remove_leg(std::vector<Leg>& values, const Leg& leg) {
    const auto it = std::find_if(values.begin(), values.end(), [&](const auto& v) {
        return v.ref == leg.ref && v.a == leg.a && v.b == leg.b;
    });
    require(it != values.end(), "placement series leg disappeared");
    values.erase(it);
}
void remove_chain(std::vector<ChainPtr>& values, const ChainPtr& chain) {
    const auto it = std::find(values.begin(), values.end(), chain);
    require(it != values.end(), "placement chain disappeared");
    values.erase(it);
}
void horizontal(SchematicPlacement& pl, const std::string& name, std::vector<double> xs, double y) {
    std::sort(xs.begin(), xs.end()); xs.erase(std::unique(xs.begin(), xs.end()), xs.end());
    for (std::size_t i = 1; i < xs.size(); ++i) pl.plan(name, {{xs[i - 1], y}, {xs[i], y}});
}
std::size_t intersection_size(const std::set<std::string>& a, const std::set<std::string>& b) {
    std::size_t count = 0;
    for (const auto& value : a) count += b.count(value);
    return count;
}
bool same_pair(const FacingPair& a, const FacingPair& b) {
    return a.net == b.net && a.a == b.a && a.b == b.b && a.a_extra == b.a_extra && a.b_extra == b.b_extra;
}
Refs refs_on_net(const CircuitNetIr& net, const Refs& multi) {
    std::set<std::string> out;
    for (const auto& pin : net.pins) if (has(multi, pin.ref)) out.insert(pin.ref);
    return {out.begin(), out.end()};
}
std::vector<Point> all_tips(Point first, const std::vector<Point>& rest) {
    std::vector<Point> out{first}; out.insert(out.end(), rest.begin(), rest.end()); return out;
}
}  // namespace

SchematicPlacement Engine::_stack_columns_template() {
    double x = 0.0;
    for (const auto& ch : float_chains) {
        require(ch->kind == "rail" || ch->kind == "port",
            "passive-only sheet: chain rooted on " + py_quote(ch->root) + " is not rail- or port-rooted");
        Point cur;
        if (ch->kind == "port") {
            label(ch->root, x, 0.0, 90); cur = {x, gceil(2 * U)};
            pl.plan(ch->root, {{x, 0.0}, cur});
        } else { power(ch->root, x, 0.0); cur = {x, 0.0}; }
        auto cur_net = ch->root;
        for (const auto& leg : ch->legs) {
            const auto near = leg.a == cur_net ? leg.a : leg.b;
            const auto far = _vertical_2pin(leg.ref, x, cur.second, near, true);
            cur = far.first; cur_net = far.second; _chain_mid_features(*ch, cur_net, cur);
        }
        if (rail(net(cur_net))) {
            const Point end{cur.first, r3(cur.second + 2 * U)};
            pl.plan(cur_net, {cur, end}); power(cur_net, end.first, end.second, _power_rot(cur_net, true));
        }
        x = gceil(_extent().x1 + 2 * sp.cap_pitch);
    }
    _rail_decoupling_columns(); _flags_row(); return pl;
}

void Engine::_rail_decoupling_columns() {
    if (cluster.empty()) return;
    const auto extent = _extent();
    double x = gsnap(extent.x0 + 8 * U);
    const double y0 = gceil(extent.y1 + 8 * U);
    for (const auto& name : sorted_keys(cluster)) for (const auto& ref : cluster.at(name)) {
        power(name, x, y0);
        const auto far = _vertical_2pin(ref, x, y0, name, true);
        require(net(far.second).net_class == "ground",
            ref + ": rail-decoupling cap far pin on " + py_quote(far.second)
            + " is not GROUND (a true rail-to-rail cap has no GND foot)");
        power(far.second, far.first.first, far.first.second, _power_rot(far.second, true));
        x = gceil(x + 2 * sp.cap_pitch);
    }
    cluster.clear();
}

void Engine::_leftover_chains_columns() {
    std::vector<ChainPtr> chains;
    for (const auto& chain : float_chains) if (chain->kind == "rail") chains.push_back(chain);
    if (chains.empty()) return;
    const bool below = chains.size() > 2;
    double x = 0.0, y0 = 0.0, pitch = 0.0;
    if (below) {
        const auto extent = _extent(); x = gsnap(extent.x0 + 4 * U); y0 = gceil(extent.y1 + 8 * U);
        double width = 0.0;
        for (const auto& chain : chains) width = std::max(width, text_wh(chain->root).first);
        pitch = gceil(width / 2 + 2 * sp.cap_pitch);
    }
    for (const auto& chain : chains) {
        if (!below) { x = gceil(_extent().x1 + 2 * sp.cap_pitch); y0 = 0.0; }
        power(chain->root, x, y0);
        Point cur{x, y0}; auto cur_net = chain->root;
        for (const auto& leg : chain->legs) {
            const auto near = leg.a == cur_net ? leg.a : leg.b;
            const auto far = _vertical_2pin(leg.ref, x, cur.second, near, true);
            cur = far.first; cur_net = far.second; _chain_mid_features(*chain, cur_net, cur);
        }
        if (rail(net(cur_net))) {
            const Point end{cur.first, r3(cur.second + 2 * U)};
            pl.plan(cur_net, {cur, end}); power(cur_net, end.first, end.second, _power_rot(cur_net, true));
        }
        remove_chain(float_chains, chain);
        if (below) x = r3(x + pitch);
    }
}

void Engine::_port_strap_columns() {
    std::vector<ChainPtr> straps;
    for (const auto& chain : float_chains) if (chain->kind == "port") straps.push_back(chain);
    if (straps.empty()) return;
    const auto extent = _extent();
    double height = 0.0; for (const auto& ch : straps) height = std::max(height, text_wh(ch->root).second);
    const double pitch = gceil(height + 2 * sp.cap_pitch), y0 = gceil(extent.y1 + 12 * U);
    double x = gsnap(extent.x0 + 8 * U);
    for (const auto& chain : straps) {
        label(chain->root, x, y0, 90);
        Point cur{x, gceil(y0 + 2 * U)}; pl.plan(chain->root, {{x, y0}, cur});
        auto cur_net = chain->root;
        for (const auto& leg : chain->legs) {
            const auto near = leg.a == cur_net ? leg.a : leg.b;
            const auto far = _vertical_2pin(leg.ref, x, cur.second, near, true);
            cur = far.first; cur_net = far.second; _chain_mid_features(*chain, cur_net, cur);
        }
        if (rail(net(cur_net))) {
            const Point end{cur.first, r3(cur.second + 2 * U)};
            pl.plan(cur_net, {cur, end}); power(cur_net, end.first, end.second, _power_rot(cur_net, true));
        }
        remove_chain(float_chains, chain); x = r3(x + pitch);
    }
}

void Engine::_shunt_cells(Handled& handled) {
    for (const auto& ref : shunts) {
        if (_done.count(ref)) continue;
        const auto extent = _extent(); const auto& symbol = lib.get(part(ref).lib_id);
        const double ay = gceil(extent.y1 + 8 * U - symbol.body[1]);
        const double ax = gsnap(extent.x0 - symbol.body[0] + 16 * U);
        for (const auto& n : c.nets) if (signal(n))
            for (const auto& pr : n.pins) if (pr.ref == ref) { _bridge(n.name); break; }
        TrunkMap no_trunks; _cell(ref, ax, ay, handled, no_trunks);
    }
}

void Engine::_pull_rank_columns() {
    if (pull.empty() && hang.empty()) return;
    std::map<std::string, std::vector<std::pair<std::string, std::string>>> by_rail;
    for (const auto& sig : sorted_keys(pull)) for (const auto& item : pull.at(sig))
        by_rail[item.second].push_back({item.first, sig});
    for (const auto& sig : sorted_keys(hang)) for (const auto& ref : hang.at(sig)) {
        const auto* far = net_of(ref, other_pin(ref, _pin_of_net(ref, sig))); require(far != nullptr);
        by_rail[far->name].push_back({ref, sig});
    }
    pull.clear(); hang.clear();
    const auto extent = _extent(); double x = gsnap(extent.x0 + 8 * U);
    const double bar_y = gceil(extent.y1 + 10 * U);
    for (const auto& [name, cols] : by_rail) {
        double width = 0.0; for (const auto& col : cols) width = std::max(width, text_wh(col.second).first);
        const double pitch = gceil(width + 4 * U);
        const bool is_ground = net(name).net_class == "ground";
        std::vector<double> xs;
        for (const auto& [ref, sig] : cols) {
            xs.push_back(x);
            if (is_ground) {
                const Point knee{x, r3(bar_y - 2 * U)}, elbow{r3(x + 2 * U), knee.second};
                pl.plan(sig, {knee, {x, bar_y}}); pl.plan(sig, {knee, elbow});
                llabel(sig, elbow.first, elbow.second); _bridge(sig);
                const auto far = _vertical_2pin(ref, x, bar_y, sig, true); require(far.second == name);
                power(name, far.first.first, far.first.second, _power_rot(name, true));
                x = r3(x + pitch); continue;
            }
            const auto far = _vertical_2pin(ref, x, bar_y, name, true); require(far.second == sig);
            if (rail(net(sig))) power(sig, far.first.first, far.first.second, _power_rot(sig, true));
            else {
                const Point elbow{r3(far.first.first + 2 * U), r3(far.first.second + 2 * U)};
                pl.plan(sig, {far.first, {far.first.first, elbow.second}});
                pl.plan(sig, {{far.first.first, elbow.second}, elbow});
                llabel(sig, elbow.first, elbow.second); _bridge(sig);
            }
            x = r3(x + pitch);
        }
        if (!is_ground) {
            if (xs.size() == 1) power(name, xs.front(), bar_y);
            else {
                const double xm = gsnap((xs.front() + xs.back()) / 2);
                auto nodes = xs; nodes.push_back(xm); horizontal(pl, name, nodes, bar_y);
                pl.plan(name, {{xm, bar_y}, {xm, bar_y - 2 * U}}); power(name, xm, bar_y - 2 * U);
            }
        }
        x = r3(x + 2 * U);
    }
}

void Engine::_series_port_columns() {
    std::vector<Leg> left;
    for (const auto& leg : series) if (net(leg.a).net_class == "port" && net(leg.b).net_class == "port") left.push_back(leg);
    if (left.empty()) return;
    const auto extent = _extent(); double x = gsnap(extent.x0 + 8 * U);
    const double y0 = gceil(extent.y1 + 12 * U), pitch = gceil(2 * sp.cap_pitch);
    for (const auto& leg : left) {
        label(leg.a, x, y0, 90); const Point cur{x, r3(y0 + 2 * U)}; pl.plan(leg.a, {{x, y0}, cur});
        const auto far = _vertical_2pin(leg.ref, x, cur.second, leg.a, true); require(far.second == leg.b);
        const Point end{x, r3(far.first.second + 2 * U)};
        pl.plan(leg.b, {far.first, end}); label(leg.b, end.first, end.second, 270);
        remove_leg(series, leg); x = r3(x + pitch);
    }
}

void Engine::_trunk_series_columns() {
    const auto named = [&](const std::string& name) {
        if (net(name).net_class != "signal") return false;
        if (trunks.contains(name) || pl.label_bridged.count(name)) return true;
        for (const auto& label : pl.llabels) if (label.name == name) return true;
        for (const auto& label : pl.hlabels) if (label.name == name) return true;
        return false;
    };
    std::vector<Leg> left;
    for (const auto& leg : series) if (!_done.count(leg.ref) && named(leg.a) && named(leg.b)) left.push_back(leg);
    if (left.empty()) return;
    const auto extent = _extent(); double x = gsnap(extent.x0 + 8 * U);
    const double y0 = gceil(extent.y1 + 12 * U), pitch = gceil(2 * sp.cap_pitch);
    for (const auto& leg : left) {
        llabel(leg.a, r3(x - 2 * U), y0, 180); _bridge(leg.a);
        pl.plan(leg.a, {{r3(x - 2 * U), y0}, {x, y0}});
        const Point cur{x, r3(y0 + 2 * U)}; pl.plan(leg.a, {{x, y0}, cur});
        const auto far = _vertical_2pin(leg.ref, x, cur.second, leg.a, true); require(far.second == leg.b);
        const Point end{r3(x - 2 * U), far.first.second};
        pl.plan(leg.b, {far.first, end}); llabel(leg.b, end.first, end.second, 180); _bridge(leg.b);
        remove_leg(series, leg); x = r3(x + pitch);
    }
}

void Engine::_rung_islet_drop(const std::string& name, Point pt, int sign) {
    const double lx = r3(pt.first + sign * sp.port_run);
    pl.plan(name, {pt, {lx, pt.second}}); llabel(name, lx, pt.second, sign > 0 ? 0 : 180); _bridge(name);
}
void Engine::_rung_islet_columns() {
    if (_rung_islets.empty()) return;
    const auto extent = _extent(); double x = gsnap(extent.x0 + 8 * U);
    const double y0 = gceil(extent.y1 + 12 * U), pitch = gceil(3 * sp.cap_pitch);
    for (const auto& item : _rung_islets) {
        llabel(item.trunk_net, r3(x - 2 * U), y0, 180); _bridge(item.trunk_net);
        const Point cur{x, r3(y0 + 2 * U)};
        pl.plan(item.trunk_net, {{r3(x - 2 * U), y0}, {x, y0}});
        pl.plan(item.trunk_net, {{x, y0}, cur});
        const auto far = _vertical_2pin(item.ref, x, cur.second, item.trunk_net, true); require(far.second == item.far_net);
        const Point end{r3(x - 2 * U), far.first.second};
        pl.plan(item.far_net, {far.first, end}); llabel(item.far_net, end.first, end.second, 180); _bridge(item.far_net);
        x = r3(x + pitch);
    }
    _rung_islets.clear();
}
void Engine::_pin_divider_columns() {
    if (_pin_islets.empty()) return;
    const auto extent = _extent(); double x = gsnap(extent.x0 + 8 * U);
    const double y0 = gceil(extent.y1 + 12 * U), pitch = gceil(3 * sp.cap_pitch);
    for (const auto& mid : _pin_islets) {
        std::vector<Leg> ser; for (const auto& leg : series) if (touches(leg, mid)) ser.push_back(leg);
        const auto hangs = get(hang, mid); const auto pulls = get(pull, mid);
        if (ser.size() != 1 || hangs.size() + pulls.size() != 1) continue;
        const auto top = ser.front(); const auto top_net = top.a == mid ? top.b : top.a;
        if (net(top_net).net_class == "port") label(top_net, x, y0, 90); else power(top_net, x, y0);
        const Point cur{x, r3(y0 + 2 * U)}; pl.plan(top_net, {{x, y0}, cur});
        const auto far = _vertical_2pin(top.ref, x, cur.second, top_net, true); require(far.second == mid);
        remove_leg(series, top);
        const double lx = r3(far.first.first - 2 * U);
        pl.plan(mid, {far.first, {lx, far.first.second}}); llabel(mid, lx, far.first.second, 180); _bridge(mid);
        const auto bot = hangs.empty() ? pulls.front().first : hangs.front();
        const auto foot = _vertical_2pin(bot, x, far.first.second, mid, true);
        const Point end{x, r3(foot.first.second + 2 * U)};
        pl.plan(foot.second, {foot.first, end}); power(foot.second, end.first, end.second, _power_rot(foot.second, true));
        hang.erase(mid); pull.erase(mid); x = r3(x + pitch);
    }
    _pin_islets.clear();
}

Refs Engine::_chain_order() {
    Refs connectors, others;
    for (const auto& ref : multi) if (!has(shunts, ref)) (ref.front() == 'J' ? connectors : others).push_back(ref);
    // Circuit connectivity is immutable; avoid rescanning the board within
    // stable-sort comparators and connected-component propagation.
    std::map<std::string, std::set<std::string>> nets, signals;
    std::map<std::string, std::size_t> port_count;
    for (const auto& ref : multi) {
        for (const auto& n : c.nets) for (const auto& pr : n.pins) if (pr.ref == ref) {
            nets[ref].insert(n.name); if (signal(n)) signals[ref].insert(n.name); break;
        }
        for (const auto& pn : lib.pin_numbers(part(ref).lib_id))
            if (const auto* n = net_of(ref, pn); n && n->net_class == "port") ++port_count[ref];
    }
    std::stable_sort(others.begin(), others.end(), [&](const auto& a, const auto& b) { return port_count[a] > port_count[b]; });
    Refs pool = others; pool.insert(pool.end(), connectors.begin(), connectors.end());
    if (pool.empty()) return {};
    std::map<std::string, std::size_t> comp;
    for (std::size_t i = 0; i < pool.size(); ++i) comp[pool[i]] = i;
    bool changed = true;
    while (changed) {
        changed = false;
        for (const auto& a : pool) for (const auto& b : pool)
            if (comp[a] != comp[b] && intersection_size(signals[a], signals[b])) {
                comp[a] = comp[b] = std::min(comp[a], comp[b]); changed = true;
            }
    }
    std::set<std::size_t> ids; for (const auto& entry : comp) ids.insert(entry.second);
    Refs order; _comp_starts.clear();
    for (const auto id : ids) {
        Refs sub; for (const auto& ref : pool) if (comp[ref] == id) sub.push_back(ref);
        Refs sub_order{sub.front()}; sub.erase(sub.begin());
        while (!sub.empty()) {
            const auto& last = nets[sub_order.back()];
            std::stable_sort(sub.begin(), sub.end(), [&](const auto& a, const auto& b) {
                return intersection_size(last, nets[a]) > intersection_size(last, nets[b]);
            });
            sub_order.push_back(sub.front()); sub.erase(sub.begin());
        }
        const auto forward = _eval_chain(sub_order);
        auto reversed = sub_order; std::reverse(reversed.begin(), reversed.end());
        const auto backward = _eval_chain(reversed);
        const auto& chosen = backward.score > forward.score ? backward : forward;
        if (backward.score > forward.score) sub_order = std::move(reversed);
        for (const auto& item : chosen.orient) orient[item.first] = item.second;
        _comp_starts.insert(sub_order.front()); order.insert(order.end(), sub_order.begin(), sub_order.end());
    }
    return order;
}

ChainScore Engine::_eval_chain(const Refs& order) {
    const auto saved = orient;
    ChainScore best{{-1, 0, 0}, {}};
    std::vector<int> combo(order.size(), 0);
    bool more = true;
    while (more) {
        for (std::size_t i = 0; i < order.size(); ++i)
            if (combo[i]) orient[order[i]] = combo[i]; else orient.erase(order[i]);
        int pairs = 0, blocked = 0, inward = 0;
        std::map<std::pair<std::string, std::string>, std::vector<double>> channel_rows;
        for (std::size_t i = 1; i < order.size(); ++i) {
            const auto ps = _facing_pairs(order[i - 1], order[i]); pairs += static_cast<int>(ps.size());
            for (const auto& p : ps) {
                channel_rows[{order[i - 1], "right"}].push_back(p.a.second);
                channel_rows[{order[i], "left"}].push_back(p.b.second);
            }
        }
        // Reuse orientation-specific pin tips within this combination. The
        // enumeration/tie order remains itertools.product((0,180), repeat=N).
        std::map<std::string, std::vector<SideTip>> tips;
        for (const auto& ref : order) tips[ref] = _side_tips(ref);
        for (const auto& [name, trunk] : trunks) {
            (void)trunk;
            int votes = 0;
            for (const auto& ref : order) for (const auto& tip : tips[ref]) if (_on_net(ref, tip.number, name))
                votes += tip.side == "top" ? 1 : tip.side == "bottom" ? -1 : 0;
            const bool up = votes > 0;
            std::set<std::string> rung_nets;
            for (const auto& leg : series) if (touches(leg, name)) rung_nets.insert(leg.b == name ? leg.a : leg.b);
            for (const auto& ref : order) for (const auto& tip : tips[ref]) {
                if (tip.side != "left" && tip.side != "right") continue;
                const auto* n = net_of(ref, tip.number); if (!n || !rung_nets.count(n->name)) continue;
                const auto& rows = channel_rows[{ref, tip.side}];
                if (std::any_of(rows.begin(), rows.end(), [&](double row) {
                        return up ? row < tip.point.second - 1e-6 : row > tip.point.second + 1e-6;
                    })) ++blocked;
            }
        }
        for (std::size_t i = 0; i < order.size(); ++i) for (const auto& tip : tips[order[i]]) {
            if (!((i + 1 < order.size() && tip.side == "right") || (i > 0 && tip.side == "left"))) continue;
            const auto* n = net_of(order[i], tip.number); if (!n) continue;
            if (n->net_class == "port" || (n->net_class == "signal" && _net_shared(n->name, order[i]))) ++inward;
        }
        const std::array<int, 3> score{pairs, -blocked, -inward};
        if (score > best.score) {
            best.score = score; best.orient.clear();
            for (std::size_t i = 0; i < order.size(); ++i) best.orient[order[i]] = combo[i];
        }
        more = false;
        for (std::size_t i = combo.size(); i > 0; --i) {
            if (combo[i - 1] == 0) { combo[i - 1] = 180; more = true; break; }
            combo[i - 1] = 0;
        }
    }
    orient = saved; return best;
}

std::optional<TipGroup> Engine::_tip_group(std::vector<Point> tips) {
    std::stable_sort(tips.begin(), tips.end(), [](const auto& a, const auto& b) { return a.second < b.second; });
    // Python only calls this with nonempty groups; fail explicitly if a direct
    // caller violates that precondition, rather than dereferencing an empty list.
    require(!tips.empty(), "list index out of range");
    for (std::size_t i = 1; i < tips.size(); ++i)
        if (std::abs(tips[i].second - tips[i - 1].second - 2.54) > 1e-6) return std::nullopt;
    return TipGroup{tips.front(), std::vector<Point>(tips.begin() + 1, tips.end())};
}

std::vector<FacingPair> Engine::_facing_pairs(const std::string& a, const std::string& b) {
    std::vector<FacingPair> out;
    const auto a_sides = _side_tips(a), b_sides = _side_tips(b);
    for (const auto& n : c.nets) {
        if (rail(n)) continue;
        bool others = false;
        for (const auto& pr : n.pins)
            if (has(multi, pr.ref) && !has(shunts, pr.ref) && pr.ref != a && pr.ref != b) { others = true; break; }
        if (others) continue;
        std::vector<Point> a_tips, b_tips;
        for (const auto& tip : a_sides) if (tip.ref == a && tip.side == "right" && _on_net(a, tip.number, n.name)) a_tips.push_back(tip.point);
        for (const auto& tip : b_sides) if (tip.ref == b && tip.side == "left" && _on_net(b, tip.number, n.name)) b_tips.push_back(tip.point);
        if (a_tips.empty() || b_tips.empty()) continue;
        const auto ga = _tip_group(a_tips), gb = _tip_group(b_tips);
        if (ga && gb) out.push_back({n.name, ga->first, gb->first, ga->rest, gb->rest});
    }
    return out;
}
std::vector<SideTip> Engine::_side_tips(const std::string& ref) {
    const auto rotation = get(orient, ref); const auto& symbol = lib.get(part(ref).lib_id);
    std::set<std::pair<Point, int>> seen; std::vector<SideTip> out;
    for (const auto& p : symbol.pins) {
        if (p.hidden) continue;
        const auto tip = pin_page_position(p, 0.0, 0.0, rotation);
        if (!seen.emplace(tip, p.rotation).second) continue;
        out.push_back({ref, p.number, side_of_rotation(p.rotation + rotation), tip});
    }
    return out;
}
bool Engine::_on_net(const std::string& ref, const std::string& number, const std::string& name) const {
    const auto* n = net_of(ref, number); return n && n->name == name;
}
std::string Engine::_pin_num_at(const std::string& ref, Point point, const std::string& side) {
    for (const auto& tip : _side_tips(ref)) if (tip.side == side && tip.point == point) return tip.number;
    throw SchematicPlaceError(ref + ": no " + side + " pin at (" + number_text(point.first) + ", " + number_text(point.second) + ")");
}

double Engine::_side_reach(const std::string& ref, const std::string& side,
                           const TrunkMap* jobs, const std::set<std::string>& exclude) {
    const auto& trunk_jobs = jobs ? *jobs : trunks;
    double out = 2 * U; std::size_t lanes = 0; std::vector<std::pair<double, double>> rows;
    for (const auto& tip : _side_tips(ref)) {
        if (tip.side != side) continue;
        const auto* n = net_of(ref, tip.number); if (!n || exclude.count(n->name)) continue;
        if (trunk_jobs.contains(n->name) || (n->net_class == "signal" && _rung_of(n->name, trunk_jobs))) { ++lanes; continue; }
        const auto ser = n->net_class == "signal" ? _series_of(n->name) : std::nullopt;
        if (ser) {
            const auto far = ser->a == n->name ? ser->b : ser->a;
            const double len = net(far).net_class == "port" ? _glabel_len(far) : text_wh(far).first + 0.7;
            rows.push_back({tip.point.second, 12 * U + len + sp.label_tap_gap}); continue;
        }
        double extra = 0.0;
        if (signal(*n)) {
            Refs refs;
            for (const auto& item : get(pull, n->name)) refs.push_back(item.first);
            const auto hanging = get(hang, n->name); refs.insert(refs.end(), hanging.begin(), hanging.end());
            for (const auto& r : refs) {
                const auto* far = net_of(r, other_pin(r, _pin_of_net(r, n->name)));
                if (far) extra = std::max(extra, sp.label_tap_gap + text_wh(far->name).first / 2 + 0.7);
            }
        }
        if (n->net_class == "port")
            rows.push_back({tip.point.second, _glabel_len(n->name) + extra + sp.stagger_extra + sp.label_tap_gap});
        else if (n->net_class == "signal" && _net_shared(n->name, ref))
            rows.push_back({tip.point.second, text_wh(n->name).first + 0.7 + extra + sp.stagger_extra + sp.label_tap_gap});
        else if (rail(*n)) out = std::max(out, 3.81 + text_wh(n->name).first + 2 * U);
        else out = std::max(out, sp.port_run + 4 * U);
    }
    if (!rows.empty()) {
        const double clash = GLABEL_H * TEXT_SIZE + 0.5;
        std::sort(rows.begin(), rows.end());
        double inner_len = 0.0, outer_len = 0.0; std::optional<double> prev_y; bool prev_inner = false;
        for (const auto& [y, len] : rows) {
            const bool outer = prev_y && std::abs(y - *prev_y) < clash && prev_inner;
            if (outer) outer_len = std::max(outer_len, len); else inner_len = std::max(inner_len, len);
            prev_y = y; prev_inner = !outer;
        }
        const double two = inner_len + (outer_len ? 1.27 + outer_len : 0.0);
        out = std::max(out, sp.port_run + two + 2 * U);
    }
    if (lanes) out += 3 * U + 2 * U * static_cast<double>(lanes);
    return out;
}

SchematicPlacement Engine::run() {
    SchematicPlacement result;
    if (multi.empty()) result = _stack_columns_template();
    else if (c.parts.size() == 1 && lib.pin_numbers(part(multi.front()).lib_id).size() >= 40)
        result = _connector_template(multi.front());
    else {
        auto stages = _detect_stages(); bool shared_ok = true;
        const std::set<std::string> multi_refs(multi.begin(), multi.end());
        // Only existence matters: scan connectivity once instead of scanning
        // every net again for every pair of multi-pin components. Stacked pins
        // on the same component do not imply a shared inter-component signal.
        for (const auto& n : c.nets) {
            if (!signal(n)) continue;
            const std::string* first = nullptr;
            for (const auto& pr : n.pins) if (multi_refs.count(pr.ref)) {
                if (!first) first = &pr.ref;
                else if (*first != pr.ref) { shared_ok = false; break; }
            }
            if (!shared_ok) break;
        }
        result = !stages.empty() && shared_ok ? _regulator_template(std::move(stages)) : _chain_template();
    }
    Refs missing; for (const auto& p : c.parts) if (!_done.count(p.ref)) missing.push_back(p.ref);
    std::sort(missing.begin(), missing.end());
    require(missing.empty(), "engine left parts unplaced: " + ref_list(missing) + " — no topology pattern matched them");
    return result;
}

SchematicPlacement Engine::_chain_template() {
    const auto order = _chain_order();
    require(!order.empty(), "list index out of range");
    std::map<std::string, Point> anchors;
    Handled handled;
    std::vector<std::tuple<std::string, std::string, std::string>> channels;
    struct Channel { Point a, b; std::optional<double> jog; };
    std::map<std::string, Channel> channel_tips;
    std::map<std::string, double> ays{{order.front(), 0.0}};
    using PairInfo = std::vector<std::pair<FacingPair, bool>>;
    std::map<std::string, PairInfo> binfo{{order.front(), {}}};

    for (std::size_t i = 1; i < order.size(); ++i) {
        const auto& a_ref = order[i - 1]; const auto& b_ref = order[i];
        const auto pairs = _facing_pairs(a_ref, b_ref); const double ay_a = ays.at(a_ref);
        if (pairs.empty()) { ays[b_ref] = ay_a; binfo[b_ref] = {}; continue; }
        std::vector<double> dys; std::map<double, std::size_t> frequency;
        for (const auto& p : pairs) { const double d = r3((ay_a + p.a.second) - p.b.second); dys.push_back(d); ++frequency[d]; }
        double dy = frequency.begin()->first;
        for (const auto& [d, count] : frequency)
            if (std::make_pair(count, -std::abs(d)) > std::make_pair(frequency.at(dy), -std::abs(dy))) dy = d;
        std::vector<FacingPair> aligned, candidates, demoted, jogged;
        std::set<double> aligned_rows; std::map<std::string, Point> spans;
        for (std::size_t j = 0; j < pairs.size(); ++j) if (dys[j] == dy) {
            aligned.push_back(pairs[j]); aligned_rows.insert(r3(ay_a + pairs[j].a.second));
        }
        for (std::size_t j = 0; j < pairs.size(); ++j) {
            if (dys[j] == dy) continue;
            const auto& p = pairs[j]; const double ya = r3(ay_a + p.a.second), yb = r3(dy + p.b.second);
            const double lo = std::min(ya, yb), hi = std::max(ya, yb);
            if (std::any_of(aligned_rows.begin(), aligned_rows.end(),
                            [&](double r) { return lo + 1e-6 < r && r < hi - 1e-6; })) demoted.push_back(p);
            else { spans[p.net] = {ya, yb}; candidates.push_back(p); }
        }
        if (!candidates.empty()) {
            OrderedMap<std::set<std::string>> after;
            for (const auto& p : candidates) after[p.net] = {};
            for (std::size_t a = 0; a < candidates.size(); ++a) for (std::size_t b = 0; b < candidates.size(); ++b) {
                if (a == b) continue;
                const auto& pi = candidates[a]; const auto& pj = candidates[b];
                const auto si = spans.at(pi.net), sj = spans.at(pj.net);
                const double lo = std::min(si.first, si.second), hi = std::max(si.first, si.second);
                if (lo + 1e-6 < sj.first && sj.first < hi - 1e-6) after[pi.net].insert(pj.net);
                if (lo + 1e-6 < sj.second && sj.second < hi - 1e-6) after[pj.net].insert(pi.net);
            }
            std::map<std::string, FacingPair> names;
            for (const auto& p : candidates) names[p.net] = p;
            Refs placed; std::set<std::string> placed_set; auto pending = after;
            while (!pending.empty()) {
                Refs ready;
                for (const auto& [name, deps] : pending)
                    if (std::all_of(deps.begin(), deps.end(), [&](const auto& dep) { return placed_set.count(dep); })) ready.push_back(name);
                if (ready.empty()) {
                    const auto worst = sorted_keys(pending).back();
                    demoted.push_back(names.at(worst)); pending.erase(worst);
                    for (auto& entry : pending) entry.second.erase(worst);
                    continue;
                }
                std::sort(ready.begin(), ready.end());
                for (const auto& name : ready) { placed.push_back(name); placed_set.insert(name); pending.erase(name); }
            }
            for (const auto& name : placed) jogged.push_back(names.at(name));
        }
        for (const auto& p : demoted) { trunks.erase(p.net); _bridge(p.net); }
        auto kept = aligned; kept.insert(kept.end(), jogged.begin(), jogged.end());
        for (const auto& p : kept) {
            for (const auto tip : all_tips(p.a, p.a_extra)) handled.emplace(a_ref, _pin_num_at(a_ref, tip, "right"), "right");
            for (const auto tip : all_tips(p.b, p.b_extra)) handled.emplace(b_ref, _pin_num_at(b_ref, tip, "left"), "left");
            trunks.erase(p.net);
        }
        ays[b_ref] = gsnap(dy);
        PairInfo info;
        for (const auto& p : kept) info.push_back({p, std::any_of(jogged.begin(), jogged.end(), [&](const auto& j) { return same_pair(p, j); })});
        binfo[b_ref] = std::move(info);
    }

    for (const auto& name : keys(trunks)) {
        const auto& n = net(name); if (n.net_class != "signal") continue;
        const auto mp = refs_on_net(n, multi); if (mp.size() < 2) continue;
        Refs nonshunts; bool any_shunt = false;
        for (const auto& r : mp) { if (has(shunts, r)) any_shunt = true; else nonshunts.push_back(r); }
        if (any_shunt && nonshunts.size() <= 2) { trunks.erase(name); _bridge(name); continue; }
        std::vector<std::string> sides;
        for (const auto& ref : nonshunts) for (const auto& tip : _side_tips(ref))
            if (_on_net(ref, tip.number, name)) sides.push_back(tip.side);
        const bool has_legs = !trunks.at(name)->chains.empty()
            || std::any_of(series.begin(), series.end(), [&](const auto& leg) { return touches(leg, name); });
        if (nonshunts.size() >= 2 && !has_legs
            && std::all_of(sides.begin(), sides.end(), [](const auto& s) { return s == "left" || s == "right"; })) {
            trunks.erase(name); _bridge(name);
        }
    }
    auto trunk_jobs = trunks; // Deliberately shallow: Python dict(self.trunks).
    for (const auto& entry : trunk_jobs) for (const auto& ref : order) for (const auto& tip : _side_tips(ref))
        if (_on_net(ref, tip.number, entry.second->net)) handled.emplace(ref, tip.number, tip.side);
    Handled rung_keys;
    for (const auto& ref : order) for (const auto& tip : _side_tips(ref)) {
        const auto key = std::make_tuple(ref, tip.number, tip.side);
        if ((tip.side != "left" && tip.side != "right") || handled.count(key)) continue;
        const auto* n = net_of(ref, tip.number);
        if (n && n->net_class == "signal" && _rung_of(n->name, trunk_jobs)) {
            handled.insert(key); rung_keys.insert(key);
        }
    }

    double comp_dy = 0.0, row_y0 = -1e9;
    const auto seat = [&](const std::string& ref, double ax, double ay) {
        anchors[ref] = {ax, ay}; _collect_trunk_pins(ref, ax, ay, trunk_jobs, rung_keys);
        _cell(ref, ax, ay, handled, trunk_jobs, true, order.size() > 1 && ref == order.back() ? 1 : -1);
    };
    for (std::size_t i = 0; i < order.size(); ++i) {
        const auto& ref = order[i]; bool new_row = false;
        if (i && _comp_starts.count(ref)) {
            const double right = row_y0 > -1e8 ? _band_edge(row_y0, 1e9, 1, 0.0) : _extent().x1;
            const double left = row_y0 > -1e8 ? _band_edge(row_y0, 1e9, -1, 0.0) : _extent().x0;
            if (right - left > 170.0) {
                const double bottom = _extent().y1;
                comp_dy = gceil(bottom + 14 * U) - ays.at(ref); row_y0 = gceil(bottom + 2 * U); new_row = true;
            }
        }
        double ay = r3(ays.at(ref) + comp_dy);
        if (i == 0 || new_row) { seat(ref, 0.0, ay); continue; }
        const auto& a_ref = order[i - 1]; const auto a = anchors.at(a_ref);
        const auto pairs = binfo.at(ref);
        const double meas = _band_edge(row_y0, 1e9, 1, row_y0 < -1e8 ? _extent().x1 : 0.0);
        const double jog_base = gceil(meas + 2 * U);
        const auto n_jogs = std::count_if(pairs.begin(), pairs.end(), [](const auto& p) { return p.second; });
        std::optional<double> left_tip;
        for (const auto& tip : _side_tips(ref)) if (tip.side == "left")
            left_tip = left_tip ? std::min(*left_tip, tip.point.first) : tip.point.first;
        const double b_left = left_tip ? *left_tip : lib.get(part(ref).lib_id).body[0];
        std::set<std::string> exclude; for (const auto& p : pairs) exclude.insert(p.first.net);
        const double reach = _side_reach(ref, "left", &trunk_jobs, exclude);
        const double margin = pairs.empty() ? 10 * U : 4 * U;
        double ax = gsnap(gceil(jog_base + static_cast<double>(n_jogs) * 2 * U + reach + margin) - b_left);
        if (!pairs.empty()) {
            double label_reach = 0.0, a_right = -std::numeric_limits<double>::infinity();
            double b_min = std::numeric_limits<double>::infinity();
            for (const auto& info : pairs) {
                const auto& p = info.first;
                if (net(p.net).net_class == "signal") label_reach = std::max(label_reach, llabel_box(p.net, 0, 0).x1);
                a_right = std::max(a_right, p.a.first); b_min = std::min(b_min, p.b.first);
            }
            a_right += a.first;
            ax = std::max(ax, gsnap(a_right + gceil(std::max(2 * sp.port_run, label_reach + 8 * U)) - b_min));
        }
        const double row_left = row_y0 > -1e8 ? _band_edge(row_y0, 1e9, -1, 0.0) : _extent().x0;
        // SCHGEN_WRAP_INSTR only prints Python diagnostics; it never changes
        // geometry and is intentionally not a process-environment dependency.
        if (!pairs.empty() && ax - row_left > PAPER_W_BUDGET) {
            for (const auto& info : pairs) {
                const auto& p = info.first;
                for (const auto tip : all_tips(p.a, p.a_extra)) {
                    handled.erase({a_ref, _pin_num_at(a_ref, tip, "right"), "right"});
                    const double tx = r3(a.first + tip.first), ty = r3(a.second + tip.second), ex = r3(tx + sp.port_run);
                    pl.plan(p.net, {{tx, ty}, {ex, ty}}); llabel(p.net, ex, ty);
                }
                for (const auto tip : all_tips(p.b, p.b_extra)) handled.erase({ref, _pin_num_at(ref, tip, "left"), "left"});
                _bridge(p.net);
            }
            binfo[ref].clear();
            const double bottom = _extent().y1;
            comp_dy = gceil(bottom + 14 * U) - ays.at(ref); row_y0 = gceil(bottom + 2 * U);
            ay = r3(ays.at(ref) + comp_dy); seat(ref, 0.0, ay); continue;
        }
        double jog_x = jog_base;
        for (const auto& info : pairs) {
            const auto& p = info.first;
            const bool jog = info.second;
            std::optional<double> jx;
            if (jog) { jx = jog_x; jog_x = r3(jog_x + 2 * U); }
            const auto plan_extra = [&](Point anchor, Point first, const std::vector<Point>& rest) {
                Point previous = first;
                for (const auto next : rest) {
                    pl.plan(p.net, {{r3(anchor.first + previous.first), r3(anchor.second + previous.second)},
                                   {r3(anchor.first + next.first), r3(anchor.second + next.second)}});
                    previous = next;
                }
            };
            plan_extra(a, p.a, p.a_extra); plan_extra({ax, ay}, p.b, p.b_extra);
            channels.emplace_back(p.net, a_ref, ref);
            channel_tips[p.net] = {{r3(a.first + p.a.first), r3(a.second + p.a.second)},
                                  {r3(ax + p.b.first), r3(ay + p.b.second)}, jx};
        }
        seat(ref, ax, ay);
    }
    // Python's label search retains the last tested end point even when every
    // candidate collides. Preserve that policy; downstream visual gates decide.
    std::optional<Point> label_end;
    for (const auto& channel : channels) {
        const auto& name = std::get<0>(channel); const auto tips = channel_tips.at(name);
        double y, start_x;
        if (tips.jog) {
            pl.plan(name, {tips.a, {*tips.jog, tips.a.second}});
            pl.plan(name, {{*tips.jog, tips.a.second}, {*tips.jog, tips.b.second}});
            y = tips.b.second; start_x = *tips.jog;
        } else {
            require(std::abs(tips.a.second - tips.b.second) < 1e-6);
            y = tips.a.second; start_x = tips.a.first;
        }
        std::vector<double> nodes{start_x};
        const auto hangs = take(hang, name); const double xs = gfloor(tips.b.first - 4 * U);
        for (std::size_t i = 0; i < hangs.size(); ++i) {
            const double xc = r3(xs - static_cast<double>(i) * sp.cap_pitch); nodes.push_back(xc);
            pl.plan(name, {{xc, y}, {xc, y + 4 * U}});
            const auto far = _vertical_2pin(hangs[i], xc, y + 4 * U, name, true, i % 2 ? "left" : "right");
            power(far.second, far.first.first, far.first.second);
        }
        nodes.push_back(tips.b.first);
        double mid, label_y;
        if (tips.jog && *tips.jog - tips.a.first > tips.b.first - *tips.jog) {
            mid = gsnap((tips.a.first + *tips.jog) / 2); label_y = tips.a.second;
        } else { mid = gsnap((start_x + tips.b.first) / 2); label_y = y; }
        const bool has_hlabel = std::any_of(pl.hlabels.begin(), pl.hlabels.end(), [&](const auto& h) { return h.name == name; });
        if (net(name).net_class == "port" && !has_hlabel) {
            double lx = mid;
            for (int k = 0; k < 20; ++k) {
                lx = r3(mid + (k / 2 + k % 2) * 2 * U * (k % 2 ? 1 : -1));
                if (!(start_x + 2 * U <= lx && lx <= tips.b.first - 2 * U)) continue;
                label_end = Point{lx, r3(y - 2 * U)};
                if (_spot_free(glabel_box(name, label_end->first, label_end->second, 90))
                    && _spot_free({lx - 0.1, label_end->second, lx + 0.1, y - 0.2}, 0.0)) break;
            }
            require(label_end.has_value(), "cannot access local variable 'end2' where it is not associated with a value");
            nodes.push_back(lx); pl.plan(name, {{lx, y}, *label_end}); label(name, label_end->first, label_end->second, 90);
        }
        horizontal(pl, name, nodes, y);
        if (net(name).net_class == "signal") llabel(name, mid, label_y);
    }
    for (const auto& entry : trunk_jobs) _build_trunk(*entry.second);
    for (const auto& item : _deferred_texts) _part_texts(item.first, item.second);
    _deferred_texts.clear();
    const auto first = std::find_if(pl.parts.begin(), pl.parts.end(), [&](const auto& p) { return p.ref == order.front(); });
    require(first != pl.parts.end(), "chain template: first component was not placed");
    const auto& symbol = lib.get(first->lib_id);
    const auto body = body_box_page(symbol, first->x, first->y, first->rotation, "body", order.front());
    _decoupling_cluster(first->x, first->y, body); _shunt_cells(handled);
    _rung_islet_columns(); _pin_divider_columns(); _pull_rank_columns();
    _series_port_columns(); _trunk_series_columns();
    if (std::any_of(float_chains.begin(), float_chains.end(), [](const auto& ch) { return ch->kind == "rail"; })) _leftover_chains_columns();
    _port_strap_columns(); _flags_row(); return pl;
}

}  // namespace schgen::schematic_place
