#pragma once
#include "schgen/pcb_placement.hpp"
#include "schgen/ratsnest.hpp"

namespace schgen {
struct PcbContractSourcePart {
    std::string footprint;
    PcbCheckFootprintPtr mod;
};
// All authoring policy is invocation-owned. Source parts are PRE-placement
// snapshots for pin-ID validation; final geometry always comes from the model.
struct PcbPlacementGatePolicy {
    std::map<std::string, JsonNode> contracts;
    std::map<std::string, std::map<std::string, std::string>> ref_maps;
    std::map<std::string, std::map<std::string, PcbContractSourcePart>> source_parts;
    std::set<std::string> wired_sheets, project_zones;
};
PcbPlacementGatePolicy pcb_placement_gate_policy(const PcbPlacementInput &);
// Default final-report scope is the placed sheet names, not every authored
// sheet. Reuses the existing live term builder without solving/placing again.
FloorplanTermIndex pcb_final_compose_index(const PcbPlacementInput &, const PcbCheckModel &);
class PcbContractPinError : public std::invalid_argument {
  public:
    using std::invalid_argument::invalid_argument;
};
void validate_pcb_contract_pins(const std::string &sheet, const JsonNode &,
                                const std::map<std::string, PcbContractSourcePart> &);
void validate_pcb_contract_pins(const PcbPlacementGatePolicy &);
struct PcbPlacementContractResult {
    bool ok = true, have_contract = false;
    std::string sheet;
    int checked = 0, hot_loop_fail = 0, same_side_fail = 0, bulk_fail = 0, bulk_out_fail = 0,
        sw_node_fail = 0, fb_fail = 0, boot_fail = 0, vcc_fail = 0, bias_fail = 0, rt_fail = 0,
        ldo_fail = 0, proximity_fail = 0, unknown_fail = 0;
    std::vector<std::string> violations, missing_refs, sheet_summaries;
    std::string summary() const;
};
// Null contract means absent policy, NOT a request for an implicit loader.
PcbPlacementContractResult
check_pcb_placement_contract(const PcbCheckInput &, const std::string &sheet,
                             const JsonNode *contract,
                             const std::map<std::string, std::string> &ref_map);
// Wired verdict includes configured sheets even when no instances were placed.
PcbPlacementContractResult check_pcb_wired_contracts(const PcbCheckInput &,
                                                     const PcbPlacementGatePolicy &);
using PcbContractResults = std::map<std::string, PcbPlacementContractResult>;
// check_all: every placed authored sheet, including inert policy.
PcbContractResults check_all_pcb_placement_contracts(const PcbCheckInput &,
                                                     const PcbPlacementGatePolicy &);
// coverage: every authored sheet, including absent and inert sheets.
PcbContractResults pcb_contract_coverage(const PcbCheckInput &, const PcbPlacementGatePolicy &);
struct PcbContractCoverageReport {
    std::string text;
    int wired = 0, met = 0, violated = 0;
};
PcbContractCoverageReport render_pcb_contract_coverage(const PcbContractResults &,
                                                       const std::set<std::string> &wired);

struct PcbPlacementFlowTerm {
    std::string kind, subject, target;
    double measured = 0, bound = 0;
    bool ok = false;
    std::string basis;
};
struct PcbPlacementFlowResult {
    bool ok = true;
    int n_contracts = 0, flow_checked = 0, flow_fail = 0, facing_checked = 0, facing_fail = 0,
        far_checked = 0, far_fail = 0, near_max_checked = 0, near_max_fail = 0;
    std::vector<std::string> unresolved, na, violations, detail;
    double board_area = 0, flow_budget_mm = 0;
    std::vector<PcbPlacementFlowTerm> terms;
    std::string summary() const;
};
// Default selection matches the emitted gate: placed WIRED external contracts.
// A supplied selection is explicit and may include inert or unplaced sheets.
PcbPlacementFlowResult
check_pcb_placement_flow(const PcbCheckInput &, const PcbPlacementGatePolicy &,
                         const std::map<std::string, JsonNode> *selected_contracts = nullptr);

struct PcbComposeCoexistence {
    std::string ref, sheet, verdict;
};
struct PcbComposeEvidence {
    // Board-relative frame; reporter adds model.origin_x/y for placed pads.
    std::vector<std::pair<std::string, Box4>> corridors;
    // Source order is meaningful: the last duplicate ref/sheet wins.
    std::vector<PcbComposeCoexistence> coexistence;
};
// Pure boundary. Null sidecar means absent. Caller decides prior versus current
// evidence; this function never reads or writes escape_block.json.
PcbComposeEvidence pcb_compose_evidence(const JsonNode &sidecar, FloorplanPoint origin = {25, 25});
// Matches generation's write-new-sidecar-before-compose ordering, without I/O.
PcbComposeEvidence pcb_compose_evidence(const PcbModel &);
std::vector<FloorplanTermEval> measure_pcb_compose_terms(const PcbCheckInput &,
                                                         const FloorplanTermIndex &,
                                                         const PcbPlacementGatePolicy &);
using PcbCrossAirwires = std::map<std::pair<std::string, std::string>, std::pair<int, double>>;
PcbCrossAirwires pcb_cross_airwires_by_pair(const PcbCheckModel &, const RatsnestNets * = nullptr,
                                            const RatsnestEdges * = nullptr);
struct PcbComposeReport {
    FloorplanTermIndex index;
    std::vector<FloorplanTermEval> evaluations;
    int hard_red = 0, soft_red = 0;
    double hard_margin_sum = 0, hard_margin_min = 0;
    std::size_t n_corridors = 0;
    std::vector<std::string> unmanaged, managed;
    PcbCrossAirwires cross_airwires;
    std::string text() const;
};
PcbComposeReport report_pcb_composition(const PcbCheckInput &, const FloorplanTermIndex &,
                                        const PcbPlacementGatePolicy &, const PcbComposeEvidence &,
                                        const RatsnestNets * = nullptr,
                                        const RatsnestEdges * = nullptr);
struct PcbPlacementGatesResult {
    PcbPlacementContractResult placement_contract;
    PcbPlacementFlowResult placement_flow;
    PcbContractResults coverage;
    PcbContractCoverageReport coverage_report;
    PcbComposeReport composition;
    // Original orchestration: coverage and composition are advisory ledgers.
    bool ok() const { return placement_contract.ok && placement_flow.ok; }
};
// Full independent post-placement family, including fresh pin validation.
// No cached success and no constructor/solver result is accepted as evidence.
PcbPlacementGatesResult
check_pcb_placement_gates(const PcbCheckInput &, const PcbPlacementGatePolicy &,
                          const FloorplanTermIndex &, const PcbComposeEvidence &,
                          const RatsnestNets * = nullptr, const RatsnestEdges * = nullptr);
// Production convenience: live policy + final placed-sheet term scope + current
// model T2 evidence. No fixtures, filesystem reads, Python or second solve.
PcbPlacementGatesResult check_pcb_placement_gates(const PcbPlacementInput &, const PcbModel &);
} // namespace schgen
