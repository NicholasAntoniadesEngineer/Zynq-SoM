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

const JsonNode& present(const JsonNode& node, const std::string& key, const std::string& where) {
    const JsonNode* found = object_field(node, key);
    if (!found) fail(where, "field '" + key + "' is missing");
    return *found;
}

std::optional<std::string> nullable_text(const JsonNode& node, const std::string& key, const std::string& where) {
    const JsonNode& value = present(node, key, where);
    if (value.kind == JsonKind::Null) return std::nullopt;
    if (value.kind != JsonKind::String || value.string_value.empty()) fail(where, "field '" + key + "' is neither null nor a name");
    return value.string_value;
}

std::optional<double> nullable_positive(const JsonNode& node, const std::string& key, const std::string& where) {
    const JsonNode& value = present(node, key, where);
    if (value.kind == JsonKind::Null) return std::nullopt;
    if (value.kind != JsonKind::Number || !(value.number_value > 0)) fail(where, "field '" + key + "' is neither null nor a number above zero");
    return value.number_value;
}

std::optional<double> optional_number(const JsonNode& node, const std::string& key, const std::string& where) {
    const JsonNode* found = object_field(node, key);
    if (!found) return std::nullopt;
    if (found->kind != JsonKind::Number) fail(where, "field '" + key + "' is not a number");
    return found->number_value;
}

bool truth(const JsonNode& node, const std::string& key, const std::string& where) {
    return member(node, key, JsonKind::Bool, where).bool_value;
}

SheetRegion region_of(const std::string& name, const std::string& where) {
    if (name == sheet_region_board) return SheetRegion::board;
    if (name == sheet_region_under_module) return SheetRegion::under_module;
    fail(where, "field 'region' is '" + name + "', not " + sheet_region_board + " or " + sheet_region_under_module);
}

SubsystemPlacement placement_of(const JsonNode& document, const std::string& where) {
    const std::string at = where + " placement";
    const JsonNode& node = member(document, "placement", JsonKind::Object, where);
    reject_unknown_keys(node, {"region", "silk_label", "far_guard_mm", "escape_basis", "escape_escalates", "reserves_edge"}, at);
    SubsystemPlacement placement;
    placement.region = region_of(text(node, "region", at), at);
    placement.silk_label = nullable_text(node, "silk_label", at);
    placement.far_guard_mm = nullable_positive(node, "far_guard_mm", at);
    placement.escape_basis = nullable_text(node, "escape_basis", at);
    placement.escape_escalates = truth(node, "escape_escalates", at);
    placement.reserves_edge = truth(node, "reserves_edge", at);
    if (placement.escape_escalates && !placement.escape_basis) fail(at, "field 'escape_escalates' is true but 'escape_basis' is null");
    return placement;
}

DividerLimit divider_limit_of(const JsonNode& row, const std::string& net, const std::string& where) {
    reject_unknown_keys(row, {"volts", "lo", "hi", "tag"}, where + " divider limit");
    DividerLimit limit;
    limit.volts = member(row, "volts", JsonKind::Number, where).number_value;
    limit.lo = optional_number(row, "lo", where);
    limit.hi = optional_number(row, "hi", where);
    limit.tag = text(row, "tag", where);
    if (!limit.lo && !limit.hi) fail(where, "a limit of divider " + net + " states neither lo nor hi");
    if (limit.lo && limit.hi && !(*limit.lo < *limit.hi)) fail(where, "a limit of divider " + net + " has lo not below hi");
    return limit;
}

SubsystemDivider divider_of(const JsonNode& row, const std::string& where) {
    reject_unknown_keys(row, {"net", "source", "limits", "why"}, where + " divider");
    SubsystemDivider divider;
    divider.net = text(row, "net", where);
    divider.source = text(row, "source", where);
    divider.why = text(row, "why", where);
    for (const JsonNode& limit : rows(row, "limits", where)) divider.limits.push_back(divider_limit_of(limit, divider.net, where));
    if (divider.limits.empty()) fail(where, "divider " + divider.net + " states no limits");
    return divider;
}

std::optional<IsetWindow> iset_window_of(const JsonNode& node, const std::string& where) {
    const JsonNode& value = present(node, "iset_window_ma", where);
    if (value.kind == JsonKind::Null) return std::nullopt;
    const bool pair = value.kind == JsonKind::Array && value.array_value.size() == 2 &&
                      value.array_value.front().kind == JsonKind::Number && value.array_value.back().kind == JsonKind::Number;
    if (!pair) fail(where, "field 'iset_window_ma' is neither null nor [low, high]");
    IsetWindow window;
    window.low_ma = value.array_value.front().number_value;
    window.high_ma = value.array_value.back().number_value;
    if (!(window.low_ma > 0) || !(window.low_ma < window.high_ma)) fail(where, "field 'iset_window_ma' is not 0 < low < high");
    return window;
}

SubsystemChecks checks_of(const JsonNode& document, const std::string& where) {
    const std::string at = where + " checks";
    const JsonNode& node = member(document, "checks", JsonKind::Object, where);
    reject_unknown_keys(node, {"dividers", "divider_sources", "iset_window_ma", "iset_basis"}, at);
    SubsystemChecks checks;
    std::set<std::string> nets;
    for (const JsonNode& row : rows(node, "dividers", at)) {
        checks.dividers.push_back(divider_of(row, at));
        if (!nets.insert(checks.dividers.back().net).second) fail(at, "divider " + checks.dividers.back().net + " is stated twice");
    }
    checks.divider_sources = texts(node, "divider_sources", at);
    checks.iset_window_ma = iset_window_of(node, at);
    checks.iset_basis = nullable_text(node, "iset_basis", at);
    if (checks.iset_window_ma.has_value() != checks.iset_basis.has_value())
        fail(at, "field 'iset_basis' must be a name exactly when 'iset_window_ma' is stated");
    return checks;
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

const std::vector<JsonNode>& listed(const JsonNode& node, const std::string& key, const std::string& where, bool complete) {
    static const std::vector<JsonNode> none;
    return complete || object_field(node, key) ? rows(node, key, where) : none;
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

void apply_sections(CircuitAuthor& circuit, const JsonNode& document, const SubsystemMeta& meta, const std::string& where,
                    bool complete) {
    for (const JsonNode& row : listed(document, "parts", where, complete)) add_part(circuit, row, where);
    for (const JsonNode& row : listed(document, "nets", where, complete)) {
        reject_unknown_keys(row, {"name", "class", "pins"}, where + " net");
        circuit.net(text(row, "name", where), texts(row, "pins", where), optional_text(row, "class", where));
    }
    if (complete || object_field(document, "unconnected")) circuit.nc(texts(document, "unconnected", where));
    for (const JsonNode& row : listed(document, "ports", where, complete)) add_port(circuit, row, meta, where);
    for (const JsonNode& row : listed(document, "hints", where, complete)) {
        reject_unknown_keys(row, {"net", "style"}, where + " hint");
        circuit.hint(text(row, "net", where), text(row, "style", where));
    }
    for (const JsonNode& row : listed(document, "draws", where, complete)) {
        reject_unknown_keys(row, {"rail", "amps", "note"}, where + " draw");
        const JsonNode* stated = object_field(row, "note");
        if (!stated) fail(where, "a draw lacks its note");
        const std::string note = per_board(*stated, where, meta, Setting::note);
        circuit.draws(text(row, "rail", where), member(row, "amps", JsonKind::Number, where).number_value, note);
    }
    for (const JsonNode& row : listed(document, "waivers", where, complete)) {
        reject_unknown_keys(row, {"kind", "key", "reason"}, where + " waiver");
        circuit.waive(text(row, "kind", where), text(row, "key", where), text(row, "reason", where));
    }
    for (const JsonNode& row : listed(document, "purpose", where, complete)) add_purpose(circuit, row, where);
    for (const JsonNode& row : listed(document, "free", where, complete)) {
        reject_unknown_keys(row, {"part", "reason"}, where + " free part");
        circuit.free(text(row, "part", where), text(row, "reason", where));
    }
}

}

CircuitSheetIr author_subsystem_data(const JsonNode& document, const SubsystemMeta& meta,
                                     const AuthoringContext& context) {
    const std::string where = document.kind == JsonKind::Object && object_field(document, "name") &&
                                      object_field(document, "name")->kind == JsonKind::String
                                  ? object_field(document, "name")->string_value
                                  : std::string("(unnamed)");
    if (document.kind != JsonKind::Object) fail(where, "the document is not an object");
    reject_unknown_keys(document, {"schema", "name", "title", "interface", "placement", "checks", "parts", "nets", "unconnected", "ports",
                                   "hints", "draws", "waivers", "purpose", "free"},
                        where);
    if (text(document, "schema", where) != subsystem_data_schema)
        fail(where, std::string("schema is not ") + subsystem_data_schema);
    subsystem_data_facts(document, where);
    require_title_fits(where, text(document, "title", where));
    CircuitAuthor circuit(text(document, "name", where), text(document, "title", where), context);
    apply_sections(circuit, document, meta, where, true);
    return meta.finish(circuit);
}

CircuitSheetIr extend_subsystem_data(CircuitSheetIr sheet, const JsonNode& additions, const AuthoringContext& context) {
    const std::string where = sheet.name + " additions";
    if (additions.kind != JsonKind::Object) fail(where, "the additions are not an object");
    reject_unknown_keys(additions, {"parts", "nets", "unconnected", "ports", "hints", "draws", "waivers", "purpose", "free"}, where);
    CircuitAuthor circuit(std::move(sheet), context);
    apply_sections(circuit, additions, SubsystemMeta{}, where, false);
    return circuit.finish();
}

SubsystemDefinition subsystem_data_definition(const JsonNode& document, const std::string& source) {
    if (document.kind != JsonKind::Object) fail(source, "the document is not an object");
    SubsystemDefinition definition;
    definition.name = text(document, "name", source);
    definition.interface = texts(document, "interface", source);
    subsystem_data_facts(document, source);
    definition.circuit = [document](const SubsystemMeta& meta, const AuthoringContext& context) {
        return author_subsystem_data(document, meta, context);
    };
    return definition;
}

SubsystemFacts subsystem_data_facts(const JsonNode& document, const std::string& source) {
    if (document.kind != JsonKind::Object) fail(source, "the document is not an object");
    return {placement_of(document, source), checks_of(document, source)};
}

SubsystemFacts load_subsystem_facts(const std::filesystem::path& library, const std::string& name) {
    const std::filesystem::path file = library / name / subsystem_data_file;
    if (library.empty() || !std::filesystem::is_regular_file(file)) throw CircuitAuthoringError("unknown subsystem " + name);
    const JsonNode document = parse_json_file(file.string());
    if (document.kind == JsonKind::Object && text(document, "name", file.string()) != name)
        fail(file.string(), "its name differs from its folder " + name);
    return subsystem_data_facts(document, file.string());
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
