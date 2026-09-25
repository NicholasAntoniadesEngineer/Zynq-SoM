#include "schgen/board_inputs.hpp"
#include "schgen/pcb_emit.hpp"
#include <fstream>
#include <iterator>
#include <set>
#include <cmath>

namespace schgen {
namespace {
namespace fs = std::filesystem;
std::string read(const fs::path& path) {
    std::ifstream input(path, std::ios::binary);
    if (!input) throw std::runtime_error("cannot read board input " + path.string());
    std::string text((std::istreambuf_iterator<char>(input)), std::istreambuf_iterator<char>());
    if (input.bad()) throw std::runtime_error("cannot finish reading board input " + path.string());
    return text;
}
std::string relative_source(const fs::path& path, const fs::path& root) {
    const auto relative = path.lexically_relative(root);
    return relative.empty() ? path.generic_string() : relative.generic_string();
}
}
PcbPlacementInput load_board_inputs(const ProjectPaths& paths,
        const std::vector<ProjectCircuit>& circuits, const LinkResult& link,
        const KicadNetlist& netlist, const BoardInputOptions& options) {
    PcbPlacementInput result;
    auto& floor = result.floorplan;
    floor.project = load_project_config(paths);
    floor.sheet_index = load_sheet_index(paths);
    floor.link = link;
    floor.regulators = analyze_power(circuits).regs;
    floor.module_offset = options.module_offset;
    floor.place_clear = options.place_clear;
    result.two_side = options.two_side;
    result.netlist = netlist;
    const auto prior_escape = paths.project_root / "escape_block.json";
    if (fs::exists(prior_escape)) {
        result.prior_escape_sidecar = parse_json_file(prior_escape.string());
        const auto* constraints = object_field(result.prior_escape_sidecar, "t1_constraints");
        const auto* corridors = constraints ? object_field(*constraints, "corridors") : nullptr;
        if (corridors) {
            if (corridors->kind != JsonKind::Object)
                throw std::runtime_error("escape corridors must be an object: " + prior_escape.string());
            std::map<std::string, Box4> sorted;
            for (const auto& [name, value] : corridors->object_value) {
                const auto* rect = object_field(value, "rect");
                if (!rect || rect->kind != JsonKind::Array || rect->array_value.size() != 4)
                    throw std::runtime_error("escape corridor requires four coordinates: " + name);
                for (const auto& coordinate : rect->array_value)
                    if (coordinate.kind != JsonKind::Number || !std::isfinite(coordinate.number_value))
                        throw std::runtime_error("escape corridor requires finite coordinates: " + name);
                const auto& r = rect->array_value;
                sorted.emplace("escape:" + name, Box4{r[0].number_value - 25, r[1].number_value - 25,
                                                      r[2].number_value - 25, r[3].number_value - 25});
            }
            floor.compose.corridors.assign(sorted.begin(), sorted.end());
        }
    }
    std::set<std::string> footprint_ids, names;
    for (const auto& sheet : circuits) {
        floor.sheets.push_back(sheet.circuit);
        names.insert(sheet.name);
        for (const auto& part : sheet.circuit.parts) footprint_ids.insert(part.footprint);
        // Match package precedence, retaining even inert contracts so coverage
        // validation can distinguish authored policy from applied policy.
        for (const auto& root : {paths.repository_root / "subsystems", paths.subsystems_dir}) {
            const auto file = root / sheet.name / "placement_contract.json";
            if (!fs::is_regular_file(file)) continue;
            auto contract = parse_json_file(file.string());
            if (contract.kind != JsonKind::Object) throw std::runtime_error("placement contract must be an object: " + file.string());
            result.contracts.emplace(sheet.name, std::move(contract));
            break;
        }
    }
    floor.spec = load_floorplan_spec(options.floorplan_spec.value_or(paths.project_root / "floorplan.json").string(), names);
    const auto som_path = options.som_pcb.value_or(paths.repository_root / "som/Zynq_SoM.kicad_pcb");
    floor.som = extract_som_scan(read(som_path));
    floor.som_source = relative_source(som_path, paths.repository_root);
    const auto si_path = paths.project_root / "research/si_spec.json";
    if (fs::is_regular_file(si_path) || needs_signal_specs(circuits)) floor.si_pairs = load_signal_specs(si_path);
    floor.si_source = relative_source(si_path, paths.repository_root);

    auto resolution = options.footprints;
    if (resolution.parts_dir.empty()) resolution.parts_dir = paths.parts_dir;
    if (resolution.kicad_footprint_root.empty())
        for (const auto* root : {"/Applications/KiCad/KiCad.app/Contents/SharedSupport/footprints",
                                "/usr/share/kicad/footprints", "/usr/local/share/kicad/footprints"})
            if (fs::is_directory(root)) { resolution.kicad_footprint_root = root; break; }
    const auto policy = pcb_emit_policy(floor.project);
    for (const auto& [from, to] : policy.footprint_aliases) resolution.aliases.emplace(from, to);
    const auto libraries = load_footprint_library_tables(resolution);
    auto snapshot = [&](const fs::path& file) {
        const auto key = file.lexically_normal().string();
        auto found = result.footprints.find(key);
        if (found != result.footprints.end()) return found->second;
        auto parsed = pcb_check_footprint(key, read(file));
        result.footprints.emplace(key, parsed);
        return parsed;
    };
    footprint_ids.insert("Fiducial:Fiducial_1mm_Mask2mm");
    for (const auto& id : footprint_ids) {
        const auto alias = resolution.aliases.find(id);
        const auto file = resolve_footprint(alias == resolution.aliases.end() ? id : alias->second, libraries, resolution);
        if (file) {
            const auto parsed = snapshot(*file);
            floor.footprint_of[id] = parsed->source;
            floor.footprints.emplace(parsed->source, FloorplanFootprint{parsed->source, parsed->document});
        }
        // Area estimation historically uses the local library dossier only;
        // standard-library packages retain the native dimension-name policy.
        const auto colon = id.find(':');
        if (colon != std::string::npos) {
            const auto lib = id.substr(0, colon);
            const auto dossier = resolution.parts_dir / lib / (lib + ".kicad_mod");
            if (!floor.courtyard_dims.count(lib) && fs::is_regular_file(dossier))
                if (const auto dims = courtyard_dims_from_text(snapshot(dossier)->bytes)) floor.courtyard_dims.emplace(lib, *dims);
        }
    }
    result.interface_bytes = read(paths.som_interface_file);
    result.som_interface = som_interface_from_json(
        parse_json_text(result.interface_bytes, paths.som_interface_file.string()), paths.som_interface_file.string());
    const auto mapping = link_mapping_from_json(parse_json_file((paths.project_root / "som_mapping.json").string()));
    auto functions = mapping.function_map;
    for (const auto& [key, value] : mapping.pudc_straps) functions[key] = value;
    result.function_map.assign(functions.begin(), functions.end());
    for (const auto& [ref, connector] : result.som_interface.connectors) {
        const auto value = connector.value.value_or("");
        auto dossier = resolution.parts_dir / value / (value + ".kicad_mod");
        if (!fs::is_regular_file(dossier)) {
            const auto fp = connector.footprint.value_or("");
            const auto colon = fp.find(':');
            auto name = colon == std::string::npos ? std::string{} : fp.substr(colon + 1);
            const auto first = name.find_first_not_of('_'), last = name.find_last_not_of('_');
            name = first == std::string::npos ? "" : name.substr(first, last - first + 1);
            if (name.rfind("HRS_", 0) == 0) name.erase(0, 4);
            dossier = resolution.parts_dir / name / (name + ".kicad_mod");
        }
        if (!fs::is_regular_file(dossier)) throw std::runtime_error(ref + ": cannot resolve return-path footprint dossier");
        result.return_path_footprints.emplace(ref, snapshot(dossier));
    }
    return result;
}
}
