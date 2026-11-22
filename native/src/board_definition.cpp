#include "schgen/board_definition.hpp"

#include <algorithm>
#include <cmath>
#include <set>
#include <stdexcept>

namespace schgen {
namespace {

[[noreturn]] void fail(const std::string& where, const std::string& what) {
    throw std::runtime_error(where + ": " + what);
}

const JsonNode& member(const JsonNode& node, const std::string& key, JsonKind kind, const std::string& where) {
    const JsonNode* found = object_field(node, key);
    if (!found || found->kind != kind) fail(where, "field '" + key + "' is missing or has the wrong type");
    return *found;
}

std::string text(const JsonNode& node, const std::string& key, const std::string& where) {
    const std::string value = member(node, key, JsonKind::String, where).string_value;
    if (value.empty()) fail(where, "field '" + key + "' is empty");
    return value;
}

double positive(const JsonNode& node, const std::string& key, const std::string& where) {
    const double value = member(node, key, JsonKind::Number, where).number_value;
    if (!(value > 0)) fail(where, "field '" + key + "' is not above zero");
    return value;
}

std::vector<std::string> names(const JsonNode& node, const std::string& key, const std::string& where) {
    std::vector<std::string> out;
    for (const JsonNode& item : member(node, key, JsonKind::Array, where).array_value) {
        if (item.kind != JsonKind::String || item.string_value.empty()) fail(where, "'" + key + "' holds a value that is not a name");
        out.push_back(item.string_value);
    }
    return out;
}

const std::vector<JsonNode>& rows(const JsonNode& node, const std::string& key, const std::string& where) {
    const auto& items = member(node, key, JsonKind::Array, where).array_value;
    for (const JsonNode& item : items)
        if (item.kind != JsonKind::Object) fail(where, "'" + key + "' holds a value that is not an object");
    return items;
}

BoardLoad load_of(const JsonNode& row, const std::string& where) {
    reject_unknown_keys(row, {"connector", "rail", "amps", "note"}, where + " load");
    return {text(row, "connector", where), text(row, "rail", where), positive(row, "amps", where), text(row, "note", where)};
}

BoardPair pair_of(const JsonNode& row, const std::string& where) {
    reject_unknown_keys(row, {"positive", "negative", "kind", "impedance"}, where + " pair");
    BoardPair pair{text(row, "positive", where), text(row, "negative", where), text(row, "kind", where), std::nullopt};
    if (const JsonNode* impedance = object_field(row, "impedance")) {
        if (impedance->kind != JsonKind::Number || impedance->number_value != std::floor(impedance->number_value))
            fail(where, "pair " + pair.positive + " impedance is not a whole number");
        pair.impedance = static_cast<int>(impedance->number_value);
    }
    return pair;
}

std::vector<BoardPair> pairs_of(const JsonNode& node, const std::string& where) {
    std::vector<BoardPair> out;
    for (const JsonNode& row : rows(node, "pairs", where)) out.push_back(pair_of(row, where));
    return out;
}

std::string folder_name(const JsonNode& node, const std::string& key, const std::string& where) {
    const std::string value = text(node, key, where);
    if (value.find_first_of("/\\") != std::string::npos || value == "." || value == "..")
        fail(where, "'" + key + "' value '" + value + "' is not a single folder or file name");
    return value;
}

int whole(const JsonNode& node, const std::string& key, const std::string& where) {
    const double value = member(node, key, JsonKind::Number, where).number_value;
    if (value < 0 || value != std::floor(value)) fail(where, "field '" + key + "' is not a whole number of at least zero");
    return static_cast<int>(value);
}

BoardModule module_of(const JsonNode& node, const std::string& where) {
    reject_unknown_keys(node, document_keys_at(board_document_keys(), "module"), where + " module");
    BoardModule module;
    module.folder = folder_name(node, "folder", where);
    module.pairs = pairs_of(node, where);
    for (const JsonNode& row : rows(node, "loads", where)) module.loads.push_back(load_of(row, where));
    return module;
}

BoardSheet sheet_of(const JsonNode& row, const std::string& where) {
    reject_unknown_keys(row, {"name", "module_connector", "title", "settings", "additions", "density"}, where + " sheet");
    BoardSheet sheet;
    sheet.name = text(row, "name", where);
    sheet.settings.kind = JsonKind::Object;
    const bool connector = object_field(row, "module_connector") != nullptr;
    if (connector) {
        sheet.module_connector = text(row, "module_connector", where);
        sheet.title = text(row, "title", where);
    } else if (object_field(row, "title")) {
        fail(where, "sheet " + sheet.name + " has a title but is not a module connector sheet");
    }
    if (const JsonNode* settings = object_field(row, "settings")) {
        if (settings->kind != JsonKind::Object) fail(where, "sheet " + sheet.name + " settings is not an object");
        sheet.settings = *settings;
    }
    if (const JsonNode* additions = object_field(row, "additions")) {
        if (additions->kind != JsonKind::Object) fail(where, "sheet " + sheet.name + " additions is not an object");
        sheet.additions = *additions;
    }
    if (const JsonNode* density = object_field(row, "density")) {
        sheet.density = density_level(*density);
        if (!sheet.density) fail(where, "sheet " + sheet.name + " field 'density' must be " + density_range());
    }
    return sheet;
}

double volts_of(const JsonNode& node, const std::string& where) {
    const double value = member(node, "volts", JsonKind::Number, where).number_value;
    if (!std::isfinite(value)) fail(where, "field 'volts' is not a finite number");
    return value;
}

PowerSupply supply_of(const JsonNode& row, const std::string& where) {
    reject_unknown_keys(row, {"rail", "volts", "amps", "basis"}, where + " supply");
    return {text(row, "rail", where), volts_of(row, where), positive(row, "amps", where), text(row, "basis", where)};
}

BoardSource source_of(const JsonNode& row, const std::string& where) {
    BoardSource source;
    if (object_field(row, "supplier")) {
        reject_unknown_keys(row, {"rail", "supplier"}, where + " source");
        source.rail = text(row, "rail", where);
        if (text(row, "supplier", where) != "module") fail(where, "source " + source.rail + " supplier is not 'module'");
        source.from_module = true;
        return source;
    }
    reject_unknown_keys(row, {"rail", "volts", "amps", "basis"}, where + " source");
    const PowerSupply own = supply_of(row, where);
    source.rail = own.rail;
    source.volts = own.volts;
    source.amps = own.amps;
    source.basis = own.basis;
    return source;
}

BoardRail rail_of(const JsonNode& row, const std::string& where) {
    reject_unknown_keys(row, {"rail", "volts", "basis"}, where + " rail");
    BoardRail rail{text(row, "rail", where), std::nullopt, text(row, "basis", where)};
    const JsonNode* volts = object_field(row, "volts");
    if (!volts) fail(where, "rail " + rail.rail + " has no 'volts' (state null for a rail with no voltage)");
    if (volts->kind != JsonKind::Null) rail.volts = volts_of(row, where + " rail " + rail.rail);
    return rail;
}

BoardFiles files_of(const JsonNode& node, const std::string& where) {
    reject_unknown_keys(node, document_keys_at(board_document_keys(), "files"), where + " files");
    BoardFiles files;
    files.stem = text(node, "stem", where + " files");
    if (files.stem.find_first_of("/\\") != std::string::npos) fail(where, "files.stem '" + files.stem + "' holds a path separator");
    return files;
}

}

std::optional<int> density_level(const JsonNode& node) {
    if (node.kind != JsonKind::Number || !std::isfinite(node.number_value)) return std::nullopt;
    for (int level = sparsest_density; level <= densest_density; ++level)
        if (node.number_value == static_cast<double>(level)) return level;
    return std::nullopt;
}

std::string density_range() {
    return "a whole number from " + std::to_string(sparsest_density) + " to " + std::to_string(densest_density);
}

const std::vector<DocumentKey>& board_document_keys() {
    static const std::vector<DocumentKey> keys{
        {"schema", true}, {"name", true}, {"files", true}, {"files.stem", true}, {"root_readme", true}, {"owned_groups", true},
        {"module", true}, {"module.folder", true}, {"module.pairs", true}, {"module.loads", true},
        {"power", true}, {"power.sources", true}, {"power.rails", true}, {"power.inlet", true}, {"sheets", true},
        {"layout", false}, {"layout.functions", false}};
    return keys;
}

BoardPower parse_board_power(const JsonNode& node, const std::string& where) {
    if (node.kind != JsonKind::Object) fail(where, "field 'power' is not an object");
    reject_unknown_keys(node, document_keys_at(board_document_keys(), "power"), where + " power");
    BoardPower power;
    std::set<std::string> seen;
    const auto once = [&](const std::string& rail) {
        if (!seen.insert(rail).second) fail(where, "power rail " + rail + " is listed twice in sources and rails");
    };
    for (const JsonNode& row : rows(node, "sources", where + " power")) {
        power.sources.push_back(source_of(row, where + " power.sources"));
        once(power.sources.back().rail);
    }
    for (const JsonNode& row : rows(node, "rails", where + " power")) {
        power.rails.push_back(rail_of(row, where + " power.rails"));
        once(power.rails.back().rail);
    }
    const JsonNode* inlet = object_field(node, "inlet");
    if (!inlet) fail(where, "power has no 'inlet' (state null for a board with no inlet audit)");
    if (inlet->kind != JsonKind::Null) {
        if (inlet->kind != JsonKind::Object) fail(where, "power.inlet is neither an object nor null");
        reject_unknown_keys(*inlet, {"rail", "bulk"}, where + " power.inlet");
        power.inlet = BoardInlet{text(*inlet, "rail", where + " power.inlet"), text(*inlet, "bulk", where + " power.inlet")};
    }
    return power;
}

const BoardSheet& BoardDefinition::sheet(const std::string& wanted) const {
    const auto found = std::find_if(sheets.begin(), sheets.end(), [&](const BoardSheet& item) { return item.name == wanted; });
    if (found == sheets.end()) throw std::runtime_error("board " + name + " has no sheet " + wanted);
    return *found;
}

BoardHeader board_header_of(const JsonNode& document, const std::string& file) {
    const std::string source = "board file " + file;
    if (document.kind != JsonKind::Object) fail(source, "the document is not an object");
    BoardHeader header;
    header.files = files_of(member(document, "files", JsonKind::Object, source), source);
    header.flags.root_readme = member(document, "root_readme", JsonKind::Bool, source).bool_value;
    header.flags.owned_groups = names(document, "owned_groups", source);
    if (std::set<std::string>(header.flags.owned_groups.begin(), header.flags.owned_groups.end()).size() != header.flags.owned_groups.size())
        fail(source, "'owned_groups' lists a sheet twice");
    header.module_folder = folder_name(member(document, "module", JsonKind::Object, source), "folder", source + " module");
    for (const JsonNode& row : rows(document, "sheets", source)) {
        const BoardSheet sheet = sheet_of(row, source);
        if (sheet.density) header.sheet_density[sheet.name] = *sheet.density;
    }
    return header;
}

BoardHeader load_board_header(const std::filesystem::path& board_root) {
    const std::filesystem::path file = board_root / board_file;
    if (!std::filesystem::is_regular_file(file)) throw std::runtime_error("board file " + file.string() + " is missing");
    return board_header_of(parse_json_file(file.string()), file.string());
}

ModuleDefinition parse_module(const JsonNode& document, const std::string& file) {
    const std::string source = "module file " + file;
    if (document.kind != JsonKind::Object) fail(source, "the document is not an object");
    reject_unknown_keys(document, {"schema", "schematic", "pcb", "connector_part", "controller_ref", "fpga_ref", "draw", "sdio_level_v", "sd_bus", "pairs",
                                   "escape_population", "escape_triage", "do_not_load_straps", "supplies", "regulated_rails",
                                   "mate_symbol", "mate_pad_names"}, source);
    if (text(document, "schema", source) != module_schema) fail(source, std::string("schema is not ") + module_schema);
    ModuleDefinition module;
    module.schematic = folder_name(document, "schematic", source);
    module.pcb = folder_name(document, "pcb", source);
    module.connector_part = text(document, "connector_part", source);
    module.controller_ref = text(document, "controller_ref", source);
    module.fpga_ref = text(document, "fpga_ref", source);
    if (module.controller_ref == module.fpga_ref) fail(source, "controller_ref and fpga_ref name the same reference " + module.controller_ref);
    module.draw = load_of(member(document, "draw", JsonKind::Object, source), source);
    module.sdio_level_v = positive(document, "sdio_level_v", source);
    module.sd_bus = names(document, "sd_bus", source);
    module.pairs = pairs_of(document, source);
    const JsonNode& population = member(document, "escape_population", JsonKind::Object, source);
    reject_unknown_keys(population, {"netted_contacts", "return_path"}, source + " escape_population");
    const JsonNode& netted = member(population, "netted_contacts", JsonKind::Object, source + " escape_population");
    if (netted.object_value.empty()) fail(source, "escape_population.netted_contacts is empty");
    for (const auto& [connector, count] : netted.object_value) {
        if (count.kind != JsonKind::Number || count.number_value < 0 || count.number_value != std::floor(count.number_value))
            fail(source, "escape_population.netted_contacts." + connector + " is not a whole number of at least zero");
        module.netted_contacts[connector] = static_cast<int>(count.number_value);
    }
    const std::string path_where = source + " escape_population.return_path";
    const JsonNode& path = member(population, "return_path", JsonKind::Object, source + " escape_population");
    reject_unknown_keys(path, {"n_pairs", "n_pair_contacts", "n_fail", "worst_distance"}, path_where);
    module.return_path = {whole(path, "n_pairs", path_where), whole(path, "n_pair_contacts", path_where),
                          whole(path, "n_fail", path_where), whole(path, "worst_distance", path_where)};
    for (const JsonNode& row : rows(document, "escape_triage", source)) {
        reject_unknown_keys(row, {"pattern", "class", "note"}, source + " escape_triage rule");
        module.escape_triage.push_back({text(row, "pattern", source), text(row, "class", source), text(row, "note", source)});
    }
    if (module.escape_triage.empty()) fail(source, "field 'escape_triage' is empty");
    module.do_not_load_straps = names(document, "do_not_load_straps", source);
    const bool symbol = object_field(document, "mate_symbol") != nullptr, renames = object_field(document, "mate_pad_names") != nullptr;
    if (symbol != renames) fail(source, "mate_symbol and mate_pad_names are stated together or not at all");
    if (symbol) {
        module.mate_symbol = text(document, "mate_symbol", source);
        if (module.mate_symbol.find(':') == std::string::npos) fail(source, "mate_symbol is not a Library:Name symbol id");
        const JsonNode& map = member(document, "mate_pad_names", JsonKind::Object, source);
        if (map.object_value.empty()) fail(source, "mate_pad_names is empty");
        std::set<std::string> targets;
        for (const auto& [pin, pad] : map.object_value) {
            if (pad.kind != JsonKind::String || pad.string_value.empty() || pin.empty())
                fail(source, "mate_pad_names." + pin + " is not a pad name");
            if (!targets.insert(pad.string_value).second) fail(source, "mate_pad_names names pad " + pad.string_value + " twice");
            module.mate_pad_names[pin] = pad.string_value;
        }
    }
    std::set<std::string> supplied;
    for (const JsonNode& row : rows(document, "supplies", source)) {
        module.supplies.push_back(supply_of(row, source + " supplies"));
        if (!supplied.insert(module.supplies.back().rail).second) fail(source, "supplies lists " + module.supplies.back().rail + " twice");
    }
    const JsonNode& regulated = member(document, "regulated_rails", JsonKind::Object, source);
    reject_unknown_keys(regulated, {"rails", "basis"}, source + " regulated_rails");
    module.regulated_rails = names(regulated, "rails", source + " regulated_rails");
    module.regulated_rails_basis = text(regulated, "basis", source + " regulated_rails");
    return module;
}

std::filesystem::path module_root_in(const std::filesystem::path& repository, const std::filesystem::path& board_root) {
    return repository / load_board_header(board_root).module_folder;
}

std::filesystem::path module_root_of(const std::filesystem::path& board_root) {
    return module_root_in(board_root.parent_path(), board_root);
}

ModuleDefinition load_module(const std::filesystem::path& module_root) {
    const std::filesystem::path file = module_root / module_file;
    if (!std::filesystem::is_regular_file(file)) throw std::runtime_error("module file " + file.string() + " is missing");
    return parse_module(parse_json_file(file.string()), file.string());
}

ModuleDefinition load_board_module(const std::filesystem::path& board_root) {
    return load_module(module_root_of(board_root));
}

BoardLayout layout_of(const JsonNode& document, const std::string& source) {
    BoardLayout out;
    const JsonNode* node = object_field(document, "layout");
    if (!node) return out;
    const std::string where = source + " layout";
    if (node->kind != JsonKind::Object) fail(where, "is not an object");
    reject_unknown_keys(*node, document_keys_at(board_document_keys(), "layout"), where);
    out.stated = true;
    std::set<std::string> parts;
    for (const JsonNode& row : rows(*node, "functions", where)) {
        reject_unknown_keys(row, {"part", "serves", "basis"}, where + " functions");
        const std::string part = text(row, "part", where + " functions");
        const auto dot = part.find('.');
        if (dot == std::string::npos || dot == 0 || dot + 1 == part.size())
            fail(where + " functions", "part " + part + " is not written sheet.REF");
        if (!parts.insert(part).second) fail(where + " functions", "part " + part + " is stated twice");
        out.functions.push_back({part.substr(0, dot), part.substr(dot + 1), text(row, "serves", where + " functions"),
                                 text(row, "basis", where + " functions")});
    }
    return out;
}

BoardDefinition parse_board(const JsonNode& document, const std::string& file, ModuleDefinition module_definition) {
    const std::string source = "board file " + file;
    if (document.kind != JsonKind::Object) fail(source, "the document is not an object");
    reject_unknown_keys(document, document_keys_at(board_document_keys(), ""), source);
    if (text(document, "schema", source) != board_schema) fail(source, std::string("schema is not ") + board_schema);
    BoardDefinition board;
    board.name = text(document, "name", source);
    const BoardHeader header = board_header_of(document, file);
    board.files = header.files;
    board.flags = header.flags;
    board.module = module_of(member(document, "module", JsonKind::Object, source), source);
    board.module_definition = std::move(module_definition);
    board.power = parse_board_power(member(document, "power", JsonKind::Object, source), source);
    board.layout = layout_of(document, source);
    std::set<std::string> seen;
    for (const JsonNode& row : rows(document, "sheets", source)) {
        board.sheets.push_back(sheet_of(row, source));
        if (!seen.insert(board.sheets.back().name).second) fail(source, "sheet " + board.sheets.back().name + " is listed twice");
    }
    if (board.sheets.empty()) fail(source, "the board lists no sheets");
    for (const BoardFunction& function : board.layout.functions)
        if (!seen.count(function.sheet)) fail(source, "layout.functions names sheet " + function.sheet + " which the board does not list");
    for (const std::string& owned : board.flags.owned_groups)
        if (!seen.count(owned)) fail(source, "'owned_groups' names sheet " + owned + " which the board does not list");
    return board;
}

BoardDefinition load_board(const std::filesystem::path& board_root) {
    return load_board(board_root, load_module(module_root_of(board_root)));
}

BoardDefinition load_board(const std::filesystem::path& board_root, ModuleDefinition module) {
    const std::filesystem::path file = board_root / board_file;
    if (!std::filesystem::is_regular_file(file)) throw std::runtime_error("board file " + file.string() + " is missing");
    BoardDefinition board = parse_board(parse_json_file(file.string()), file.string(), std::move(module));
    if (board.name != board_root.filename().string()) fail(file.string(), "name " + board.name + " differs from its folder");
    return board;
}

}
