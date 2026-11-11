#pragma once

#include "schgen/layout_kernel.hpp"

#include <string>

namespace schgen::layout {

namespace constants {
inline constexpr NamedConstant search_pitch{"search_pitch", 0.25e6, "nm", "policy",
    "lattice pitch of the relocation search"};
inline constexpr NamedConstant part_reach{"part_reach", 2e6, "nm", "policy",
    "largest relocation tried for one part on its own"};
inline constexpr NamedConstant unit_reach{"unit_reach", 6e6, "nm", "policy",
    "largest relocation tried for one bundle"};
inline constexpr NamedConstant first_step{"first_step", 2e6, "nm", "policy",
    "largest distance one edge moves in a single attempt"};
inline constexpr NamedConstant last_step{"last_step", 0.25e6, "nm", "policy",
    "smallest distance one edge moves in a single attempt"};
inline constexpr NamedConstant step_ratio{"step_ratio", 2.0, "ratio", "policy",
    "factor between successive edge steps"};
inline constexpr NamedConstant settle_rounds{"settle_rounds", 4.0, "count", "policy",
    "full rule sweeps allowed while one edge step settles"};
inline constexpr std::array squeeze_registry{search_pitch, part_reach, unit_reach, first_step, last_step,
                                             step_ratio, settle_rounds};
}

enum class Side : std::uint8_t { north, south, west, east };

const char* side_name(Side side);

struct Bundles {
    std::vector<std::vector<std::size_t>> units;
    std::vector<std::size_t> unit_of;
};

Bundles bundle(const Problem& problem);

struct SqueezeOptions {
    Nm pitch = 0, part_reach = 0, unit_reach = 0, first_step = 0, last_step = 0;
    std::size_t rounds = 0;
    std::array<Side, edge_count> order{Side::east, Side::south, Side::west, Side::north};
};

SqueezeOptions default_squeeze();

struct Attempt {
    Side side = Side::north;
    Nm step = 0;
    bool kept = false, scaled = false, along_x = false;
    std::size_t relocated = 0, pushed = 0, sunk = 0;
    std::string blocker;
};

struct SqueezeReport {
    Board before, after;
    Nm routed_before = 0, routed_after = 0;
    std::vector<Attempt> attempts;
    std::vector<double> tried;
};

SqueezeReport squeeze(Kernel& kernel, const SqueezeOptions& options);
SqueezeReport squeeze_best(Kernel& kernel, const SqueezeOptions& options);

}
