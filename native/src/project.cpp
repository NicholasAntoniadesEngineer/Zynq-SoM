#include "schgen/project.hpp"
#include "schgen/project_catalog.hpp"

#include <algorithm>
#include <cmath>
#include <cstdlib>
#include <limits>
#include <map>
#include <set>

namespace schgen {
namespace {
namespace fs = std::filesystem;

[[noreturn]] void fail(const std::string& where, const std::string& message) {
    throw ProjectError(where + ": " + message);
}

template <typename F>
auto contextual(const fs::path& path, F action) -> decltype(action()) {
    try { return action(); }
    catch (const std::exception& error) {
        throw ProjectError("project " + path.string() + ": " + error.what());
    }
}

void kind(const JsonNode& node, JsonKind expected, const std::string& where) {
    if (node.kind != expected) fail(where, "unexpected JSON type");
}

const JsonNode& field(const JsonNode& node, const std::string& key) {
    const auto* value = object_field(node, key);
    if (!value) fail(key, "missing required field");
    return *value;
}

JsonNode empty_object() {
    JsonNode node;
    node.kind = JsonKind::Object;
    return node;
}

JsonNode optional_object(const JsonNode& node, const std::string& key) {
    const auto* value = object_field(node, key);
    if (!value) return empty_object();
    kind(*value, JsonKind::Object, key);
    return *value;
}

std::string string(const JsonNode& node, const std::string& where, bool empty = false) {
    kind(node, JsonKind::String, where);
    if (!empty && node.string_value.empty()) fail(where, "must not be empty");
    return node.string_value;
}

std::string string_field(const JsonNode& node, const std::string& key, bool empty = false) {
    return string(field(node, key), key, empty);
}

double number(const JsonNode& node, const std::string& where) {
    kind(node, JsonKind::Number, where);
    if (!std::isfinite(node.number_value)) fail(where, "must be finite");
    return node.number_value;
}

int32_t integer(const JsonNode& node, const std::string& where) {
    const double value = number(node, where);
    if (std::trunc(value) != value || value < std::numeric_limits<int32_t>::min()
        || value > std::numeric_limits<int32_t>::max()) {
        fail(where, "must be a signed 32-bit integer");
    }
    return static_cast<int32_t>(value);
}

std::vector<std::string> strings(const JsonNode& node, const std::string& where) {
    kind(node, JsonKind::Array, where);
    std::vector<std::string> out;
    for (std::size_t i = 0; i < node.array_value.size(); ++i) {
        out.push_back(string(node.array_value[i], where + "[" + std::to_string(i) + "]"));
    }
    return out;
}

ProjectStrings mapping(const JsonNode& node, const std::string& where) {
    kind(node, JsonKind::Object, where);
    ProjectStrings out;
    for (const auto& [key, value] : node.object_value) {
        if (key.empty()) fail(where, "empty key");
        out.emplace_back(key, string(value, where + "[" + key + "]", true));
    }
    return out;
}

void subsystem_name(const std::string& name) {
    if (name.empty() || name.front() == '.' || name.front() == '_'
        || name.find_first_of("/\\") != std::string::npos
        || name.find('\0') != std::string::npos) {
        fail("subsystem", "invalid name '" + name + "'");
    }
}

bool regular_file(const fs::path& path) {
    std::error_code ec;
    const auto status = fs::status(path, ec);
    if (ec == std::errc::no_such_file_or_directory) return false;
    if (ec) fail(path.string(), ec.message());
    if (!fs::exists(status)) return false;
    if (!fs::is_regular_file(status)) fail(path.string(), "expected regular file");
    return true;
}

void directory(const fs::path& path) {
    if (!fs::is_directory(path)) fail(path.string(), "directory missing or not a directory");
}

void validate_index(const SheetIndex& index) {
    std::set<std::string> names;
    std::set<int32_t> bands;
    for (const auto& [name, band] : index) {
        subsystem_name(name);
        if (!names.insert(name).second) fail("sheet_index", "duplicate name '" + name + "'");
        if (band < first_sheet_band) fail("sheet_index[" + name + "]", "band must be positive");
        if (!bands.insert(band).second) fail("sheet_index[" + name + "]", "duplicate band");
    }
}

}  // namespace

ProjectPaths resolve_project_paths(const fs::path& repository_root,
                                  const std::optional<fs::path>& project) {
    return contextual(repository_root, [&] {
        if (repository_root.empty()) fail("repository_root", "must not be empty");
        ProjectPaths out;
        out.repository_root = fs::weakly_canonical(fs::absolute(repository_root));
        const char* env = std::getenv("SCHGEN_PROJECT");
        const fs::path selection = project ? *project : fs::path(env ? env : "carrier");
        // Like pathlib.Path(""), an explicitly empty selection denotes the repo.
        out.project_root = fs::weakly_canonical(selection.is_absolute() ? selection : out.repository_root / selection);
        // Remove a trailing separator so default-project identity is stable.
        if (out.project_root.filename().empty()) out.project_root = out.project_root.parent_path();
        out.project_file = out.project_root / "project.json";
        directory(out.repository_root);
        directory(out.project_root);
        if (!regular_file(out.project_file)) fail(out.project_file.string(), "project configuration missing");
        out.is_default_project = out.project_root == out.repository_root / "carrier";
        out.subsystems_dir = out.project_root / "subsystems";
        out.sheet_index_file = out.project_root / "sheet_index.json";
        out.som_interface_file = out.project_root / "som_interface.json";
        out.manifest_file = out.project_root / "manifest.json";
        const auto catalogs = project_catalog_paths(out.repository_root, out.project_root);
        out.parts_dir = catalogs.parts_dir;
        out.part_catalog_file = catalogs.part_catalog;
        out.circuit_catalog_file = catalogs.circuit_catalog;
        out.som_schematic = out.repository_root / "som/Zynq_SoM.kicad_sch";
        out.schematic_dir = out.project_root / "schematic";
        out.reports_dir = out.project_root / "reports";
        out.fpga_dir = out.project_root / "fpga";
        return out;
    });
}

ProjectConfig load_project_config(const ProjectPaths& paths) {
    return contextual(paths.project_file, [&] {
        ProjectConfig out;
        out.raw = parse_json_file(paths.project_file.string());
        out.name = string_field(out.raw, "name");
        const auto& placement = field(out.raw, "placement");
        out.wired_sheets = strings(field(placement, "wired_sheets"), "placement.wired_sheets");
        out.pilot_prox_sheets = strings(field(placement, "pilot_prox_sheets"), "placement.pilot_prox_sheets");
        const auto& offset = field(placement, "module_offset");
        kind(offset, JsonKind::Array, "placement.module_offset");
        if (offset.array_value.size() != 2) fail("placement.module_offset", "expected two coordinates");
        for (std::size_t i = 0; i < 2; ++i) out.module_offset[i] = number(offset.array_value[i], "placement.module_offset");
        out.module_face_anchors = mapping(field(placement, "module_face_anchors"), "placement.module_face_anchors");
        out.reg_band_prefixes = strings(field(placement, "reg_band_prefixes"), "placement.reg_band_prefixes");
        out.bank_rails = mapping(optional_object(optional_object(out.raw, "fpga"), "bank_rails"), "fpga.bank_rails");
        const auto labels = optional_object(out.raw, "silk_labels");
        out.header_desc = mapping(optional_object(labels, "headers"), "silk_labels.headers");
        out.switch_desc = mapping(optional_object(labels, "switches"), "silk_labels.switches");
        out.escape = optional_object(out.raw, "escape");
        return out;
    });
}

ProjectManifest load_project_manifest(const ProjectPaths& paths) {
    return contextual(paths.manifest_file, [&] {
        ProjectManifest out;
        out.raw = parse_json_file(paths.manifest_file.string());
        const auto& device = field(out.raw, "device");
        if (device.kind != JsonKind::Null) out.device = string(device, "device", true);
        const auto& artifacts = field(out.raw, "artifacts");
        kind(artifacts, JsonKind::Array, "artifacts");
        for (const auto& item : artifacts.array_value) {
            out.artifacts.push_back({string_field(item, "path"), string_field(item, "sha256")});
        }
        return out;
    });
}

std::vector<CircuitSource> inventory_project_circuits(const ProjectPaths& paths) {
    return contextual(paths.subsystems_dir, [&] {
        std::vector<CircuitSource> out;
        // Discovery owns layout, schema, name, symlink and migration rules.
        // Authoring paths are optional provenance and are never executed.
        for (const auto& source : discover_project_subsystems(paths.subsystems_dir)) {
            CircuitSource entry{source.name, source.circuit_json, true, std::nullopt};
            const auto flat = paths.subsystems_dir / (source.name + ".py");
            if (regular_file(source.legacy_handle)) entry.authoring_path = source.legacy_handle;
            else if (regular_file(flat)) entry.authoring_path = flat;
            out.push_back(std::move(entry));
        }
        return out;
    });
}

ProjectCircuit load_project_circuit(const ProjectPaths& paths, const std::string& name) {
    subsystem_name(name);
    const auto path = paths.subsystems_dir / name / "circuit.json";
    return contextual(path, [&] {
        // Discovery excludes symlinked subsystem directories. Explicit loads
        // must not bypass that boundary.
        if (fs::is_symlink(path.parent_path())) fail(name, "symlinked subsystem directory is not canonical");
        auto circuit = load_circuit_json(path);
        if (circuit.name != name) fail(path.string(), "circuit name '" + circuit.name + "' does not match subsystem '" + name + "'");
        return ProjectCircuit{name, path, std::move(circuit)};
    });
}

std::vector<ProjectCircuit> load_project_circuits(const ProjectPaths& paths) {
    const auto sources = inventory_project_circuits(paths);
    if (sources.empty()) fail(paths.subsystems_dir.string(), "no subsystem circuits found");
    std::vector<ProjectCircuit> out;
    for (const auto& source : sources) out.push_back(load_project_circuit(paths, source.name));
    return out;
}

std::vector<ProjectCircuit> load_project_circuits(const ProjectPaths& paths,
                                               const std::vector<std::string>& names) {
    std::vector<ProjectCircuit> out;
    for (const auto& name : names) out.push_back(load_project_circuit(paths, name));
    return out;
}

CircuitPortIr circuit_port_type(const CircuitSheetIr& circuit, const std::string& net) {
    for (const auto& port : circuit.port_types) if (port.net == net) return port;
    CircuitPortIr port;
    port.net = net;
    port.kind = "single";
    return port;
}

SheetIndex load_sheet_index(const ProjectPaths& paths) {
    return contextual(paths.sheet_index_file, [&] {
        SheetIndex out;
        if (!regular_file(paths.sheet_index_file)) return out;
        const auto root = parse_json_file(paths.sheet_index_file.string());
        kind(root, JsonKind::Object, "sheet_index");
        for (const auto& [name, band] : root.object_value) out.emplace_back(name, integer(band, "sheet_index[" + name + "]"));
        validate_index(out);
        return out;
    });
}

SheetIndex positional_sheet_index(const std::vector<std::string>& names) {
    SheetIndex out;
    for (std::size_t i = 0; i < names.size(); ++i) {
        subsystem_name(names[i]);
        if (i >= static_cast<std::size_t>(std::numeric_limits<int32_t>::max())) fail("sheet_index", "band overflow");
        const auto found = std::find_if(out.begin(), out.end(), [&](const auto& row) { return row.first == names[i]; });
        const auto band = static_cast<int32_t>(i + first_sheet_band);
        if (found == out.end()) out.emplace_back(names[i], band);
        else found->second = band;  // Python dict comprehension: last value wins.
    }
    return out;
}

SheetIndexUpdate extend_sheet_index(const SheetIndex& existing, const std::vector<std::string>& names) {
    validate_index(existing);
    SheetIndexUpdate out{existing, {}};
    std::set<std::string> known;
    int64_t band = first_sheet_band - 1;
    for (const auto& [name, value] : existing) { known.insert(name); band = std::max(band, int64_t(value)); }
    for (const auto& name : names) {
        subsystem_name(name);
        if (!known.count(name)) out.unseen.push_back(name);
    }
    std::sort(out.unseen.begin(), out.unseen.end());
    for (const auto& name : out.unseen) {
        if (++band > std::numeric_limits<int32_t>::max()) fail("sheet_index", "band overflow");
        const auto found = std::find_if(out.index.begin(), out.index.end(), [&](const auto& row) { return row.first == name; });
        if (found == out.index.end()) out.index.emplace_back(name, static_cast<int32_t>(band));
        else found->second = static_cast<int32_t>(band);
    }
    return out;
}

}  // namespace schgen
