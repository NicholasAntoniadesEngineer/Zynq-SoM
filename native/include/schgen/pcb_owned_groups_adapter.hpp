#pragma once
#include "schgen/pcb_owned_groups.hpp"
#include "schgen/owned_shape_quality.hpp"
#include "schgen/floorplan.hpp"

namespace schgen {
struct PcbPlacementInput;
struct PcbZoneResult;
// Opaque, immutable evidence. Only the resolver can create it; raw ownership
// rows cannot enter the production placement input as trusted declarations.
class TrustedOwnedGroups;
const std::vector<OwnedCapPlacement>& owned_group_placements(const TrustedOwnedGroups&);
using TrustedOwnedGroupInputs = std::map<std::string, std::shared_ptr<const TrustedOwnedGroups>>;
TrustedOwnedGroupInputs resolve_owned_group_inputs(const ProjectPaths&,
    const std::vector<ProjectCircuit>&, const PcbPlacementInput&);

namespace pcb_placement {
struct Context;
// Snapshot originals once, append only. allow_movement is the zone eligibility
// decision; excluded zones still receive quality for all their original shapes.
void append_owned_group_zone_shapes(Context&, PcbZoneResult&, const std::string&,
    const FloorplanZoneShape& incumbent, bool allow_movement,
    ExecutionFailureReceipt* failure = nullptr);
}
}
