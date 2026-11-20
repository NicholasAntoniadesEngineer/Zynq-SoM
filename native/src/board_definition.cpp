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
    reject_unknown_keys(node, {"folder", "pairs", "loads"}, where + " module");
    BoardModule module;
    module.folder = folder_name(node, "folder", where);
    module.pairs = pairs_of(node, where);
    for (const JsonNode& row : rows(node, "loads", where)) module.loads.push_back(load_of(row, where));
    return module;
}

BoardSheet sheet_of(const JsonNode& row, const std::string& where) {
    reject_unknown_keys(row, {"name", "module_connector", "title", "settings", "additions"}, where + " sheet");
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
    return sheet;
}

BoardFiles files_of(const JsonNode& node, const std::string& where) {
    reject_unknown_keys(node, {"stem"}, where + " files");
    BoardFiles files;
    files.stem = text(node, "stem", where + " files");
    if (files.stem.find_first_of("/\\") != std::string::npos) fail(where, "files.stem '" + files.stem + "' holds a path separator");
    return files;
}

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
    header.flags.owned_groups = member(document, "owned_groups", JsonKind::Bool, source).bool_value;
    header.module_folder = folder_name(member(document, "module", JsonKind::Object, source), "folder", source + " module");
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
    reject_unknown_keys(document, {"schema", "schematic", "pcb", "connector_part", "draw", "sdio_level_v", "sd_bus", "pairs",
                                   "escape_population", "escape_triage", "do_not_load_straps", "mate_symbol",
                                   "mate_pad_names"}, source);
    if (text(document, "schema", source) != module_schema) fail(source, std::string("schema is not ") + module_schema);
    ModuleDefinition module;
    module.schematic = folder_name(document, "schematic", source);
    module.pcb = folder_name(document, "pcb", source);
    module.connector_part = text(document, "connector_part", source);
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

BoardDefinition parse_board(const JsonNode& document, const std::string& file, ModuleDefinition module_definition) {
    const std::string source = "board file " + file;
    if (document.kind != JsonKind::Object) fail(source, "the document is not an object");
    reject_unknown_keys(document, {"schema", "name", "files", "root_readme", "owned_groups", "module", "sheets"}, source);
    if (text(document, "schema", source) != board_schema) fail(source, std::string("schema is not ") + board_schema);
    BoardDefinition board;
    board.name = text(document, "name", source);
    const BoardHeader header = board_header_of(document, file);
    board.files = header.files;
    board.flags = header.flags;
    board.module = module_of(member(document, "module", JsonKind::Object, source), source);
    board.module_definition = std::move(module_definition);
    std::set<std::string> seen;
    for (const JsonNode& row : rows(document, "sheets", source)) {
        board.sheets.push_back(sheet_of(row, source));
        if (!seen.insert(board.sheets.back().name).second) fail(source, "sheet " + board.sheets.back().name + " is listed twice");
    }
    if (board.sheets.empty()) fail(source, "the board lists no sheets");
    return board;
}

BoardDefinition load_board(const std::filesystem::path& board_root) {
    const std::filesystem::path file = board_root / board_file;
    if (!std::filesystem::is_regular_file(file)) throw std::runtime_error("board file " + file.string() + " is missing");
    BoardDefinition board = parse_board(parse_json_file(file.string()), file.string(), load_module(module_root_of(board_root)));
    if (board.name != board_root.filename().string()) fail(file.string(), "name " + board.name + " differs from its folder");
    return board;
}

}
