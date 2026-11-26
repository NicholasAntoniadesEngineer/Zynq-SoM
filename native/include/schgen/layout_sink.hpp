#pragma once

#include "schgen/layout_kernel.hpp"

#include <optional>

namespace schgen::layout {

namespace constants {
inline constexpr NamedConstant sink_reach{"sink_reach", 3e6, "nm", "policy",
    "largest distance from its target at which a part is seated when it changes face or joins its owner"};
inline constexpr NamedConstant ring_limit{"ring_limit", 8e6, "nm", "policy",
    "largest radius searched for a seat at a pin; seats farther out are no better and cost time"};
inline constexpr NamedConstant aside_reach{"aside_reach", 4e6, "nm", "policy",
    "farthest a blocking small part is moved aside to free a seat at a pin"};
inline constexpr NamedConstant evict_tries{"evict_tries", 6, "seats", "policy",
    "number of best seats within reach at which blockers are moved aside for one part"};
inline constexpr NamedConstant small_pins{"small_pins", 2, "pins", "policy",
    "a part with at most this many connected pins may be moved aside for a part that serves a pin"};
inline constexpr NamedConstant far_pitch{"far_pitch", 1e6, "nm", "policy",
    "lattice pitch of the widening search for a part with no seat near the pin it serves; it only has to find the nearest room"};
inline constexpr NamedConstant obstacle_rows{"obstacle_rows", 8, "rows", "report",
    "number of most frequent obstacles named for a part that is not within reach of the pin it serves"};
inline constexpr NamedConstant order_tries{"order_tries", 24, "seats", "policy",
    "seats at a connector pin tried for a protection part when the parts nearer than it are moved back together"};
inline constexpr NamedConstant balance_samples{"balance_samples", 48, "seats", "report",
    "refused rear seats examined to name what keeps a cluster on top; the report needs the commonest causes, not every seat"};
inline constexpr NamedConstant balance_reach{"balance_reach", 12e6, "nm", "policy",
    "farthest from its mirrored place that a cluster is seated on the rear when that place is taken; the squeeze closes the board over it afterwards"};
inline constexpr NamedConstant exchange_rounds{"exchange_rounds", 4, "rounds", "policy",
    "times a cluster with no rear seat takes the parts found in its way along, so that they change faces together"};
inline constexpr std::array sink_registry{sink_reach, ring_limit, aside_reach, evict_tries, small_pins, far_pitch, obstacle_rows,
                                          order_tries, balance_samples, balance_reach, exchange_rounds};
}

struct AttractReport {
    std::size_t wanted = 0, seated = 0, to_rear = 0, met_before = 0, met_after = 0, moved_aside = 0, far_seated = 0, together = 0;
    Nm routed_before = 0, routed_after = 0;
};

struct OrderReport {
    std::size_t wanted = 0, met_before = 0, reseated = 0, moved_back = 0, met_after = 0;
};

std::vector<Point> seat_ring(Nm pitch, Nm reach, Point preferred);
bool steps_aside(Kernel& kernel, std::size_t part, const std::vector<Point>& offsets);
bool may_sink(const Problem& problem, const Placement& placement, std::size_t part);
bool crowds_escape(const Problem& problem, const Placement& placement, std::size_t part, const Pose& pose);
bool sink_part(Kernel& kernel, std::size_t part, const std::vector<Point>& offsets);
struct BalanceReport {
    std::size_t sets = 0, flipped = 0, parts = 0, shifted = 0, exchanged = 0, risen = 0, released = 0;
    double top_before = 0, rear_before = 0, top_after = 0, rear_after = 0;
    std::vector<std::pair<double, std::string>> kept_on_top;
};

BalanceReport balance_faces(Kernel& kernel, Nm pitch, Nm reach);
AttractReport attract(Kernel& kernel, Nm pitch, Nm reach);
OrderReport lead_first(Kernel& kernel, Nm pitch);
std::string seat_obstacles(const Kernel& kernel, const PadGap& rule, Nm pitch);
bool seat_first(Kernel& kernel, const NetOrder& rule, Nm pitch);
bool seat_faced(Kernel& kernel, const PadGap& rule, Nm pitch, Nm radius, bool evict, std::size_t& moved_aside);
bool seat_faced_chain(Kernel& kernel, const PadGap& rule, Nm pitch, Nm radius, std::size_t& moved_aside);
bool seat_faced_together(Kernel& kernel, const PadGap& rule, Nm pitch, Nm radius);

}
