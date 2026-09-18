#pragma once

#include <filesystem>
#include <string>
#include <vector>

namespace schgen {

struct ProjectCatalogPaths {
    std::filesystem::path project_root;
    std::filesystem::path subsystems_dir;
    std::filesystem::path parts_dir;
    std::filesystem::path part_catalog;
    std::filesystem::path circuit_catalog;
};

struct ProjectSubsystem {
    std::string name;
    std::filesystem::path circuit_json;
    // Compatibility with Python callers using .stem/.parent. Not an input file
    // and not required to exist; discovery never reads or executes Python.
    std::filesystem::path legacy_handle;
};

// Relative selectors are resolved against the repository; absolute selectors
// support external projects. Circuit outputs belong to the selected project;
// parts use the repository's shared native/catalog.bin.
ProjectCatalogPaths project_catalog_paths(
    const std::filesystem::path& repository_root,
    const std::filesystem::path& project = "carrier");

// Canonical layout: subsystems/<name>/circuit.json, matching schema and name.
// Hidden/private directories are not sheets. Flat/foldered authoring Python
// without matching canonical JSON is an incomplete-migration error, never a
// discovery input or execution fallback. Projects need no Python files.
std::vector<ProjectSubsystem> discover_project_subsystems(
    const std::filesystem::path& subsystems_dir);

// Validate the project layout before calling the general recursive IR compiler.
// Refuses extra circuit.json inputs outside the canonical discovery set.
bool compile_project_circuit_catalog(const ProjectCatalogPaths& paths);

}  // namespace schgen
