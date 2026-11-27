#include "schgen/route_pair.hpp"

#include <algorithm>
#include <cmath>

namespace schgen::route {
namespace {

struct Spot {
    double x = 0, y = 0;
};

Point centre_of(const Item& item) {
    const Box bound = item.shape.bound();
    return {(bound.x0 + bound.x1) / 2, (bound.y0 + bound.y1) / 2};
}

Spot unit(Point from, Point to) {
    const double length = length_of(from, to);
    return {static_cast<double>(to.x - from.x) / length, static_cast<double>(to.y - from.y) / length};
}

double side_of(Spot heading, Point first, Point second) {
    return heading.x * static_cast<double>(first.y - second.y) - heading.y * static_cast<double>(first.x - second.x);
}

std::vector<Point> offset(const std::vector<Point>& spine, double by) {
    std::vector<Point> out;
    for (std::size_t index = 0; index < spine.size(); ++index) {
        const Spot before = index == 0 ? unit(spine[0], spine[1]) : unit(spine[index - 1], spine[index]);
        const Spot after = index + 1 == spine.size() ? before : unit(spine[index], spine[index + 1]);
        const Spot first{-before.y, before.x}, second{-after.y, after.x};
        const double scale = by / (1 + first.x * second.x + first.y * second.y);
        out.push_back({spine[index].x + static_cast<Nm>(std::llround((first.x + second.x) * scale)), spine[index].y + static_cast<Nm>(std::llround((first.y + second.y) * scale))});
    }
    return out;
}

bool ends_with(const std::string& text, const std::string& tail) {
    return text.size() > tail.size() && text.compare(text.size() - tail.size(), std::string::npos, tail) == 0;
}

}

std::optional<std::string> pair_partner(const std::string& name) {
    for (const auto& [one, other] : std::vector<std::pair<std::string, std::string>>{{"_P", "_N"}, {"_N", "_P"}, {"+", "-"}, {"-", "+"}})
        if (ends_with(name, one)) return name.substr(0, name.size() - one.size()) + other;
    return std::nullopt;
}

PairResult route_pair(World& world, const SearchSetup& setup, int first, int second, const PairEnds& ends) {
    PairResult result;
    const Board& board = world.board();
    const NetClass& entry = board.rules.classes[board.nets[static_cast<std::size_t>(first)].net_class];
    if (entry.pair_width <= 0 || entry.pair_gap <= 0) {
        result.why = "its class states no pair width and gap";
        return result;
    }
    const Item& near_one = world.item(ends.near_first.front());
    const Item& near_two = world.item(ends.near_second.front());
    const Item& far_one = world.item(ends.far_first.front());
    const Item& far_two = world.item(ends.far_second.front());
    const std::size_t layer = near_one.first;
    for (const Item* pad : {&near_one, &near_two, &far_one, &far_two})
        if (pad->first != pad->last || pad->first != layer) {
            result.why = "its four pads are not on one layer";
            return result;
        }
    const auto middle = [](Point a, Point b) { return Point{(a.x + b.x) / 2, (a.y + b.y) / 2}; };
    const Point from = middle(centre_of(near_one), centre_of(near_two)), to = middle(centre_of(far_one), centre_of(far_two));
    const Nm reach = static_cast<Nm>(constants::pair_reach.value);
    const SearchResult spine = find_spine(world, setup, first, second, entry.pair_width + entry.pair_gap / 2, layer, from, to, reach);
    result.opened = spine.opened;
    if (!spine.path || spine.path->items.empty()) {
        result.why = spine.exhausted ? "search budget spent on the coupled run" : "no room for the coupled run on its layer";
        return result;
    }
    std::vector<Point> points{spine.path->items.front().shape.core[0]};
    for (const Item& item : spine.path->items) points.push_back(item.shape.core[item.shape.count > 1 ? 1 : 0]);
    points.erase(std::unique(points.begin(), points.end()), points.end());
    if (points.size() < 2) {
        result.why = "the pads are too close for a coupled run";
        return result;
    }
    const double away = static_cast<double>(entry.pair_width + entry.pair_gap) / 2;
    const double start_side = side_of(unit(points[0], points[1]), centre_of(near_one), centre_of(near_two));
    const double end_side = side_of(unit(points[points.size() - 2], points.back()), centre_of(far_one), centre_of(far_two));
    if (start_side == 0 || end_side == 0 || (start_side > 0) != (end_side > 0)) {
        result.why = "the pair would have to cross itself to reach its far pads";
        return result;
    }
    const double sign = start_side > 0 ? 1 : -1;
    const std::vector<Point> first_line = offset(points, sign * away), second_line = offset(points, -sign * away);
    const std::size_t mark = world.mark();
    const auto lay = [&](const std::vector<Point>& line, int net, std::vector<std::size_t>& items, std::size_t& head, std::size_t& tail) {
        for (std::size_t index = 0; index + 1 < line.size(); ++index) {
            const Item track{ItemKind::track, net, layer, layer, capsule(line[index], line[index + 1], entry.pair_width / 2), 0, {}, 0};
            if (world.conflict(track)) return false;
            items.push_back(world.add(track));
        }
        for (const Point at : {line.front(), line.back()}) {
            const Item anchor{ItemKind::track, net, layer, layer, disc(at, entry.pair_width / 2), 0, {}, 0};
            if (world.conflict(anchor)) return false;
            items.push_back(world.add(anchor));
        }
        head = items[items.size() - 2];
        tail = items.back();
        return true;
    };
    std::size_t first_head = 0, first_tail = 0, second_head = 0, second_tail = 0;
    if (!lay(first_line, first, result.first_items, first_head, first_tail) || !lay(second_line, second, result.second_items, second_head, second_tail)) {
        world.rollback(mark);
        result = {};
        result.opened = spine.opened;
        result.why = "the two coupled tracks do not clear their neighbours";
        return result;
    }
    const auto join = [&](int net, const std::vector<std::size_t>& pads, std::size_t anchor, std::vector<std::size_t>& items) {
        const SearchResult found = find_path(world, setup, net, pads, {anchor});
        result.opened += found.opened;
        if (!found.path) return false;
        for (const Item& item : found.path->items) {
            if (world.conflict(item)) return false;
            items.push_back(world.add(item));
        }
        result.loose_length += found.path->length;
        return true;
    };
    if (!join(first, ends.near_first, first_head, result.first_items) || !join(second, ends.near_second, second_head, result.second_items) ||
        !join(first, ends.far_first, first_tail, result.first_items) || !join(second, ends.far_second, second_tail, result.second_items)) {
        world.rollback(mark);
        const std::size_t opened = result.opened;
        result = {};
        result.opened = opened;
        result.why = "no way from a pad to its end of the coupled run";
        return result;
    }
    result.coupled = true;
    result.coupled_length = spine.path->length;
    return result;
}

}
