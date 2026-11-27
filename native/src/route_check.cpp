#include "schgen/route_check.hpp"

#include <algorithm>
#include <map>
#include <numeric>

namespace schgen::route {
namespace {

struct Entry {
    const Item* item = nullptr;
    Box bound;
    std::size_t index = 0;
    bool routed = false;
};

std::string where(const Item& item) {
    const Box bound = item.shape.bound();
    return std::string(kind_name(item.kind)) + (item.owner.empty() ? "" : " " + item.owner) + " at " +
           std::to_string(layout::to_mm((bound.x0 + bound.x1) / 2)) + "," + std::to_string(layout::to_mm((bound.y0 + bound.y1) / 2));
}

std::string net_name(const Board& board, int net) { return net == no_net ? std::string("no net") : board.nets[static_cast<std::size_t>(net)].name; }

std::size_t root(std::vector<std::size_t>& parent, std::size_t node) {
    while (parent[node] != node) {
        parent[node] = parent[parent[node]];
        node = parent[node];
    }
    return node;
}

bool shares_layer(const Item& a, const Item& b) { return a.first <= b.last && b.first <= a.last; }

}

CheckReport verify(const Board& board, const std::vector<Item>& copper) {
    board.validate();
    CheckReport report;
    std::vector<Entry> entries;
    for (const Item& item : board.fixed) entries.push_back({&item, item.shape.bound(), entries.size(), false});
    for (const Item& item : copper) {
        if (item.first > item.last || item.last >= board.rules.layers.size() || item.net == no_net || static_cast<std::size_t>(item.net) >= board.nets.size() ||
            item.kind == ItemKind::pad || item.kind == ItemKind::keepout || item.shape.count == 0)
            throw RouteError("route: routed copper must be tracks and vias on stated nets and layers");
        entries.push_back({&item, item.shape.bound(), entries.size(), true});
    }
    report.items = entries.size();
    report.nets = board.nets.size();
    Nm widest = std::max(board.rules.hole_clearance, board.rules.hole_spacing);
    for (const NetClass& entry : board.rules.classes) widest = std::max(widest, entry.clearance);
    for (const Item& item : board.fixed) widest = std::max(widest, item.clearance);
    std::vector<std::size_t> order(entries.size());
    std::iota(order.begin(), order.end(), std::size_t{0});
    std::stable_sort(order.begin(), order.end(), [&](std::size_t a, std::size_t b) { return entries[a].bound.x0 < entries[b].bound.x0; });
    std::vector<std::size_t> parent(entries.size() + board.rules.layers.size());
    std::iota(parent.begin(), parent.end(), std::size_t{0});
    for (const Entry& entry : entries) {
        const Item& item = *entry.item;
        if (item.kind != ItemKind::keepout && !within(item.shape, board.outline, board.rules.edge_clearance) && entry.routed)
            report.edges.push_back(where(item) + " on " + net_name(board, item.net) + " is nearer the board edge than the edge clearance");
        if (entry.routed && item.kind == ItemKind::track && board.rules.layers[item.first].kind == LayerKind::plane)
            report.strays.push_back(where(item) + " on " + net_name(board, item.net) + " is a track on the plane layer " + board.rules.layers[item.first].name);
        if (item.net == no_net || (item.kind != ItemKind::via && !(item.kind == ItemKind::pad && item.first != item.last))) continue;
        for (std::size_t layer = item.first; layer <= item.last; ++layer)
            if (board.rules.layers[layer].kind == LayerKind::plane && board.rules.layers[layer].plane_net == item.net)
                parent[root(parent, entry.index)] = root(parent, entries.size() + layer);
    }
    for (std::size_t first = 0; first < order.size(); ++first) {
        const Entry& a = entries[order[first]];
        for (std::size_t second = first + 1; second < order.size(); ++second) {
            const Entry& b = entries[order[second]];
            if (b.bound.x0 > a.bound.x1 + widest) break;
            if (b.bound.y0 > a.bound.y1 + widest || a.bound.y0 > b.bound.y1 + widest) continue;
            const Item& one = *a.item;
            const Item& other = *b.item;
            if (!a.routed && !b.routed) {
                if (one.net != no_net && one.net == other.net && shares_layer(one, other) && touching(one.shape, other.shape))
                    parent[root(parent, a.index)] = root(parent, b.index);
                continue;
            }
            if (one.drill > 0 && other.drill > 0 && !(one.net == other.net && one.shape.core[0] == other.shape.core[0]) &&
                !apart(disc(one.shape.core[0], one.drill / 2), disc(other.shape.core[0], other.drill / 2), board.rules.hole_spacing))
                report.holes.push_back(where(one) + " and " + where(other) + " have holes nearer than the hole spacing");
            if (!shares_layer(one, other)) continue;
            if (one.kind == ItemKind::keepout || other.kind == ItemKind::keepout) {
                if (one.kind != other.kind && touching(one.shape, other.shape))
                    report.keepouts.push_back(where(one.kind == ItemKind::keepout ? other : one) + " lies in the keep-out " + (one.kind == ItemKind::keepout ? one : other).owner);
                continue;
            }
            if (one.net != no_net && one.net == other.net) {
                if (touching(one.shape, other.shape)) parent[root(parent, a.index)] = root(parent, b.index);
                continue;
            }
            const std::string pair = where(one) + " on " + net_name(board, one.net) + " and " + where(other) + " on " + net_name(board, other.net);
            if (touching(one.shape, other.shape)) report.shorts.push_back(pair + " touch");
            else if (!apart(one.shape, other.shape, board.rules.between(one, other, board.nets)))
                report.clearances.push_back(pair + " are nearer than their clearance");
            else if ((one.drill > 0 && !apart(disc(one.shape.core[0], one.drill / 2), other.shape, board.rules.hole_clearance)) ||
                     (other.drill > 0 && !apart(disc(other.shape.core[0], other.drill / 2), one.shape, board.rules.hole_clearance)))
                report.holes.push_back(pair + " have a hole nearer copper than the hole clearance");
        }
    }
    std::map<int, std::vector<std::size_t>> pads;
    for (const Entry& entry : entries)
        if (entry.item->kind == ItemKind::pad && entry.item->net != no_net) pads[entry.item->net].push_back(entry.index);
    for (const auto& [net, members] : pads) {
        std::vector<std::size_t> groups;
        for (const std::size_t member : members) groups.push_back(root(parent, member));
        std::sort(groups.begin(), groups.end());
        groups.erase(std::unique(groups.begin(), groups.end()), groups.end());
        if (groups.size() == 1) ++report.joined;
        else report.opens.push_back(net_name(board, net) + " is in " + std::to_string(groups.size()) + " pieces across " + std::to_string(members.size()) + " pads");
    }
    for (const Entry& entry : entries) {
        if (!entry.routed) continue;
        const auto found = pads.find(entry.item->net);
        const bool tied = found != pads.end() && std::any_of(found->second.begin(), found->second.end(), [&](std::size_t pad) { return root(parent, pad) == root(parent, entry.index); });
        if (!tied) report.strays.push_back(where(*entry.item) + " on " + net_name(board, entry.item->net) + " reaches no pad of its net");
    }
    return report;
}

std::string CheckReport::summary() const {
    std::string out = std::string("ROUTE CHECK: ") + (ok() ? "PASS" : "FAIL") + " (" + std::to_string(items) + " copper items, " + std::to_string(joined) + " nets joined)\n";
    const auto section = [&](const char* title, const std::vector<std::string>& rows) {
        out += std::string("  ") + title + ": " + std::to_string(rows.size()) + "\n";
        for (const std::string& row : rows) out += "    " + row + "\n";
    };
    section("shorts", shorts);
    section("clearance", clearances);
    section("holes", holes);
    section("board edge", edges);
    section("keep-outs", keepouts);
    section("open nets", opens);
    section("stray copper", strays);
    return out;
}

}
