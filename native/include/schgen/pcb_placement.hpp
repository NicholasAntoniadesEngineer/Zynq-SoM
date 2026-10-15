#pragma once
#include "schgen/pcb_escape.hpp"
#include "schgen/pcb_stage_templates.hpp"
#include "schgen/pcb_owned_groups_adapter.hpp"

namespace schgen {
// A packed spill needs a new edge-conditioned zone solve, not a connector-only
// translation. The retry specification preserves non-edge policy verbatim.
FloorplanSpec pcb_edge_replan_spec(const FloorplanSpec&, const FloorplanPlan&);
class PcbEdgeGeometryMismatch : public PcbZoneInfeasible {
  public:
    FloorplanSpec retry_spec;
    PcbEdgeGeometryMismatch(const std::string& message, FloorplanSpec spec)
        : PcbZoneInfeasible(message), retry_spec(std::move(spec)) {}
};
struct PcbPlacementExperiment;
struct PcbPlacementInput {
    FloorplanInput floorplan;
    // Opaque footprint keys agree with floorplan.footprint_of. These are exact
    // source documents, not posed models. Mirroring stays in memory.
    PcbFootprintPool footprints;
    std::map<std::string, JsonNode> contracts; // all authored, including inert
    KicadNetlist netlist; // independently extracted board schematic connectivity
    SomInterface som_interface;
    std::map<std::string, PcbCheckFootprintPtr> return_path_footprints;
    std::string interface_bytes;
    ProjectStrings function_map;
    bool two_side = true;
    std::shared_ptr<const PcbPlacementExperiment> experiment;
    TrustedOwnedGroupInputs owned_groups; // compact-only, validated board inputs
};
struct PcbZoneResult {
    FloorplanZoneGeometry geometry;
    PcbFootprintPool footprints;
    std::vector<std::string> fallback_events;
    std::map<std::string, std::size_t> quantization_engagements;
    // Sheet + stable shape index (zero also covers the implicit incumbent).
    // Selector transport is a separate integration; no geometry is replaced.
    std::map<FloorplanShapeKey, OwnedShapeQuality> owned_shape_quality;
};
using PcbPlacementPose = std::tuple<double, double, double, std::string>;
enum class PcbZoneAccountingOwnership { Unspecified, IncludedInFloorplan, SeparateFromFloorplan };
struct PcbPlacementResult {
    PcbModel model;
    FloorplanStage floorplan;
    std::map<std::string, std::map<std::string, PcbPlacementPose>> stages;
    std::vector<std::string> fallback_events;
    // Legacy fallback_events above remains zone prefix + placement events.
    // Import these disjoint observations, never that legacy vector as a delta.
    ExecutionAccounting placement_accounting; // only post-floorplan placement/refit
    ExecutionAccounting zone_accounting;      // actual placement-zone invocation
    PcbZoneAccountingOwnership zone_accounting_ownership = PcbZoneAccountingOwnership::Unspecified;
};
PcbZoneResult build_pcb_zone_geometry(const PcbPlacementInput &, ExecutionFailureReceipt* failure = nullptr);
FloorplanZoneGeometry bind_pcb_zone_shapes(const PcbZoneResult &,
                                           const std::map<std::string, int> &chosen);
// Rebuilds compose terms, metrics, side offers and impedance classes from live
// authored inputs. Caller-supplied prior escape corridors are retained; no
// other precomputed geometry or compose result is reused.
FloorplanInput prepare_pcb_floorplan(const PcbPlacementInput &, const PcbZoneResult &);
// Executes the placed-board stages against an explicitly owned native solve.
// Useful when board generation already owns the physical floorplan result.
PcbPlacementResult place_pcb_model(const PcbPlacementInput &, const PcbZoneResult &,
                                   const FloorplanStage &);
// Explicit ownership for an externally supplied solve; no ancestry guessing.
PcbPlacementResult place_pcb_model_accounted(const PcbPlacementInput &, const PcbZoneResult &,
    const FloorplanStage &, PcbZoneAccountingOwnership, ExecutionFailureReceipt* failure = nullptr);
// Complete build-owned aggregate: plan + separate zones (if any) + placement.
// Unknown ownership rejects. Counts are added with overflow checks; no math runs.
ExecutionAccounting pcb_placement_accounting(const PcbPlacementResult &);
// Production path: derive zones -> native floorplan -> all placement stages ->
// return-path remediation and escape plan. No fixture/model deserialization.
// This constructs a model, not a verification verdict: independent final-model
// placement-contract, placement-flow, compose/coverage and PCB checks remain
// mandatory orchestration steps. Solver feasibility does not replace them.
PcbPlacementResult build_pcb_model(const PcbPlacementInput &, ExecutionFailureReceipt* failure = nullptr);
// Search-policy overrides only: circuit, contracts, outline and caller-owned
// shape/face restrictions remain the same for every attempt.
struct PcbPlacementSearchStrategy {
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
