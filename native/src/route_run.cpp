#include "schgen/route_run.hpp"

#include <algorithm>
#include <cmath>
#include <map>
#include <numeric>

namespace schgen::route {
namespace {

struct Terminal {
    std::vector<std::size_t> items;
    Point centre;
};

struct Job {
    int net = no_net;
    bool plane = false;
    std::vector<Terminal> terminals;
    double span = 0;
    std::size_t failures = 0;
};

Point centre_of(const Item& item) {
    const Box bound = item.shape.bound();
    return {(bound.x0 + bound.x1) / 2, (bound.y0 + bound.y1) / 2};
}

bool on_own_plane(const Board& board, const Item& item) {
    for (std::size_t layer = item.first; layer <= item.last; ++layer)
        if (board.rules.layers[layer].kind == LayerKind::plane && board.rules.layers[layer].plane_net == item.net) return true;
    return false;
}

std::vector<Job> jobs_of(const World& world) {
    const Board& board = world.board();
    std::vector<char> planar(board.nets.size(), 0);
    for (const Layer& layer : board.rules.layers)
        if (layer.kind == LayerKind::plane) planar[static_cast<std::size_t>(layer.plane_net)] = 1;
    std::map<int, std::vector<std::size_t>> members;
    for (std::size_t id = 0; id < board.fixed.size(); ++id)
        if (board.fixed[id].net != no_net && board.fixed[id].kind != ItemKind::keepout) members[board.fixed[id].net].push_back(id);
    std::vector<Job> jobs;
    for (const auto& [net, ids] : members) {
        std::vector<std::size_t> group(ids.size());
        std::iota(group.begin(), group.end(), std::size_t{0});
        const auto root = [&](std::size_t node) {
            while (group[node] != node) node = group[node] = group[group[node]];
            return node;
        };
        for (std::size_t a = 0; a < ids.size(); ++a)
            for (std::size_t b = a + 1; b < ids.size(); ++b) {
                const Item& one = board.fixed[ids[a]];
                const Item& other = board.fixed[ids[b]];
                if (one.first <= other.last && other.first <= one.last && touching(one.shape, other.shape)) group[root(a)] = root(b);
            }
        Job job;
        job.net = net;
        job.plane = planar[static_cast<std::size_t>(net)] != 0;
        std::map<std::size_t, std::size_t> slot;
        for (std::size_t index = 0; index < ids.size(); ++index) {
            const auto found = slot.emplace(root(index), job.terminals.size());
            if (found.second) job.terminals.push_back({{}, centre_of(board.fixed[ids[index]])});
            job.terminals[found.first->second].items.push_back(ids[index]);
        }
        if (job.plane) {
            std::vector<Terminal> kept;
            for (Terminal& terminal : job.terminals)
                if (std::none_of(terminal.items.begin(), terminal.items.end(), [&](std::size_t id) { return on_own_plane(board, board.fixed[id]); }))
                    kept.push_back(std::move(terminal));
            job.terminals = std::move(kept);
            if (job.terminals.empty()) continue;
        } else if (job.terminals.size() < 2) {
            continue;
        }
        Box hull{job.terminals.front().centre.x, job.terminals.front().centre.y, job.terminals.front().centre.x, job.terminals.front().centre.y};
        for (const Terminal& terminal : job.terminals) hull = layout::united(hull, Box{terminal.centre.x, terminal.centre.y, terminal.centre.x, terminal.centre.y});
        job.span = static_cast<double>(hull.x1 - hull.x0) + static_cast<double>(hull.y1 - hull.y0);
        jobs.push_back(std::move(job));
    }
    return jobs;
}

bool commit(World& world, const Path& path, std::vector<std::size_t>& added) {
    const std::size_t mark = world.mark();
    for (const Item& item : path.items) {
        if (world.conflict(item)) {
            world.rollback(mark);
            added.clear();
            return false;
        }
        added.push_back(world.add(item));
    }
    return true;
}

NetOutcome route_job(World& world, const RunSetup& setup, const Job& job, std::size_t& opened) {
    NetOutcome outcome;
    outcome.net = job.net;
    if (job.plane) {
        outcome.links = job.terminals.size();
        for (const Terminal& terminal : job.terminals) {
            const SearchResult found = find_plane_drop(world, setup.search, job.net, terminal.items);
            opened += found.opened;
            std::vector<std::size_t> added;
            if (!found.path || !commit(world, *found.path, added)) {
                if (outcome.failure.empty()) outcome.failure = "no place for a via to its plane";
                continue;
            }
            ++outcome.joined;
            outcome.length += found.path->length;
            outcome.vias += found.path->vias;
        }
        return outcome;
    }
    outcome.links = job.terminals.size() - 1;
    std::vector<char> joined(job.terminals.size(), 0);
    std::vector<std::size_t> tree = job.terminals.front().items;
    std::vector<Point> reached{job.terminals.front().centre};
    joined.front() = 1;
    for (std::size_t link = 0; link + 1 < job.terminals.size(); ++link) {
        std::size_t pick = job.terminals.size();
        double nearest = 0;
        for (std::size_t index = 0; index < job.terminals.size(); ++index) {
            if (joined[index]) continue;
            for (const Point& from : reached) {
                const double distance = length_of(from, job.terminals[index].centre);
                if (pick == job.terminals.size() || distance < nearest) {
                    pick = index;
                    nearest = distance;
                }
            }
        }
        joined[pick] = 1;
        const SearchResult found = find_path(world, setup.search, job.net, tree, job.terminals[pick].items);
        opened += found.opened;
        std::vector<std::size_t> added;
        if (!found.path || !commit(world, *found.path, added)) {
            if (outcome.failure.empty()) outcome.failure = found.exhausted ? "search budget spent" : "no path";
            continue;
        }
        ++outcome.joined;
        outcome.length += found.path->length;
        outcome.vias += found.path->vias;
        tree.insert(tree.end(), added.begin(), added.end());
        tree.insert(tree.end(), job.terminals[pick].items.begin(), job.terminals[pick].items.end());
        reached.push_back(job.terminals[pick].centre);
    }
    return outcome;
}

}

RunReport route_all(World& world, const RunSetup& setup) {
    std::vector<Job> jobs = jobs_of(world);
    const std::size_t clean = world.mark();
    RunReport best;
    bool have = false;
    std::vector<Item> kept;
    std::vector<int> failed_before;
    for (std::size_t pass = 0; pass < setup.passes; ++pass) {
        world.rollback(clean);
        std::stable_sort(jobs.begin(), jobs.end(), [](const Job& a, const Job& b) {
            if (a.failures != b.failures) return a.failures > b.failures;
            if (a.plane != b.plane) return a.plane;
            if (a.span != b.span) return a.span < b.span;
            return a.net < b.net;
        });
        RunReport report;
        std::vector<int> failed;
        for (Job& job : jobs) {
            const NetOutcome outcome = route_job(world, setup, job, report.opened);
            report.links += outcome.links;
            report.joined += outcome.joined;
            report.vias += outcome.vias;
            report.length += outcome.length;
            if (outcome.joined != outcome.links) {
                failed.push_back(job.net);
                ++job.failures;
            }
            report.nets.push_back(outcome);
        }
        std::sort(failed.begin(), failed.end());
        const bool better = !have || report.joined > best.joined;
        const std::vector<std::size_t> history = best.pass_failures;
        if (better) {
            best = report;
            kept = world.routed();
            have = true;
        }
        best.pass_failures = history;
        best.pass_failures.push_back(failed.size());
        best.passes = pass + 1;
        if (failed.empty() || failed == failed_before) break;
        failed_before = failed;
    }
    world.rollback(clean);
    for (const Item& item : kept) world.add(item);
    return best;
}

std::string RunReport::summary(const Board& board) const {
    std::string out = "ROUTE: " + std::to_string(joined) + " of " + std::to_string(links) + " connections made in " + std::to_string(passes) + " passes; " +
                      std::to_string(static_cast<long long>(std::llround(length / 1e6))) + " mm of track, " + std::to_string(vias) + " vias; " + std::to_string(opened) +
                      " lattice points opened\n  nets failing per pass:";
    for (const std::size_t count : pass_failures) out += " " + std::to_string(count);
    out += "\n";
    for (const NetOutcome& outcome : nets)
        if (outcome.joined != outcome.links)
            out += "  " + board.nets[static_cast<std::size_t>(outcome.net)].name + ": " + std::to_string(outcome.joined) + " of " + std::to_string(outcome.links) + " (" +
                   outcome.failure + ")\n";
    return out;
}

}
