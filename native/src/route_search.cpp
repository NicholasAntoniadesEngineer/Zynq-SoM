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
constexpr Nm neck_step = 1000, lane_cell = 1000000;

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
    Search(const World& world, const SearchSetup& setup, int net, bool guarded) : world_(world), setup_(setup), net_(net), board_(world.board()) {
        const NetClass& entry = board_.rules.classes[board_.nets[static_cast<std::size_t>(net)].net_class];
        half_ = entry.track / 2;
        const Nm reach = half_ + entry.clearance;
        sag_ = guarded ? setup.pitch * setup.pitch / (4 * std::max<Nm>(reach, 1)) + 1 : 0;
        greed_ = static_cast<std::int64_t>(setup.greed * static_cast<double>(greed_base));
        for (std::size_t index = 0; index < setup.lanes.size(); ++index) {
            const Lane& lane = setup.lanes[index];
            if (lane.net == net) continue;
            for (Nm column = lane.box.x0 / lane_cell; column <= lane.box.x1 / lane_cell; ++column)
                for (Nm row = lane.box.y0 / lane_cell; row <= lane.box.y1 / lane_cell; ++row) lanes_[cell_key({column, row, lane.layer})].push_back(index);
        }
        cross_ = static_cast<Nm>(constants::cross_length.value) * straight / setup.pitch;
        turn_ = setup.turn * straight / setup.pitch;
        via_ = setup.via * straight / setup.pitch;
    }

    void neck_at(const Item& pad) {
        const Box bound = pad.shape.bound();
        const Point centre{(bound.x0 + bound.x1) / 2, (bound.y0 + bound.y1) / 2};
        const auto fits = [&](Nm width) {
            Item probe{ItemKind::track, net_, pad.first, pad.first, disc(centre, width / 2), 0, {}, 0};
            for (std::size_t layer = pad.first; layer <= pad.last; ++layer) {
                if (board_.rules.layers[layer].kind == LayerKind::plane) continue;
                probe.first = probe.last = layer;
                if (world_.conflicts(probe).empty()) return true;
            }
            return false;
        };
        Nm wide = std::min(2 * half_, std::min(bound.x1 - bound.x0, bound.y1 - bound.y0)), narrow = board_.rules.least_track;
        if (setup_.narrowest) wide = narrow;
        if (wide >= 2 * half_ && fits(wide)) return;
        if (wide > narrow && !fits(wide)) {
            if (!fits(narrow)) wide = narrow;
            else {
                while (wide - narrow > neck_step) {
                    const Nm middle = narrow + (wide - narrow) / 2;
                    (fits(middle) ? narrow : wide) = middle;
                }
                wide = narrow;
            }
        }
        necks_.push_back({bound, std::max(wide, board_.rules.least_track) / 2});
    }

    void as_spine(int partner, Nm half) {
        partner_ = partner;
        spine_half_ = half;
    }

    Nm half_at(const Cell& cell) const {
        if (spine_half_ > 0) return spine_half_;
        const Point at = point(cell);
        Nm half = half_;
        for (const auto& [bound, narrow] : necks_) {
            const Nm dx = std::max<Nm>({bound.x0 - at.x, at.x - bound.x1, 0}), dy = std::max<Nm>({bound.y0 - at.y, at.y - bound.y1, 0});
            if (dx * dx + dy * dy <= setup_.neck * setup_.neck) half = std::min(half, narrow);
        }
        return half;
    }

    std::int64_t toll(const Cell& cell) const {
        if (lanes_.empty()) return 0;
        const Point at = point(cell);
        const auto bucket = lanes_.find(cell_key({at.x / lane_cell, at.y / lane_cell, cell.layer}));
        if (bucket == lanes_.end()) return 0;
        for (const std::size_t index : bucket->second) {
            const Box& box = setup_.lanes[index].box;
            if (at.x >= box.x0 && at.x <= box.x1 && at.y >= box.y0 && at.y <= box.y1) return static_cast<std::int64_t>(constants::lane_weight.value) * straight;
        }
        return 0;
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
        Item probe{ItemKind::track, net_, cell.layer, cell.layer, disc(at, half_at(cell) + sag_), 0, {}, 0};
        bool free = at.x >= window_.x0 && at.x <= window_.x1 && at.y >= window_.y0 && at.y <= window_.y1;
        if (free) {
            if (!within(probe.shape, board_.outline, board_.rules.edge_clearance)) free = false;
            else {
                std::vector<std::size_t> found = world_.conflicts(probe);
                if (partner_ != no_net)
                    found.erase(std::remove_if(found.begin(), found.end(), [&](std::size_t id) { return world_.item(id).net == partner_; }), found.end());
                free = found.empty();
                for (const std::size_t id : found) blockers_.insert(id);
                if (!free && soft(found)) {
                    free = true;
                    soft_[key] = found;
                }
            }
        }
        legal_.emplace(key, free);
        return free;
    }

    bool soft(const std::vector<std::size_t>& found) const {
        return setup_.soft_from != 0 && std::all_of(found.begin(), found.end(), [&](std::size_t id) { return id >= setup_.soft_from; });
    }

    std::int64_t crossing(const Cell& cell) const { return soft_.count(cell_key(cell)) ? cross_ : 0; }

    bool via_fits(const Cell& cell) {
        const Key key = cell_key({cell.column, cell.row, 0});
        const auto known = drill_.find(key);
        if (known != drill_.end()) return known->second;
        const Item probe = via(board_, net_, point(cell));
        bool free = within(probe.shape, board_.outline, board_.rules.edge_clearance);
        for (std::size_t layer = probe.first; free && layer <= probe.last; ++layer)
            if (toll({cell.column, cell.row, layer}) > 0) free = false;
        if (free) {
            const std::vector<std::size_t> found = world_.conflicts(probe);
            free = found.empty();
            for (const std::size_t id : found) blockers_.insert(id);
            if (!free && soft(found)) {
                free = true;
                soft_drill_[key] = found;
            }
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
                relax(cell, heading, here.cost + (heading % 2 == 0 ? straight : diagonal) + bend * turn_ + toll(cell) + crossing(cell));
            }
            if (drop || spine_half_ > 0 || here.cell.layer < low || here.cell.layer > high || !via_fits(here.cell)) continue;
            for (std::size_t layer = low; layer <= high; ++layer) {
                if (layer == here.cell.layer || board_.rules.layers[layer].kind == LayerKind::plane) continue;
                const Cell cell{here.cell.column, here.cell.row, layer};
                if (!goal(cell) && !open_cell(cell)) continue;
                relax(cell, undirected, here.cost + via_ + crossing(cell) + (soft_drill_.count(cell_key({cell.column, cell.row, 0})) ? cross_ : 0));
            }
        }
        return std::nullopt;
    }

    Path trace(Key end, bool drop) {
        Path path;
        std::vector<const Visit*> chain;
        for (Key key = end;; key = visits_.at(key).parent) {
            chain.push_back(&visits_.at(key));
            if (visits_.at(key).start) break;
        }
        for (const Visit* visit : chain) {
            for (const auto* held : {&soft_, &soft_drill_}) {
                const auto found = held->find(held == &soft_ ? cell_key(visit->cell) : cell_key({visit->cell.column, visit->cell.row, 0}));
                if (found == held->end()) continue;
                if (held == &soft_drill_ && visit->heading != undirected) continue;
                for (const std::size_t id : found->second)
                    if (std::find(crossed_.begin(), crossed_.end(), id) == crossed_.end()) crossed_.push_back(id);
            }
        }
        std::reverse(chain.begin(), chain.end());
        std::size_t from = 0;
        const auto flush = [&](std::size_t to) {
            if (to == from) return;
            const Point a = point(chain[from]->cell), b = point(chain[to]->cell);
            Nm half = half_;
            for (std::size_t step = from; step <= to; ++step) half = std::min(half, half_at(chain[step]->cell));
            path.items.push_back({ItemKind::track, net_, chain[from]->cell.layer, chain[from]->cell.layer, capsule(a, b, half), 0, {}, 0});
            path.least_width = path.least_width == 0 ? 2 * half : std::min(path.least_width, 2 * half);
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
            if (index + 1 < chain.size() && chain[index + 1]->cell.layer == chain[index]->cell.layer && chain[index + 1]->heading == chain[index]->heading &&
                half_at(chain[index + 1]->cell) == half_at(chain[index]->cell) && half_at(chain[index]->cell) == half_at(chain[index - 1]->cell))
                continue;
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
        soft_.clear();
        soft_drill_.clear();
    }

    SearchResult result(std::optional<Path> path) const {
        SearchResult out;
        out.path = std::move(path);
        out.blockers.assign(blockers_.begin(), blockers_.end());
        std::sort(out.blockers.begin(), out.blockers.end());
        out.crossed = crossed_;
        out.opened = opened_;
        out.exhausted = exhausted_;
        return out;
    }

    bool exhausted() const { return exhausted_; }
    Nm width() const { return 2 * half_; }
    const Box& outline() const { return board_.outline; }

private:
    const World& world_;
    const SearchSetup& setup_;
    int net_;
    const Board& board_;
    Nm half_ = 0, sag_ = 0, spine_half_ = 0;
    int partner_ = no_net;
    std::vector<std::pair<Box, Nm>> necks_;
    std::int64_t turn_ = 0, via_ = 0, greed_ = 0, cross_ = 0;
    Box window_;
    std::unordered_map<Key, bool> legal_, drill_;
    std::unordered_map<Key, std::vector<std::size_t>> lanes_, soft_, soft_drill_;
    std::vector<std::size_t> crossed_;
    std::unordered_map<Key, Visit> visits_;
    std::unordered_set<std::size_t> blockers_;
    std::size_t opened_ = 0;
    bool exhausted_ = false;
};

Box grown_within(Box box, Nm by, const Box& limit) {
    return {std::max(limit.x0, box.x0 - by), std::max(limit.y0, box.y0 - by), std::min(limit.x1, box.x1 + by), std::min(limit.y1, box.y1 + by)};
}

bool covers(const Box& a, const Box& b) { return a.x0 <= b.x0 && a.y0 <= b.y0 && a.x1 >= b.x1 && a.y1 >= b.y1; }

SearchResult search(const World& world, const SearchSetup& setup, int net, const std::vector<std::size_t>& sources, const std::vector<std::size_t>& goals, bool drop,
                    bool guarded, const std::pair<Point, std::size_t>* spot = nullptr) {
    Search engine(world, setup, net, guarded);
    std::vector<Cell> starts, ends;
    Box span = world.item(sources.front()).shape.bound();
    for (const std::size_t id : sources)
        if (world.item(id).kind == ItemKind::pad) engine.neck_at(world.item(id));
    for (const std::size_t id : goals)
        if (world.item(id).kind == ItemKind::pad) engine.neck_at(world.item(id));
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
    if (spot) {
        targets.push_back({spot->first.x, spot->first.y, spot->first.x, spot->first.y});
        span = layout::united(span, targets.back());
    }
    if (starts.empty() || (!drop && !spot && wanted.empty())) return engine.result(std::nullopt);
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
        if (spot) {
            wanted.clear();
            const Box& outline = engine.outline();
            const Nm reach = engine.width() / 2;
            for (Nm x = spot->first.x - reach; x <= spot->first.x + reach + setup.pitch; x += setup.pitch)
                for (Nm y = spot->first.y - reach; y <= spot->first.y + reach + setup.pitch; y += setup.pitch) {
                    const Cell cell{(x - outline.x0) / setup.pitch, (y - outline.y0) / setup.pitch, spot->second};
                    if (length_of(engine.point(cell), spot->first) <= static_cast<double>(reach) && engine.open_cell(cell)) wanted.insert(cell_key(cell));
                }
            if (wanted.empty()) return engine.result(std::nullopt);
        }
        if (const auto end = engine.run(starts, goal, estimate, drop)) return engine.result(engine.trace(*end, drop));
        if (engine.exhausted() || covers(window, engine.outline())) return engine.result(std::nullopt);
        margin *= static_cast<Nm>(constants::search_growth.value);
    }
}

SearchResult checked(const World& world, const SearchSetup& setup, int net, const std::vector<std::size_t>& sources, const std::vector<std::size_t>& goals, bool drop) {
    SearchResult exact = search(world, setup, net, sources, goals, drop, false);
    if (!exact.path || setup.soft_from != 0) return exact;
    const bool sound = std::none_of(exact.path->items.begin(), exact.path->items.end(), [&](const Item& item) { return world.conflict(item).has_value(); });
    if (sound) return exact;
    SearchResult guarded = search(world, setup, net, sources, goals, drop, true);
    guarded.opened += exact.opened;
    return guarded;
}

}

SearchResult find_path_to(const World& world, const SearchSetup& setup, int net, const std::vector<std::size_t>& sources, Point goal, std::size_t layer) {
    if (sources.empty()) throw RouteError("route: a path needs a source");
    const std::pair<Point, std::size_t> spot{goal, layer};
    SearchResult exact = search(world, setup, net, sources, {}, false, false, &spot);
    if (!exact.path) return exact;
    const bool sound = std::none_of(exact.path->items.begin(), exact.path->items.end(), [&](const Item& item) { return world.conflict(item).has_value(); });
    if (sound) return exact;
    SearchResult guarded = search(world, setup, net, sources, {}, false, true, &spot);
    guarded.opened += exact.opened;
    return guarded;
}

SearchResult find_spine(const World& world, const SearchSetup& setup, int net, int partner, Nm half, std::size_t layer, Point from, Point to, Nm reach) {
    Search engine(world, setup, net, true);
    engine.as_spine(partner, half);
    const Box span{std::min(from.x, to.x), std::min(from.y, to.y), std::max(from.x, to.x), std::max(from.y, to.y)};
    const auto near = [&](Point centre) {
        std::vector<Cell> cells;
        const Box& outline = engine.outline();
        for (Nm x = centre.x - reach; x <= centre.x + reach; x += setup.pitch)
            for (Nm y = centre.y - reach; y <= centre.y + reach; y += setup.pitch) {
                const Cell cell{(x - outline.x0) / setup.pitch, (y - outline.y0) / setup.pitch, layer};
                const Point at = engine.point(cell);
                if (length_of(at, centre) <= static_cast<double>(reach) && engine.open_cell(cell)) cells.push_back(cell);
            }
        return cells;
    };
    Nm margin = setup.margin + reach;
    for (;;) {
        const Box window = grown_within(span, margin, engine.outline());
        engine.set_window(window);
        const std::vector<Cell> starts = near(from), ends = near(to);
        if (starts.empty() || ends.empty()) return engine.result(std::nullopt);
        std::unordered_set<Key> wanted;
        for (const Cell& cell : ends) wanted.insert(cell_key(cell));
        const auto goal = [&](const Cell& cell) { return wanted.count(cell_key(cell)) != 0; };
        const auto estimate = [&](const Cell& cell) -> std::int64_t {
            const Point at = engine.point(cell);
            const std::int64_t dx = std::max<Nm>(std::abs(at.x - to.x) - reach, 0) / setup.pitch, dy = std::max<Nm>(std::abs(at.y - to.y) - reach, 0) / setup.pitch;
            return straight * std::max(dx, dy) + (diagonal - straight) * std::min(dx, dy);
        };
        if (const auto end = engine.run(starts, goal, estimate, false)) return engine.result(engine.trace(*end, false));
        if (engine.exhausted() || covers(window, engine.outline())) return engine.result(std::nullopt);
        margin *= static_cast<Nm>(constants::search_growth.value);
    }
}

SearchResult find_path(const World& world, const SearchSetup& setup, int net, const std::vector<std::size_t>& sources, const std::vector<std::size_t>& goals) {
    if (sources.empty() || goals.empty()) throw RouteError("route: a path needs a source and a goal");
    return checked(world, setup, net, sources, goals, false);
}

SearchResult find_plane_drop(const World& world, const SearchSetup& setup, int net, const std::vector<std::size_t>& sources) {
    if (sources.empty()) throw RouteError("route: a plane drop needs a source");
    return checked(world, setup, net, sources, {}, true);
}

}
