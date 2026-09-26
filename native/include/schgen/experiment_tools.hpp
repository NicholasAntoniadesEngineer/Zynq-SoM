#pragma once
#include "schgen/compose_repair.hpp"
#include "schgen/experiment_observers.hpp"
#include "schgen/project_authoring.hpp"

namespace schgen {
using ExperimentDocument = ComposeDocument;
// Explicit formatting boundary: Python-compatible integer/float distinctions,
// insertion order and separators. indent=-1 means json.dumps default spacing.
std::string render_experiment_json(const ExperimentDocument &, int indent = -1,
                                   bool ensure_ascii = true);
ExperimentDocument experiment_either_side_spec(const ExperimentDocument &,
                                               const std::vector<std::string> &sheets);
// Decimal/scientific literal only, never a source expression. Full consumption,
// finite, >= 0; preserves the original argument separately in SWEEP output.
double parse_experiment_ordinary_via(const std::string &);

struct ExperimentBoardRequest {
    bool no_render = true;
    std::optional<double> ordinary_via_mm;
};
struct ExperimentBoardRun { int exit_code = 1; std::string stdout_text, stderr_text; };
struct ExperimentBoardPaths { std::filesystem::path spec, fallback_baseline, pcb, verdict; };
struct ExperimentBoardHost {
    // Parent supplies the real native board publication + independent gates.
    // The W11 override MUST reach each build-owned FloorplanInput.experiment;
    // it is never a source rewrite or a process-global constant mutation.
    std::function<ExperimentBoardRun(const ExperimentBoardRequest &)> run_board;
};
struct ExperimentBoardReport {
    std::string output;
    // Historical diagnostics use the stdout token, NOT the subprocess status.
    // Neither member is a substitute for the actual native gate result.
    bool pass_token = false;
    int board_exit_code = 1;
};
ExperimentBoardReport format_chir_rung(const std::string &tag, const ExperimentBoardRun &,
    const ExperimentDocument &verdict, const std::string &pcb_bytes);
ExperimentBoardReport format_w11_sweep(const std::string &ordinary_argument,
    const std::vector<std::string> &sheets, const ExperimentBoardRun &,
    const ExperimentDocument &verdict, const std::string &pcb_bytes);
// Explicit write/apply boundary. Temporarily writes only spec (when sheets are
// requested), calls the host once, reads PCB/verdict, then restores exact spec
// and baseline bytes on success/failure/exception. Board artifacts are NOT
// rolled back. All original files must exist before any write. No Python file
// is read, rewritten or executed. Original scripts return success for a printed
// failed experiment; CLI dispatch should return zero after these functions.
ExperimentBoardReport run_chir_rung(const ExperimentBoardPaths &, const ExperimentBoardHost &,
    const std::string &tag, const std::vector<std::string> &sheets = {});
ExperimentBoardReport run_w11_sweep(const ExperimentBoardPaths &, const ExperimentBoardHost &,
    const std::string &ordinary_argument, const std::vector<std::string> &sheets = {});

struct ExperimentLengths { double cross = 0, total = 0; int n_cross = 0; };
ExperimentLengths experiment_cross_lengths(const std::vector<PcbCheckInstance> &);
struct ExperimentProbeResult {
    PcbPlacementResult placement;
    ExperimentDocument document;
    std::string output;
};
// Read/build only. Candidate layer edits exist in a private typed input copy;
// no floorplan, board, baseline, sidecar or catalog is published. The caller
// supplies live native-authored inputs; these never load frozen test evidence.
ExperimentProbeResult run_w12_bound(PcbPlacementInput, const std::string &tag,
    const std::vector<std::string> &sheets = {});
ExperimentProbeResult run_w12_stageprobe(PcbPlacementInput, const std::string &tag,
    const std::vector<std::string> &sheets = {}, bool conservative_only = false);

struct NativeCircuitDump { std::filesystem::path path; std::string bytes; };
std::filesystem::path experiment_circuit_json_path(const std::filesystem::path &legacy_handle);
NativeCircuitDump prepare_native_circuit_dump(const CircuitSheetIr &,
                                             const std::filesystem::path &legacy_handle);
// Uses registered C++ factories and live native part authoring, never stored
// circuit.json outputs or a Python module. Caller opens/retains the part catalog
// as for author_project_subsystem. Registry order is sorted by subsystem name.
std::vector<NativeCircuitDump> prepare_native_circuit_dumps(const ProjectPaths &,
    const std::string &authoring_project, ProjectAuthoringInput = {});
void publish_native_circuit_dump(const NativeCircuitDump &);
// Explicit catalog publication: author/roundtrip/write each sheet in order.
// A later failure leaves earlier writes, matching the original script. Output
// is returned only once all writes succeed. It does not compile any catalog or
// touch the historical "dump_circuits 2.py" cloud duplicate.
std::string run_dump_circuits(const ProjectPaths &, const std::string &authoring_project,
                             ProjectAuthoringInput = {});
} // namespace schgen
