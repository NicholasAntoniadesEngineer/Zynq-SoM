#include "schgen/schematic.hpp"

#include "schgen/emit.hpp"

#include <algorithm>
#include <array>
#include <cmath>
#include <limits>
#include <set>
#include <stdexcept>
#include <utility>

namespace schgen {
namespace {

// UUIDv5 uses SHA-1 as a deterministic name digest, not for authentication.
// Keep it local and portable: no OpenSSL/CommonCrypto or interpreter dependency.
std::uint32_t rotate_left(std::uint32_t value, unsigned count) {
    return (value << count) | (value >> (32 - count));
}
std::array<std::uint8_t, 20> sha1(std::vector<std::uint8_t> bytes) {
    const auto bit_count = static_cast<std::uint64_t>(bytes.size()) * 8;
    bytes.push_back(0x80);
    while (bytes.size() % 64 != 56) bytes.push_back(0);
    for (int shift = 56; shift >= 0; shift -= 8)
        bytes.push_back(static_cast<std::uint8_t>(bit_count >> shift));
    std::array<std::uint32_t, 5> digest{
        0x67452301, 0xefcdab89, 0x98badcfe, 0x10325476, 0xc3d2e1f0};
    for (std::size_t offset = 0; offset < bytes.size(); offset += 64) {
        std::array<std::uint32_t, 80> words{};
        for (std::size_t i = 0; i < 16; ++i)
            for (std::size_t j = 0; j < 4; ++j)
                words[i] = (words[i] << 8) | bytes[offset + 4 * i + j];
        for (std::size_t i = 16; i < words.size(); ++i)
            words[i] = rotate_left(words[i - 3] ^ words[i - 8] ^ words[i - 14] ^ words[i - 16], 1);
        auto a = digest[0], b = digest[1], c = digest[2], d = digest[3], e = digest[4];
        for (std::size_t i = 0; i < words.size(); ++i) {
            std::uint32_t f, k;
            if (i < 20) { f = (b & c) | (~b & d); k = 0x5a827999; }
            else if (i < 40) { f = b ^ c ^ d; k = 0x6ed9eba1; }
            else if (i < 60) { f = (b & c) | (b & d) | (c & d); k = 0x8f1bbcdc; }
            else { f = b ^ c ^ d; k = 0xca62c1d6; }
            const auto temp = rotate_left(a, 5) + f + e + k + words[i];
            e = d; d = c; c = rotate_left(b, 30); b = a; a = temp;
        }
        digest[0] += a; digest[1] += b; digest[2] += c; digest[3] += d; digest[4] += e;
    }
    std::array<std::uint8_t, 20> result{};
    for (std::size_t i = 0; i < result.size(); ++i)
        result[i] = static_cast<std::uint8_t>(digest[i / 4] >> (24 - 8 * (i % 4)));
    return result;
}
using UuidBytes = std::array<std::uint8_t, 16>;
UuidBytes uuid5(const UuidBytes& ns, const std::string& name) {
    std::vector<std::uint8_t> bytes(ns.begin(), ns.end());
    bytes.insert(bytes.end(), name.begin(), name.end());
    const auto hash = sha1(std::move(bytes));
    UuidBytes result{};
    std::copy_n(hash.begin(), result.size(), result.begin());
    result[6] = (result[6] & 0x0f) | 0x50;
    result[8] = (result[8] & 0x3f) | 0x80;
    return result;
}
std::string uuid_text(const UuidBytes& uuid) {
    constexpr char hex[] = "0123456789abcdef";
    std::string result;
    for (std::size_t i = 0; i < uuid.size(); ++i) {
        if (i == 4 || i == 6 || i == 8 || i == 10) result += '-';
        result += hex[uuid[i] >> 4]; result += hex[uuid[i] & 15];
    }
    return result;
}

Sexpr sym(const char* value) { return Sexpr{Sexpr::Sym{value}}; }
Sexpr text(const std::string& value) { return Sexpr{value}; }
Sexpr num(double value) { return Sexpr{value}; }
Sexpr list(SexprList values) { return Sexpr{std::move(values)}; }

const JsonNode* optional_field(const JsonNode& object, const std::string& key) {
    if (object.kind != JsonKind::Object)
        throw std::runtime_error("schematic: placement record must be an object");
    return object_field(object, key);
}
const JsonNode& required_field(const JsonNode& object, const std::string& key) {
    const auto* field = optional_field(object, key);
    if (!field) throw std::runtime_error("schematic: missing placement field '" + key + "'");
    return *field;
}
std::string string_value(const JsonNode& node, const std::string& where) {
    if (node.kind != JsonKind::String)
        throw std::runtime_error("schematic: " + where + " must be a string");
    return node.string_value;
}
std::string string_field(const JsonNode& node, const std::string& key) {
    return string_value(required_field(node, key), key);
}
std::string optional_string(const JsonNode& node, const std::string& key, const std::string& fallback = "") {
    const auto* value = optional_field(node, key);
    return value ? string_value(*value, key) : fallback;
}
double number_value(const JsonNode& node, const std::string& where) {
    if (node.kind != JsonKind::Number || !std::isfinite(node.number_value))
        throw std::runtime_error("schematic: " + where + " must be a finite number");
    return node.number_value;
}
double number_field(const JsonNode& node, const std::string& key) {
    return number_value(required_field(node, key), key);
}
int rotation_value(const JsonNode& node) {
    const auto value = number_value(node, "rotation");
    if (std::trunc(value) != value || value < std::numeric_limits<int>::min() ||
        value > std::numeric_limits<int>::max())
        throw std::runtime_error("schematic: rotation must be an integer in int range");
    return static_cast<int>(value);
}
int rotation_field(const JsonNode& node, int fallback = 0) {
    const auto* value = optional_field(node, "rotation");
    return value ? rotation_value(*value) : fallback;
}
bool boolean_field(const JsonNode& node, const std::string& key, bool fallback) {
    const auto* value = optional_field(node, key);
    if (!value) return fallback;
    if (value->kind != JsonKind::Bool)
        throw std::runtime_error("schematic: " + key + " must be a bool");
    return value->bool_value;
}
const std::vector<JsonNode>& array_field(const JsonNode& node, const std::string& key) {
    static const std::vector<JsonNode> empty;
    const auto* value = optional_field(node, key);
    if (!value) return empty;
    if (value->kind != JsonKind::Array)
        throw std::runtime_error("schematic: " + key + " must be an array");
    return value->array_value;
}
std::optional<SchematicTextPosition> position_field(const JsonNode& node, const std::string& key) {
    const auto* value = optional_field(node, key);
    if (!value || value->kind == JsonKind::Null) return std::nullopt;
    if (value->kind != JsonKind::Array || value->array_value.size() != 3)
        throw std::runtime_error("schematic: " + key + " must be [x, y, rotation] or null");
    const auto& items = value->array_value;
    return SchematicTextPosition{number_value(items[0], key + ".x"),
        number_value(items[1], key + ".y"), rotation_value(items[2])};
}

const CircuitPartIr* circuit_part(const CircuitSheetIr& circuit, const std::string& ref) {
    for (const auto& part : circuit.parts) if (part.ref == ref) return &part;
    return nullptr;
}
std::string label_justify(int rotation) {
    return rotation == 180 || rotation == 270 ? "right" : "left";
}

}  // namespace

std::string schematic_stable_uuid(const std::vector<std::string>& parts) {
    // RFC 4122/9562 DNS namespace, in network byte order.
    static const UuidBytes ns = uuid5(
        {0x6b, 0xa7, 0xb8, 0x10, 0x9d, 0xad, 0x11, 0xd1,
         0x80, 0xb4, 0x00, 0xc0, 0x4f, 0xd4, 0x30, 0xc8}, "schgen.kicad-id");
    std::string name;
    for (std::size_t i = 0; i < parts.size(); ++i) {
        if (i) name += '/';
        name += parts[i];
    }
    return uuid_text(uuid5(ns, name));
}

std::string SchematicIdFactory::operator()(const std::string& kind) {
    auto& count = counts_[kind];
    if (count == std::numeric_limits<std::uint64_t>::max())
        throw std::runtime_error("schematic: UUID counter exhausted for " + kind);
    return schematic_stable_uuid({scope_, kind, std::to_string(count++)});
}

SchematicDesign schematic_design_from_json(const JsonNode& node, CircuitSheetIr circuit) {
    SchematicDesign design;
    design.circuit = std::move(circuit);
    design.paper = optional_string(node, "paper", "A4");
    design.standalone = boolean_field(node, "standalone", true);
    for (const auto& row : array_field(node, "parts")) {
        SchematicPlacedPart part;
        part.ref = string_field(row, "ref"); part.lib_id = string_field(row, "lib_id");
        part.value = string_field(row, "value");
        part.x = number_field(row, "x"); part.y = number_field(row, "y");
        part.rotation = rotation_field(row); part.footprint = optional_string(row, "footprint");
        part.ref_pos = position_field(row, "ref_pos"); part.val_pos = position_field(row, "val_pos");
        design.parts.push_back(std::move(part));
    }
    for (const auto& row : array_field(node, "powers")) {
        SchematicPlacedPower power;
        power.lib_id = string_field(row, "lib_id"); power.value = string_field(row, "value");
        power.ref = string_field(row, "ref");
        power.x = number_field(row, "x"); power.y = number_field(row, "y");
        power.rotation = rotation_field(row); power.net = optional_string(row, "net");
        power.val_pos = position_field(row, "val_pos"); power.show_value = boolean_field(row, "show_value", false);
        design.powers.push_back(std::move(power));
    }
    for (const auto& row : array_field(node, "wires"))
        design.wires.push_back({number_field(row, "x0"), number_field(row, "y0"),
                               number_field(row, "x1"), number_field(row, "y1")});
    for (const auto& row : array_field(node, "junctions"))
        design.junctions.push_back({number_field(row, "x"), number_field(row, "y")});
    for (const auto& row : array_field(node, "hlabels"))
        design.hlabels.push_back({string_field(row, "name"), number_field(row, "x"),
            number_field(row, "y"), rotation_field(row), optional_string(row, "shape", "bidirectional")});
    for (const auto& row : array_field(node, "llabels"))
        design.llabels.push_back({string_field(row, "name"), number_field(row, "x"),
            number_field(row, "y"), rotation_field(row)});
    for (const auto& row : array_field(node, "no_connects"))
        design.no_connects.push_back({number_field(row, "x"), number_field(row, "y")});
    for (const auto& row : array_field(node, "sheets")) {
        SchematicSheetSymbol sheet;
        sheet.name = string_field(row, "name"); sheet.file = string_field(row, "file");
        sheet.x = number_field(row, "x"); sheet.y = number_field(row, "y");
        sheet.w = number_field(row, "w"); sheet.h = number_field(row, "h");
        sheet.uuid = string_field(row, "uuid"); sheet.page = optional_string(row, "page", "2");
        for (const auto& pin : array_field(row, "pins"))
            sheet.pins.push_back({string_field(pin, "name"), number_field(pin, "x"),
                number_field(pin, "y"), rotation_field(pin, 180), optional_string(pin, "shape", "bidirectional")});
        design.sheets.push_back(std::move(sheet));
    }
    return design;
}

SchematicOutput emit_schematic(const SchematicDesign& design,
                               const SchematicSymbolResolver& symbols,
                               const SchematicOptions& options) {
    SchematicOutput output;
    const auto& circuit = design.circuit;
    output.project = options.project.empty() ? circuit.name : options.project;
    output.root_uuid = options.sheet_uuid.empty() ?
        schematic_stable_uuid({output.project, circuit.name, "sheet"}) : options.sheet_uuid;
    output.instance_path = options.instance_path.empty() ? "/" + output.root_uuid : options.instance_path;
    SchematicIdFactory uid(output.root_uuid);
    SexprList document{sym("kicad_sch"), list({sym("version"), num(20260306)}),
        list({sym("generator"), text("schgen")}), list({sym("generator_version"), text("1.0")}),
        list({sym("uuid"), text(output.root_uuid)}), list({sym("paper"), text(design.paper)}),
        list({sym("title_block"), list({sym("title"), text(circuit.title)}),
            list({sym("company"), text("Zynq SoM Carrier")}),
            list({sym("comment"), num(1), text(circuit.name + " — generated by schgen (do not hand-edit)")})})};
    std::set<std::string> ids;
    for (const auto& part : design.parts) ids.insert(part.lib_id);
    for (const auto& power : design.powers) ids.insert(power.lib_id);
    if (!ids.empty() && !symbols) throw std::runtime_error("schematic: symbol resolver is required");
    SexprList embedded{sym("lib_symbols")};
    for (const auto& id : ids) {
        auto block = symbols(id).raw;  // Deep value copy; never change the library cache.
        auto* values = std::get_if<SexprList>(&block.v);
        if (!values || values->size() < 2 || !std::holds_alternative<Sexpr::Sym>((*values)[0].v) ||
            std::get<Sexpr::Sym>((*values)[0].v).name != "symbol")
            throw std::runtime_error("schematic: invalid symbol block for " + id);
        (*values)[1] = text(id);
        embedded.push_back(std::move(block));
    }
    document.push_back(list(std::move(embedded)));
    for (const auto& wire : design.wires)
        document.push_back(emit_wire(wire.x0, wire.y0, wire.x1, wire.y1, uid("wire")));
    for (const auto& junction : design.junctions)
        document.push_back(emit_junction(junction.x, junction.y, uid("junction")));
    for (const auto& nc : design.no_connects)
        document.push_back(emit_no_connect(nc.x, nc.y, uid("no_connect")));
    for (const auto& label : design.hlabels)
        document.push_back(emit_sch_label(design.standalone ? "global_label" : "hierarchical_label",
            label.name, label.shape, label.x, label.y, label.rotation, label_justify(label.rotation), uid("hlabel")));
    for (const auto& label : design.llabels)
        document.push_back(emit_sch_label("label", label.name, "", label.x, label.y, label.rotation,
            label.rotation == 180 ? "right bottom" : "left bottom", uid("llabel")));
    for (const auto& sheet : design.sheets) {
        std::vector<SheetPin> pins;
        for (const auto& pin : sheet.pins)
            pins.push_back({pin.name, pin.shape, pin.x, pin.y, static_cast<double>(pin.rotation),
                           label_justify(pin.rotation), uid("sheet-pin")});
        document.push_back(emit_sheet(sheet.x, sheet.y, sheet.w, sheet.h, sheet.uuid, sheet.name, sheet.file,
            output.project, "/" + output.root_uuid, sheet.page, pins));
    }
    const auto instance = [&](const std::string& ref, const std::string& lib_id,
            const std::string& value, double x, double y, int rotation, const std::string& footprint,
            const std::optional<SchematicTextPosition>& ref_pos,
            const std::optional<SchematicTextPosition>& val_pos, bool hide_ref, bool hide_val,
            const std::vector<CircuitFieldIr>& fields) {
        const auto& definition = symbols(lib_id);
        const auto rp = ref_pos.value_or(SchematicTextPosition{x, y - 2.54, 0});
        const auto vp = val_pos.value_or(SchematicTextPosition{x, y + 2.54, 0});
        std::vector<std::pair<std::string, std::string>> extra{{"Datasheet", ""}};
        for (const auto& field : fields) {
            if (field.key == "Datasheet") extra.front().second = field.value;
            else extra.emplace_back(field.key, field.value);
        }
        const auto symbol_uuid = uid("symbol");
        std::vector<std::pair<std::string, std::string>> pins;
        for (const auto& pin : definition.pins) pins.emplace_back(pin.number, uid("pin"));
        return emit_symbol(lib_id, x, y, rotation, symbol_uuid, ref, rp.x, rp.y, rp.rotation,
            hide_ref, value, vp.x, vp.y, vp.rotation, hide_val, footprint, extra, pins,
            output.project, output.instance_path);
    };
    for (const auto& part : design.parts) {
        const auto* original = circuit_part(circuit, part.ref);
        const auto footprint = part.footprint.empty() && original ? original->footprint : part.footprint;
        document.push_back(instance(part.ref, part.lib_id, part.value, part.x, part.y, part.rotation,
            footprint, part.ref_pos, part.val_pos, false, false,
            original ? original->fields : std::vector<CircuitFieldIr>{}));
    }
    for (const auto& power : design.powers)
        document.push_back(instance(power.ref, power.lib_id, power.value, power.x, power.y, power.rotation,
            "", std::nullopt, power.val_pos, true, !power.show_value, {}));
    document.push_back(list({sym("sheet_instances"), list({sym("path"), text("/"),
        list({sym("page"), text("1")})})}));
    output.document = list(std::move(document));
    output.text = sexpr_dumps(output.document) + "\n";
    return output;
}

SchematicOutput emit_schematic(const SchematicDesign& design,
                               const std::vector<SymbolDef>& symbols,
                               const SchematicOptions& options) {
    std::map<std::string, const SymbolDef*> by_id;
    for (const auto& symbol : symbols)
        if (!by_id.emplace(symbol.lib_id, &symbol).second)
            throw std::runtime_error("schematic: duplicate symbol definition " + symbol.lib_id);
    return emit_schematic(design, [&](const std::string& id) -> const SymbolDef& {
        const auto found = by_id.find(id);
        if (found == by_id.end()) throw std::runtime_error("schematic: missing symbol definition " + id);
        return *found->second;
    }, options);
}

}  // namespace schgen
