#include "schematic_place_internal.hpp"

#include "schgen/occupancy.hpp"
#include "schgen/turn.hpp"
#include "schgen/validation.hpp"

#include <cmath>

#if defined(__clang__)
#pragma clang fp contract(off)
#endif

namespace schgen::schematic_place {
namespace {
double r3(double value) { return py_round(value, static_cast<int>(COORDINATE_DECIMALS.value)); }
bool rail(const CircuitNetIr& n) { return n.net_class == "power" || n.net_class == "ground"; }
bool has(const Refs& refs, const std::string& ref) { return std::find(refs.begin(), refs.end(), ref) != refs.end(); }
void require(bool value, const std::string& message) {
    if (!value) throw SchematicPlaceError(message);
}
std::optional<RouteCell> cell_at(Point p) {
    const Point q{r3(p.first), r3(p.second)};
    if (!route_snap_ok(q.first, U) || !route_snap_ok(q.second, U)) return std::nullopt;
    return route_cell_of(q.first, q.second, U);
}
std::optional<std::vector<RouteCell>> cells_along(Point a, Point b) {
    const auto ca = cell_at(a), cb = cell_at(b);
    if (!ca || !cb || (ca->first != cb->first && ca->second != cb->second)) return std::nullopt;
    return route_cells_between({r3(a.first), r3(a.second)}, {r3(b.first), r3(b.second)}, U);
}
const std::string* owner_at(const std::map<RouteCell, std::string>& map, RouteCell cell) {
    const auto found = map.find(cell);
    return found == map.end() ? nullptr : &found->second;
}
std::string at_text(RouteCell cell) {
    const auto p = route_point_of(cell.first, cell.second, U);
    return "(" + std::to_string(p.first) + ", " + std::to_string(p.second) + ")";
}
struct StemRun { std::string owner; std::vector<RouteCell> cells; std::vector<RouteCell> escape; };
std::optional<StemRun> stem_run(const SchematicPlacedPart& placed, const SymbolPin& pin, const CircuitNetIr* net) {
    StemRun run;
    run.owner = net ? net->name : "nc:" + placed.ref + "." + pin.number;
    const auto tip = pin_page_position(pin, placed.x, placed.y, placed.rotation);
    const auto [dx, dy] = stem_dir(pin.rotation, placed.rotation);
    const int steps = static_cast<int>(pin.length / U + STEM_ROUNDING.value);
    for (int k = 0; k <= steps; ++k) {
        const auto cell = cell_at({tip.first + dx * k * U, tip.second + dy * k * U});
        if (!cell) return std::nullopt;
        run.cells.push_back(*cell);
    }
    for (int k = 0; k <= static_cast<int>(PIN_ESCAPE.value); ++k) {
        const auto cell = cell_at({tip.first - dx * k * U, tip.second - dy * k * U});
        if (!cell) return std::nullopt;
        run.escape.push_back(*cell);
    }
    return run;
}
struct Offset { int i, j; };
std::vector<Offset> ring_offsets() {
    const int reach = static_cast<int>(GRAFT_REACH.value);
    std::vector<Offset> out;
    for (int i = -reach; i <= reach; ++i) for (int j = -reach; j <= reach; ++j)
        if (std::abs(i) + std::abs(j) <= reach) out.push_back({i, j});
    const auto key = [](const Offset& o) {
        return std::make_tuple(std::abs(o.i) + std::abs(o.j), std::min(std::abs(o.i), std::abs(o.j)), o.j != 0, o.j < 0, o.i < 0);
    };
    std::stable_sort(out.begin(), out.end(), [&](const Offset& a, const Offset& b) { return key(a) < key(b); });
    return out;
}
}  // namespace

void Engine::_reserve(const std::string& name, Point a, Point b) {
    _reserved.push_back({name, {r3(a.first), r3(a.second)}, {r3(b.first), r3(b.second)}});
}
void Engine::_release(const std::string& name) {
    _reserved.erase(std::remove_if(_reserved.begin(), _reserved.end(),
        [&](const ReservedWire& wire) { return wire.net == name; }), _reserved.end());
}

Checkpoint Engine::_checkpoint() const { return {_mark(), _pwr, _flg, _done, pl.label_bridged}; }
void Engine::_rollback(const Checkpoint& saved) {
    const auto& mark = saved.mark;
    pl.parts.erase(pl.parts.begin() + static_cast<std::ptrdiff_t>(mark.parts), pl.parts.end());
    pl.powers.erase(pl.powers.begin() + static_cast<std::ptrdiff_t>(mark.powers), pl.powers.end());
    pl.hlabels.erase(pl.hlabels.begin() + static_cast<std::ptrdiff_t>(mark.hlabels), pl.hlabels.end());
    pl.llabels.erase(pl.llabels.begin() + static_cast<std::ptrdiff_t>(mark.llabels), pl.llabels.end());
    pl.no_connects.erase(pl.no_connects.begin() + static_cast<std::ptrdiff_t>(mark.no_connects), pl.no_connects.end());
    pl.boxes.erase(pl.boxes.begin() + static_cast<std::ptrdiff_t>(mark.boxes), pl.boxes.end());
    _open_stubs.erase(_open_stubs.begin() + static_cast<std::ptrdiff_t>(mark.stubs), _open_stubs.end());
    for (auto entry = pl.plans.begin(); entry != pl.plans.end();) {
        const auto kept = mark.plans.find(entry->first);
        if (kept == mark.plans.end()) { entry = pl.plans.erase(entry); continue; }
        entry->second.erase(entry->second.begin() + static_cast<std::ptrdiff_t>(kept->second), entry->second.end());
        ++entry;
    }
    _pwr = saved.powers; _flg = saved.flags; _done = saved.done; pl.label_bridged = saved.bridged;
}

Occupancy Engine::_occupancy(const PlacementMark& upto, bool guard_pins) {
    Occupancy out;
    out.strict = guard_pins;
    for (std::size_t i = 0; i < upto.parts; ++i) {
        const auto& placed = pl.parts[i];
        const auto& symbol = lib.get(placed.lib_id);
        for (const auto& pin : symbol.pins) {
            const auto* n = net_of(placed.ref, pin.number);
            const auto run = stem_run(placed, pin, n);
            if (!run) continue;
            for (const auto cell : run->cells) out.fixed.emplace(cell, run->owner);
            if (guard_pins && n && has(multi, placed.ref)) for (const auto cell : run->escape) out.guard.emplace(cell, run->owner);
        }
    }
    for (std::size_t i = 0; i < upto.powers; ++i)
        if (const auto cell = cell_at({pl.powers[i].x, pl.powers[i].y})) out.fixed.emplace(*cell, pl.powers[i].net_name());
    for (std::size_t i = 0; i < upto.hlabels; ++i)
        if (const auto cell = cell_at({pl.hlabels[i].x, pl.hlabels[i].y})) out.fixed.emplace(*cell, pl.hlabels[i].name);
    for (std::size_t i = 0; i < upto.llabels; ++i)
        if (const auto cell = cell_at({pl.llabels[i].x, pl.llabels[i].y})) out.fixed.emplace(*cell, pl.llabels[i].name);
    for (std::size_t i = 0; i < upto.boxes; ++i)
        out.walls.block_box(pl.boxes[i].x0, pl.boxes[i].y0, pl.boxes[i].x1, pl.boxes[i].y1, U);
    const auto wire = [&](const std::string& name, Point a, Point b) {
        if (a == b) return;
        out.wires.push_back({a.first, a.second, b.first, b.second, name});
        if (const auto cells = cells_along(a, b)) for (const auto cell : *cells) out.wired.emplace(cell, name);
    };
    for (const auto& [name, paths] : pl.plans) {
        const auto kept = upto.plans.find(name);
        const std::size_t count = kept == upto.plans.end() ? 0 : kept->second;
        for (std::size_t i = 0; i < count && i < paths.size(); ++i)
            for (std::size_t j = 1; j < paths[i].size(); ++j) wire(name, paths[i][j - 1], paths[i][j]);
    }
    for (const auto& held : _reserved) wire(held.net, held.a, held.b);
    return out;
}

std::optional<std::string> Engine::_fault_since(const PlacementMark& since, const Occupancy& base) {
    std::map<RouteCell, std::string> fixed, wired;
    const auto pin_down = [&](std::optional<RouteCell> cell, const std::string& owner, const std::string& what) -> std::optional<std::string> {
        if (!cell) return what + " is off the drawing grid";
        for (const std::map<RouteCell, std::string>* map : {&base.fixed, &base.wired, &base.guard, &std::as_const(fixed)})
            if (const auto* other = owner_at(*map, *cell); other && *other != owner)
                return what + " lands on " + *other + " at " + at_text(*cell);
        if (base.strict && !base.walls.free_or(owner, *cell)) return what + " lands inside a symbol or text at " + at_text(*cell);
        fixed.emplace(*cell, owner);
        return std::nullopt;
    };
    for (std::size_t i = since.parts; i < pl.parts.size(); ++i) {
        const auto& placed = pl.parts[i];
        for (const auto& pin : lib.get(placed.lib_id).pins) {
            const auto run = stem_run(placed, pin, net_of(placed.ref, pin.number));
            if (!run) return placed.ref + "." + pin.number + " is off the drawing grid";
            for (const auto cell : run->cells)
                if (const auto fault = pin_down(cell, run->owner, placed.ref + "." + pin.number)) return fault;
        }
    }
    for (std::size_t i = since.powers; i < pl.powers.size(); ++i)
        if (const auto fault = pin_down(cell_at({pl.powers[i].x, pl.powers[i].y}), pl.powers[i].net_name(), pl.powers[i].ref)) return fault;
    for (std::size_t i = since.hlabels; i < pl.hlabels.size(); ++i)
        if (const auto fault = pin_down(cell_at({pl.hlabels[i].x, pl.hlabels[i].y}), pl.hlabels[i].name, "label " + pl.hlabels[i].name)) return fault;
    for (std::size_t i = since.llabels; i < pl.llabels.size(); ++i)
        if (const auto fault = pin_down(cell_at({pl.llabels[i].x, pl.llabels[i].y}), pl.llabels[i].name, "label " + pl.llabels[i].name)) return fault;

    RouteGrid fresh;
    const double clearance = default_engine_config.visual_clearance_mm;
    for (std::size_t i = since.boxes; i < pl.boxes.size(); ++i) {
        const auto& box = pl.boxes[i];
        fresh.block_box(box.x0, box.y0, box.x1, box.y1, U);
        for (std::size_t j = 0; j < i; ++j) {
            const auto& other = pl.boxes[j];
            if (other.owner == box.owner && !(visual_text_kind(other.kind) && visual_text_kind(box.kind))) continue;
            if (other.intersects(box, clearance))
                return box.kind + "(" + box.owner + ") overlaps " + other.kind + "(" + other.owner + ")";
        }
    }
    const std::string nobody;
    const auto walled = [&](const RouteGrid& grid, RouteCell cell) { return !grid.free_or(nobody, cell); };
    const auto own_fixed = [&](RouteCell cell, const std::string& name) {
        const auto* held = owner_at(base.fixed, cell);
        if (!held) held = owner_at(fixed, cell);
        return held && *held == name;
    };
    if (since.boxes < pl.boxes.size()) {
        Box4 hull = pl.boxes[since.boxes].bounds();
        for (std::size_t i = since.boxes; i < pl.boxes.size(); ++i) {
            const auto b = pl.boxes[i].bounds();
            hull = {std::min(hull.x0, b.x0), std::min(hull.y0, b.y0), std::max(hull.x1, b.x1), std::max(hull.y1, b.y1)};
        }
        for (const auto& wire : base.wires) {
            if (std::max(wire.x0, wire.x1) < hull.x0 - U || std::min(wire.x0, wire.x1) > hull.x1 + U
                || std::max(wire.y0, wire.y1) < hull.y0 - U || std::min(wire.y0, wire.y1) > hull.y1 + U) continue;
            for (std::size_t i = since.boxes; i < pl.boxes.size(); ++i)
                if (wire_over_text(wire, pl.boxes[i])) return "wire(" + wire.net + ") over " + pl.boxes[i].kind + "(" + pl.boxes[i].owner + ")";
            if (const auto cells = cells_along({wire.x0, wire.y0}, {wire.x1, wire.y1}))
                for (const auto cell : *cells)
                    if (walled(fresh, cell) && !own_fixed(cell, wire.net)) return "wire(" + wire.net + ") is covered at " + at_text(cell);
        }
        for (const auto& [cell, owner] : base.guard)
            if (walled(fresh, cell) && !own_fixed(cell, owner)) return "the way out of a pin on " + owner + " is covered at " + at_text(cell);
        if (base.strict) for (const auto& [cell, owner] : base.fixed)
            if (walled(fresh, cell)) return "a pin or symbol end on " + owner + " is covered at " + at_text(cell);
    }
    for (const auto& [name, paths] : pl.plans) {
        const auto kept = since.plans.find(name);
        for (std::size_t i = kept == since.plans.end() ? 0 : kept->second; i < paths.size(); ++i)
            for (std::size_t j = 1; j < paths[i].size(); ++j) {
                const auto a = paths[i][j - 1], b = paths[i][j];
                if (a == b) continue;
                const auto cells = cells_along(a, b);
                if (!cells) return "wire(" + name + ") is off the drawing grid or not orthogonal";
                for (const auto cell : *cells) {
                    for (const std::map<RouteCell, std::string>* map : {&base.fixed, &std::as_const(fixed)})
                        if (const auto* held = owner_at(*map, cell); held && *held != name)
                            return "wire(" + name + ") runs into " + *held + " at " + at_text(cell);
                    if (!own_fixed(cell, name) && (walled(base.walls, cell) || walled(fresh, cell)))
                        return "wire(" + name + ") runs through a symbol or text at " + at_text(cell);
                    for (const std::map<RouteCell, std::string>* map : {&base.wired, &base.guard, &std::as_const(wired)})
                        if (const auto* held = owner_at(*map, cell); held && *held != name)
                            return "wire(" + name + ") runs into " + *held + " at " + at_text(cell);
                    wired.emplace(cell, name);
                }
                const VisualSegment wire{a.first, a.second, b.first, b.second, name};
                const Point first = paths[i].front(), last = paths[i].back();
                const VisualBox lane{std::min(a.first, b.first), std::min(a.second, b.second), std::max(a.first, b.first), std::max(a.second, b.second), "wire", name};
                const auto ends_in = [&](const VisualBox& box) {
                    for (const auto& end : {first, last})
                        if (box.x0 - clearance <= end.first && end.first <= box.x1 + clearance
                            && box.y0 - clearance <= end.second && end.second <= box.y1 + clearance) return true;
                    return false;
                };
                for (const auto& box : pl.boxes) {
                    if (wire_over_text(wire, box)) return "wire(" + name + ") over " + box.kind + "(" + box.owner + ")";
                    if (base.strict && lane.intersects(box, clearance) && !ends_in(box))
                        return "wire(" + name + ") brushes " + box.kind + "(" + box.owner + ")";
                }
            }
    }
    return std::nullopt;
}
std::optional<std::string> Engine::_fault_since(const PlacementMark& since) {
    return _fault_since(since, _occupancy(since, false));
}

std::vector<Point> Engine::_net_points(const std::string& name) {
    std::vector<Point> out;
    const auto add = [&](Point p) {
        const Point q{r3(p.first), r3(p.second)};
        if (std::find(out.begin(), out.end(), q) == out.end()) out.push_back(q);
    };
    for (const auto& placed : pl.parts) for (const auto& pin : lib.get(placed.lib_id).pins) {
        const auto* n = net_of(placed.ref, pin.number);
        if (n && n->name == name) add(pin_page_position(pin, placed.x, placed.y, placed.rotation));
    }
    for (const auto& [planned, paths] : pl.plans) if (planned == name)
        for (const auto& path : paths) for (const auto& p : path) add(p);
    return out;
}

std::string Engine::_graft_tag(const std::string& name, const std::string& ref) const {
    const auto& n = net(name);
    if (n.net_class == "port") {
        const bool exported = std::any_of(pl.hlabels.begin(), pl.hlabels.end(), [&](const auto& h) { return h.name == name; });
        return exported ? "" : "port";
    }
    if (pl.label_bridged.count(name)) return "local";
    const bool alone = std::none_of(n.pins.begin(), n.pins.end(), [&](const auto& p) { return p.ref != ref; });
    return alone ? "local" : "";
}

void Engine::_graft_end(const std::string& name, const std::string& ref, Point at, Point outward) {
    const bool upright = outward.first == 0;
    if (rail(net(name))) {
        const bool grounded = net(name).net_class == "ground";
        if (upright) { power(name, at.first, at.second, _power_rot(name, outward.second > 0)); return; }
        const Point knee{r3(at.first + outward.first * GRAFT_STEP), at.second};
        const Point end{knee.first, r3(knee.second + (grounded ? 1 : -1) * GRAFT_STEP)};
        pl.plan(name, {at, knee, end});
        power(name, end.first, end.second, _power_rot(name, grounded));
        return;
    }
    const auto tag = _graft_tag(name, ref);
    if (tag.empty()) return;
    const Point end{r3(at.first + outward.first * GRAFT_STEP), r3(at.second + outward.second * GRAFT_STEP)};
    pl.plan(name, {at, end});
    const Tuned turned = upright ? (outward.second > 0 ? LABEL_BELOW : LABEL_ABOVE) : (outward.first < 0 ? LABEL_LEFT : Tuned{0, ""});
    if (tag == "port") label(name, end.first, end.second, static_cast<int>(turned.value));
    else { llabel(name, end.first, end.second, upright ? 0 : static_cast<int>(turned.value)); _bridge(name); }
}

bool Engine::_graftable(const std::string& ref) {
    if (has(multi, ref)) return false;
    const auto numbers = lib.pin_numbers(part(ref).lib_id);
    if (numbers.size() != 2) return false;
    const auto* a = net_of(ref, *numbers.begin());
    const auto* b = net_of(ref, *std::next(numbers.begin()));
    if (!a || !b) return false;
    const bool decoupling = (a->net_class == "power" && b->net_class == "ground") || (a->net_class == "ground" && b->net_class == "power");
    return !decoupling;
}

bool Engine::_graft_settled(const std::string& ref, bool plant) {
    const auto before = _done;
    if (!_graft(ref, plant, static_cast<int>(GRAFT_REACH.value))) return false;
    for (const auto& seated : _done) if (!before.count(seated)) _forget(seated);
    return true;
}

bool Engine::_graft(const std::string& ref, bool plant, int reach) {
    require(_graftable(ref), ref + ": only a two-pin part off a signal net can be seated beside its net");
    const auto numbers = lib.pin_numbers(part(ref).lib_id);
    const std::array<const CircuitNetIr*, 2> ends{net_of(ref, *numbers.begin()), net_of(ref, *std::next(numbers.begin()))};
    const CircuitNetIr* near = nullptr;
    std::vector<Point> points;
    for (const auto* candidate : ends) {
        if (rail(*candidate)) continue;
        auto found = _net_points(candidate->name);
        if (found.empty()) continue;
        near = candidate; points = std::move(found); break;
    }
    const bool planted = near == nullptr;
    if (planted && !plant) return false;
    if (planted) {
        near = rail(*ends[0]) || !rail(*ends[1]) ? ends[0] : ends[1];
        const auto extent = _extent();
        points = {{gsnap(extent.x0 + GRAFT_APART.value * U), gceil(extent.y1 + GRAFT_APART.value * U)}};
    }
    const auto* far = near == ends[0] ? ends[1] : ends[0];
    std::set<Point> hubs;
    for (const auto& placed : pl.parts) if (has(multi, placed.ref))
        for (const auto& pin : lib.get(placed.lib_id).pins) {
            const auto tip = pin_page_position(pin, placed.x, placed.y, placed.rotation);
            hubs.insert({r3(tip.first), r3(tip.second)});
        }
    const auto& symbol = lib.get(part(ref).lib_id);
    const auto& near_pin = pin(symbol, _pin_of_net(ref, near->name));
    const auto& far_pin = pin(symbol, other_pin(ref, near_pin.number));
    struct Pose { int rotation; Point near_tip, far_tip, near_out, far_out; int rank; };
    std::vector<Pose> poses;
    for (int rotation = 0; rotation < static_cast<int>(FULL_TURN.value); rotation += static_cast<int>(QUARTER_TURN.value)) {
        const auto near_tip = pin_page_position(near_pin, 0.0, 0.0, rotation), far_tip = pin_page_position(far_pin, 0.0, 0.0, rotation);
        const auto near_stem = stem_dir(near_pin.rotation, rotation), far_stem = stem_dir(far_pin.rotation, rotation);
        const double dx = far_tip.first - near_tip.first, dy = far_tip.second - near_tip.second;
        const bool rises = far->net_class == "power";
        const bool upright = std::fabs(dy) >= std::fabs(dx);
        const int rank = upright ? ((dy > 0) != rises ? 0 : 1) : 2;
        poses.push_back({rotation, near_tip, far_tip, {-near_stem.first, -near_stem.second}, {-far_stem.first, -far_stem.second}, rank});
    }
    std::stable_sort(poses.begin(), poses.end(), [](const Pose& a, const Pose& b) { return a.rank < b.rank; });
    const auto saved = _checkpoint();
    const auto base = _occupancy(saved.mark, true);
    static const std::vector<Offset> offsets = ring_offsets();
    Refs followers;
    if (!rail(*far)) for (const auto& p : c.parts)
        if (p.ref != ref && !_done.count(p.ref) && _graftable(p.ref)
            && std::any_of(far->pins.begin(), far->pins.end(), [&](const auto& pin_ref) { return pin_ref.ref == p.ref; })) followers.push_back(p.ref);
    for (const auto& offset : offsets) for (const auto& from : points) {
        if (std::abs(offset.i) + std::abs(offset.j) > reach) return false;
        if (offset.i == 0 && offset.j == 0 && hubs.count(from)) continue;
        const Point seat{r3(from.first + offset.i * GRAFT_STEP), r3(from.second + offset.j * GRAFT_STEP)};
        std::vector<std::vector<Point>> ways;
        if (planted || (offset.i == 0 && offset.j == 0)) ways.push_back({});
        else if (offset.i == 0 || offset.j == 0) ways.push_back({from, seat});
        else { ways.push_back({from, {seat.first, from.second}, seat}); ways.push_back({from, {from.first, seat.second}, seat}); }
        for (const auto& pose : poses) for (const auto& way : ways) for (const std::string side : {"right", "left"}) {
            if (!way.empty()) pl.plan(near->name, way);
            if (planted) _graft_end(near->name, ref, seat, pose.near_out);
            const Point centre{r3(seat.first - pose.near_tip.first), r3(seat.second - pose.near_tip.second)};
            passive(ref, centre.first, centre.second, pose.rotation, side);
            const auto pin_texts = pin_text_boxes(symbol, pl.parts.back());
            pl.boxes.insert(pl.boxes.end(), pin_texts.begin(), pin_texts.end());
            _graft_end(far->name, ref, {r3(centre.first + pose.far_tip.first), r3(centre.second + pose.far_tip.second)}, pose.far_out);
            bool settled = !_fault_since(saved.mark, base);
            for (std::size_t k = 0; settled && k < followers.size(); ++k)
                settled = _done.count(followers[k]) != 0 || _graft(followers[k], false, static_cast<int>(GRAFT_NEAR.value));
            if (settled) return true;
            _rollback(saved);
        }
    }
    return false;
}

void Engine::_forget(const std::string& ref) {
    Refs emptied;
    for (auto& [name, refs] : hang) {
        refs.erase(std::remove(refs.begin(), refs.end(), ref), refs.end());
        if (refs.empty()) emptied.push_back(name);
    }
    for (const auto& name : emptied) hang.erase(name);
    emptied.clear();
    for (auto& [name, legs] : pull) {
        legs.erase(std::remove_if(legs.begin(), legs.end(), [&](const auto& leg) { return leg.first == ref; }), legs.end());
        if (legs.empty()) emptied.push_back(name);
    }
    for (const auto& name : emptied) pull.erase(name);
    series.erase(std::remove_if(series.begin(), series.end(), [&](const Leg& leg) { return leg.ref == ref; }), series.end());
}

void Engine::_defer(const Refs& refs) { _grafts.insert(_grafts.end(), refs.begin(), refs.end()); }

void Engine::_stack_or_defer(const FloatChain& chain, Point pt, const std::string& side) {
    const auto saved = _checkpoint();
    _stack_from_pin(chain, pt, side);
    if (!_fault_since(saved.mark)) return;
    _rollback(saved);
    for (const auto& leg : chain.legs) _defer({leg.ref});
    for (const auto& [name, refs] : chain.hangs) { (void)name; _defer(refs); }
}

void Engine::_graft_pending() {
    const auto pending = _grafts;
    _grafts.clear();
    for (const auto& ref : pending) if (!_done.count(ref) && !_graft_settled(ref, false)) _grafts.push_back(ref);
}

void Engine::_graft_unplaced() {
    while (true) {
        Refs waiting;
        for (const auto& p : c.parts) if (!_done.count(p.ref) && _graftable(p.ref)) waiting.push_back(p.ref);
        if (waiting.empty()) return;
        const auto anchored = std::find_if(waiting.begin(), waiting.end(), [&](const std::string& ref) {
            for (const auto& number : lib.pin_numbers(part(ref).lib_id)) {
                const auto* n = net_of(ref, number);
                if (n && !rail(*n) && !_net_points(n->name).empty()) return true;
            }
            return false;
        });
        const std::string next = anchored == waiting.end() ? waiting.front() : *anchored;
        std::sort(waiting.begin(), waiting.end());
        std::string names;
        for (const auto& ref : waiting) names += (names.empty() ? "'" : ", '") + ref + "'";
        require(_graft_settled(next, anchored == waiting.end()), "engine left parts unplaced: [" + names + "] — no free seat within "
            + std::to_string(static_cast<int>(GRAFT_REACH.value * GRAFT_STEP)) + " mm of the nets they hang from, first " + next);
    }
}

}  // namespace schgen::schematic_place
