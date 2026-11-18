#include "schgen/circuit.hpp"

#include <algorithm>
#include <map>
#include <set>
#include <stdexcept>

namespace schgen {
namespace {

constexpr const char* layout_schema = "schgen.subsystem-layout/1";
constexpr const char* support_library = "Device:";
constexpr const char* module_target = "module";

[[noreturn]] void reject(const CircuitSheetIr& sheet, const std::string& what) {
    throw std::runtime_error("layout intent of " + sheet.name + ": " + what);
}

const CircuitPartIr* part_named(const CircuitSheetIr& sheet, const std::string& ref) {
    const auto found = std::find_if(sheet.parts.begin(), sheet.parts.end(),
                                    [&](const CircuitPartIr& part) { return part.ref == ref; });
    return found == sheet.parts.end() ? nullptr : &*found;
}

std::set<std::string> nets_of(const CircuitSheetIr& sheet, const std::string& ref, const std::string* pin) {
    std::set<std::string> found;
    for (const auto& net : sheet.nets)
        for (const auto& member : net.pins)
            if (member.ref == ref && (!pin || member.pin == *pin)) found.insert(net.name);
    return found;
}

JsonNode text(const std::string& value) {
    JsonNode node;
    node.kind = JsonKind::String;
    node.string_value = value;
    return node;
}

JsonNode record(std::vector<std::pair<std::string, JsonNode>> fields) {
    JsonNode node;
    node.kind = JsonKind::Object;
    node.object_value = std::move(fields);
    return node;
}

JsonNode list() {
    JsonNode node;
    node.kind = JsonKind::Array;
    return node;
}

const JsonNode& member(const JsonNode& node, const char* key, JsonKind kind, const CircuitSheetIr& sheet) {
    const JsonNode* found = node.kind == JsonKind::Object ? object_field(node, key) : nullptr;
    if (!found || found->kind != kind) reject(sheet, std::string("field '") + key + "' is missing or has the wrong type");
    return *found;
}

void only(const JsonNode& node, const std::set<std::string>& allowed, const CircuitSheetIr& sheet) {
    if (node.kind != JsonKind::Object) reject(sheet, "a record is not an object");
    std::set<std::string> seen;
    for (const auto& [key, value] : node.object_value) {
        if (!allowed.count(key)) reject(sheet, "unknown field '" + key + "'");
        if (!seen.insert(key).second) reject(sheet, "duplicate field '" + key + "'");
    }
}

}

const std::vector<std::string>& circuit_service_roles() {
    static const std::vector<std::string> roles{"bypass", "reservoir", "pull",   "series",  "terminate",
                                                "filter", "feedback",  "switching", "timing", "protect",
                                                "sense",  "indicate",  "set"};
    return roles;
}

void validate_circuit_layout(const CircuitSheetIr& sheet) {
    const auto& roles = circuit_service_roles();
    std::set<std::string> declared;
    std::map<std::string, std::string> owner_of;
    for (const auto& service : sheet.layout.serves) {
        const std::string where = "serves(" + service.part + ")";
        if (std::find(roles.begin(), roles.end(), service.role) == roles.end())
            reject(sheet, where + ": unknown role '" + service.role + "'");
        if (!part_named(sheet, service.part)) reject(sheet, where + ": no such part");
        if (!declared.insert(service.part).second) reject(sheet, where + ": the part already has a declaration");
        const std::set<std::string> own = nets_of(sheet, service.part, nullptr);
        const bool by_pin = !service.owner.ref.empty();
        if (by_pin == !service.net.empty()) reject(sheet, where + ": needs exactly one of an owner pin or a net");
        if (!service.target.empty() && (by_pin || service.target != module_target))
            reject(sheet, where + ": target '" + service.target + "' is not a known off-sheet owner");
        if (!by_pin) {
            if (!own.count(service.net)) reject(sheet, where + ": the part has no pin on net '" + service.net + "'");
            continue;
        }
        const CircuitPartIr* owner = part_named(sheet, service.owner.ref);
        const std::string pin = service.owner.ref + "." + service.owner.pin;
        if (!owner) reject(sheet, where + ": owner " + pin + " names no part");
        if (service.owner.ref == service.part) reject(sheet, where + ": a part cannot serve itself");
        const std::set<std::string> theirs = nets_of(sheet, service.owner.ref, &service.owner.pin);
        if (std::none_of(theirs.begin(), theirs.end(), [&](const std::string& net) { return own.count(net) > 0; }))
            reject(sheet, where + ": shares no net with its owner " + pin);
        owner_of.emplace(service.part, service.owner.ref);
    }
    for (const auto& [part, owner] : owner_of) {
        std::set<std::string> chain{part};
        for (auto next = owner_of.find(owner); next != owner_of.end(); next = owner_of.find(next->second))
            if (!chain.insert(next->first).second) reject(sheet, "serves(" + part + "): ownership forms a cycle");
    }
    for (const auto& entry : sheet.layout.free) {
        const std::string where = "free(" + entry.part + ")";
        if (!part_named(sheet, entry.part)) reject(sheet, where + ": no such part");
        if (!declared.insert(entry.part).second) reject(sheet, where + ": the part already has a declaration");
        if (entry.reason.find_first_not_of(" \t\r\n") == std::string::npos) reject(sheet, where + ": a reason is required");
    }
}

JsonNode circuit_layout_json(const CircuitSheetIr& sheet) {
    JsonNode serves = list(), free = list();
    for (const auto& service : sheet.layout.serves) {
        std::vector<std::pair<std::string, JsonNode>> fields{{"part", text(service.part)}, {"role", text(service.role)}};
        if (service.owner.ref.empty()) {
            fields.emplace_back("net", text(service.net));
            if (!service.target.empty()) fields.emplace_back("target", text(service.target));
        } else
            fields.emplace_back("pin", text(service.owner.ref + "." + service.owner.pin));
        serves.array_value.push_back(record(std::move(fields)));
    }
    for (const auto& entry : sheet.layout.free)
        free.array_value.push_back(record({{"part", text(entry.part)}, {"reason", text(entry.reason)}}));
    return record({{"schema", text(layout_schema)}, {"name", text(sheet.name)}, {"serves", serves}, {"free", free}});
}

CircuitLayoutIr parse_circuit_layout(const JsonNode& document, const CircuitSheetIr& sheet) {
    only(document, {"schema", "name", "serves", "free"}, sheet);
    if (member(document, "schema", JsonKind::String, sheet).string_value != layout_schema)
        reject(sheet, std::string("schema must be ") + layout_schema);
    if (member(document, "name", JsonKind::String, sheet).string_value != sheet.name)
        reject(sheet, "document belongs to another sheet");
    CircuitSheetIr bound = sheet;
    bound.layout = {};
    for (const auto& item : member(document, "serves", JsonKind::Array, sheet).array_value) {
        only(item, {"part", "role", "pin", "net", "target"}, sheet);
        CircuitServiceIr service;
        service.part = member(item, "part", JsonKind::String, sheet).string_value;
        service.role = member(item, "role", JsonKind::String, sheet).string_value;
        if (object_field(item, "net")) service.net = member(item, "net", JsonKind::String, sheet).string_value;
        if (object_field(item, "target")) service.target = member(item, "target", JsonKind::String, sheet).string_value;
        if (object_field(item, "pin")) {
            const std::string pin = member(item, "pin", JsonKind::String, sheet).string_value;
            const auto dot = pin.find('.');
            if (dot == std::string::npos || dot == 0 || dot + 1 == pin.size())
                reject(sheet, "serves(" + service.part + "): owner '" + pin + "' is not REF.PIN");
            service.owner = {pin.substr(0, dot), pin.substr(dot + 1)};
        }
        bound.layout.serves.push_back(std::move(service));
    }
    for (const auto& item : member(document, "free", JsonKind::Array, sheet).array_value) {
        only(item, {"part", "reason"}, sheet);
        bound.layout.free.push_back({member(item, "part", JsonKind::String, sheet).string_value,
                                     member(item, "reason", JsonKind::String, sheet).string_value});
    }
    validate_circuit_layout(bound);
    return bound.layout;
}

CircuitLayoutIr load_circuit_layout(const std::filesystem::path& path, const CircuitSheetIr& sheet) {
    try {
        return parse_circuit_layout(parse_json_file(path.string()), sheet);
    } catch (const std::exception& error) {
        throw std::runtime_error(path.string() + ": " + error.what());
    }
}

LayoutIntentResult check_layout_intent(const std::vector<CircuitSheetIr>& sheets) {
    LayoutIntentResult result;
    for (const auto& sheet : sheets) {
        std::set<std::string> declared;
        for (const auto& service : sheet.layout.serves) declared.insert(service.part);
        for (const auto& entry : sheet.layout.free) declared.insert(entry.part);
        result.served += sheet.layout.serves.size();
        result.released += sheet.layout.free.size();
        for (const auto& part : sheet.parts) {
            if (part.lib_id.rfind(support_library, 0) != 0) continue;
            ++result.support_parts;
            if (!declared.count(part.ref)) result.undeclared.push_back(sheet.name + " " + part.ref + " (" + part.value + ")");
        }
    }
    result.ok = result.undeclared.empty();
    return result;
}

std::string LayoutIntentResult::summary() const {
    std::string text = std::string("LAYOUT INTENT GATE: ") + (ok ? "PASS" : "FAIL") + "\n  generic support parts: " +
                       std::to_string(support_parts) + "; declarations: " + std::to_string(served) + " serving a pin or net, " +
                       std::to_string(released) + " released with a reason; undeclared: " + std::to_string(undeclared.size()) + "\n";
    for (const auto& row : undeclared) text += "    FAIL " + row + " does not say what it serves\n";
    return text;
}

}
