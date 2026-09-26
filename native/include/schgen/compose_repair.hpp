#pragma once
#include "schgen/pcb_emit.hpp"
#include "schgen/pcb_placement_gates.hpp"
#include <functional>

namespace schgen {
// Value-owned JSON with Python int/float spelling and arbitrary integer tokens.
// No file is read or written by parsing, edits, prediction or measurement.
using ComposeDocument = PcbProjectDocument;
ComposeDocument parse_compose_document(std::string_view, const std::string &source = "<compose>");
std::string render_compose_json(const ComposeDocument &, int indent = 2, bool sorted = false);
using ComposeTermKey = std::tuple<std::string, std::string, std::string>;
enum class ComposeEditKind { AddPull, SetPullWeight, MoveEdgeBlock, Composite };
struct ComposeSpecEdit {
    ComposeEditKind kind = ComposeEditKind::AddPull;
    std::optional<ComposeTermKey> target_key;
    std::string block, to, face = "center", basis, name, from_edge, to_edge;
    double weight = 10.;
    bool exclusive = false;
    // MoveEdgeBlock is always intent. Composite derives intent from children.
    bool intent() const;
    std::vector<ComposeSpecEdit> edits;
    std::string describe() const;
    ComposeDocument apply(const ComposeDocument &) const;
};
std::vector<ComposeSpecEdit> parse_compose_allow_intent(const std::vector<std::string> &);
std::vector<ComposeSpecEdit> propose_compose_repairs(ComposeDocument &ledger,
    const ComposeDocument &raw_spec, const std::vector<ComposeSpecEdit> &allowed);
struct ComposeAcceptance {
    bool ok = true;
    std::vector<std::string> reasons;
};
ComposeAcceptance accept_compose_repair(const ComposeDocument &before, const ComposeDocument &after,
    const std::set<ComposeTermKey> &targets = {}, bool allow_area_growth = false);

// Reuses the independent final-model gates; never accepts predicted verdicts.
ComposeDocument measure_compose_ledger(const PcbPlacementInput &, const PcbModel &);
struct ComposeReplica {
    FloorplanPlan plan;
    FloorplanOffsets poses;
    FloorplanLegalizeInput evaluation;
    double area = 0.;
};
ComposeReplica compose_plan_replica(const PcbPlacementInput &, const FloorplanSpec &);
struct ComposeCandidate {
    ComposeSpecEdit edit;
    ComposeDocument edited;
    std::vector<FloorplanTermEval> evaluations;
    double area = 0., aggregate_margin = 0.;
    int soft_red = 0;
    std::vector<std::string> spilled;
    std::string error;
};
ComposeCandidate evaluate_compose_candidate(const PcbPlacementInput &, const ComposeDocument &raw,
    const ComposeSpecEdit &, const FloorplanTermIndex &,
    const std::optional<std::set<std::string>> &valid_names = std::nullopt);
// Ranking is policy only. It does not turn predictions into rebuilt-board proof.
struct ComposeRanking {
    std::vector<ComposeCandidate> ranked;
    std::string output;
};
ComposeRanking rank_compose_candidates(std::vector<ComposeCandidate>);
struct ComposeLedgerDocuments { std::string json, markdown; };
ComposeLedgerDocuments append_compose_ledger(const ComposeDocument &history,
    const ComposeDocument &ledger, const std::string &step);
void write_compose_ledger(const ComposeDocument &, const std::string &step,
    const std::filesystem::path &json_path, const std::filesystem::path &md_path);

struct ComposeCommandOptions {
    bool repair = false, dry_run = false;
    int max_steps = 4; // Reserved by the original CLI: one selected edit per invocation.
    std::vector<std::string> allow_intent;
};
struct ComposeCommandPaths {
    std::filesystem::path spec, ledger_json, ledger_markdown;
};
struct ComposeBoardSnapshot { PcbPlacementInput input; PcbModel model; };
struct ComposeBoardRun {
    int exit_code = 1;
    std::string stdout_text;
};
struct ComposeCommandHost {
    // Read/build a fresh native model, with current authored spec and evidence.
    std::function<ComposeBoardSnapshot()> build_model;
    // APPLY ONLY. Parent supplies its complete native board publication + gate
    // pipeline. Exit zero must mean that whole command passed, not just placement.
    // A successful run is followed by build_model and independent measurement.
    // This is an orchestration seam, not a callback for any gate or solver.
    std::function<ComposeBoardRun()> run_board;
    std::function<void(const std::string &)> output;
};
struct ComposeCommandResult { int exit_code = 0; std::string output; bool applied = false; };
// Explicit publication entry point. Measure/dry-run append ledgers only.
// Apply writes the selected spec, runs the host's native board pipeline once,
// then accepts or restores the original spec bytes. It never commits or retries
// another candidate, and does not roll back board artifacts produced by the host.
// Rebuild/measurement exceptions restore the tentative spec, then propagate.
// After acceptance, ledger publication errors propagate without undoing the
// accepted spec; JSON and Markdown publication are not a multi-file transaction.
ComposeCommandResult run_compose_command(const ComposeCommandOptions &,
    const ComposeCommandPaths &, const ComposeCommandHost &);
} // namespace schgen
