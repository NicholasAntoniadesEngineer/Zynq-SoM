#include "schgen/subsystem_data.hpp"

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <set>

namespace schgen {
namespace {

[[noreturn]] void fail(const std::string& where, const std::string& what) {
    throw CircuitAuthoringError("subsystem file " + where + ": " + what);
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

std::optional<std::string> optional_text(const JsonNode& node, const std::string& key, const std::string& where) {
    const JsonNode* found = object_field(node, key);
    if (!found) return std::nullopt;
    if (found->kind != JsonKind::String) fail(where, "field '" + key + "' is not text");
    return found->string_value;
}

std::optional<int32_t> optional_whole(const JsonNode& node, const std::string& key, const std::string& where) {
    const JsonNode* found = object_field(node, key);
    if (!found) return std::nullopt;
    if (found->kind != JsonKind::Number || found->number_value != std::floor(found->number_value))
        fail(where, "field '" + key + "' is not a whole number");
    return static_cast<int32_t>(found->number_value);
}

std::vector<std::string> texts(const JsonNode& node, const std::string& key, const std::string& where) {
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

enum class Setting : std::uint8_t { bus, note };

std::string per_board(const JsonNode& value, const std::string& where, const SubsystemMeta& meta, Setting setting) {
    if (value.kind == JsonKind::String) return value.string_value;
    if (value.kind != JsonKind::Object) fail(where, "a value is neither text nor a per-board setting");
    reject_unknown_keys(value, {"instance", "default"}, where);
    const std::string key = text(value, "instance", where);
    const std::string fallback = member(value, "default", JsonKind::String, where).string_value;
    return setting == Setting::bus ? meta.bus(key, fallback) : meta.note(key, fallback);
}

std::optional<std::string> expectation(const JsonNode* value, const std::string& port, const SubsystemMeta& meta,
                                       const std::string& where) {
    if (!value) return std::nullopt;
    if (value->kind == JsonKind::String) return value->string_value;
    if (value->kind != JsonKind::Object) fail(where, "port " + port + " expect is neither text nor a per-board setting");
    reject_unknown_keys(*value, {"instance", "key", "default"}, where);
    const std::string mode = text(*value, "instance", where);
    const std::string key = optional_text(*value, "key", where).value_or(port);
    const JsonNode* fallback = object_field(*value, "default");
    if (mode == "non_empty") {
        if (fallback) fail(where, "port " + port + " expect 'non_empty' takes no default");
        return meta.expect_kw(key);
    }
    if (mode != "as_given") fail(where, "port " + port + " expect names an unknown per-board mode " + mode);
    if (!fallback) return meta.expect(key);
    if (fallback->kind != JsonKind::String) fail(where, "port " + port + " expect default is not text");
    return meta.expect(key, fallback->string_value);
}

AuthoringStrings part_fields(const JsonNode& row, const std::string& ref, const std::string& where) {
    AuthoringStrings fields;
    const JsonNode* listed = object_field(row, "fields");
    if (!listed) return fields;
    if (listed->kind != JsonKind::Object) fail(where, "part " + ref + " fields is not an object");
    for (const auto& [key, value] : listed->object_value) {
        if (value.kind != JsonKind::String) fail(where, "part " + ref + " field " + key + " is not text");
        fields.emplace_back(key, value.string_value);
    }
    return fields;
}

void add_part(CircuitAuthor& circuit, const JsonNode& row, const std::string& where) {
    const std::string ref = text(row, "ref", where);
    if (object_field(row, "part")) {
        reject_unknown_keys(row, {"ref", "part", "value", "lcsc", "symbol", "footprint", "fields"}, where + " part " + ref);
        AuthoringPartSelection selection;
        selection.ref = ref;
        selection.value = optional_text(row, "value", where);
        selection.lcsc = optional_text(row, "lcsc", where);
        selection.lib_id = optional_text(row, "symbol", where);
        selection.footprint = optional_text(row, "footprint", where);
        circuit.use_part(text(row, "part", where), selection);
        for (const auto& [key, value] : part_fields(row, ref, where)) circuit.field(ref, key, value);
        return;
    }
    reject_unknown_keys(row, {"ref", "symbol", "value", "footprint", "fields"}, where + " part " + ref);
    const AuthoringStrings fields = part_fields(row, ref, where);
    circuit.part(ref, text(row, "symbol", where), text(row, "value", where), text(row, "footprint", where), fields);
}

void add_port(CircuitAuthor& circuit, const JsonNode& row, const SubsystemMeta& meta, const std::string& where) {
    reject_unknown_keys(row, {"net", "kind", "pair_with", "impedance", "role", "bus", "speed_hz", "level_v", "expect", "explicit"},
                        where + " port");
    const std::string net = text(row, "net", where);
    AuthoringPort type;
    type.kind = text(row, "kind", where);
    type.pair_with = optional_text(row, "pair_with", where);
    type.impedance = optional_whole(row, "impedance", where);
    type.role = optional_text(row, "role", where);
    type.speed_hz = optional_whole(row, "speed_hz", where);
    if (const JsonNode* bus = object_field(row, "bus"))
        type.bus = per_board(*bus, where, meta, Setting::bus);
    if (const JsonNode* level = object_field(row, "level_v")) {
        if (level->kind != JsonKind::Number) fail(where, "port " + net + " level_v is not a number");
        type.level_v = level->number_value;
    }
    type.expect = expectation(object_field(row, "expect"), net, meta, where);
    const JsonNode* explicit_type = object_field(row, "explicit");
    if (explicit_type && explicit_type->kind != JsonKind::Bool) fail(where, "port " + net + " explicit is not true or false");
    const bool typed = type.kind != "single" || type.pair_with || type.role || type.bus || type.expect || type.impedance ||
                       type.speed_hz || type.level_v;
    if (typed || (explicit_type && explicit_type->bool_value)) circuit.port_type(net, type);
}

void add_purpose(CircuitAuthor& circuit, const JsonNode& row, const std::string& where) {
    reject_unknown_keys(row, {"part", "role", "pin", "net", "module_net"}, where + " purpose");
    const std::string part = text(row, "part", where), role = text(row, "role", where);
    const auto pin = optional_text(row, "pin", where), net = optional_text(row, "net", where),
               module_net = optional_text(row, "module_net", where);
    if ((pin ? 1 : 0) + (net ? 1 : 0) + (module_net ? 1 : 0) != 1)
        fail(where, "purpose of " + part + " names exactly one of pin, net and module_net");
    if (pin) circuit.serves(part, *pin, role);
    if (net) circuit.serves_net(part, *net, role);
    if (module_net) circuit.serves_module(part, *module_net, role);
}

}

CircuitSheetIr author_subsystem_data(const JsonNode& document, const SubsystemMeta& meta,
                                     const AuthoringContext& context) {
    const std::string where = document.kind == JsonKind::Object && object_field(document, "name") &&
                                      object_field(document, "name")->kind == JsonKind::String
                                  ? object_field(document, "name")->string_value
                                  : std::string("(unnamed)");
    if (document.kind != JsonKind::Object) fail(where, "the document is not an object");
    reject_unknown_keys(document, {"schema", "name", "title", "interface", "parts", "nets", "unconnected", "ports", "hints",
                                   "draws", "waivers", "purpose", "free"},
                        where);
    if (text(document, "schema", where) != subsystem_data_schema)
        fail(where, std::string("schema is not ") + subsystem_data_schema);
    CircuitAuthor circuit(text(document, "name", where), text(document, "title", where), context);
    for (const JsonNode& row : rows(document, "parts", where)) add_part(circuit, row, where);
    for (const JsonNode& row : rows(document, "nets", where)) {
        reject_unknown_keys(row, {"name", "class", "pins"}, where + " net");
        circuit.net(text(row, "name", where), texts(row, "pins", where), optional_text(row, "class", where));
    }
    circuit.nc(texts(document, "unconnected", where));
    for (const JsonNode& row : rows(document, "ports", where)) add_port(circuit, row, meta, where);
    for (const JsonNode& row : rows(document, "hints", where)) {
        reject_unknown_keys(row, {"net", "style"}, where + " hint");
        circuit.hint(text(row, "net", where), text(row, "style", where));
    }
    for (const JsonNode& row : rows(document, "draws", where)) {
        reject_unknown_keys(row, {"rail", "amps", "note"}, where + " draw");
        const JsonNode* stated = object_field(row, "note");
        if (!stated) fail(where, "a draw lacks its note");
        const std::string note = per_board(*stated, where, meta, Setting::note);
        circuit.draws(text(row, "rail", where), member(row, "amps", JsonKind::Number, where).number_value, note);
    }
    for (const JsonNode& row : rows(document, "waivers", where)) {
        reject_unknown_keys(row, {"kind", "key", "reason"}, where + " waiver");
        circuit.waive(text(row, "kind", where), text(row, "key", where), text(row, "reason", where));
    }
    for (const JsonNode& row : rows(document, "purpose", where)) add_purpose(circuit, row, where);
    for (const JsonNode& row : rows(document, "free", where)) {
        reject_unknown_keys(row, {"part", "reason"}, where + " free part");
        circuit.free(text(row, "part", where), text(row, "reason", where));
    }
    return meta.finish(circuit);
}

SubsystemDefinition subsystem_data_definition(const JsonNode& document, const std::string& source) {
    if (document.kind != JsonKind::Object) fail(source, "the document is not an object");
    SubsystemDefinition definition;
    definition.name = text(document, "name", source);
    definition.interface = texts(document, "interface", source);
    definition.circuit = [document](const SubsystemMeta& meta, const AuthoringContext& context) {
        return author_subsystem_data(document, meta, context);
    };
    return definition;
}

std::vector<SubsystemDefinition> subsystem_data_definitions(const std::filesystem::path& library) {
    std::vector<SubsystemDefinition> definitions;
    if (library.empty()) return definitions;
    if (!std::filesystem::is_directory(library))
        throw CircuitAuthoringError("subsystem library " + library.string() + " is not a folder");
    std::vector<std::filesystem::path> files;
    for (const auto& entry : std::filesystem::directory_iterator(library)) {
        const std::filesystem::path file = entry.path() / subsystem_data_file;
        if (entry.is_directory() && std::filesystem::is_regular_file(file)) files.push_back(file);
    }
    std::sort(files.begin(), files.end());
    for (const auto& file : files) {
        SubsystemDefinition definition = subsystem_data_definition(parse_json_file(file.string()), file.string());
        if (definition.name != file.parent_path().filename().string())
            fail(file.string(), "name " + definition.name + " differs from its folder");
        definitions.push_back(std::move(definition));
    }
    return definitions;
}

}
