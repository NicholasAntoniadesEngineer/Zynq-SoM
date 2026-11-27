#pragma once

#include "schgen/route_board.hpp"

#include <optional>
#include <vector>

namespace schgen::route {

namespace constants {
inline constexpr NamedConstant lattice_pitch{"lattice_pitch", 50000, "nm", "policy",
    "spacing of the points a track may turn at; a divisor of the 0.4 mm connector pitch and half the least fabricator track, so every pad row has points on it"};
inline constexpr NamedConstant turn_length{"turn_length", 200000, "nm", "policy",
    "track length a path will add to save one 45 degree turn"};
inline constexpr NamedConstant via_length{"via_length", 2500000, "nm", "policy",
    "track length a path will add to save one via; a via costs a drilled hole on every layer and breaks the return path"};
inline constexpr NamedConstant search_margin{"search_margin", 3000000, "nm", "policy",
    "distance beyond the two ends within which the first search for a connection looks"};
inline constexpr NamedConstant search_growth{"search_growth", 3, "ratio", "policy",
    "factor by which the search area grows after a search that found no path inside it"};
inline constexpr NamedConstant search_budget{"search_budget", 400000, "points", "policy",
    "lattice points one search may open before it reports no path; a count, so results never depend on the clock"};
inline constexpr NamedConstant search_greed{"search_greed", 1.5, "ratio", "policy",
    "weight of the remaining-distance estimate against the cost so far; above one the search heads for the goal and opens far fewer points, at the price of a path up to that factor longer than the best"};
inline constexpr NamedConstant neck_reach{"neck_reach", 2500000, "nm", "policy",
    "distance from a pad within which a track may be as narrow as the pad instead of its class width; the figure KiCadRoutingTools documents for power nets (docs/power-nets.md, read 2026-11-27)"};
inline constexpr NamedConstant lane_length{"lane_length", 3000000, "nm", "policy",
    "length of the lane kept in front of a crowded pin's exit stub, in which other nets pay to run; long enough for the pin's own track to leave the row and reach a via site"};
inline constexpr NamedConstant lane_weight{"lane_weight", 4, "ratio", "policy",
    "extra cost, in step lengths, of each step another net takes inside a pin's lane; a track crosses a lane when it must and does not run along a row of them"};
inline constexpr NamedConstant cross_length{"cross_length", 2500000, "nm", "policy",
    "track length a probing search will add to avoid one lattice step inside another routed net's copper; a track crossing costs about ten such steps, so the probe crosses as few nets as it can"};
inline constexpr std::array route_search_registry{lattice_pitch, turn_length, via_length, search_margin, search_growth, search_budget, search_greed, neck_reach, lane_length, lane_weight, cross_length};
}

struct Lane {
    Box box;
    std::size_t layer = 0;
    int net = no_net;
};

struct SearchSetup {
    Nm pitch = static_cast<Nm>(constants::lattice_pitch.value);
    Nm turn = static_cast<Nm>(constants::turn_length.value);
    Nm via = static_cast<Nm>(constants::via_length.value);
    Nm margin = static_cast<Nm>(constants::search_margin.value);
    std::size_t budget = static_cast<std::size_t>(constants::search_budget.value);
    Nm neck = static_cast<Nm>(constants::neck_reach.value);
    bool narrowest = false;
    std::vector<Lane> lanes;
    std::size_t soft_from = 0;
    double greed = constants::search_greed.value;
};

struct Path {
    std::vector<Item> items;
    double length = 0;
    std::size_t vias = 0;
    Nm least_width = 0;
};

struct SearchResult {
    std::optional<Path> path;
    std::vector<std::size_t> blockers, crossed;
    std::size_t opened = 0;
    bool exhausted = false;
};

SearchResult find_path(const World& world, const SearchSetup& setup, int net, const std::vector<std::size_t>& sources, const std::vector<std::size_t>& goals);
SearchResult find_spine(const World& world, const SearchSetup& setup, int net, int partner, Nm half, std::size_t layer, Point from, Point to, Nm reach);
SearchResult find_plane_drop(const World& world, const SearchSetup& setup, int net, const std::vector<std::size_t>& sources);

}
