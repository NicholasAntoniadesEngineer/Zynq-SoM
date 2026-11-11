#pragma once

#include "schgen/layout_kernel.hpp"

#include <optional>

namespace schgen::layout {

namespace constants {
inline constexpr NamedConstant sink_reach{"sink_reach", 3e6, "nm", "policy",
    "largest distance from its target at which a part is seated when it changes face or joins its owner"};
inline constexpr std::array sink_registry{sink_reach};
}

struct AttractReport {
    std::size_t wanted = 0, seated = 0, to_rear = 0, met_before = 0, met_after = 0;
    Nm routed_before = 0, routed_after = 0;
};

std::vector<Point> seat_ring(Nm pitch, Nm reach, Point preferred);
bool may_sink(const Problem& problem, const Placement& placement, std::size_t part);
bool crowds_escape(const Problem& problem, const Placement& placement, std::size_t part, const Pose& pose);
bool sink_part(Kernel& kernel, std::size_t part, const std::vector<Point>& offsets);
struct BalanceReport {
    std::size_t sets = 0, flipped = 0, parts = 0;
    double top_before = 0, rear_before = 0, top_after = 0, rear_after = 0;
};

BalanceReport balance_faces(Kernel& kernel, Nm pitch, Nm reach);
AttractReport attract(Kernel& kernel, Nm pitch, Nm reach);

}
