#pragma once
#include "schgen/pcb_placement.hpp"

namespace schgen {
// Search-policy overrides only: circuit, contracts, outline and caller-owned
// shape/face restrictions remain the same for every attempt.
struct PcbPlacementSearchStrategy {
    bool vertical_compaction = false;
    bool granular_minor_occupancy = false;
    bool dual_primary_reservations = false;
    std::optional<bool> shape_area_first, owned_extent_alternatives, contract_group_rotations;
    std::optional<std::size_t> shape_choice_replays;
};
struct PcbPlacementSearchAttempt {
    std::string status, detail;
    ExecutionAccounting accounting; // actual construction + independent screening
};
struct PcbPlacementSearchResult {
    std::optional<PcbPlacementResult> incumbent;
    std::optional<std::size_t> incumbent_attempt;
    std::vector<PcbPlacementSearchAttempt> attempts; // baseline first
    ExecutionAccounting accounting; // import THIS, not incumbent's subset
};
// Build baseline, then each supplied strategy once. Keep a complete screened
// incumbent on failed/non-improving trials; never reuse historical geometry.
// Rank screened models by area, width, height, then advisory cross-wire length;
// an exact tie retains the earlier complete model. No wiring-length ceiling.
// Screening covers placement gates, enforced compose terms, fanout and board
// bounds. This is NOT full board qualification: final pipeline gates remain
// mandatory. Unknown exceptions propagate with all available work receipts.
PcbPlacementSearchResult search_pcb_models(const PcbPlacementInput &,
    const std::vector<PcbPlacementSearchStrategy> &, ExecutionFailureReceipt* failure = nullptr);
} // namespace schgen
