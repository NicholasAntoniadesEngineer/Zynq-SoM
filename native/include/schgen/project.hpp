#pragma once

#include "schgen/board_definition.hpp"
#include "schgen/circuit.hpp"
#include "schgen/json.hpp"
#include "schgen/part_facts.hpp"

#include <array>
#include <cstdint>
#include <filesystem>
#include <optional>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

namespace schgen {

// Vectors retain JSON/Python dictionary insertion order. No process-global
// project, catalog, cache, interpreter or current-directory change is needed.
using ProjectStrings = std::vector<std::pair<std::string, std::string>>;
using SheetIndex = std::vector<std::pair<std::string, int32_t>>;

class ProjectError : public std::runtime_error {
public:
    using std::runtime_error::runtime_error;
};

struct ProjectPaths {
    std::filesystem::path repository_root, project_root;
    std::filesystem::path project_file, subsystems_dir, library_dir, sheet_index_file;
    std::filesystem::path som_interface_file, manifest_file;
    std::filesystem::path parts_dir, part_catalog_file, som_schematic, som_pcb, module_root;
    std::filesystem::path circuit_catalog_file;
    std::filesystem::path schematic_dir, reports_dir, fpga_dir;
    std::optional<std::filesystem::path> run_config;
    ModuleDefinition module;
    std::string file_stem;
    bool root_readme = false;
    std::vector<std::string> owned_groups;
};

struct ProjectConfig {
    std::string name, stackup, file_stem;
    bool labels = true, arrange = false, construct = false;
    int density = 0;
    // Set-like membership in Python; retained in source order here.
    std::vector<std::string> wired_sheets, pilot_prox_sheets;
    std::array<double, 2> module_offset{};
    ProjectStrings module_face_anchors;
    std::vector<std::string> reg_band_prefixes;
    ProjectStrings bank_rails, header_desc, switch_desc;
    ConnectorFacts connectors;
    ModuleDefinition module;
    IsolationFacts isolation;
    ThermalCopperFacts thermal_copper;
    RegulatorFacts regulators;
    ModelOverrideFacts model_overrides;
    FootprintAliasFacts footprint_aliases;
    ControlGridFacts control_grid;
    JsonNode escape;  // Object, defaults to {} as in ProjectSpec.
    JsonNode raw;     // Complete project.json, including extension metadata.
};

struct EngineConfig {
    double grid = 1.27;
    double char_w = 0.95;
    double misplaced_overlap = 0.20;
    double cross_k = 3.0;
    double visual_clearance_mm = 0.2;
};

inline constexpr EngineConfig default_engine_config{};
inline constexpr int32_t first_sheet_band = 1;

struct CircuitSource {
    std::string name;
    std::filesystem::path path;  // Expected subsystems/<name>/circuit.json.
    bool has_circuit_json = false;
    // For migration diagnostics only; never imported or executed.
    std::optional<std::filesystem::path> authoring_path;
};

struct ProjectCircuit {
    std::string name;
    std::filesystem::path path;
    CircuitSheetIr circuit;
};

struct SheetIndexUpdate {
    SheetIndex index;
    std::vector<std::string> unseen;
};

struct ProjectArtifact {
    std::string path, sha256;
};

struct ProjectManifest {
    std::optional<std::string> device;
    std::vector<ProjectArtifact> artifacts;
    JsonNode raw;  // Preserve rails, BOM, GPIO/I2C, XDC and future sections.
};

// Relative project paths are relative to repository_root, never the cwd.
// Paths are absolute with existing symlinks resolved; existing directories and the
// project.json file are required. Other inputs are checked only when loaded.
ProjectPaths resolve_project_paths(
    const std::filesystem::path& repository_root,
    const std::optional<std::filesystem::path>& project = std::nullopt);
const std::vector<DocumentKey>& project_document_keys();
struct PlacementRequirementsScope {
    bool applicable = false;
    std::string statement;
};
PlacementRequirementsScope placement_requirements_scope(const JsonNode& project, const std::string& file);
ProjectConfig load_project_config(const ProjectPaths& paths);
ProjectManifest load_project_manifest(const ProjectPaths& paths);

// Canonical discovery is delegated to discover_project_subsystems, sorted by
// name. Missing JSON for retained flat/foldered authoring sources is an
// incomplete-migration error. Python files are never required or executed.
std::vector<CircuitSource> inventory_project_circuits(const ProjectPaths& paths);
// load_circuit_json is declared in circuit.hpp (included above).
ProjectCircuit load_project_circuit(const ProjectPaths& paths, const std::string& name);
std::vector<ProjectCircuit> load_project_circuits(const ProjectPaths& paths);
// Explicit selection retains caller order, including repeated names.
std::vector<ProjectCircuit> load_project_circuits(
    const ProjectPaths& paths, const std::vector<std::string>& names);

// PortType() defaults without inserting synthetic records into the source IR.
CircuitPortIr circuit_port_type(const CircuitSheetIr& circuit, const std::string& net);

// Missing sheet_index.json means an empty index. Stable extension retains old
// entries and appends sorted unseen names after max(existing band). These
// functions do NOT persist; the caller owns any explicit publication step.
SheetIndex load_sheet_index(const ProjectPaths& paths);
SheetIndex positional_sheet_index(const std::vector<std::string>& names);
SheetIndexUpdate extend_sheet_index(const SheetIndex& existing,
                                   const std::vector<std::string>& names);

}  // namespace schgen
