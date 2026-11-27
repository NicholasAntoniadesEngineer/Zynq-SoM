#include "schgen/route_board.hpp"

#include <algorithm>

namespace schgen::route {
namespace {

const Nm cell = static_cast<Nm>(constants::index_cell.value);

Nm floor_cell(Nm value) { return value >= 0 ? value / cell : -((-value + cell - 1) / cell); }

}

Nm Rules::clearance(std::size_t first, std::size_t second) const { return std::max(classes.at(first).clearance, classes.at(second).clearance); }

void Rules::validate() const {
    if (layers.empty() || layers.size() > static_cast<std::size_t>(constants::layer_limit.value))
        throw RouteError("route: a board states between 1 and " + std::to_string(static_cast<int>(constants::layer_limit.value)) + " copper layers, not " +
                         std::to_string(layers.size()));
    if (classes.empty()) throw RouteError("route: no net class is stated");
    for (const Layer& layer : layers)
        if ((layer.kind == LayerKind::plane) != (layer.plane_net != no_net))
            throw RouteError("route: layer " + layer.name + " must state a plane net exactly when it is a plane");
    for (const NetClass& entry : classes) {
        if (entry.track <= 0 || entry.clearance <= 0) throw RouteError("route: net class " + entry.name + " needs a positive track width and clearance");
        if (entry.via >= vias.size()) throw RouteError("route: net class " + entry.name + " names a via kind that is not stated");
    }
    for (const ViaKind& entry : vias)
        if (entry.pad <= entry.drill || entry.drill <= 0 || entry.first > entry.last || entry.last >= layers.size())
            throw RouteError("route: via kind " + entry.name + " needs a drill, a larger pad and a layer span inside the stack");
    if (edge_clearance < 0 || hole_clearance < 0 || hole_spacing < 0) throw RouteError("route: clearances cannot be negative");
}

void Board::validate() const {
    rules.validate();
    if (outline.x1 <= outline.x0 || outline.y1 <= outline.y0) throw RouteError("route: the board outline is empty");
    for (const Net& net : nets)
        if (net.net_class >= rules.classes.size()) throw RouteError("route: net " + net.name + " names a class that is not stated");
    for (const Item& item : fixed) {
        if (item.first > item.last || item.last >= rules.layers.size()) throw RouteError("route: " + item.owner + " lies outside the layer stack");
        if (item.net != no_net && static_cast<std::size_t>(item.net) >= nets.size()) throw RouteError("route: " + item.owner + " names a net that is not stated");
        if (item.shape.count == 0) throw RouteError("route: " + item.owner + " has no shape");
    }
}

Item track(const Board& board, int net, std::size_t layer, Point from, Point to) {
    const NetClass& entry = board.rules.classes.at(board.nets.at(static_cast<std::size_t>(net)).net_class);
    const Nm half = entry.track / 2;
    return {ItemKind::track, net, layer, layer, capsule(from, to, half), 0, {}};
}

Item via(const Board& board, int net, Point at) {
    const NetClass& entry = board.rules.classes.at(board.nets.at(static_cast<std::size_t>(net)).net_class);
    const ViaKind& kind = board.rules.vias.at(entry.via);
    const Nm half = kind.pad / 2;
    return {ItemKind::via, net, kind.first, kind.last, disc(at, half), kind.drill, {}};
}

const char* kind_name(ItemKind kind) {
    switch (kind) {
    case ItemKind::pad: return "pad";
    case ItemKind::track: return "track";
    case ItemKind::via: return "via";
    case ItemKind::keepout: return "keepout";
    }
    return "item";
}

World::World(const Board& board) : board_(board) {
    board.validate();
    for (const NetClass& entry : board.rules.classes) reach_ = std::max(reach_, entry.clearance);
    reach_ = std::max({reach_, board.rules.hole_clearance, board.rules.hole_spacing});
    for (const Item& item : board.fixed) add(item);
    fixed_ = items_.size();
    journal_.clear();
}

World::Key World::key(std::size_t layer, Nm column, Nm row) {
    const std::uint64_t bits = 26, mask = (std::uint64_t{1} << bits) - 1;
    return (static_cast<std::uint64_t>(layer) << (bits + bits)) | ((static_cast<std::uint64_t>(column) & mask) << bits) | (static_cast<std::uint64_t>(row) & mask);
}

template <typename Visit> void World::each_cell(const Item& item, const Visit& visit) const {
    const Box bound = item.shape.bound();
    for (std::size_t layer = item.first; layer <= item.last; ++layer)
        for (Nm column = floor_cell(bound.x0 - reach_); column <= floor_cell(bound.x1 + reach_); ++column)
            for (Nm row = floor_cell(bound.y0 - reach_); row <= floor_cell(bound.y1 + reach_); ++row) visit(key(layer, column, row));
}

void World::index(std::size_t id, bool insert) {
    const Item& item = items_[id];
    const Box bound = item.shape.bound();
    for (std::size_t layer = item.first; layer <= item.last; ++layer)
        for (Nm column = floor_cell(bound.x0); column <= floor_cell(bound.x1); ++column)
            for (Nm row = floor_cell(bound.y0); row <= floor_cell(bound.y1); ++row) {
                std::vector<std::size_t>& bucket = cells_[key(layer, column, row)];
                if (insert) bucket.push_back(id);
                else bucket.erase(std::remove(bucket.begin(), bucket.end(), id), bucket.end());
            }
}

bool World::clash(const Item& candidate, const Item& other) const {
    if (candidate.kind == ItemKind::keepout || other.kind == ItemKind::keepout) {
        if (candidate.kind == other.kind) return false;
        return touching(candidate.shape, other.shape);
    }
    const bool same = candidate.net != no_net && candidate.net == other.net;
    if (candidate.drill > 0 && other.drill > 0 && !(same && candidate.shape.core[0] == other.shape.core[0])) {
        const Shape first = disc(candidate.shape.core[0], candidate.drill / 2), second = disc(other.shape.core[0], other.drill / 2);
        if (!apart(first, second, board_.rules.hole_spacing)) return true;
    }
    if (same) return false;
    const auto class_of = [&](const Item& item) { return item.net == no_net ? std::size_t{0} : board_.nets[static_cast<std::size_t>(item.net)].net_class; };
    if (!apart(candidate.shape, other.shape, board_.rules.clearance(class_of(candidate), class_of(other)))) return true;
    if (candidate.drill > 0 && !apart(disc(candidate.shape.core[0], candidate.drill / 2), other.shape, board_.rules.hole_clearance)) return true;
    return other.drill > 0 && !apart(disc(other.shape.core[0], other.drill / 2), candidate.shape, board_.rules.hole_clearance);
}

std::vector<std::size_t> World::conflicts(const Item& candidate) const {
    std::vector<std::size_t> found;
    each_cell(candidate, [&](Key cell_key) {
        const auto bucket = cells_.find(cell_key);
        if (bucket == cells_.end()) return;
        for (const std::size_t id : bucket->second)
            if (live_[id] && clash(candidate, items_[id])) found.push_back(id);
    });
    std::sort(found.begin(), found.end());
    found.erase(std::unique(found.begin(), found.end()), found.end());
    return found;
}

std::optional<Conflict> World::conflict(const Item& candidate) const {
    if (candidate.kind != ItemKind::keepout && !within(candidate.shape, board_.outline, board_.rules.edge_clearance)) return Conflict{0, true};
    const std::vector<std::size_t> found = conflicts(candidate);
    if (found.empty()) return std::nullopt;
    return Conflict{found.front(), false};
}

std::size_t World::add(const Item& item) {
    items_.push_back(item);
    live_.push_back(1);
    index(items_.size() - 1, true);
    journal_.emplace_back(items_.size() - 1, true);
    return items_.size() - 1;
}

void World::remove(std::size_t id) {
    if (id < fixed_) throw RouteError("route: fixed copper cannot be removed");
    if (!live_.at(id)) return;
    index(id, false);
    live_[id] = 0;
    journal_.emplace_back(id, false);
}

void World::rollback(std::size_t mark) {
    while (journal_.size() > mark) {
        const auto [id, added] = journal_.back();
        journal_.pop_back();
        if (added) {
            index(id, false);
            live_[id] = 0;
        } else {
            index(id, true);
            live_[id] = 1;
        }
    }
}

std::vector<Item> World::routed() const {
    std::vector<Item> out;
    for (std::size_t id = fixed_; id < items_.size(); ++id)
        if (live_[id]) out.push_back(items_[id]);
    return out;
}

}
