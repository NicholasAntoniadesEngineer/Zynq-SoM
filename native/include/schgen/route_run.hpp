#pragma once

#include "schgen/route_search.hpp"

#include <string>
#include <vector>

namespace schgen::route {

namespace constants {
inline constexpr NamedConstant route_passes{"route_passes", 6, "rounds", "policy",
    "rounds in which every net still open has the nets walling it in pulled out and routed again after it; a round that gains no connection ends the search"};
inline constexpr NamedConstant rip_nets{"rip_nets", 3, "nets", "policy",
    "nets pulled out at once to let one blocked net through; KiCadRoutingTools reports that small limits beat large ones (docs/rip-up-reroute.md, read 2026-11-27)"};
inline constexpr NamedConstant rip_cap{"rip_cap", 4, "times", "policy",
    "times one net may be pulled out for others before it is left alone, so two nets cannot displace each other for ever"};
inline constexpr NamedConstant probe_budget{"probe_budget", 30000, "points", "policy",
    "lattice points opened from the blocked end to find what walls it in"};
inline constexpr NamedConstant dense_pins{"dense_pins", 8, "pads", "policy",
    "pads a part needs before its crowded pins are given exit stubs; smaller parts are reached from any side"};
inline constexpr NamedConstant stub_step{"stub_step", 10000, "nm", "policy",
    "step by which an exit stub is narrowed until it clears its neighbours"};
inline constexpr NamedConstant tidy_rounds{"tidy_rounds", 2, "rounds", "policy",
    "rounds in which every finished net is lifted and routed again by the shortest path with the rest in place, and kept only if it is shorter or has fewer vias"};
inline constexpr NamedConstant tidy_greed{"tidy_greed", 1.2, "ratio", "policy",
    "weight of the remaining-distance estimate when a finished net is routed again alone; nearer one than the first search, so the path found is within a fifth of the shortest"};
inline constexpr std::array route_run_registry{route_passes, rip_nets, rip_cap, probe_budget, dense_pins, stub_step, tidy_rounds, tidy_greed};
}

struct RunSetup {
    SearchSetup search;
    std::size_t passes = static_cast<std::size_t>(constants::route_passes.value);
};

struct NetOutcome {
    int net = no_net;
    std::size_t links = 0, joined = 0, vias = 0;
    double length = 0;
    Nm least_width = 0;
    std::string failure;
};

struct RunReport {
    std::vector<NetOutcome> nets;
    std::size_t links = 0, joined = 0, vias = 0, passes = 0, opened = 0, ripped = 0, first_joined = 0, stubs = 0, tidied = 0;
    double tidy_saved = 0;
    std::size_t pairs = 0, coupled_pairs = 0;
    double coupled_length = 0, breakout_length = 0;
    std::vector<std::string> loose_pairs;
    double length = 0;
    std::vector<std::size_t> pass_failures;
    bool complete() const { return links == joined; }
    std::string summary(const Board& board) const;
};

RunReport route_all(World& world, const RunSetup& setup);

}
