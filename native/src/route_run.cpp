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

struct State {
    Job job;
    std::vector<std::size_t> items;
    std::vector<char> done;
    NetOutcome outcome;
    std::vector<int> walls;
    std::size_t rips = 0;
};

void note_walls(const World& world, const std::vector<std::size_t>& blockers, std::size_t fixed, int self, std::map<int, std::size_t>& tally) {
    for (const std::size_t id : blockers)
        if (id >= fixed && world.present(id) && world.item(id).net != self) ++tally[world.item(id).net];
}

void route_state(World& world, const RunSetup& setup, State& state, std::size_t fixed, std::size_t& opened) {
    const Job& job = state.job;
    std::map<int, std::size_t> tally;
    state.outcome.net = job.net;
    state.outcome.failure.clear();
    if (job.plane) {
        state.outcome.links = job.terminals.size();
        if (state.done.empty()) state.done.assign(job.terminals.size(), 0);
        for (std::size_t index = 0; index < job.terminals.size(); ++index) {
            if (state.done[index]) continue;
            const SearchResult found = find_plane_drop(world, setup.search, job.net, job.terminals[index].items);
            opened += found.opened;
            std::vector<std::size_t> added;
            if (!found.path || !commit(world, *found.path, added)) {
                state.outcome.failure += (state.outcome.failure.empty() ? "no place for a via to its plane: " : ", ") + world.item(job.terminals[index].items.front()).owner;
                note_walls(world, found.blockers, fixed, job.net, tally);
                continue;
            }
            state.done[index] = 1;
            ++state.outcome.joined;
            state.outcome.length += found.path->length;
            state.outcome.vias += found.path->vias;
            state.items.insert(state.items.end(), added.begin(), added.end());
        }
    } else {
        state.outcome.links = job.terminals.size() - 1;
        state.outcome.joined = 0;
        state.outcome.length = 0;
        state.outcome.vias = 0;
        state.outcome.least_width = 0;
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
            SearchResult found = find_path(world, setup.search, job.net, tree, job.terminals[pick].items);
            opened += found.opened;
            std::vector<std::size_t> added;
            if (!found.path || !commit(world, *found.path, added)) {
                SearchSetup slim = setup.search;
                slim.narrowest = true;
                found = find_path(world, slim, job.net, tree, job.terminals[pick].items);
                opened += found.opened;
            }
            if (added.empty() && (!found.path || !commit(world, *found.path, added))) {
                state.outcome.failure += (state.outcome.failure.empty() ? "" : "; ") + std::string(found.exhausted ? "search budget spent" : "no path") + " to " +
                                         world.item(job.terminals[pick].items.front()).owner;
                SearchSetup probe = setup.search;
                probe.budget = static_cast<std::size_t>(constants::probe_budget.value);
                const SearchResult back = find_path(world, probe, job.net, job.terminals[pick].items, tree);
                opened += back.opened;
                note_walls(world, back.blockers, fixed, job.net, tally);
                continue;
            }
            ++state.outcome.joined;
            state.outcome.length += found.path->length;
            state.outcome.vias += found.path->vias;
            state.outcome.least_width = state.outcome.least_width == 0 ? found.path->least_width : std::min(state.outcome.least_width, found.path->least_width);
            state.items.insert(state.items.end(), added.begin(), added.end());
            tree.insert(tree.end(), added.begin(), added.end());
            tree.insert(tree.end(), job.terminals[pick].items.begin(), job.terminals[pick].items.end());
            reached.push_back(job.terminals[pick].centre);
        }
    }
    std::vector<std::pair<std::size_t, int>> ranked;
    for (const auto& [net, count] : tally) ranked.emplace_back(count, net);
    std::sort(ranked.begin(), ranked.end(), [](const auto& a, const auto& b) { return a.first != b.first ? a.first > b.first : a.second < b.second; });
    state.walls.clear();
    for (const auto& entry : ranked) state.walls.push_back(entry.second);
}

void lift(World& world, State& state) {
    for (const std::size_t id : state.items) world.remove(id);
    state.items.clear();
    if (!state.job.plane) state.outcome.joined = 0;
}

}

RunReport route_all(World& world, const RunSetup& setup) {
    const std::size_t fixed = world.size();
    const Board& board = world.board();
    std::vector<State> states;
    for (Job& job : jobs_of(world)) states.push_back({std::move(job), {}, {}, {}, {}, 0});
    std::stable_sort(states.begin(), states.end(), [&](const State& a, const State& b) {
        if (a.job.plane != b.job.plane) return a.job.plane;
        const bool stated_a = board.nets[static_cast<std::size_t>(a.job.net)].net_class != 0, stated_b = board.nets[static_cast<std::size_t>(b.job.net)].net_class != 0;
        if (stated_a != stated_b) return stated_a;
        if (a.job.span != b.job.span) return a.job.span < b.job.span;
        return a.job.net < b.job.net;
    });
    RunReport report;
    for (State& state : states) route_state(world, setup, state, fixed, report.opened);
    const auto joined_now = [&] {
        std::size_t total = 0;
        for (const State& state : states) total += state.outcome.joined;
        return total;
    };
    report.first_joined = joined_now();
    std::map<int, std::size_t> index_of;
    for (std::size_t index = 0; index < states.size(); ++index) index_of[states[index].job.net] = index;
    for (std::size_t round = 0; round < setup.passes; ++round) {
        std::size_t open_nets = 0;
        bool gained = false;
        for (std::size_t failed = 0; failed < states.size(); ++failed) {
            if (states[failed].outcome.joined == states[failed].outcome.links) continue;
            ++open_nets;
            std::vector<std::size_t> pulled;
            for (const int net : states[failed].walls) {
                const auto found = index_of.find(net);
                if (found == index_of.end() || states[found->second].job.plane || states[found->second].rips >= static_cast<std::size_t>(constants::rip_cap.value)) continue;
                pulled.push_back(found->second);
                if (pulled.size() == static_cast<std::size_t>(constants::rip_nets.value)) break;
            }
            if (pulled.empty()) continue;
            const std::size_t mark = world.mark();
            std::vector<State> before{states[failed]};
            for (const std::size_t index : pulled) before.push_back(states[index]);
            std::size_t had = 0;
            for (const State& state : before) had += state.outcome.joined;
            if (!states[failed].job.plane) lift(world, states[failed]);
            for (const std::size_t index : pulled) lift(world, states[index]);
            route_state(world, setup, states[failed], fixed, report.opened);
            for (const std::size_t index : pulled) route_state(world, setup, states[index], fixed, report.opened);
            std::size_t have = states[failed].outcome.joined;
            for (const std::size_t index : pulled) have += states[index].outcome.joined;
            if (have > had) {
                for (const std::size_t index : pulled) ++states[index].rips;
                report.ripped += pulled.size();
                gained = true;
                continue;
            }
            world.rollback(mark);
            states[failed] = before.front();
            for (std::size_t slot = 0; slot < pulled.size(); ++slot) states[pulled[slot]] = before[slot + 1];
        }
        report.pass_failures.push_back(open_nets);
        report.passes = round + 1;
        if (!gained) break;
    }
    for (const State& state : states) {
        report.links += state.outcome.links;
        report.joined += state.outcome.joined;
        report.vias += state.outcome.vias;
        report.length += state.outcome.length;
        report.nets.push_back(state.outcome);
    }
    return report;
}

std::string RunReport::summary(const Board& board) const {
    std::string out = "ROUTE: " + std::to_string(joined) + " of " + std::to_string(links) + " connections made (" + std::to_string(first_joined) + " before any net was pulled out, " +
                      std::to_string(ripped) + " nets pulled out and routed again over " + std::to_string(passes) + " rounds); " +
                      std::to_string(static_cast<long long>(std::llround(length / 1e6))) + " mm of track, " + std::to_string(vias) + " vias; " + std::to_string(opened) +
                      " lattice points opened\n  open nets at the start of each round:";
    for (const std::size_t count : pass_failures) out += " " + std::to_string(count);
    out += "\n";
    std::size_t necked = 0;
    for (const NetOutcome& outcome : nets) {
        const Nm stated = board.rules.classes[board.nets[static_cast<std::size_t>(outcome.net)].net_class].track;
        if (outcome.least_width != 0 && outcome.least_width < stated) ++necked;
    }
    out += "  nets with a neck narrower than their class width: " + std::to_string(necked) + "\n";
    for (const NetOutcome& outcome : nets)
        if (outcome.joined != outcome.links)
            out += "  " + board.nets[static_cast<std::size_t>(outcome.net)].name + ": " + std::to_string(outcome.joined) + " of " + std::to_string(outcome.links) + " (" +
                   outcome.failure + ")\n";
    return out;
}

}
