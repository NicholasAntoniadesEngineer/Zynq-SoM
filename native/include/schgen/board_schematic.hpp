#pragma once

#include "schgen/netlist_gate.hpp"
#include "schgen/schematic_place.hpp"

#include <cstdint>
#include <filesystem>
#include <optional>
#include <stdexcept>
#include <string>
#include <vector>

namespace schgen {

class BoardSchematicError : public std::runtime_error {
public:
    using std::runtime_error::runtime_error;
};

// The caller assigns persistent project-local bands; sheet order controls page
// order only. Local numeric reference suffixes must be <1000. No source reloads.
std::string board_renamed_ref(const std::string& ref, std::int64_t band,
                              const std::string& sheet = {});
SchematicDesign uniquify_board_design(const SchematicDesign& design, std::int64_t band);
void strip_duplicate_board_flags(std::vector<SchematicDesign>& designs, SymbolLibrary& library);

struct BoardSheetDesign {
    SchematicDesign design;
    std::int64_t reference_band = 0;
};
struct BoardPlacedSheet {
    std::string name;
    SchematicDesign design;  // Uniquified, hierarchical (standalone=false).
    std::string symbol_uuid;
};
struct BoardHierarchy {
    SchematicDesign root;
    std::string root_uuid;
    std::vector<BoardPlacedSheet> sheets;
};

// Pure assembly, not a gate verdict. Child and root emission use the existing
// native emitter. Rejects collisions, unsafe output paths and an unplaceable
// hierarchy instead of silently omitting sheets. All input values are copied.
BoardHierarchy make_board_hierarchy(const std::vector<BoardSheetDesign>& sheets,
    SymbolLibrary& library, const std::string& root_name = "board",
    const std::string& sheet_subdir = {});

struct BoardNetlistResult {
    std::size_t failures = 0;
    std::vector<std::string> lines;
    // Root ERC is informational in the original board gate, not hidden or
    // conflated with connectivity. Command orchestration may enforce it.
    bool erc_ran = false;
    int erc_exit_code = 0;
    std::filesystem::path erc_report;
    bool ok() const { return failures == 0; }
    std::string summary() const;
};

// Every public PORT and POWER/GROUND net is checked, in sorted port-then-rail
// order. Same-sheet internal SIGNAL names are not linked by this gate.
BoardNetlistResult check_board_netlist(const std::vector<BoardPlacedSheet>& sheets,
    const ExtractedNetlist& extracted, SymbolLibrary& library);
// Live extraction and root ERC; writes board_gate.txt and board.erc.rpt in the
// requested report directory. No cached netlist or success fallback.
BoardNetlistResult check_board_netlist(const std::vector<BoardPlacedSheet>& sheets,
    const std::filesystem::path& root_path, const std::filesystem::path& reports_dir,
    SymbolLibrary& library, const NetlistExtractOptions& options = {});

struct BoardPreparedSheet {
    SchematicPlacement placement;
    SchematicRoutedSheet routed;
};
struct BoardSheetInput {
    CircuitSheetIr circuit;
    std::int64_t reference_band = 0;
    // Previously computed native placements may be reused; this never skips
    // completeness, input-driver, visual or emitted-netlist checks.
    std::optional<BoardPreparedSheet> prepared;
};
struct BoardSchematicOptions {
    std::string root_name = "board";
    std::string sheet_subdir;
    std::filesystem::path reports_dir;  // Empty means output directory.
    NetlistExtractOptions extraction;
    // Zero selects min(8, hardware concurrency); never exceeds sheet count.
    // Emission/library access stays sequential. Results/errors retain input order.
    std::size_t netlist_workers = 0;
};
struct BoardSheetGateResult {
    std::string name;
    ElectricalValidationResult electrical;
    VisualResult visual;
    NetlistGateResult netlist;
    bool ok() const { return electrical.ok() && visual.ok && netlist.ok; }
};
struct BoardSchematicResult {
    std::filesystem::path root_path, project_path;
    std::vector<BoardSheetGateResult> per_sheet;
    BoardNetlistResult board;
    std::vector<std::string> per_sheet_failures;
    std::string report;  // Ordered board-stage console report, no trailing LF.
    bool ok() const;
};

// Complete board.py stage. Missing placements use the real native placer and
// router. Every emitted uniquified sheet is independently exported and gated;
// the root hierarchy is then exported and checked even after sheet failures.
// Link/SoM policy and other whole-command gates remain caller-owned; no project
// configuration, source JSON or shared output path is inferred here.
BoardSchematicResult build_board_schematic(const std::vector<BoardSheetInput>& sheets,
    SymbolLibrary& library, const std::filesystem::path& outdir,
    const BoardSchematicOptions& options = {});

// Existing unrelated project JSON fields survive; meta and erc are replaced as
// in board.py. Output uses Python json.dumps(indent=2) spelling and final LF.
std::string board_project_json(const JsonNode& existing, const std::string& root_name);
std::string strip_board_report_timestamp(const std::string& report);

}  // namespace schgen
