#pragma once
#include "schgen/board_pipeline.hpp"
#include "schgen/pcb_verification.hpp"
#include "schgen/firmware_docs.hpp"
#include "schgen/design_rules.hpp"
#include "schgen/execution_timing.hpp"
#include "schgen/project_outputs.hpp"
#include <fstream>
#include <iterator>
#include <sstream>
#include <algorithm>

namespace schgen::board_pipeline_detail {
namespace fs = std::filesystem;
std::string read(const fs::path&);
std::string quote(const std::string&);
std::string json(const JsonNode&);
JsonNode number(double);
JsonNode text(std::string);
std::string join(const std::vector<std::string>&, const std::string& = ", ");
struct Context {
    const ProjectPaths& paths;
    BoardPipelineOptions options;
    fs::path out, reports, docs, renders, manufacturing;
    SymbolLibrary library;
    BoardPipelineResult result;
    std::vector<ProjectCircuit> circuits;
    std::optional<BoardAuthoredProject> authored;
    std::vector<CircuitSheetIr> sheets;
    SheetIndex index;
    std::optional<LinkResult> link;
    std::optional<SomInterface> som;
    std::optional<BoardSchematicResult> schematic;
    std::optional<BoardPcbStage> pcb;
    std::optional<PcbVerificationResult> geometry;
    std::optional<PowerCheckResult> power;
    std::optional<TestpointCoverage> testpoints;
    std::optional<SpiceResult> spice;
    std::optional<FirmwareDocsInput> firmware;
    std::optional<ManufacturingXdc> xdc;
    NativeLedger ledger;
    NativeQuantizations quantizations;
    NativeFallbacks fallbacks;
    NativeAccountingInbox inbox;
    bool loaded = false, pcb_published = false;
    ExecutionTimings* timing = nullptr;
    Context(const ProjectPaths&, const BoardPipelineOptions&);
    void gate(const std::string&, bool, const std::string&);
    void status(const std::string&, BoardGateStatus, const std::string&);
    void report(const std::string& filename, const std::string& value);
    ExecutionTimings::Scope timed(const std::string& name) { return {timing,name}; }
    template<class F> decltype(auto) measure(const std::string& name, F action) {
        auto scope = timed(name); return action();
    }
    template<class F> void attempt(const std::string& name, F action) {
        auto scope = timed(name);
        try { action(); }
        catch(const std::bad_alloc&) { throw; }
        catch(const std::exception& e) {
            report(name + ".txt", std::string("FAIL: ") + e.what());
            // Do not overwrite a gate that succeeded before a later operation
            // threw; publication failure is separately fatal for this stage.
            // Child checks may publish their own verdict before this parent
            // stage fails. Only a verdict for THIS stage makes the exception
            // a late completion failure; a child verdict is not parent success.
            if(std::none_of(result.gates.begin(),result.gates.end(),[&](const auto& g){return g.name==name;})) gate(name, false, e.what());
            else gate(name + ".completion", false, e.what());
        }
    }
};
void schematic_stage(Context&);
void electrical_stages(Context&);
void pcb_stages(Context&);
void document_stages(Context&);
void audit_stages(Context&);
} // namespace schgen::board_pipeline_detail
