#include "schgen/route_search.hpp"

#include <algorithm>
#include <queue>
#include <unordered_map>
#include <unordered_set>

namespace schgen::route {
namespace {

constexpr int directions = 8, undirected = 8;
constexpr std::array<int, directions> step_x{1, 1, 0, -1, -1, -1, 0, 1};
constexpr std::array<int, directions> step_y{0, 1, 1, 1, 0, -1, -1, -1};
constexpr std::int64_t straight = 1000, diagonal = 1414;
constexpr int sharpest = 2;
constexpr std::int64_t greed_base = 100;

struct Cell {
    std::int64_t column = 0, row = 0;
    std::size_t layer = 0;
};

using Key = std::uint64_t;

Key cell_key(const Cell& cell) {
    const std::uint64_t bits = 26, mask = (std::uint64_t{1} << bits) - 1;
    return (static_cast<std::uint64_t>(cell.layer) << (bits + bits)) | ((static_cast<std::uint64_t>(cell.column) & mask) << bits) |
           (static_cast<std::uint64_t>(cell.row) & mask);
}

Key state_key(const Cell& cell, int) { return cell_key(cell); }

struct Visit {
    std::int64_t cost = 0;
    Key parent = 0;
    Cell cell;
    int heading = undirected;
    bool start = false, closed = false;
};

struct Open {
    std::int64_t estimate = 0;
    std::uint64_t serial = 0;
    Key key = 0;
    bool operator>(const Open& other) const { return estimate != other.estimate ? estimate > other.estimate : serial > other.serial; }
};

class Search {
public:
    Search(const World& world, const SearchSetup& setup, int net) : world_(world), setup_(setup), net_(net), board_(world.board()) {
        const NetClass& entry = board_.rules.classes[board_.nets[static_cast<std::size_t>(net)].net_class];
        half_ = entry.track / 2;
        const Nm reach = half_ + entry.clearance;
        sag_ = setup.pitch * setup.pitch / (4 * std::max<Nm>(reach, 1)) + 1;
        greed_ = static_cast<std::int64_t>(constants::search_greed.value * static_cast<double>(greed_base));
        turn_ = setup.turn * straight / setup.pitch;
        via_ = setup.via * straight / setup.pitch;
    }

    Point point(const Cell& cell) const { return {board_.outline.x0 + cell.column * setup_.pitch, board_.outline.y0 + cell.row * setup_.pitch}; }

    std::vector<Cell> cells_on(const Item& item) const {
        std::vector<Cell> cells;
        const Box bound = item.shape.bound();
        const auto low = [&](Nm value, Nm origin) { return (value - origin + setup_.pitch - 1) / setup_.pitch; };
        const auto high = [&](Nm value, Nm origin) { return (value - origin) / setup_.pitch; };
        for (std::size_t layer = item.first; layer <= item.last; ++layer) {
            if (board_.rules.layers[layer].kind == LayerKind::plane) continue;
            for (std::int64_t column = low(bound.x0, board_.outline.x0); column <= high(bound.x1, board_.outline.x0); ++column)
                for (std::int64_t row = low(bound.y0, board_.outline.y0); row <= high(bound.y1, board_.outline.y0); ++row) {
                    const Cell cell{column, row, layer};
                    if (touching(item.shape, disc(point(cell), 0))) cells.push_back(cell);
                }
        }
        return cells;
    }

    bool open_cell(const Cell& cell) {
        const Key key = cell_key(cell);
        const auto known = legal_.find(key);
        if (known != legal_.end()) return known->second;
        const Point at = point(cell);
        Item probe{ItemKind::track, net_, cell.layer, cell.layer, disc(at, half_ + sag_), 0, {}};
        bool free = at.x >= window_.x0 && at.x <= window_.x1 && at.y >= window_.y0 && at.y <= window_.y1;
        if (free) {
            if (!within(probe.shape, board_.outline, board_.rules.edge_clearance)) free = false;
            else {
                const std::vector<std::size_t> found = world_.conflicts(probe);
                free = found.empty();
                for (const std::size_t id : found) blockers_.insert(id);
            }
        }
        legal_.emplace(key, free);
        return free;
    }

    bool via_fits(const Cell& cell) {
        const Key key = cell_key({cell.column, cell.row, 0});
        const auto known = drill_.find(key);
        if (known != drill_.end()) return known->second;
        const Item probe = via(board_, net_, point(cell));
        bool free = within(probe.shape, board_.outline, board_.rules.edge_clearance);
        if (free) {
            const std::vector<std::size_t> found = world_.conflicts(probe);
            free = found.empty();
            for (const std::size_t id : found) blockers_.insert(id);
        }
        drill_.emplace(key, free);
        return free;
    }

    std::optional<std::pair<std::size_t, std::size_t>> span() const {
        const ViaKind& kind = board_.rules.vias[board_.rules.classes[board_.nets[static_cast<std::size_t>(net_)].net_class].via];
        return std::make_pair(kind.first, kind.last);
    }

    template <typename Goal, typename Estimate>
    std::optional<Key> run(const std::vector<Cell>& starts, const Goal& goal, const Estimate& estimate, bool drop) {
        std::priority_queue<Open, std::vector<Open>, std::greater<Open>> open;
        std::uint64_t serial = 0;
        for (const Cell& cell : starts) {
            const Key key = state_key(cell, undirected);
            if (visits_.count(key)) continue;
            legal_[cell_key(cell)] = true;
            visits_[key] = {0, key, cell, undirected, true, false};
            open.push({greed_ * estimate(cell) / greed_base, serial++, key});
        }
        const auto [low, high] = *span();
        while (!open.empty()) {
            const Open next = open.top();
            open.pop();
            Visit& visit = visits_[next.key];
            if (visit.closed) continue;
            visit.closed = true;
            if (++opened_ > setup_.budget) {
                exhausted_ = true;
                return std::nullopt;
            }
            const Visit here = visit;
            if (drop) {
                if (!here.start && here.cell.layer >= low && here.cell.layer <= high && via_fits(here.cell)) return next.key;
            } else if (goal(here.cell)) {
                return next.key;
            }
            const auto relax = [&](const Cell& cell, int heading, std::int64_t cost) {
                const Key key = state_key(cell, heading);
                const auto found = visits_.find(key);
                if (found != visits_.end() && found->second.cost <= cost) return;
                visits_[key] = {cost, next.key, cell, heading, false, false};
                open.push({cost + greed_ * estimate(cell) / greed_base, serial++, key});
            };
            for (int heading = 0; heading < directions; ++heading) {
                int bend = 0;
                if (here.heading != undirected) {
                    bend = std::abs(heading - here.heading);
                    bend = std::min(bend, directions - bend);
                    if (bend > sharpest) continue;
                }
                const Cell cell{here.cell.column + step_x[heading], here.cell.row + step_y[heading], here.cell.layer};
                if (!goal(cell) && !open_cell(cell)) continue;
                relax(cell, heading, here.cost + (heading % 2 == 0 ? straight : diagonal) + bend * turn_);
            }
            if (drop || here.cell.layer < low || here.cell.layer > high || !via_fits(here.cell)) continue;
            for (std::size_t layer = low; layer <= high; ++layer) {
                if (layer == here.cell.layer || board_.rules.layers[layer].kind == LayerKind::plane) continue;
                const Cell cell{here.cell.column, here.cell.row, layer};
                if (!goal(cell) && !open_cell(cell)) continue;
                relax(cell, undirected, here.cost + via_);
            }
        }
        return std::nullopt;
    }

    Path trace(Key end, bool drop) const {
        Path path;
        std::vector<const Visit*> chain;
        for (Key key = end;; key = visits_.at(key).parent) {
            chain.push_back(&visits_.at(key));
            if (visits_.at(key).start) break;
        }
        std::reverse(chain.begin(), chain.end());
        std::size_t from = 0;
        const auto flush = [&](std::size_t to) {
            if (to == from) return;
            const Point a = point(chain[from]->cell), b = point(chain[to]->cell);
            path.items.push_back(track(board_, net_, chain[from]->cell.layer, a, b));
            path.length += length_of(a, b);
            from = to;
        };
        for (std::size_t index = 1; index < chain.size(); ++index) {
            if (chain[index]->cell.layer != chain[index - 1]->cell.layer) {
                flush(index - 1);
                path.items.push_back(via(board_, net_, point(chain[index]->cell)));
                ++path.vias;
                from = index;
                continue;
            }
            if (index + 1 < chain.size() && chain[index + 1]->cell.layer == chain[index]->cell.layer && chain[index + 1]->heading == chain[index]->heading) continue;
            flush(index);
        }
        if (drop) {
            path.items.push_back(via(board_, net_, point(chain.back()->cell)));
            ++path.vias;
        }
        return path;
    }

    void set_window(const Box& window) {
        window_ = window;
        legal_.clear();
        drill_.clear();
        visits_.clear();
    }

    SearchResult result(std::optional<Path> path) const {
        SearchResult out;
        out.path = std::move(path);
        out.blockers.assign(blockers_.begin(), blockers_.end());
        std::sort(out.blockers.begin(), out.blockers.end());
        out.opened = opened_;
        out.exhausted = exhausted_;
        return out;
    }

    bool exhausted() const { return exhausted_; }
    const Box& outline() const { return board_.outline; }

private:
    const World& world_;
    const SearchSetup& setup_;
    int net_;
    const Board& board_;
    Nm half_ = 0, sag_ = 0;
    std::int64_t turn_ = 0, via_ = 0, greed_ = 0;
    Box window_;
    std::unordered_map<Key, bool> legal_, drill_;
    std::unordered_map<Key, Visit> visits_;
    std::unordered_set<std::size_t> blockers_;
    std::size_t opened_ = 0;
    bool exhausted_ = false;
};

Box grown_within(Box box, Nm by, const Box& limit) {
    return {std::max(limit.x0, box.x0 - by), std::max(limit.y0, box.y0 - by), std::min(limit.x1, box.x1 + by), std::min(limit.y1, box.y1 + by)};
}

bool covers(const Box& a, const Box& b) { return a.x0 <= b.x0 && a.y0 <= b.y0 && a.x1 >= b.x1 && a.y1 >= b.y1; }

SearchResult search(const World& world, const SearchSetup& setup, int net, const std::vector<std::size_t>& sources, const std::vector<std::size_t>& goals, bool drop) {
    Search engine(world, setup, net);
    std::vector<Cell> starts, ends;
    Box span = world.item(sources.front()).shape.bound();
    for (const std::size_t id : sources) {
        const std::vector<Cell> cells = engine.cells_on(world.item(id));
        starts.insert(starts.end(), cells.begin(), cells.end());
        span = layout::united(span, world.item(id).shape.bound());
    }
    std::unordered_set<Key> wanted;
    std::vector<Box> targets;
    for (const std::size_t id : goals) {
        for (const Cell& cell : engine.cells_on(world.item(id))) wanted.insert(cell_key(cell));
        targets.push_back(world.item(id).shape.bound());
        span = layout::united(span, world.item(id).shape.bound());
    }
    if (starts.empty() || (!drop && wanted.empty())) return engine.result(std::nullopt);
    const auto goal = [&](const Cell& cell) { return wanted.count(cell_key(cell)) != 0; };
    const auto estimate = [&](const Cell& cell) -> std::int64_t {
        if (drop) return 0;
        const Point at = engine.point(cell);
        std::int64_t best = -1;
        for (const Box& target : targets) {
            const std::int64_t dx = std::max<Nm>({target.x0 - at.x, at.x - target.x1, 0}) / setup.pitch;
            const std::int64_t dy = std::max<Nm>({target.y0 - at.y, at.y - target.y1, 0}) / setup.pitch;
            const std::int64_t value = straight * std::max(dx, dy) + (diagonal - straight) * std::min(dx, dy);
            if (best < 0 || value < best) best = value;
        }
        return best;
    };
    Nm margin = setup.margin;
    for (;;) {
        const Box window = grown_within(span, margin, engine.outline());
        engine.set_window(window);
        if (const auto end = engine.run(starts, goal, estimate, drop)) return engine.result(engine.trace(*end, drop));
        if (engine.exhausted() || covers(window, engine.outline())) return engine.result(std::nullopt);
        margin *= static_cast<Nm>(constants::search_growth.value);
    }
}

}

SearchResult find_path(const World& world, const SearchSetup& setup, int net, const std::vector<std::size_t>& sources, const std::vector<std::size_t>& goals) {
    if (sources.empty() || goals.empty()) throw RouteError("route: a path needs a source and a goal");
    return search(world, setup, net, sources, goals, false);
}

SearchResult find_plane_drop(const World& world, const SearchSetup& setup, int net, const std::vector<std::size_t>& sources) {
    if (sources.empty()) throw RouteError("route: a plane drop needs a source");
    return search(world, setup, net, sources, {}, true);
}

}
