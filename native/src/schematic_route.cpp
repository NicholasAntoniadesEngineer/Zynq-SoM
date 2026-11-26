#include "schgen/schematic_route.hpp"

#if defined(__clang__)
#pragma clang fp contract(off)
#endif

#include "schgen/occupancy.hpp"
#include "schgen/turn.hpp"

#include <algorithm>
#include <charconv>
#include <cmath>
#include <cstdint>
#include <limits>
#include <map>
#include <optional>
#include <set>
#include <utility>

namespace schgen {
namespace {
using Point = RoutePoint;
using Cell = RouteCell;
using Leg = std::pair<Point, Point>;
constexpr double grid_mm = 1.27;

std::string repr(const std::string& value) {
    const char quote = value.find('\'') != std::string::npos && value.find('"') == std::string::npos ? '"' : '\'';
    constexpr char hex[] = "0123456789abcdef";
    std::string out(1, quote);
    for (unsigned char c : value) {
        if (c == quote || c == '\\') { out += '\\'; out += static_cast<char>(c); }
        else if (c == '\n') out += "\\n";
        else if (c == '\r') out += "\\r";
        else if (c == '\t') out += "\\t";
        else if (c < 32 || c == 127) { out += "\\x"; out += hex[c >> 4]; out += hex[c & 15]; }
        else out += static_cast<char>(c);
    }
    return out + quote;
}

std::string number(double value) {
    if (std::isnan(value)) return "nan";
    if (std::isinf(value)) return value < 0 ? "-inf" : "inf";
    const std::string sign = std::signbit(value) ? "-" : "";
    char buffer[64];
    const auto converted = std::to_chars(buffer, buffer + sizeof(buffer), std::abs(value), std::chars_format::scientific);
    if (converted.ec != std::errc{}) throw SchematicRouteError("route: coordinate formatting failed");
    const std::string scientific(buffer, converted.ptr);
    const auto e = scientific.find('e');
    const int exponent = std::stoi(scientific.substr(e + 1));
    if (exponent < -4 || exponent >= 16) return sign + scientific;
    auto digits = scientific.substr(0, e);
    const auto dot = digits.find('.');
    if (dot != std::string::npos) digits.erase(dot, 1);
    const int point = exponent + 1;
    if (point <= 0) return sign + "0." + std::string(-point, '0') + digits;
    if (point >= static_cast<int>(digits.size()))
        return sign + digits + std::string(point - digits.size(), '0') + ".0";
    digits.insert(static_cast<std::size_t>(point), ".");
    return sign + digits;
}

std::string show(Point p) { return "(" + number(p.first) + ", " + number(p.second) + ")"; }

void check_range(Point p) {
    // The shared kernel stores cells as int and expands its BFS boundary by 12.
    // Check before a floating-to-int cast can overflow; retain its grid rules.
    constexpr double limit = static_cast<double>(std::numeric_limits<int>::max() - 1024);
    if (!std::isfinite(p.first) || !std::isfinite(p.second))
        throw SchematicRouteError("point " + show(p) + " is off the 1.27 mm grid");
    if (std::abs(p.first / grid_mm) > limit || std::abs(p.second / grid_mm) > limit)
        throw SchematicRouteError("point " + show(p) + " exceeds the native schematic grid range");
}

Cell cell(Point p) {
    check_range(p);
    try { return route_cell_of(p.first, p.second, grid_mm); }
    catch (const std::runtime_error&) {
        throw SchematicRouteError("point " + show(p) + " is off the 1.27 mm grid");
    }
}

Point point(Cell c) { return route_point_of(c.first, c.second, grid_mm); }
Point rounded(Point p) { check_range(p); return {py_round(p.first, 3), py_round(p.second, 3)}; }

std::vector<Cell> cells(Point a, Point b) {
    check_range(a); check_range(b);
    // route_cells_between computes its inclusive span in int. Endpoint range
    // alone cannot prove that subtraction is representable for opposite signs.
    constexpr double max_span = static_cast<double>(std::numeric_limits<int>::max() - 1);
    if (std::abs(std::round(a.first / grid_mm) - std::round(b.first / grid_mm)) > max_span ||
        std::abs(std::round(a.second / grid_mm) - std::round(b.second / grid_mm)) > max_span)
        throw SchematicRouteError("route: segment exceeds the native schematic cell span");
    try { return route_cells_between(a, b, grid_mm); }
    catch (const std::runtime_error& e) {
        if (std::string(e.what()).find("orthogonal") != std::string::npos)
            throw SchematicRouteError("segment " + show(a) + "->" + show(b) + " is not orthogonal");
        throw SchematicRouteError(e.what());
    }
}

void claim(RouteGrid& grid, const std::string& owner, const std::vector<Cell>& values, const std::string& what) {
    try { grid.claim(owner, values, what); }
    catch (const std::runtime_error& e) { throw SchematicRouteError(e.what()); }
}

// Ordering-only compatibility for numeric two-tuples. Set membership is ordinary
// equality; there is no interpreter, randomized string hashing, or process state.
// The baseline uses CPython's 64-bit numeric/tuple hashes and set probing/resizing:
// https://github.com/python/cpython/blob/v3.14.0/Objects/setobject.c
// https://github.com/python/cpython/blob/v3.14.0/Objects/tupleobject.c
// https://github.com/python/cpython/blob/v3.14.0/Python/pyhash.c
std::uint64_t numeric_hash(double value) {
    constexpr std::uint64_t modulus = (std::uint64_t{1} << 61) - 1;
    int exponent = 0;
    const double fraction = std::frexp(std::abs(value), &exponent);
    const auto significand = static_cast<std::uint64_t>(std::ldexp(fraction, 53));
    int shift = (exponent - 53) % 61;
    if (shift < 0) shift += 61;
    auto hash = ((significand << shift) & modulus) | (significand >> (61 - shift));
    if (value < 0) hash = 0 - hash;
    return hash == UINT64_MAX ? UINT64_MAX - 1 : hash;
}

std::uint64_t point_hash(Point p) {
    constexpr std::uint64_t prime1 = 11400714785074694791ULL;
    constexpr std::uint64_t prime2 = 14029467366897019727ULL;
    constexpr std::uint64_t prime5 = 2870177450012600261ULL;
    auto hash = prime5;
    for (auto coordinate : {p.first, p.second}) {
        hash += numeric_hash(coordinate) * prime2;
        hash = (hash << 31) | (hash >> 33);
        hash *= prime1;
    }
    hash += 2 ^ (prime5 ^ 3527539ULL);
    return hash == UINT64_MAX ? 1546275796ULL : hash;
}

class PointSet {
    struct Slot { Point value{}; std::uint64_t hash = 0; int state = 0; };
    std::vector<Slot> slots_{8};
    std::size_t used_ = 0, fill_ = 0;

    std::size_t find(Point p, std::uint64_t hash, bool inserting) const {
        const auto mask = slots_.size() - 1;
        auto i = static_cast<std::size_t>(hash) & mask;
        auto perturb = hash;
        auto free = slots_.size();
        for (;;) {
            const auto end = i + (i + 9 <= mask ? 9 : 0);
            for (auto j = i; j <= end; ++j) {
                const auto& slot = slots_[j];
                if (slot.state == 0) return inserting && free != slots_.size() ? free : j;
                if (slot.state == 1 && slot.hash == hash && slot.value == p) return j;
                if (slot.state == 2) free = j;
            }
            perturb >>= 5;
            i = (i * 5 + 1 + perturb) & mask;
        }
    }
    void insert_clean(const Slot& slot) {
        slots_[find(slot.value, slot.hash, true)] = slot;
    }
    void resize(std::size_t minimum) {
        std::size_t size = 8;
        while (size <= minimum) size *= 2;
        if (size == slots_.size() && fill_ == used_) return;
        auto old = std::move(slots_);
        slots_ = std::vector<Slot>(size);
        fill_ = used_;
        for (const auto& slot : old) if (slot.state == 1) insert_clean(slot);
    }
public:
    std::size_t size() const { return used_; }
    bool contains(Point p) const {
        const auto hash = point_hash(p);
        return slots_[find(p, hash, false)].state == 1;
    }
    void add(Point p) {
        const auto hash = point_hash(p);
        auto& slot = slots_[find(p, hash, true)];
        if (slot.state == 1) return;
        const bool virgin = slot.state == 0;
        slot = {p, hash, 1};
        ++used_;
        if (virgin) {
            ++fill_;
            if (fill_ * 5 >= (slots_.size() - 1) * 3) resize(used_ * (used_ > 50000 ? 2 : 4));
        }
    }
    std::vector<Point> values() const {
        std::vector<Point> out;
        out.reserve(used_);
        for (const auto& slot : slots_) if (slot.state == 1) out.push_back(slot.value);
        return out;
    }
    static PointSet from_dict(const std::vector<Point>& keys) {
        PointSet out;
        if (keys.size() * 5 >= 7 * 3) out.resize(keys.size() * 2);
        for (auto p : keys) out.add(p);
        return out;
    }
    void merge(const PointSet& other) {
        if (other.size() == 0) return;
        if ((fill_ + other.used_) * 5 >= (slots_.size() - 1) * 3) resize((used_ + other.used_) * 2);
        if (fill_ == 0 && slots_.size() == other.slots_.size() && other.fill_ == other.used_) {
            *this = other;
        } else if (fill_ == 0) {
            fill_ = used_ = other.used_;
            for (const auto& slot : other.slots_) if (slot.state == 1) insert_clean(slot);
        } else for (auto p : other.values()) add(p);
    }
    PointSet copy() const { PointSet out; out.merge(*this); return out; }
    PointSet united(const PointSet& other) const { auto out = copy(); out.merge(other); return out; }
    PointSet difference(const PointSet& other) const {
        if ((size() >> 2) > other.size()) {
            auto out = copy();
            for (auto p : other.values()) {
                auto& slot = out.slots_[out.find(p, point_hash(p), false)];
                if (slot.state == 1) { slot.state = 2; --out.used_; }
            }
            if (out.fill_ - out.used_ > (out.slots_.size() - 1) / 4)
                out.resize(out.used_ * (out.used_ > 50000 ? 2 : 4));
            return out;
        }
        PointSet out;
        for (auto p : values()) if (!other.contains(p)) out.add(p);
        return out;
    }
};

struct NetGeom {
    std::vector<Leg> legs, bonds;
    std::vector<Point> pin_order;
    std::map<Point, std::set<std::string>> pin_parts;
    PointSet power_pts, label_pts;
};

std::vector<PointSet> components(const NetGeom& g) {
    const auto pts = PointSet::from_dict(g.pin_order).united(g.power_pts).united(g.label_pts);
    std::vector<Point> order = pts.values();
    std::map<Point, PointSet> adj;
    for (auto p : order) adj.emplace(p, PointSet{});
    const auto edge = [&](const Leg& leg) {
        for (auto p : {leg.first, leg.second})
            if (adj.emplace(p, PointSet{}).second) order.push_back(p);
        adj.at(leg.first).add(leg.second);
        adj.at(leg.second).add(leg.first);
    };
    for (const auto& leg : g.legs) edge(leg);
    for (const auto& bond : g.bonds) edge(bond);
    PointSet seen;
    std::vector<PointSet> comps;
    for (auto p : order) {
        if (seen.contains(p)) continue;
        PointSet comp;
        std::vector<Point> todo{p};
        while (!todo.empty()) {
            const auto q = todo.back(); todo.pop_back();
            if (seen.contains(q)) continue;
            seen.add(q); comp.add(q);
            const auto pending = adj.at(q).difference(seen).values();
            todo.insert(todo.end(), pending.begin(), pending.end());
        }
        comps.push_back(std::move(comp));
    }
    return comps;
}

bool intersects(const PointSet& a, const PointSet& b) {
    for (auto p : a.values()) if (b.contains(p)) return true;
    return false;
}

std::string islet(const PointSet& comp) {
    auto pts = comp.values();
    std::sort(pts.begin(), pts.end());
    std::string out = "[";
    for (std::size_t i = 0; i < std::min(pts.size(), std::size_t{3}); ++i) {
        if (i) out += ", ";
        out += show(pts[i]);
    }
    return out + "]";
}

std::vector<Point> bfs_points(const std::vector<Point>& comp) {
    PointSet starts;
    for (auto p : comp) {
        const auto c = cell(p);
        starts.add({static_cast<double>(c.first), static_cast<double>(c.second)});
    }
    std::vector<Point> out;
    for (auto c : starts.values()) out.push_back(point({static_cast<int>(c.first), static_cast<int>(c.second)}));
    return out;
}

std::vector<Point> bfs_points(const PointSet& comp) { return bfs_points(comp.values()); }

void split_plans(NetGeom& g) {
    std::set<Cell> anchors;
    for (auto p : g.label_pts.values()) anchors.insert(cell(p));
    for (const auto& [a, b] : g.legs) { anchors.insert(cell(a)); anchors.insert(cell(b)); }
    for (int pass = 0; pass < 64; ++pass) {
        bool changed = false;
        auto endpoints = anchors;
        for (const auto& [a, b] : g.legs) { endpoints.insert(cell(a)); endpoints.insert(cell(b)); }
        std::vector<Leg> out;
        for (const auto& leg : g.legs) {
            const auto segment = cells(leg.first, leg.second);
            std::optional<Cell> cut;
            std::set<Cell> interior;
            for (std::size_t i = 1; i + 1 < segment.size(); ++i) {
                interior.insert(segment[i]);
                if (!cut && endpoints.count(segment[i])) cut = segment[i];
            }
            if (!cut) {
                for (const auto& other : g.legs) {
                    if (other == leg) continue;
                    for (auto c : cells(other.first, other.second)) if (interior.count(c)) { cut = c; break; }
                    if (cut) break;
                }
            }
            if (cut && *cut != segment.front() && *cut != segment.back()) {
                const auto mid = point(*cut);
                out.emplace_back(leg.first, mid); out.emplace_back(mid, leg.second);
                changed = true;
            } else out.push_back(leg);
        }
        g.legs = std::move(out);
        if (!changed) break;
    }
    std::set<Leg> seen;
    std::vector<Leg> unique;
    for (const auto& [a, b] : g.legs) {
        if (a == b) continue;
        if (seen.emplace(a <= b ? Leg{a, b} : Leg{b, a}).second) unique.emplace_back(a, b);
    }
    g.legs = std::move(unique);
}

void check_overlap(const std::string& net, const NetGeom& g) {
    std::set<Cell> endpoints, seen;
    for (const auto& [a, b] : g.legs) { endpoints.insert(cell(a)); endpoints.insert(cell(b)); }
    for (const auto& [a, b] : g.legs) {
        const auto segment = cells(a, b);
        for (std::size_t i = 1; i + 1 < segment.size(); ++i) {
            const auto c = segment[i];
            if (seen.count(c) || endpoints.count(c))
                throw SchematicRouteError("net " + net + ": leg " + show(a) + "->" + show(b) +
                    " overlaps own geometry at " + show(point(c)) + " (split legs at taps)");
            seen.insert(c);
        }
    }
}
}  // namespace

std::vector<std::vector<RoutePoint>> schematic_route_components(
        const std::vector<std::pair<RoutePoint, RoutePoint>>& legs,
        const std::vector<RoutePoint>& pin_points,
        const std::vector<RoutePoint>& power_points,
        const std::vector<RoutePoint>& label_points,
        const std::vector<std::pair<RoutePoint, RoutePoint>>& bonds) {
    NetGeom g;
    g.legs = legs; g.bonds = bonds; g.pin_order = pin_points;
    // This helper is topological: points need not lie on the drawing grid, but
    // NaNs/infinities cannot be keys in the native ordered graph or point sets.
    const auto finite = [](Point p) {
        if (!std::isfinite(p.first) || !std::isfinite(p.second))
            throw SchematicRouteError("route components: points must be finite");
    };
    for (const auto& edges : {&g.legs, &g.bonds})
        for (const auto& edge : *edges) { finite(edge.first); finite(edge.second); }
    for (auto p : pin_points) finite(p);
    for (auto p : power_points) { finite(p); g.power_pts.add(p); }
    for (auto p : label_points) { finite(p); g.label_pts.add(p); }
    std::vector<std::vector<RoutePoint>> out;
    for (const auto& comp : components(g)) out.push_back(comp.values());
    return out;
}

std::vector<RoutePoint> schematic_route_join(const RouteGrid& grid,
        const std::string& net, const std::vector<RoutePoint>& first,
        const std::vector<RoutePoint>& second) {
    const auto a = bfs_points(first), b = bfs_points(second);
    try { return route_bfs_join(grid, net, a, b, grid_mm); }
    catch (const std::runtime_error&) {
        throw SchematicRouteError("net " + net + ": no free corridor joins its parts — placement must expand");
    }
}

SchematicRoutedSheet route_schematic(const CircuitSheetIr& circuit,
                                    const SchematicRoutePlacement& placement,
                                    const SchematicSymbolResolver& symbols) {
    RouteGrid grid;
    std::map<std::string, std::string> net_of_pin;
    std::map<std::string, NetGeom> geoms;
    for (const auto& net : circuit.nets) {
        geoms.try_emplace(net.name);
        for (const auto& pin : net.pins) net_of_pin[pin.ref + "." + pin.pin] = net.name;
    }
    using Pad = std::pair<std::string, std::string>;
    std::map<Pad, std::vector<Point>> pad_tips;
    std::vector<Pad> pad_order;
    for (const auto& part : placement.parts) {
        check_range({part.x, part.y});
        const auto& symbol = symbols(part.lib_id);
        for (const auto& pin : symbol.pins) {
            const auto tip = pin_page_position(pin, part.x, part.y, part.rotation);
            const auto key = part.ref + "." + pin.number;
            const auto net = net_of_pin.find(key);
            const auto owner = net == net_of_pin.end() ? "nc:" + key : net->second;
            std::vector<Cell> stem{cell(tip)};
            if (!std::isfinite(pin.length) || std::abs(pin.length / grid_mm) > std::numeric_limits<int>::max() - 1)
                throw SchematicRouteError("invalid pin length for " + key);
            const int steps = static_cast<int>(pin.length / grid_mm + 1e-6);
            const auto [dx, dy] = stem_dir(pin.rotation, part.rotation);
            for (int k = 1; k <= steps; ++k)
                stem.push_back(cell(rounded({tip.first + dx * k * grid_mm, tip.second + dy * k * grid_mm})));
            claim(grid, owner, stem, "stem " + key);
            if (net != net_of_pin.end()) {
                auto& g = geoms.at(net->second);
                auto [found, inserted] = g.pin_parts.try_emplace(tip);
                if (inserted) g.pin_order.push_back(tip);
                found->second.insert(part.ref);
                const Pad pad{part.ref, pin.number};
                auto [tips, new_pad] = pad_tips.try_emplace(pad);
                if (new_pad) pad_order.push_back(pad);
                tips->second.push_back(tip);
            }
        }
    }
    for (const auto& pad : pad_order) {
        const auto& tips = pad_tips.at(pad);
        auto& g = geoms.at(net_of_pin.at(pad.first + "." + pad.second));
        for (std::size_t i = 1; i < tips.size(); ++i) g.bonds.emplace_back(tips[i - 1], tips[i]);
    }
    for (const auto& power : placement.powers) {
        const auto& net = power.net_name();
        if (net == "PWR_FLAG") throw SchematicRouteError(power.ref + ": PWR_FLAG must carry net=<rail>");
        const auto found = geoms.find(net);
        if (found == geoms.end()) throw SchematicRouteError("power symbol " + power.ref + " on undeclared net " + repr(net));
        const auto pt = rounded({power.x, power.y});
        claim(grid, net, {cell(pt)}, "power " + power.ref);
        found->second.power_pts.add(pt);
    }
    const auto label = [&](const std::string& name, double x, double y, bool local) {
        const auto found = geoms.find(name);
        if (found == geoms.end())
            throw SchematicRouteError(std::string(local ? "local label " : "label ") + repr(name) + " is not a declared net");
        const auto pt = rounded({x, y});
        claim(grid, name, {cell(pt)}, (local ? "llabel " : "label ") + name);
        found->second.label_pts.add(pt);
    };
    for (const auto& h : placement.hlabels) label(h.name, h.x, h.y, false);
    for (const auto& h : placement.llabels) label(h.name, h.x, h.y, true);
    for (const auto& box : placement.boxes) {
        check_range({box.x0, box.y0}); check_range({box.x1, box.y1});
        grid.block_box(box.x0, box.y0, box.x1, box.y1, grid_mm);
    }
    for (const auto& [net, paths] : placement.plans) {
        const auto found = geoms.find(net);
        if (found == geoms.end()) throw SchematicRouteError("plan for undeclared net " + repr(net));
        for (const auto& path : paths) for (std::size_t i = 1; i < path.size(); ++i) {
            const auto a = rounded(path[i - 1]), b = rounded(path[i]);
            if (a == b) continue;
            claim(grid, net, cells(a, b), "wire " + net);
            found->second.legs.emplace_back(a, b);
        }
    }
    // Preserve net insertion order even for failure priority.
    for (const auto& net : circuit.nets) split_plans(geoms.at(net.name));
    for (const auto& net : circuit.nets) check_overlap(net.name, geoms.at(net.name));
    for (const auto& net : circuit.nets) {
        auto& g = geoms.at(net.name);
        auto comps = components(g);
        if (net.net_class == "power" || net.net_class == "ground") {
            for (const auto& comp : comps) if (!intersects(comp, g.power_pts))
                throw SchematicRouteError("power net " + net.name + ": drawn islet " + islet(comp) +
                    "… has no " + net.name + " power symbol — opens forbidden");
        } else {
            const bool bridged = placement.label_bridged.count(net.name) ||
                (net.net_class == "port" && comps.size() > 1 && std::all_of(comps.begin(), comps.end(),
                    [&](const auto& comp) { return intersects(comp, g.label_pts); }));
            if (bridged) {
                for (const auto& comp : comps) if (!intersects(comp, g.label_pts))
                    throw SchematicRouteError("label-bridged net " + net.name + ": islet " + islet(comp) +
                        "… has no " + net.name + " label — opens forbidden");
            } else while (comps.size() > 1) {
                std::stable_sort(comps.begin(), comps.end(), [](const auto& a, const auto& b) { return a.size() > b.size(); });
                std::vector<Point> path;
                const auto a = bfs_points(comps[0]), b = bfs_points(comps[1]);
                try { path = route_bfs_join(grid, net.name, a, b, grid_mm); }
                catch (const std::runtime_error&) {
                    throw SchematicRouteError("net " + net.name + ": no free corridor joins its parts — placement must expand");
                }
                for (std::size_t i = 1; i < path.size(); ++i) {
                    claim(grid, net.name, cells(path[i - 1], path[i]), "bfs " + net.name);
                    g.legs.emplace_back(path[i - 1], path[i]);
                }
                auto next = components(g);
                // Near-grid floating points can quantize together without
                // joining the original graph. Fail instead of looping forever.
                if (next.size() >= comps.size())
                    throw SchematicRouteError("net " + net.name + ": grid join made no connectivity progress");
                comps = std::move(next);
            }
            if (net.net_class == "port" && g.label_pts.size() == 0)
                throw SchematicRouteError("PORT net " + net.name + ": no label placed");
            if (!bridged && !comps.empty() && g.label_pts.size() && !intersects(comps.front(), g.label_pts))
                throw SchematicRouteError("PORT net " + net.name + ": label not on the drawn net");
        }
    }
    SchematicRoutedSheet out;
    for (const auto& net : circuit.nets) {
        const auto& g = geoms.at(net.name);
        std::map<Point, std::size_t> degree;
        for (const auto& [a, b] : g.legs) {
            ++degree[a]; ++degree[b];
            out.segs.push_back({a.first, a.second, b.first, b.second, net.name});
        }
        for (const auto& [p, parts] : g.pin_parts) degree[p] += parts.size();
        for (auto p : g.power_pts.values()) ++degree[p];
        for (const auto& [p, count] : degree) if (count >= 3) out.junctions.push_back({p.first, p.second});
    }
    return out;
}

SchematicRoutedSheet route_schematic(const CircuitSheetIr& circuit,
                                    const SchematicRoutePlacement& placement,
                                    SymbolLibrary& library) {
    return route_schematic(circuit, placement, [&library](const std::string& id) -> const SymbolDef& { return library.get(id); });
}

SheetGeometry schematic_route_geometry(const SchematicRoutePlacement& placement, const SchematicRoutedSheet& routed) {
    return {placement.boxes, routed.segs, routed.junctions};
}

void apply_schematic_route(SchematicDesign& design, const SchematicRoutedSheet& routed) {
    std::vector<SchematicWire> wires;
    std::vector<SchematicJunction> junctions;
    wires.reserve(routed.segs.size()); junctions.reserve(routed.junctions.size());
    for (const auto& seg : routed.segs) wires.push_back({seg.x0, seg.y0, seg.x1, seg.y1});
    for (const auto& p : routed.junctions) junctions.push_back({p.x, p.y});
    design.wires = std::move(wires); design.junctions = std::move(junctions);
}

}  // namespace schgen
