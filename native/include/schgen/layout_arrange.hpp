#pragma once

#include "schgen/layout_squeeze.hpp"

#include <functional>
#include <string>
#include <vector>

namespace schgen::layout {

namespace constants {
inline constexpr NamedConstant arrange_pitch{"arrange_pitch", 1e6, "nm", "policy",
    "lattice pitch on which a block of clusters is offered a new position"};
inline constexpr NamedConstant arrange_gap{"arrange_gap", 1e6, "nm", "policy",
    "gap left between clusters when a sheet is repacked into one block; every rule is still checked on the result"};
inline constexpr NamedConstant room_factor{"room_factor", 1.6, "ratio", "policy",
    "board area opened on the kept sides for each unit of cluster area that has to leave a closed side"};
inline constexpr NamedConstant tighten_rounds{"tighten_rounds", 8, "rounds", "policy",
    "passes in which a cluster holding the span out is offered a place that shrinks it"};
inline constexpr NamedConstant arrange_tries{"arrange_tries", 600, "positions", "policy",
    "positions checked against every rule for one block before it is left where it is"};
inline constexpr NamedConstant rehome_pitch{"rehome_pitch", 2e6, "nm", "policy",
    "lattice pitch of the whole-board search for a cluster that would otherwise stop an edge; coarse because it only has to find room"};
inline constexpr NamedConstant rehome_tries{"rehome_tries", 20000, "positions", "policy",
    "positions anywhere on the board, nearest first and in any rotation, checked for a cluster that would otherwise stop an edge"};
inline constexpr NamedConstant arrange_choices{"arrange_choices", 6, "positions", "policy",
    "legal positions compared by airwire length before one is taken for a block"};
inline constexpr NamedConstant arrange_finalists{"arrange_finalists", 2, "plans", "policy",
    "plans with the smallest span that are squeezed to find which gives the smallest board"};
inline constexpr NamedConstant draw_rounds{"draw_rounds", 4, "passes", "policy",
    "passes in which every cluster is offered a place nearer the pins it connects to; a pass that moves nothing ends the search"};
inline constexpr NamedConstant draw_slack{"draw_slack", 1e6, "nm", "policy",
    "distance from the centre of what a cluster connects to within which it is left alone; one lattice step, so nearer cannot be offered"};
inline constexpr NamedConstant draw_tries{"draw_tries", 200, "positions", "policy",
    "positions nearest the wanted place checked against every rule for one cluster in one pass"};
inline constexpr std::array arrange_registry{arrange_pitch, arrange_gap, room_factor, rehome_pitch, rehome_tries, tighten_rounds, arrange_tries, arrange_choices, draw_rounds, draw_slack, draw_tries,
                                             arrange_finalists};
}

struct ArrangePlan {
    std::string kept_sides;
    std::size_t moved = 0, tightened = 0;
    Nm widened = 0;
    std::vector<std::string> stuck;
    Box span;
    Nm routed = 0;
    double squeezed = 0;
};

struct ArrangeReport {
    std::size_t clusters = 0, sheets = 0, chosen = 0;
    Box before;
    double unarranged = 0;
    std::vector<ArrangePlan> plans;
    std::string holders, anchored_sides;
    double plan_seconds = 0, squeeze_seconds = 0;
};

struct DrawReport {
    std::size_t clusters = 0, moved = 0, rounds = 0;
    Nm routed_before = 0, routed_after = 0, pulled_before = 0, pulled_after = 0;
};

DrawReport draw_in(Kernel& kernel);
Box held_extent(const Kernel& kernel);
std::string extent_holders(const Kernel& kernel);
ArrangeReport arrange(Kernel& kernel, const SqueezeOptions& options, const std::function<void()>& settle = {});
bool rehome(Kernel& kernel, const std::vector<std::size_t>& members);

}
