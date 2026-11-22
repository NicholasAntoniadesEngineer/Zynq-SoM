#include "schgen/board_check.hpp"

#include "schgen/board_definition.hpp"
#include "schgen/board_power.hpp"
#include "schgen/component_basis.hpp"
#include "schgen/constraints.hpp"
#include "schgen/floorplan.hpp"
#include "schgen/i2c_inventory.hpp"
#include "schgen/link.hpp"
#include "schgen/part_facts.hpp"
#include "schgen/pcb_checks.hpp"
#include "schgen/pcb_escape.hpp"
#include "schgen/project.hpp"
#include "schgen/project_authoring.hpp"
#include "schgen/project_catalog.hpp"
#include "schgen/run_config.hpp"
#include "schgen/sheet_roles.hpp"
#include "schgen/som_interface.hpp"

#include <algorithm>
#include <map>
#include <optional>
#include <set>
#include <sstream>

namespace schgen {
namespace {
namespace fs = std::filesystem;

const char* const escape_triage_file = "escape_triage.json";
const char* const signal_spec_file = "research/si_spec.json";
const char* const floorplan_file = "floorplan.json";
const char* const sheet_index_file = "sheet_index.json";
const char* const basis_file = "component_basis.json";
const char* const mapping_file = "som_mapping.json";
const char* const project_file = "project.json";
const char* const run_config_label = "run config";
const char* const file_item = "file";
const char* const loads_item = "loads";
const char* const part_facts_label = "parts/part_facts.json";
const char* const module_prefix = "module folder/";

struct Rows {
    std::vector<BoardRequirement> list;
    void add(const std::string& file, const std::string& item, bool required, RequirementStatus status, const std::string& message = {}) {
        list.push_back({file, item, required, status, message});
    }
    bool file(const fs::path& path, const std::string& label, bool required) {
        const bool exists = fs::is_regular_file(path);
        add(label, file_item, required, exists ? RequirementStatus::present : required ? RequirementStatus::missing : RequirementStatus::absent);
        return exists;
    }
    template <class F> bool judge(const std::string& file, const std::string& item, bool ready, F&& action) {
        if (!ready) { add(file, item, true, RequirementStatus::blocked); return false; }
        try { action(); }
        catch (const std::exception& error) { add(file, item, true, RequirementStatus::invalid, error.what()); return false; }
        add(file, item, true, RequirementStatus::present);
        return true;
    }
};

std::optional<JsonNode> parsed(const fs::path& path, bool exists) {
    if (!exists) return std::nullopt;
    try { return parse_json_file(path.string()); }
    catch (const std::exception&) { return std::nullopt; }
}

bool key_required(const std::vector<DocumentKey>& keys, const std::string& path) {
    const auto found = std::find_if(keys.begin(), keys.end(), [&](const DocumentKey& key) { return key.path == path; });
    return found != keys.end() && found->required;
}

void key_rows(Rows& rows, const std::string& file, const std::optional<JsonNode>& document, const std::vector<DocumentKey>& keys) {
    for (const DocumentKey& key : keys) {
        const auto dot = key.path.rfind('.');
        const std::string parent = dot == std::string::npos ? std::string() : key.path.substr(0, dot);
        RequirementStatus status = RequirementStatus::blocked;
        if (document && document->kind == JsonKind::Object) {
            if (!parent.empty() && !document_member(*document, parent))
                status = key_required(keys, parent) ? RequirementStatus::blocked : RequirementStatus::absent;
            else if (document_member(*document, key.path)) status = RequirementStatus::present;
            else status = key.required ? RequirementStatus::missing : RequirementStatus::absent;
        }
        rows.add(file, key.path, key.required, status);
    }
}

std::string text_member(const std::optional<JsonNode>& document, const std::string& path) {
    if (!document) return {};
    const JsonNode* node = document_member(*document, path);
    return node && node->kind == JsonKind::String ? node->string_value : std::string();
}

}

const char* requirement_status_name(RequirementStatus status) {
    switch (status) {
    case RequirementStatus::present: return "present";
    case RequirementStatus::missing: return "missing";
    case RequirementStatus::invalid: return "invalid";
    case RequirementStatus::absent: return "absent";
    case RequirementStatus::blocked: return "blocked";
    }
    throw std::logic_error("unknown requirement status");
}

bool BoardDefinitionCheck::ok() const {
    return std::none_of(rows.begin(), rows.end(), [](const BoardRequirement& row) {
        return row.status == RequirementStatus::missing || row.status == RequirementStatus::invalid ||
               (row.required && row.status == RequirementStatus::blocked);
    });
}

std::string BoardDefinitionCheck::text() const {
    std::map<RequirementStatus, std::size_t> counts;
    for (const BoardRequirement& row : rows) ++counts[row.status];
    std::ostringstream out;
    out << "BOARD DEFINITION " << board << ": " << rows.size() << " rows; " << counts[RequirementStatus::present] << " present, "
        << counts[RequirementStatus::missing] << " missing, " << counts[RequirementStatus::invalid] << " invalid, "
        << counts[RequirementStatus::absent] << " absent (optional), " << counts[RequirementStatus::blocked] << " blocked\n";
    out << "status | file | item | message\n";
    for (const BoardRequirement& row : rows) {
        out << requirement_status_name(row.status) << " | " << row.file << " | " << row.item << " | ";
        std::string message = row.message;
        std::replace(message.begin(), message.end(), '\n', ' ');
        out << message << "\n";
    }
    out << "not judged here: part ratings (gates part_rules, bom_ratings) and footprint lands (gate footprint_pads) need the power tree and the footprint libraries\n";
    out << "BOARD DEFINITION: " << (ok() ? "PASS" : "FAIL") << "\n";
    return out.str();
}

BoardDefinitionCheck check_board_definition(const fs::path& repository, const fs::path& board_root, const fs::path& run_config) {
    Rows rows;
    BoardDefinitionCheck result;
    result.board = board_root.filename().string();

    const bool board_exists = rows.file(board_root / board_file, board_file, true);
    const auto board_document = parsed(board_root / board_file, board_exists);
    key_rows(rows, board_file, board_document, board_document_keys());
    const std::string module_folder = text_member(board_document, "module.folder");
    const fs::path module_root = repository / module_folder;
    const std::string module_label = std::string(module_prefix) + module_file;
    std::optional<ModuleDefinition> module;
    if (module_folder.empty()) rows.add(module_label, file_item, true, RequirementStatus::blocked);
    const bool module_exists = !module_folder.empty() && rows.file(module_root / module_file, module_label, true);
    rows.judge(module_label, loads_item, module_exists, [&] { module = load_module(module_root); });
    std::optional<BoardDefinition> board;
    rows.judge(board_file, loads_item, board_exists && module.has_value(), [&] { board = load_board(board_root, *module); });

    const bool project_exists = rows.file(board_root / project_file, project_file, true);
    const auto project_document = parsed(board_root / project_file, project_exists);
    key_rows(rows, project_file, project_document, project_document_keys());

    const std::string name = text_member(project_document, "name");
    const bool config_exists = rows.file(run_config, run_config_label, true);
    const auto config_document = parsed(run_config, config_exists);
    bool configured = false;
    for (const std::string section : {"stackup", "overmold_parts", "fabrication"}) {
        const std::string item = section + "." + (name.empty() ? std::string("<project.json name>") : name);
        const JsonNode* table = config_document ? object_field(*config_document, section) : nullptr;
        if (name.empty() || !config_document) { rows.add(run_config_label, item, true, RequirementStatus::blocked); continue; }
        if (!table || table->kind != JsonKind::Object || !object_field(*table, name)) { rows.add(run_config_label, item, true, RequirementStatus::missing); continue; }
        const bool judged = rows.judge(run_config_label, item, true, [&] {
            if (section == "stackup") apply_run_config(run_config, name);
            else if (section == "fabrication") (void)load_run_config(run_config).fabrication_of(name);
            else (void)load_run_config(run_config).overmold_parts_of(name);
        });
        if (section == "stackup") configured = judged;
    }

    std::optional<ProjectPaths> paths;
    std::optional<ProjectConfig> config;
    rows.judge(project_file, loads_item, project_exists && board.has_value() && configured, [&] {
        ProjectPaths resolved = resolve_project_paths(repository, board_root);
        resolved.run_config = run_config;
        config = load_project_config(resolved);
        (void)placement_requirements_scope(config->raw, resolved.project_file.string());
        (void)pcb_escape_population_from_json(config->escape, *module);
        paths = resolved;
    });

    const bool mapping_exists = rows.file(board_root / mapping_file, mapping_file, true);
    key_rows(rows, mapping_file, parsed(board_root / mapping_file, mapping_exists), som_mapping_document_keys());
    std::optional<LinkMapping> mapping;
    rows.judge(mapping_file, loads_item, mapping_exists && module.has_value(), [&] {
        mapping = link_mapping_from_json(parse_json_file((board_root / mapping_file).string()), module->do_not_load_straps);
    });

    const bool triage_exists = rows.file(board_root / escape_triage_file, escape_triage_file, true);
    rows.judge(escape_triage_file, loads_item, triage_exists && module.has_value(), [&] {
        (void)load_escape_triage(board_root, module->escape_triage, module_root.string());
    });

    std::optional<SomInterface> som;
    rows.judge(std::string(module_prefix) + module_interface_file, loads_item, module.has_value(), [&] {
        som = load_som_interface(module_root / module_interface_file);
    });

    std::vector<ProjectCircuit> circuits;
    bool authored = board.has_value();
    const AuthoringContext context = make_authoring_context(repository);
    if (board) {
        ProjectAuthoringInput input;
        input.project_root = board_root;
        input.context = context;
        input.board = board;
        input.som = som;
        input.mapping = mapping;
        for (const BoardSheet& sheet : board->sheets) {
            const bool ready = !sheet.from_module() || (som.has_value() && mapping.has_value());
            authored = rows.judge(board_file, "sheets." + sheet.name, ready, [&] {
                circuits.push_back({sheet.name, board_root / "subsystems" / sheet.name / "circuit.json",
                                    author_project_subsystem(board->name, sheet.name, input)});
            }) && authored;
        }
    } else rows.add(board_file, "sheets.*", true, RequirementStatus::blocked);

    std::set<std::string> names;
    for (const ProjectCircuit& circuit : circuits) names.insert(circuit.name);
    if (authored) {
        const bool needed = needs_signal_specs(circuits);
        if (rows.file(board_root / signal_spec_file, signal_spec_file, needed))
            rows.judge(signal_spec_file, loads_item, true, [&] { (void)load_signal_specs(board_root / signal_spec_file); });
    } else rows.add(signal_spec_file, file_item, true, RequirementStatus::blocked);
    if (rows.file(board_root / floorplan_file, floorplan_file, false))
        rows.judge(floorplan_file, loads_item, authored, [&] { (void)load_floorplan_spec((board_root / floorplan_file).string(), names); });
    if (rows.file(board_root / sheet_index_file, sheet_index_file, false))
        rows.judge(sheet_index_file, loads_item, paths.has_value(), [&] { (void)load_sheet_index(*paths); });

    const bool basis_exists = rows.file(board_root / basis_file, basis_file, true);
    rows.judge(basis_file, "coverage", basis_exists && authored, [&] {
        const ComponentBasisBoards boards = single_basis_board(board_root);
        const ComponentBasisPolicy policy = load_component_basis_policy(repository, boards);
        const ComponentBasisResult audited = audit_component_basis(author_component_basis_inputs(repository, boards, policy),
                                                                   component_basis_scopes(boards), policy);
        if (!audited.ok()) throw std::runtime_error(component_basis_report(audited));
    });

    const std::string facts_label = part_facts_label;
    std::optional<PartFacts> facts;
    rows.judge(facts_label, loads_item, true, [&] { facts = load_part_facts_in(project_catalog_paths(repository, board_root).parts_dir); });
    const bool facts_ready = facts.has_value() && authored;
    rows.judge(facts_label, "classes", facts_ready, [&] {
        for (const ProjectCircuit& circuit : circuits)
            for (const CircuitPartIr& part : circuit.circuit.parts) (void)symbol_class(*facts, part.lib_id, part.ref + " (" + circuit.name + ")");
    });
    rows.judge(facts_label, "i2c_devices", facts_ready, [&] { (void)build_i2c_inventory(circuits, *facts); });
    std::optional<SheetRoles> roles;
    rows.judge(board_file, "sheet roles", facts_ready && som.has_value(), [&] {
        std::vector<CircuitSheetIr> sheets;
        for (const ProjectCircuit& circuit : circuits) sheets.push_back(circuit.circuit);
        AuthoringContext library;
        library.library = context.library;
        roles = sheet_roles(*board, library, *som, sheets, *facts);
    });
    rows.judge(board_file, "power", roles.has_value() && mapping.has_value(), [&] {
        std::vector<std::string> module_sheets;
        for (const ProjectCircuit& circuit : circuits) if (module_connector_sheet(*roles, circuit.name)) module_sheets.push_back(circuit.name);
        (void)board_power_policy(board->power, board->module_definition, mapping->rebound_som_rails, module_sheets, circuits, *facts);
    });

    if (board && !board->layout.stated)
        rows.add(board_file, "intent.layout", false, RequirementStatus::absent,
                 "the board states no layout object: function statements are not judged");
    if (board && board->layout.stated && facts_ready && roles) {
        std::set<std::pair<std::string, std::string>> stated, known;
        for (const BoardFunction& function : board->layout.functions) stated.insert({function.sheet, function.reference});
        for (const ProjectCircuit& circuit : circuits) {
            const std::string module_part = sheet_role(*roles, circuit.name).module_connector;
            for (const CircuitPartIr& part : circuit.circuit.parts) {
                known.insert({circuit.name, part.ref});
                if (part.ref == module_part) continue;
                const PartClass kind = symbol_class(*facts, part.lib_id, part.ref + " (" + circuit.name + ")");
                if (kind != PartClass::connector && kind != PartClass::header && kind != PartClass::battery_holder) continue;
                const std::string subject = circuit.name + "." + part.ref;
                rows.add(board_file, "intent.function." + subject, true,
                         stated.count({circuit.name, part.ref}) ? RequirementStatus::present : RequirementStatus::missing,
                         stated.count({circuit.name, part.ref}) ? "" : "state what " + subject + " is for in layout.functions");
            }
        }
        for (const BoardFunction& function : board->layout.functions)
            if (!known.count({function.sheet, function.reference}))
                rows.add(board_file, "intent.function." + function.sheet + "." + function.reference, true, RequirementStatus::invalid,
                         "layout.functions names a part the sheet does not hold");
    }
    result.rows = std::move(rows.list);
    return result;
}

}
