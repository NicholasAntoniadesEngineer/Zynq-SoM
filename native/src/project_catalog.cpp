#include "schgen/project_catalog.hpp"

#include "schgen/circuit.hpp"
#include "schgen/json.hpp"

#include <algorithm>
#include <map>
#include <set>
#include <stdexcept>

namespace schgen {
namespace fs = std::filesystem;

ProjectCatalogPaths project_catalog_paths(const fs::path& repository_root,
                                          const fs::path& project) {
    if (repository_root.empty() || project.empty()) {
        throw std::runtime_error("project catalog: repository and project are required");
    }
    const auto repository = fs::weakly_canonical(fs::absolute(repository_root));
    const auto root = fs::weakly_canonical(
        project.is_absolute() ? project : repository / project);
    return {root, root / "subsystems", repository / "parts",
            repository / "native/catalog.bin", root / "native/circuits.bin"};
}

std::vector<ProjectSubsystem> discover_project_subsystems(const fs::path& root) {
    if (!fs::is_directory(root)) {
        throw std::runtime_error("subsystems directory missing: " + root.string());
    }
    std::vector<fs::path> folders;
    std::map<std::string, fs::path> authoring;
    for (const auto& entry : fs::directory_iterator(root)) {
        const auto name = entry.path().filename().string();
        if (name.empty() || name[0] == '.' || name[0] == '_' || entry.is_symlink()) {
            continue;
        }
        if (entry.is_regular_file() && entry.path().extension() == ".py"
            && name.rfind("test_", 0) != 0) {
            authoring[entry.path().stem().string()] = entry.path();
        }
        if (!entry.is_directory()) continue;
        const auto legacy = entry.path() / (name + ".py");
        if (fs::is_regular_file(legacy)) authoring[name] = legacy;
        if (fs::is_regular_file(entry.path() / "circuit.json")) {
            folders.push_back(entry.path());
        }
    }
    std::sort(folders.begin(), folders.end());
    std::vector<ProjectSubsystem> entries;
    for (const auto& folder : folders) {
        const auto name = folder.filename().string();
        const auto path = folder / "circuit.json";
        const auto payload = parse_json_file(path.string());
        if (payload.kind != JsonKind::Object
            || require_string(payload, "schema", false, path.string()) != "schgen.circuit/1") {
            throw std::runtime_error("invalid circuit schema: " + path.string());
        }
        if (require_string(payload, "name", false, path.string()) != name) {
            throw std::runtime_error("circuit name must match directory '" + name
                                     + "': " + path.string());
        }
        entries.push_back({name, path, folder / (name + ".py")});
        authoring.erase(name);
    }
    if (!authoring.empty()) {
        const auto& [name, path] = *authoring.begin();
        throw std::runtime_error("incomplete subsystem migration: " + path.string()
                                 + " requires canonical "
                                 + (root / name / "circuit.json").string());
    }
    return entries;
}

bool compile_project_circuit_catalog(const ProjectCatalogPaths& paths) {
    const auto entries = discover_project_subsystems(paths.subsystems_dir);
    std::set<fs::path> canonical;
    for (const auto& entry : entries) canonical.insert(entry.circuit_json);
    for (const auto& entry : fs::recursive_directory_iterator(paths.subsystems_dir)) {
        if (entry.is_regular_file() && entry.path().filename() == "circuit.json"
            && canonical.count(entry.path()) == 0) {
            throw std::runtime_error("noncanonical circuit JSON: " + entry.path().string());
        }
    }
    return compile_circuit_catalog(paths.subsystems_dir.string(), paths.circuit_catalog.string());
}

}  // namespace schgen
