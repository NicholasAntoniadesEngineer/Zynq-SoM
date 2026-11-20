#include "schgen/board_inputs.hpp"
#include "schgen/module_mating.hpp"
#include "schgen/model3d.hpp"
#include "schgen/pcb_emit.hpp"
#include <algorithm>
#include <fstream>
#include <iterator>
#include <set>
#include <cmath>

namespace schgen {
namespace {
namespace fs = std::filesystem;
const char* const part_facts_file = "part_facts.json";
const char* const fiducial_footprint = "Fiducial:Fiducial_1mm_Mask2mm";
const char* const kicad_footprint_table = "fp-lib-table";
const char* const part_record_file = "part.json";
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
    floor.compact_search = options.compact_search;
    floor.experiment = options.experiment;
    result.two_side = options.two_side;
    result.netlist = netlist;
    // escape_block.json is generated output, never a placement input. Current
    // connector/pad geometry supplies reservations during each floorplan trial.
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
    result.interface_bytes = read(paths.som_interface_file);
    result.som_interface = som_interface_from_json(
        parse_json_text(result.interface_bytes, paths.som_interface_file.string()), paths.som_interface_file.string());
    std::vector<std::string> module_connectors;
    for (const auto& [ref, connector] : result.som_interface.connectors) module_connectors.push_back(ref);
    const auto som_path = options.som_pcb.value_or(paths.som_pcb);
    floor.som = extract_som_scan(read(som_path), module_connectors);
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
    const auto module_table = paths.module_root / kicad_footprint_table;
    if (std::find(resolution.library_tables.begin(), resolution.library_tables.end(), module_table) == resolution.library_tables.end())
        resolution.library_tables.push_back(module_table);
    const PartFacts facts = load_part_facts(resolution.parts_dir / part_facts_file);
    floor.project.connectors = facts.connectors;
    for (const auto& [folder, fact] : facts.model_overrides) {
        const auto part_file = resolution.parts_dir / folder / part_record_file;
        const auto part = parse_json_file(part_file.string());
        const auto* mpn = object_field(part, "mpn");
        if (!mpn || mpn->kind != JsonKind::String || mpn->string_value.empty())
            throw std::runtime_error(part_file.string() + ": mpn is required for its model override");
        floor.project.model_overrides.emplace_back(mpn->string_value, fact);
    }
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
    footprint_ids.insert(fiducial_footprint);
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
    const ModelRoots roots{default_model3d_directory(), paths.project_file.parent_path(), resolution.parts_dir};
    std::map<std::string, PartHeight> measured;
    const auto height_of = [&](const std::string& footprint, const std::string& value, const std::string& part) {
        const auto document = floor.footprints.find(floor.footprint_of.at(footprint));
        const auto override = std::find_if(policy.model_overrides.begin(), policy.model_overrides.end(),
            [&](const PcbModelOverride& entry) { return entry.value == value && entry.footprint == footprint; });
        const bool overridden = override != policy.model_overrides.end();
        const std::string key = overridden ? override->path : footprint;
        auto known = measured.find(key);
        if (known == measured.end())
            known = measured.emplace(key, overridden ? model_height(override->path, roots, part)
                                                     : footprint_height(facts, footprint, document->second.document,
                                                                        roots, part)).first;
        return known->second;
    };
    for (const auto& sheet : circuits)
        for (const auto& part : sheet.circuit.parts) {
            if (!floor.footprint_of.count(part.footprint)) continue;
            const std::string label = part.ref + " (" + sheet.name + ")";
            result.part_facts.emplace(std::make_pair(sheet.name, part.ref),
                PartFact{symbol_class(facts, part.lib_id, label), height_of(part.footprint, part.value, label)});
        }
    if (floor.footprint_of.count(fiducial_footprint))
        result.fiducial_height = height_of(fiducial_footprint, {}, fiducial_footprint);
    FootprintResolutionOptions module_resolution;
    module_resolution.library_tables = {paths.module_root / kicad_footprint_table};
    const auto module_libraries = load_footprint_library_tables(module_resolution);
    for (auto& jack : floor.som.js) {
        const auto connector = std::find_if(result.som_interface.connectors.begin(), result.som_interface.connectors.end(),
                                            [&](const auto& row) { return row.first == jack.ref; });
        const auto mate_id = connector->second.footprint.value_or("");
        if (mate_id.empty()) throw std::runtime_error(paths.som_interface_file.string() + ": connector " + jack.ref + " names no mate footprint");
        const auto file = resolve_footprint(mate_id, module_libraries, module_resolution);
        if (!file) throw std::runtime_error(paths.som_interface_file.string() + ": mate footprint " + mate_id + " of " + jack.ref +
                                            " is not in the module footprint table " + module_resolution.library_tables.front().string());
        std::set<std::string> pins;
        for (const auto& [pin, net] : connector->second.pins) { (void)net; pins.insert(pin); }
        jack = fit_module_mate(jack, *snapshot(*file), pins);
    }
    const auto mapping = link_mapping_from_json(parse_json_file((paths.project_root / "som_mapping.json").string()), paths.module.do_not_load_straps);
    auto functions = mapping.function_map;
    for (const auto& [key, value] : mapping.pudc_straps) functions[key] = value;
    result.function_map.assign(functions.begin(), functions.end());
    result.escape_triage = load_escape_triage(paths.project_root, paths.module.escape_triage, paths.module_root.string());
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
    if (options.compact_search)
        result.owned_groups = resolve_owned_group_inputs(paths, circuits, result);
    return result;
}
}
