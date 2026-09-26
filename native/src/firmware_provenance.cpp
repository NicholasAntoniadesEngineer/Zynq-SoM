#include "schgen/firmware_provenance.hpp"
#include "schgen/firmware_docs.hpp"
#include "schgen/project_authoring.hpp"

#include <set>

namespace schgen {
namespace {
namespace fs = std::filesystem;
bool entry_present(const fs::path& path) {
    // A broken symlink is a damaged source, not an absent optional input.
    return fs::exists(fs::symlink_status(path));
}
std::string source_path(const ProjectPaths& paths, const fs::path& source) {
    if (!fs::is_regular_file(source))
        throw FirmwareDocsError("firmware provenance: missing source file " + source.string());
    const auto actual = fs::canonical(source);
    const auto relative = actual.lexically_relative(fs::canonical(paths.repository_root));
    const auto result = (relative.empty() || *relative.begin() == ".." ? actual : relative).generic_string();
    if (result.find_first_of("\r\n") != std::string::npos || result.find("*/") != std::string::npos)
        throw FirmwareDocsError("firmware provenance: source path is unsafe in a generated C comment");
    return result;
}
const ProjectSubsystemDefinition* declaration(const std::string& project, const std::string& name) {
    const ProjectSubsystemDefinition* found = nullptr;
    for (const auto& entry : project_subsystem_definitions()) {
        if (entry.project != project || entry.name != name) continue;
        if (found) throw FirmwareDocsError("firmware provenance: duplicate native factory " + project + ":" + name);
        found = &entry;
    }
    return found;
}
} // namespace

const std::vector<std::string>& firmware_provenance_dependencies() {
    // Preserve the original dependency order; make formerly omitted PD and
    // optional manual-service sources explicit instead of consulting .py files.
    static const std::vector<std::string> names{
        "power", "power_mon", "bringup_rails", "bringup_en", "bringup_en_modules",
        "bringup_modules", "debug_boot", "board_aux", "board_services", "usb_pd",
        "pd_input", "user_io", "board_qwiic"};
    return names;
}

std::vector<std::string> native_firmware_sources(const ProjectPaths& paths) {
    const auto project = paths.project_root.filename().string();
    std::vector<std::string> result{
        source_path(paths, paths.som_interface_file),
        source_path(paths, paths.som_schematic) + " (U9 pin map, live kicad-cli extraction)"};
    bool registry_added = false, adapter_added = false;
    for (const auto& name : firmware_provenance_dependencies()) {
        const auto* factory = declaration(project, name);
        const auto json = paths.subsystems_dir / name / "circuit.json";
        // A genuinely absent optional subsystem is not a missing constructor.
        // Once registered or present on disk it must remain in the provenance.
        if (!factory && !entry_present(json.parent_path()) && !entry_present(json)) continue;
        const auto canonical = source_path(paths, json);
        const auto circuit = load_circuit_json(json);
        if (circuit.name != name)
            throw FirmwareDocsError("firmware provenance: canonical circuit name mismatch for " + name);
        result.push_back(canonical + " (canonical circuit IR)");
        if (!factory) {
            result.push_back("native authoring factory not registered for " + project + ":" + name +
                             " (canonical IR only; no native builder provenance claimed)");
            continue;
        }
        if (!registry_added) {
            result.push_back(source_path(paths, paths.repository_root / "native/src/project_authoring_registry.cpp") +
                             " (native factory declarations and project metadata)");
            result.push_back(source_path(paths, paths.repository_root / "native/src/project_authoring.cpp") +
                             " (native project dispatch and adapter post-processing)");
            registry_added = true;
        }
        if (factory->adapter) {
            // Confirm this is a callable compiled library declaration, not
            // merely an adapter record with a plausible source filename.
            const auto& library = subsystem_definition(name);
            if (!library.circuit)
                throw FirmwareDocsError("firmware provenance: missing native library factory " + name);
            if (!adapter_added) {
                result.push_back(source_path(paths, paths.repository_root / "native/src/subsystem_authoring.cpp") +
                                 " (native library registry)");
                adapter_added = true;
            }
            result.push_back(source_path(paths, paths.repository_root / "native/src" /
                ("subsystem_authoring_" + name + ".cpp")) + " (native reusable builder: " + name + ")");
        } else {
            if (!factory->circuit)
                throw FirmwareDocsError("firmware provenance: missing native project factory " + project + ":" + name);
            result.push_back(source_path(paths, paths.repository_root / "native/src" /
                ("project_authoring_" + project + "_" + name + ".cpp")) +
                " (native project builder: " + project + ":" + name + ")");
        }
    }
    for (const auto& [relative, description] : ProjectStrings{
             {"research/debug_boot_pmod.md", "BOOTSEL decode, SWD reservation"},
             {"research/power_mon.md", "I2C address map"},
             {"research/bringup_power_gating.md", "EN-cell semantics, GPIO plan"}}) {
        const auto path = paths.project_root / relative;
        if (entry_present(path)) result.push_back(source_path(paths, path) + " (" + description + ")");
    }
    return result;
}

std::string firmware_native_regeneration_command(const std::string& command) {
    static const std::set<std::string> commands{"firmware", "manual", "scfw", "testplan", "power-sequence"};
    if (!commands.count(command))
        throw FirmwareDocsError("firmware provenance: unknown native regeneration command " + command);
    return "native/bin/schgen " + command + " --project PROJECT_DIR";
}
} // namespace schgen
