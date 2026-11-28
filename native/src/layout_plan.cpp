#include "schgen/layout_plan.hpp"

#include <algorithm>
#include <cmath>
#include <iomanip>
#include <limits>
#include <map>
#include <optional>
#include <sstream>

namespace schgen::layout {
namespace {

struct Spot {
    double x = 0, y = 0;
    std::size_t block = 0;
};

double side(const Spot& a, const Spot& b, const Spot& c) { return (b.x - a.x) * (c.y - a.y) - (b.y - a.y) * (c.x - a.x); }

bool cross(const Spot& a, const Spot& b, const Spot& c, const Spot& d) {
    const double first = side(a, b, c), second = side(a, b, d), third = side(c, d, a), fourth = side(c, d, b);
    return ((first > 0 && second < 0) || (first < 0 && second > 0)) && ((third > 0 && fourth < 0) || (third < 0 && fourth > 0));
}

std::string figure(double value, int places) {
    std::ostringstream out;
    out << std::fixed << std::setprecision(places) << value;
    return out.str();
}

}

PlanFigures plan_figures(const Problem& problem, const Placement& placement) {
    PlanFigures figures;
    std::map<std::string, std::size_t> index;
    std::vector<std::size_t> block_of(problem.parts.size(), 0);
    std::vector<Box> hulls;
    std::vector<std::optional<Box>> seen;
    for (std::size_t part = 0; part < problem.parts.size(); ++part) {
        const Part& entry = problem.parts[part];
        const auto found = index.emplace(entry.group, figures.blocks.size());
        const Pose& pose = placement[part];
        const Box box = placed(problem.footprints[entry.footprint].on(pose.face).gate_box, pose.at, pose.turn);
        if (found.second) {
            figures.blocks.push_back({entry.group});
            hulls.push_back(box);
            seen.emplace_back();
        } else {
            hulls[found.first->second] = united(hulls[found.first->second], box);
        }
        BlockFigure& block = figures.blocks[found.first->second];
        block_of[part] = found.first->second;
        ++block.parts;
        block.module = block.module || entry.module;
        if (!entry.cohesion_member || entry.fixed || entry.edge || entry.corner) continue;
        block.area += to_mm(box.x1 - box.x0) * to_mm(box.y1 - box.y0);
        seen[found.first->second] = seen[found.first->second] ? united(*seen[found.first->second], box) : box;
    }
    for (std::size_t block = 0; block < figures.blocks.size(); ++block) {
        BlockFigure& entry = figures.blocks[block];
        const Box& hull = hulls[block];
        if (seen[block]) entry.hull = to_mm(seen[block]->x1 - seen[block]->x0) * to_mm(seen[block]->y1 - seen[block]->y0);
        entry.spread = entry.area > 0 ? entry.hull / entry.area : 0;
        entry.x = to_mm(hull.x0 + hull.x1) / 2;
        entry.y = to_mm(hull.y0 + hull.y1) / 2;
    }
    std::map<std::pair<std::size_t, std::size_t>, BlockLink> links;
    for (const Net& net : problem.nets) {
        if (net.category == Category::plane || net.pins.size() < 2) continue;
        std::vector<Spot> spots;
        for (const Pin& pin : net.pins) {
            const Pose& pose = placement[pin.part];
            const Point at = placed(problem.footprints[problem.parts[pin.part].footprint].on(pose.face).pads[pin.pad].centre, pose.at, pose.turn);
            spots.push_back({to_mm(at.x), to_mm(at.y), block_of[pin.part]});
        }
        std::vector<double> best(spots.size(), std::numeric_limits<double>::infinity());
        std::vector<std::size_t> from(spots.size(), 0);
        std::vector<char> used(spots.size(), 0);
        best.front() = 0;
        std::vector<std::pair<std::size_t, std::size_t>> touched;
        for (std::size_t step = 0; step < spots.size(); ++step) {
            std::size_t pick = spots.size();
            for (std::size_t spot = 0; spot < spots.size(); ++spot)
                if (!used[spot] && (pick == spots.size() || best[spot] < best[pick])) pick = spot;
            used[pick] = 1;
            if (step > 0) {
                figures.length += best[pick];
                figures.pulled += best[pick] * net.pull;
                const std::size_t a = std::min(spots[pick].block, spots[from[pick]].block);
                const std::size_t b = std::max(spots[pick].block, spots[from[pick]].block);
                if (a != b) {
                    figures.crossing += best[pick];
                    figures.pulled_crossing += best[pick] * net.pull;
                    BlockLink& link = links[{a, b}];
                    link.first = a;
                    link.second = b;
                    link.length += best[pick];
                    link.pull += best[pick] * net.pull;
                    if (std::find(touched.begin(), touched.end(), std::make_pair(a, b)) == touched.end()) {
                        touched.emplace_back(a, b);
                        ++link.nets;
                    }
                }
            }
            for (std::size_t spot = 0; spot < spots.size(); ++spot) {
                if (used[spot]) continue;
                const double distance = std::hypot(spots[spot].x - spots[pick].x, spots[spot].y - spots[pick].y);
                if (distance < best[spot]) {
                    best[spot] = distance;
                    from[spot] = pick;
                }
            }
        }
    }
    for (const auto& entry : links) figures.links.push_back(entry.second);
    std::sort(figures.links.begin(), figures.links.end(), [](const BlockLink& a, const BlockLink& b) {
        if (a.pull != b.pull) return a.pull > b.pull;
        return a.first != b.first ? a.first < b.first : a.second < b.second;
    });
    const auto centre = [&](std::size_t block) { return Spot{figures.blocks[block].x, figures.blocks[block].y, block}; };
    for (std::size_t first = 0; first < figures.links.size(); ++first)
        for (std::size_t second = first + 1; second < figures.links.size(); ++second) {
            const BlockLink& a = figures.links[first];
            const BlockLink& b = figures.links[second];
            if (a.first == b.first || a.first == b.second || a.second == b.first || a.second == b.second) continue;
            if (cross(centre(a.first), centre(a.second), centre(b.first), centre(b.second))) ++figures.crossings;
        }
    return figures;
}

std::string PlanFigures::summary() const {
    const double percent = 100;
    std::string out = "BOARD PLAN\n";
    out += "  airwire between blocks: " + figure(crossing, 1) + " of " + figure(length, 1) + " mm (" +
           figure(length > 0 ? percent * crossing / length : 0, 1) + "%); weighted by net kind " + figure(pulled_crossing, 1) + " of " +
           figure(pulled, 1) + " (" + figure(pulled > 0 ? percent * pulled_crossing / pulled : 0, 1) + "%)\n";
    out += "  block links: " + std::to_string(links.size()) + "; pairs of links that cross between block centres: " + std::to_string(crossings) + "\n";
    out += "  blocks, most spread first (parts, own area mm2, hull mm2, hull over own area; edge parts, fixed parts and test points left out of the areas):\n";
    std::vector<const BlockFigure*> order;
    for (const BlockFigure& block : blocks) order.push_back(&block);
    std::sort(order.begin(), order.end(), [](const BlockFigure* a, const BlockFigure* b) {
        return a->spread != b->spread ? a->spread > b->spread : a->name < b->name;
    });
    for (const BlockFigure* block : order)
        out += "    " + block->name + (block->module ? " (module)" : "") + ": " + std::to_string(block->parts) + ", " + figure(block->area, 0) + ", " +
               figure(block->hull, 0) + ", " + figure(block->spread, 1) + "\n";
    out += "  links, heaviest first (weighted mm, mm, nets):\n";
    for (const BlockLink& link : links)
        out += "    " + blocks[link.first].name + " - " + blocks[link.second].name + ": " + figure(link.pull, 1) + ", " + figure(link.length, 1) + ", " +
               std::to_string(link.nets) + "\n";
    return out;
}

}
