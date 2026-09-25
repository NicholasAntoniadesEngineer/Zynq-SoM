#pragma once

#include "schgen/board_schematic.hpp"
#include "schgen/pcb_checks.hpp"
#include "schgen/selftest.hpp"

#include <functional>
#include <chrono>

namespace schgen {

struct SelftestStackVerdict {
    std::vector<std::string> failures, passed;
    bool green() const { return failures.empty(); }
    std::string killed_by() const;
};
struct SelftestBuilt {
    CircuitSheetIr circuit;
    std::filesystem::path schematic;
    std::string text;
    SchematicPlacedPage page;
};
struct SelftestMutation {
    std::string name, description;
    std::optional<CircuitSheetIr> circuit;
    std::optional<std::string> text;
    std::optional<SheetGeometry> geometry;
};
struct SelftestMutationResult {
    std::string name, description;
    SelftestStackVerdict verdict;
    bool killed = false;
};
struct SelftestDeterminism {
    bool ok = false;
    std::string diagnostic;
};
struct SelftestSheetInput {
    CircuitSheetIr circuit;
    std::string display_path; // Already selected/resolved by the caller.
    std::string scratch_name; // Empty uses circuit.name; a single path component.
};
struct SelftestSheetResult {
    std::string name;
    SelftestStackVerdict baseline;
    std::vector<SelftestMutationResult> mutations;
    std::vector<std::string> problems;
    std::size_t injected = 0, killed = 0;
    SelftestDeterminism determinism, hashseed;
    std::string report;
};
struct SelftestModelFixtures {
    CircuitSheetIr design_rules, ep, buck, testpoints, mounting_hole;
    CircuitSheetIr cap_voltage, symbol_law, rail_cap, esd_clamp;
    std::vector<CircuitSheetIr> board;
    PcbCheckModel ratsnest;
};
// Input fixtures only, never expected verdicts. Each baseline and mutated copy
// goes through the ordinary live production gate on every invocation.
SelftestModelFixtures selftest_model_fixtures(PcbCheckFootprintPtr resistor_footprint);
CircuitSheetIr selftest_rc_fixture();
struct SelftestModelProof {
    std::string name;
    bool baseline_ok = false, mutation_killed = false;
    std::string diagnostic;
};
struct SelftestModelResult {
    std::vector<SelftestModelProof> proofs;
    std::vector<std::string> problems;
    std::size_t injected = 0, killed = 0;
    std::string report;
};
struct SelftestFullOptions {
    NetlistExtractOptions extraction;
    std::filesystem::path scratch_parent; // Empty selects system temp directory.
    bool keep = false;
    // Native CLI argv prefix. Runner appends request JSON path and output dir.
    // Child dispatches selftest_worker_emit and writes its returned bytes to
    // stdout. Empty is an error, never a skipped determinism proof. No shell.
    std::vector<std::string> worker_command;
    std::chrono::milliseconds worker_timeout{120000};
    std::function<void(const std::string&)> progress;
};
struct SelftestFullResult {
    std::vector<SelftestSheetResult> sheets;
    SelftestModelResult models;
    std::vector<std::string> problems;
    std::size_t injected = 0, killed = 0;
    std::filesystem::path scratch;
    std::string report;
    bool ok() const { return problems.empty(); }
    int exit_code() const { return ok() ? 0 : 1; }
};

SelftestBuilt build_selftest_sheet(const CircuitSheetIr&, SymbolLibrary&,
    const std::filesystem::path& outdir);
SelftestStackVerdict selftest_gate_stack(const CircuitSheetIr&,
    const std::filesystem::path& schematic, SymbolLibrary&,
    const SheetGeometry* geometry = nullptr, const NetlistExtractOptions& = {});
// Preserves pin/label/NC/junction/each-wire/visual mutation ordering. Absent
// targets are absent mutations and are diagnosed by selftest_sheet, not kills.
std::vector<SelftestMutation> selftest_sheet_mutations(const SelftestBuilt&, SymbolLibrary&);
SelftestSheetResult selftest_sheet(const SelftestSheetInput&, SymbolLibrary&,
    const std::filesystem::path& scratch, const NetlistExtractOptions& = {});
SelftestModelResult selftest_model_gates(const SelftestModelFixtures&, SymbolLibrary&,
    const std::filesystem::path& scratch, const NetlistExtractOptions& = {});
SelftestDeterminism selftest_determinism(const CircuitSheetIr&, SymbolLibrary&,
    const std::filesystem::path& scratch);
// Request owns ordered IR and resolved raw symbol snapshots. Worker never
// reloads project circuits or imports Python. Both seed subprocesses rebuild.
JsonNode selftest_worker_request(const SelftestBuilt&, SymbolLibrary&);
std::string selftest_worker_emit(const JsonNode& request, const std::filesystem::path& outdir);
SelftestDeterminism selftest_hashseed_determinism(const CircuitSheetIr&, SymbolLibrary&,
    const std::filesystem::path& scratch, const SelftestFullOptions&);
SelftestFullResult run_full_selftest(const std::vector<SelftestSheetInput>&,
    const SelftestModelFixtures&, SymbolLibrary&, const SelftestFullOptions&);
JsonNode selftest_full_result_json(const SelftestFullResult&);

} // namespace schgen
