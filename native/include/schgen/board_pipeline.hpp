#pragma once
#include "schgen/board_schematic.hpp"
#include "schgen/board_pcb.hpp"
#include "schgen/native_audit_state.hpp"
#include "schgen/spice.hpp"
#include "schgen/manufacturing_exports.hpp"
#include "schgen/project_authoring.hpp"

namespace schgen {
enum class BoardGateStatus { passed, failed, skipped, unavailable };
struct BoardPipelineGate {
    std::string name;
    bool mandatory = true;
    BoardGateStatus status = BoardGateStatus::unavailable;
    std::string report;
};
struct BoardPipelineResult {
    struct Measurements {
        double board_w=0, board_h=0, cross_mm=0;
        int n_top=0, n_bottom=0;
    };
    std::optional<Measurements> measurements;
    std::vector<BoardPipelineGate> gates;
    AuditCounts quantization, fallbacks;
    std::string ledger;
    std::filesystem::path output_root;
    std::size_t sheets = 0;
    std::vector<std::pair<std::string,double>> timing_seconds;
    // complete distinguishes explicitly reported missing native capabilities
    // from successful coverage. Advisory failures do not fail the board.
    bool complete() const;
    bool ok() const;
    int exit_code() const { return ok() ? 0 : 1; }
    std::string report() const;
};
std::string board_pipeline_verdict_json(const BoardPipelineResult&);
// Experiment compatibility document from typed invocation measurements only.
// Missing geometry omits measurements, never supplies fabricated zeroes.
std::string board_pipeline_experiment_json(const BoardPipelineResult&);
// Never approves missing mandatory stages or unauthorized conditional skips.
bool board_pipeline_gate_mandatory(const std::string& name);
// Minimum decision scope for a final board audit. Callers may add files, never
// shrink to just the already-covered quantization implementation pair.
std::vector<CppAuditSource> board_pipeline_audit_sources();
struct BoardAuthoredProject {
    std::vector<ProjectCircuit> circuits;
    // Factories retain metadata and the actual one-time authored IR for gates.
    // They are never loaders of the canonical JSON being verified.
    std::vector<CarrierPackageFactory> factories;
};
// Live C++ project factories, not load_project_circuits. Pure read/build: no
// canonical snapshots or artifacts are published until the explicit call below.
// As with AuthoringContext, the caller must open and retain the repository's
// part catalog before authoring (and before run_board_pipeline).
BoardAuthoredProject author_board_pipeline_inputs(const ProjectPaths&);
// Writes canonical snapshots and required native package assets under output.
// An isolated output never rewrites the source project's stored circuit.json.
void publish_board_pipeline_inputs(BoardAuthoredProject&,const ProjectPaths&,
    const std::filesystem::path& output);

struct BoardPipelineOptions {
    // Explicit output tree. Empty means paths.project_root, as cmd_board.
    // Inputs remain rooted at ProjectPaths; no chdir/environment modification.
    std::filesystem::path output_root;
    NetlistExtractOptions extraction;
    BoardInputOptions pcb;
    SpiceRunOptions spice;
    bool no_render = false, bless = false, timing = false;
    // Configure the built-in reviewed policy from this invocation's real inputs.
    // Explicit caller declarations remain supported when this is false.
    bool native_policy = false;
    bool enforce_coverage_lint = false;
    std::size_t netlist_workers = 0;
    // Empty paths select the original project/repository locations.
    std::filesystem::path fanout_baseline, fallback_baseline, model_directory;
    // Explicit reviewed policy, never synthesized from scanner output or from
    // measured decision names. Missing declarations/manifest hard-fail audits.
    std::vector<NativeLedgerDeclaration> ledger_declarations;
    std::vector<CppAuditSource> audit_sources;
    CppAuditOptions audit;
    // Actual native stage/fallback metadata for pipeline documentation. An
    // empty manifest is a missing capability, not an empty successful document.
    ManufacturingPipelineInput pipeline_metadata;
    std::function<void(const std::string&)> progress;
};
// Live, composed board generation and independent gates. No Python subprocess,
// cached placed board, fixture result, supplied verdict or gate-skip callback.
// Gate/individual publication exceptions become ordered failures; bad_alloc
// and final report publication errors propagate. Missing prerequisites fail.
BoardPipelineResult run_board_pipeline(const ProjectPaths&, const BoardPipelineOptions& = {});

struct BoardCcResult {
    std::string sheet;
    std::vector<std::string> shorts, opens;
    std::size_t n_components = 0, n_declared = 0;
    bool ok() const { return shorts.empty() && opens.empty(); }
    std::string summary() const;
};
// Geometry-first connectivity: declared nets NEVER seed a union. Labels and
// power symbols may legally bridge components, as in the independent CC gate.
BoardCcResult check_board_sheet_cc(const CircuitSheetIr&, const SchematicRoutePlacement&,
    const SchematicRoutedSheet&, const SchematicSymbolResolver&);
// Replays measured decisions into an already declared ledger. Validates live
// assumption providers, exact declaration keys and nesting; no math reexecution.
void import_board_floorplan_ledger(NativeLedger&, const FloorplanAccounting&,
    const std::vector<NativeLedgerDeclaration>&);
struct BoardGoldenResult {
    bool match = false, blessed = false, have_baseline = false;
    std::map<std::string,std::string> current;
    std::vector<std::string> drift;
    std::string summary() const;
};
// Legacy 16x16 grayscale/bicubic average hash. Ignores PNG alpha like convert L.
std::string board_png_average_hash(const std::filesystem::path&);
// Advisory comparison. Only explicit bless writes golden.json, including when
// the baseline is absent. Corrupt baselines/PNGs throw; no discrepancy waiver.
// An external baseline is read-only; explicit blessing always writes to renders.
BoardGoldenResult check_board_golden(const std::filesystem::path& renders,bool bless=false,
    const std::filesystem::path& baseline={});
struct BoardCoverageLintResult {
    std::size_t sheets=0,parts=0,structured=0,free=0,ungated=0;
    std::string report;
    bool ok() const { return ungated==0; }
};
// Checks the explicitly supplied wired-sheet IR, even if no footprints placed.
// Missing contracts expose ungated parts; no implicit filesystem/package load.
BoardCoverageLintResult check_board_contract_coverage(const std::vector<CircuitSheetIr>&,
    const std::map<std::string,JsonNode>& contracts,
    const std::map<std::string,std::map<std::string,std::string>>& ref_maps,
    bool enforce=false);
} // namespace schgen
