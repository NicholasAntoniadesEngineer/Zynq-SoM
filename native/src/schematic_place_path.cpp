#include "schematic_place_internal.hpp"
#include "schgen/occupancy.hpp"

#include <cmath>

#if defined(__clang__)
#pragma clang fp contract(off)
#endif

namespace schgen::schematic_place {
namespace {
double r3(double value) { return py_round(value, 3); }
bool rail(const CircuitNetIr& net) { return net.net_class == "power" || net.net_class == "ground"; }
bool signal(const CircuitNetIr& net) { return net.net_class == "signal" || net.net_class == "port"; }
bool has(const Refs& refs, const std::string& ref) { return std::find(refs.begin(), refs.end(), ref) != refs.end(); }
void require(bool value, const std::string& message) {
    if (!value) throw SchematicPlaceError(message);
}
template<class T> T get(const OrderedMap<T>& map, const std::string& key) {
    const auto it = map.find(key);
    return it == map.end() ? T{} : it->second;
}
void horizontal(SchematicPlacement& pl, const std::string& name, std::vector<double> xs, double y) {
    std::sort(xs.begin(), xs.end()); xs.erase(std::unique(xs.begin(), xs.end()), xs.end());
    for (std::size_t i = 1; i < xs.size(); ++i) pl.plan(name, {{xs[i - 1], y}, {xs[i], y}});
}
}  // namespace

void Engine::_detect_power_path() {
    _path = PowerPath{}; _path_refs.clear();
    Refs hinted;
    for (const auto& hint : c.hints) if (hint.style == "path") {
        require(net(hint.net).net_class == "power", "power path: hinted net " + hint.net + " is not a power rail");
        hinted.push_back(hint.net);
    }
    if (hinted.empty()) return;
    const std::set<std::string> on_path(hinted.begin(), hinted.end());
    std::vector<PathLink> links;
    for (const auto& p : c.parts) {
        std::set<std::string> rails;
        for (const auto& number : lib.pin_numbers(p.lib_id))
            if (const auto* n = net_of(p.ref, number); n && n->net_class == "power") rails.insert(n->name);
        if (rails.size() != 2 || !on_path.count(*rails.begin()) || !on_path.count(*rails.rbegin())) continue;
        links.push_back({p.ref, *rails.begin(), *rails.rbegin(), has(multi, p.ref)});
    }
    std::map<std::string, std::vector<std::size_t>> at;
    for (std::size_t i = 0; i < links.size(); ++i) { at[links[i].a].push_back(i); at[links[i].b].push_back(i); }
    for (const auto& name : hinted)
        require(at[name].size() <= 2, "power path: rail " + name + " has more than two series elements");
    const auto start = std::find_if(hinted.begin(), hinted.end(), [&](const auto& name) { return at[name].size() <= 1; });
    require(start != hinted.end(), "power path: the hinted rails form a loop");
    std::set<std::size_t> used;
    std::string cur = *start;
    _path.nets.push_back(cur);
    while (true) {
        const auto& choices = at[cur];
        const auto next = std::find_if(choices.begin(), choices.end(), [&](std::size_t i) { return !used.count(i); });
        if (next == choices.end()) break;
        used.insert(*next);
        auto link = links[*next];
        if (link.a != cur) std::swap(link.a, link.b);
        cur = link.b; _path.links.push_back(link); _path.nets.push_back(cur);
    }
    require(_path.nets.size() == hinted.size() && used.size() == links.size(),
            "power path: the hinted rails are not one chain of series elements");
    const auto terminal = [&](const std::string& name) -> std::optional<std::string> {
        std::optional<std::string> found;
        for (const auto& ref : multi) {
            bool touches = false, plain = true;
            for (const auto& number : lib.pin_numbers(part(ref).lib_id)) {
                const auto* n = net_of(ref, number);
                if (!n) continue;
                if (n->name == name) touches = true;
                else if (n->net_class != "ground") plain = false;
            }
            if (!touches || !plain) continue;
            require(!found, "power path: rail " + name + " has more than one terminal part");
            found = ref;
        }
        return found;
    };
    _path.source = terminal(_path.nets.front());
    if (_path.nets.size() > 1) _path.sink = terminal(_path.nets.back());
    for (const auto& link : _path.links) {
        _path_refs.insert(link.ref);
        if (link.multi) continue;
        for (const auto& name : {link.a, link.b}) {
            if (!pull.contains(name)) continue;
            auto& entries = pull.at(name);
            entries.erase(std::remove_if(entries.begin(), entries.end(), [&](const auto& e) { return e.first == link.ref; }), entries.end());
            if (entries.empty()) pull.erase(name);
        }
    }
    if (_path.source) _path_refs.insert(*_path.source);
    if (_path.sink) _path_refs.insert(*_path.sink);
}

SideTip Engine::_path_tip(const std::string& ref, const std::string& name, const std::string& side) {
    std::optional<SideTip> found;
    for (const int rotation : {0, 180}) {
        if (rotation) orient[ref] = rotation; else orient.erase(ref);
        found.reset();
        bool single = true;
        for (const auto& tip : _side_tips(ref)) if (_on_net(ref, tip.number, name)) { single = single && !found; found = tip; }
        require(found.has_value() && single, "power path: " + ref + " needs exactly one pin on " + name);
        if (found->side == side) return *found;
    }
    throw SchematicPlaceError("power path: " + ref + " has no " + side + "-facing pin on " + name);
}

void Engine::_path_cell(const std::string& ref, double ax, double ay, const std::set<std::string>& rails, Handled& handled) {
    for (const auto& tip : _side_tips(ref)) {
        const auto* n = net_of(ref, tip.number);
        if (n && rails.count(n->name)) handled.emplace(ref, tip.number, tip.side);
        else if (n && signal(*n)) _bridge(n->name);
    }
    TrunkMap none;
    _cell(ref, ax, ay, handled, none);
}

void Engine::_power_path_row(Handled& handled) {
    if (_path.nets.empty()) return;
    Point cursor{0.0, 0.0};
    double lead = 4 * U;
    if (_path.source) {
        const auto tip = _path_tip(*_path.source, _path.nets.front(), "right");
        _path_cell(*_path.source, r3(-tip.point.first), r3(-tip.point.second), {_path.nets.front()}, handled);
    }
    for (std::size_t i = 0; i < _path.nets.size(); ++i) {
        const auto& name = _path.nets[i];
        const bool last = i + 1 == _path.nets.size();
        const double y = cursor.second;
        std::vector<double> nodes{cursor.first};
        double x = gceil(cursor.first + lead);
        nodes.push_back(x);
        pl.plan(name, {{x, y}, {x, r3(y - PATH_TAG_RISE)}}); power(name, x, r3(y - PATH_TAG_RISE));
        const double tag = text_wh(name).first / 2;
        x = gceil(x + std::max(sp.cap_pitch, tag + 2 * U));
        const auto pitch = [&](const std::string& ref, const std::string& foot_net) {
            const auto& p = part(ref);
            double half = 0;
            for (const auto v : lib.get(p.lib_id).body) half = std::max(half, std::fabs(v));
            const double texts = 2 * half + TEXT_GAP + std::max(text_wh(p.ref).first, text_wh(p.value).first);
            return std::max({sp.cap_pitch, texts + 2 * U, text_wh(foot_net).first + 2 * U});
        };
        for (const auto& ref : get(cluster, name)) {
            nodes.push_back(x);
            const auto foot = _vertical_2pin(ref, x, y, name, true);
            require(net(foot.second).net_class == "ground", ref + ": power path capacitor does not end on ground");
            power(foot.second, foot.first.first, foot.first.second, _power_rot(foot.second, true));
            x = gceil(x + pitch(ref, foot.second));
        }
        cluster.erase(name);
        std::vector<ChainPtr> chains;
        for (const auto& chain : float_chains) if (chain->kind == "rail" && chain->root == name) chains.push_back(chain);
        for (const auto& chain : chains) {
            nodes.push_back(x);
            Point cur{x, y}; auto cur_net = name;
            for (const auto& leg : chain->legs) {
                const auto far = _vertical_2pin(leg.ref, x, cur.second, leg.a == cur_net ? leg.a : leg.b, true);
                cur = far.first; cur_net = far.second; _chain_mid_features(*chain, cur_net, cur);
            }
            require(rail(net(cur_net)), "power path: chain off " + name + " does not end on a rail");
            power(cur_net, cur.first, cur.second, _power_rot(cur_net, true));
            float_chains.erase(std::find(float_chains.begin(), float_chains.end(), chain));
            x = gceil(std::max(_band_edge(y, y + static_cast<double>(chain->legs.size()) * PASSIVE_SPAN, 1, x) + 2 * U,
                               x + pitch(chain->legs.front().ref, cur_net)));
        }
        const std::string next = last ? (_path.sink ? *_path.sink : std::string{}) : _path.links[i].ref;
        const bool body = !next.empty() && has(multi, next);
        std::optional<SideTip> in;
        if (body) in = _path_tip(next, name, "left");
        const double tail = body ? std::max(4 * U, _side_reach(next, "left", nullptr, {name})) : 4 * U;
        const double end = gceil(std::max(nodes.back(), x - sp.cap_pitch) + tail);
        if (next.empty()) { horizontal(pl, name, nodes, y); break; }
        nodes.push_back(end); horizontal(pl, name, nodes, y);
        if (last) {
            _path_cell(next, r3(end - in->point.first), r3(y - in->point.second), {name}, handled);
            break;
        }
        const auto& link = _path.links[i];
        if (body) {
            const double ax = r3(end - in->point.first), ay = r3(y - in->point.second);
            std::optional<SideTip> out;
            for (const auto& tip : _side_tips(next)) if (_on_net(next, tip.number, link.b)) {
                require(!out, "power path: " + next + " needs exactly one pin on " + link.b); out = tip;
            }
            require(out && out->side == "right", "power path: " + next + " does not pass " + link.a + " to " + link.b + " left to right");
            _path_cell(next, ax, ay, {link.a, link.b}, handled);
            cursor = {r3(ax + out->point.first), r3(ay + out->point.second)};
            lead = std::max(4 * U, _side_reach(next, "right", nullptr, {link.b}));
        } else {
            const auto& near = pin(lib.get(part(next).lib_id), _pin_of_net(next, name));
            const double off = std::fabs(near.y) > 1e-6 ? std::fabs(near.y) : std::fabs(near.x);
            const auto mark = pl.boxes.size();
            _horizontal_2pin(next, r3(end + off), y, name, "right");
            auto& placed = pl.parts.back();
            const auto shape = pl.boxes[mark];
            const double cx = (shape.x0 + shape.x1) / 2, base = r3(shape.y0 - TEXT_GAP - U);
            placed.ref_pos = SchematicTextPosition{cx, r3(base - 2 * U), 0};
            placed.val_pos = SchematicTextPosition{cx, base, 0};
            for (std::size_t k = mark + 1; k < pl.boxes.size(); ++k) {
                const bool is_ref = pl.boxes[k].kind == "reference";
                const auto b = centered_box(is_ref ? placed.ref : placed.value, cx, is_ref ? placed.ref_pos->y : placed.val_pos->y);
                pl.boxes[k] = {b.x0, b.y0, b.x1, b.y1, pl.boxes[k].kind, pl.boxes[k].owner};
            }
            cursor = {r3(end + 2 * off), y}; lead = 4 * U;
        }
    }
}

}  // namespace schgen::schematic_place
