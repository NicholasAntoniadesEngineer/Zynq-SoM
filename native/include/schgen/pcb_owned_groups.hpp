#pragma once
#include "schgen/pcb_checks.hpp"
#include <set>

namespace schgen {
// Placement policy only: Bypass includes explicitly declared pin-local
// reference filters. Electrical roles remain distinct in trusted requirements.
enum class OwnedCapRole { Bypass, OutputBulk };
// Resolved from validated declarations and trusted hierarchy maps, never from
// a nearest component, shared-net membership, or candidate geometry.
struct OwnedCapPlacement {
    std::string owner, owner_pin, cap, cap_pin, return_pin, rail, return_net;
    OwnedCapRole role = OwnedCapRole::Bypass;
};
struct OwnedGroupOptions {
    bool compact = false;
    double clearance = 0;
    // Explicit permission supplied by the existing placement eligibility path.
    // Empty means no movement. No side/rotation permission is inferred here.
    std::set<std::string> movable_caps, fixed_refs, top_refs;
};
struct OwnedGroupCandidate {
    PcbCheckModel model;
    std::map<std::string, double> owned_pad_gaps;
    std::string tag;
};
struct OwnedGroupResult {
    std::vector<OwnedGroupCandidate> alternatives;
    QuantizationCounts quantization;
    std::vector<std::string> diagnostics;
};
// Bounded local search, not a clearance/decoupling acceptance gate. Original
// model is immutable and is NOT replaced. At most two alternatives, each with
// no owned bypass gap increased and at least one strictly decreased. Same side
// and rotation, immutable pad nets, fixed owners and output bulk. Courtyard +
// pad extents obey caller clearance and THT blocks both copper faces.
// Existing independent electrical/mechanical/fanout/placement gates remain
// mandatory after integration. Qualitative proximity always stays UNVERIFIED.
OwnedGroupResult construct_owned_group_candidates(const PcbCheckModel&,
    const std::vector<OwnedCapPlacement>&, const OwnedGroupOptions&);
} // namespace schgen
