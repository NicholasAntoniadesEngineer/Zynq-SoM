#include "schgen/board_definition.hpp"

#include <algorithm>
#include <cmath>
#include <set>
#include <stdexcept>

namespace schgen {
namespace {

[[noreturn]] void fail(const std::string& where, const std::string& what) {
    throw std::runtime_error("board file " + where + ": " + what);
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

BoardModule module_of(const JsonNode& node, const std::string& where) {
    reject_unknown_keys(node, {"connector_part", "draw", "sdio_level_v", "sd_bus", "pairs", "loads"}, where + " module");
    BoardModule module;
    module.connector_part = text(node, "connector_part", where);
    module.draw = load_of(member(node, "draw", JsonKind::Object, where), where);
    module.sdio_level_v = positive(node, "sdio_level_v", where);
    module.sd_bus = names(node, "sd_bus", where);
    for (const JsonNode& row : rows(node, "pairs", where)) {
        reject_unknown_keys(row, {"positive", "negative", "kind", "impedance"}, where + " pair");
        BoardPair pair{text(row, "positive", where), text(row, "negative", where), text(row, "kind", where), std::nullopt};
        if (const JsonNode* impedance = object_field(row, "impedance")) {
            if (impedance->kind != JsonKind::Number || impedance->number_value != std::floor(impedance->number_value))
                fail(where, "pair " + pair.positive + " impedance is not a whole number");
            pair.impedance = static_cast<int>(impedance->number_value);
        }
        module.pairs.push_back(std::move(pair));
    }
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

BoardHeader board_header_of(const JsonNode& document, const std::string& source) {
    if (document.kind != JsonKind::Object) fail(source, "the document is not an object");
    BoardHeader header;
    header.files = files_of(member(document, "files", JsonKind::Object, source), source);
    header.flags.root_readme = member(document, "root_readme", JsonKind::Bool, source).bool_value;
    header.flags.owned_groups = member(document, "owned_groups", JsonKind::Bool, source).bool_value;
    return header;
}

BoardHeader load_board_header(const std::filesystem::path& board_root) {
    const std::filesystem::path file = board_root / board_file;
    if (!std::filesystem::is_regular_file(file)) throw std::runtime_error("board file " + file.string() + " is missing");
    return board_header_of(parse_json_file(file.string()), file.string());
}

BoardDefinition parse_board(const JsonNode& document, const std::string& source) {
    if (document.kind != JsonKind::Object) fail(source, "the document is not an object");
    reject_unknown_keys(document, {"schema", "name", "files", "root_readme", "owned_groups", "module", "sheets"}, source);
    if (text(document, "schema", source) != board_schema) fail(source, std::string("schema is not ") + board_schema);
    BoardDefinition board;
    board.name = text(document, "name", source);
    const BoardHeader header = board_header_of(document, source);
    board.files = header.files;
    board.flags = header.flags;
    board.module = module_of(member(document, "module", JsonKind::Object, source), source);
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
    BoardDefinition board = parse_board(parse_json_file(file.string()), file.string());
    if (board.name != board_root.filename().string()) fail(file.string(), "name " + board.name + " differs from its folder");
    return board;
}

}
