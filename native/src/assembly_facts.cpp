#include "schgen/assembly_facts.hpp"

#include <algorithm>
#include <cctype>
#include <cmath>
#include <sstream>
#include <stdexcept>

namespace schgen {
namespace {

const char* const facts_schema = "schgen.assembly_facts/1";
const std::set<std::string> library_classes{"basic", "preferred", "extended"};
const std::set<std::string> library_pcba_types{"economic_and_standard", "standard_only"};
const char* const timestamp_shape = "0000-00-00T00:00:00Z";
const char shape_digit = '0';
const char* const indent_unit = "  ";
const std::set<std::string> library_keys{"in_library", "class", "assembly_type", "assembly_mode", "pcba_type", "buyable",
                                         "jlc_stock", "lcsc_stock", "msl", "audit_flag", "special_fee", "jlc_package", "mpn",
                                         "read_utc", "source_urls", "route"};
const std::set<std::string> absent_keys{"in_library", "buyable", "lcsc_stock", "read_utc", "source_urls", "route"};
const std::set<std::string> route_names{"pre_order", "global"};

[[noreturn]] void refuse(const std::string& file, const std::string& where, const std::string& what) {
    throw std::runtime_error(file + (where.empty() ? "" : " " + where) + ": " + what);
}

const JsonNode& need(const JsonNode& node, const std::string& key, JsonKind kind, const std::string& file, const std::string& where) {
    const JsonNode* found = object_field(node, key);
    if (!found || found->kind != kind) refuse(file, where, "key '" + key + "' is missing or has the wrong type");
    return *found;
}

std::string name_of(const JsonNode& node, const std::string& key, const std::string& file, const std::string& where) {
    const std::string& value = need(node, key, JsonKind::String, file, where).string_value;
    if (value.empty()) refuse(file, where, "key '" + key + "' is empty");
    return value;
}

std::int64_t count_of(const JsonNode& node, const std::string& key, const std::string& file, const std::string& where) {
    const double value = need(node, key, JsonKind::Number, file, where).number_value;
    if (value < 0 || value != std::floor(value)) refuse(file, where, "key '" + key + "' must be a whole number of at least 0");
    return static_cast<std::int64_t>(value);
}

bool timestamp_ok(const std::string& text) {
    const std::string shape = timestamp_shape;
    if (text.size() != shape.size()) return false;
    for (std::size_t index = 0; index < shape.size(); ++index) {
        if (shape[index] == shape_digit ? !std::isdigit(static_cast<unsigned char>(text[index])) : text[index] != shape[index])
            return false;
    }
    return true;
}

bool code_ok(const std::string& code) {
    return code.size() > 1 && code.front() == 'C' && std::all_of(code.begin() + 1, code.end(), [](char c) { return std::isdigit(static_cast<unsigned char>(c)); });
}

AssemblyPart parse_part(const JsonNode& node, const std::string& file, const std::string& where) {
    if (node.kind != JsonKind::Object) refuse(file, where, "must be an object");
    AssemblyPart part;
    part.in_library = need(node, "in_library", JsonKind::Bool, file, where).bool_value;
    reject_unknown_keys(node, part.in_library ? library_keys : absent_keys, file + " " + where);
    part.buyable = need(node, "buyable", JsonKind::Bool, file, where).bool_value;
    const JsonNode* held = object_field(node, "lcsc_stock");
    if (held && held->kind == JsonKind::Null) part.lcsc_stock = std::nullopt;
    else part.lcsc_stock = count_of(node, "lcsc_stock", file, where);
    part.read_utc = name_of(node, "read_utc", file, where);
    if (!timestamp_ok(part.read_utc)) refuse(file, where, "read_utc '" + part.read_utc + "' is not a UTC time stamp");
    for (const JsonNode& url : need(node, "source_urls", JsonKind::Array, file, where).array_value) {
        if (url.kind != JsonKind::String || url.string_value.empty()) refuse(file, where, "source_urls holds a value that is not a URL");
        part.source_urls.push_back(url.string_value);
    }
    if (part.source_urls.empty()) refuse(file, where, "source_urls names no source");
    if (const JsonNode* route = object_field(node, "route")) {
        if (route->kind != JsonKind::String || !route_names.count(route->string_value))
            refuse(file, where, "route must be pre_order or global");
        part.route = route->string_value;
    }
    if (!part.in_library) {
        return part;
    }
    part.part_class = name_of(node, "class", file, where);
    if (!library_classes.count(part.part_class)) refuse(file, where, "class '" + part.part_class + "' is not basic, preferred or extended");
    part.preferred = part.part_class == "preferred";
    part.assembly_type = name_of(node, "assembly_type", file, where);
    part.assembly_mode = name_of(node, "assembly_mode", file, where);
    part.pcba_type = name_of(node, "pcba_type", file, where);
    if (!library_pcba_types.count(part.pcba_type)) refuse(file, where, "pcba_type '" + part.pcba_type + "' is not economic_and_standard or standard_only");
    part.jlc_stock = count_of(node, "jlc_stock", file, where);
    part.audit_flag = need(node, "audit_flag", JsonKind::Bool, file, where).bool_value;
    part.special_fee = need(node, "special_fee", JsonKind::Number, file, where).number_value;
    part.jlc_package = name_of(node, "jlc_package", file, where);
    part.mpn = name_of(node, "mpn", file, where);
    const JsonNode* msl = object_field(node, "msl");
    if (!msl || (msl->kind != JsonKind::Null && (msl->kind != JsonKind::String || msl->string_value.empty())))
        refuse(file, where, "key 'msl' must be null or a level name");
    part.msl = msl->kind == JsonKind::String ? msl->string_value : std::string();
    return part;
}

std::string quoted(const std::string& text) {
    std::string out = "\"";
    for (char c : text) {
        if (c == '"' || c == '\\') out += '\\';
        out += c;
    }
    return out + '"';
}

std::string number_text(double value) {
    std::ostringstream text;
    text << value;
    return text.str();
}

}

AssemblyFacts parse_assembly_facts(const JsonNode& document, const std::string& file) {
    if (document.kind != JsonKind::Object) refuse(file, "", "the file must hold one object");
    reject_unknown_keys(document, {"schema", "unplaced_classes", "needs", "parts"}, file);
    if (name_of(document, "schema", file, "") != facts_schema) refuse(file, "", "unknown schema");
    AssemblyFacts facts;
    facts.file = file;
    for (const JsonNode& item : need(document, "unplaced_classes", JsonKind::Array, file, "").array_value) {
        if (item.kind != JsonKind::String) refuse(file, "unplaced_classes", "holds a value that is not a class name");
        facts.unplaced_classes.insert(part_class_named(item.string_value));
    }
    for (const auto& [name, node] : need(document, "needs", JsonKind::Object, file, "").object_value) {
        const std::string where = "needs." + name;
        if (node.kind != JsonKind::Object) refuse(file, where, "must be an object");
        reject_unknown_keys(node, {"item", "satisfied_by", "owner_fits"}, file + " " + where);
        AssemblyNeed row;
        row.item = name_of(node, "item", file, where);
        for (const JsonNode& code : need(node, "satisfied_by", JsonKind::Array, file, where).array_value) {
            if (code.kind != JsonKind::String || !code_ok(code.string_value)) refuse(file, where, "satisfied_by holds a value that is not an LCSC code");
            row.satisfied_by.push_back(code.string_value);
        }
        const JsonNode& fitted = need(node, "owner_fits", JsonKind::String, file, where);
        row.owner_fits = fitted.string_value;
        facts.needs.emplace(part_class_named(name), row);
    }
    for (const auto& [code, node] : need(document, "parts", JsonKind::Object, file, "").object_value) {
        if (!code_ok(code)) refuse(file, "parts", "key '" + code + "' is not an LCSC code");
        if (!facts.parts.emplace(code, parse_part(node, file, "parts." + code)).second) refuse(file, "parts", "code '" + code + "' is listed twice");
    }
    return facts;
}

AssemblyFacts load_assembly_facts(const std::filesystem::path& file) {
    if (!std::filesystem::exists(file)) throw std::runtime_error("assembly facts not found at " + file.string());
    return parse_assembly_facts(parse_json_file(file.string()), file.string());
}

AssemblyFacts load_assembly_facts_in(const std::filesystem::path& parts_directory) {
    return load_assembly_facts(parts_directory / assembly_facts_name);
}

bool assembly_class_unplaced(const AssemblyFacts& facts, PartClass part_class) { return facts.unplaced_classes.count(part_class) > 0; }

std::string assembly_facts_text(const AssemblyFacts& facts) {
    std::string in1 = indent_unit, in2 = in1 + indent_unit, in3 = in2 + indent_unit;
    std::vector<std::string> classes;
    for (PartClass part_class : facts.unplaced_classes) classes.push_back(quoted(std::string(part_class_name(part_class))));
    std::sort(classes.begin(), classes.end());
    std::string out = "{\n" + in1 + "\"schema\": " + quoted(facts_schema) + ",\n" + in1 + "\"unplaced_classes\": [";
    for (std::size_t index = 0; index < classes.size(); ++index) out += (index ? ", " : "") + classes[index];
    out += "],\n" + in1 + "\"needs\": {";
    bool first_need = true;
    std::vector<std::pair<std::string, const AssemblyNeed*>> needs;
    for (const auto& [part_class, row] : facts.needs) needs.emplace_back(std::string(part_class_name(part_class)), &row);
    std::sort(needs.begin(), needs.end());
    for (const auto& [name, row] : needs) {
        out += std::string(first_need ? "\n" : ",\n") + in2 + quoted(name) + ": {\"item\": " + quoted(row->item) + ", \"satisfied_by\": [";
        for (std::size_t index = 0; index < row->satisfied_by.size(); ++index) out += (index ? ", " : "") + quoted(row->satisfied_by[index]);
        out += "], \"owner_fits\": " + quoted(row->owner_fits) + "}";
        first_need = false;
    }
    out += std::string(first_need ? "" : "\n" + in1) + "},\n" + in1 + "\"parts\": {";
    bool first_part = true;
    for (const auto& [code, part] : facts.parts) {
        out += std::string(first_part ? "\n" : ",\n") + in2 + quoted(code) + ": {\n";
        first_part = false;
        std::vector<std::string> lines;
        lines.push_back("\"in_library\": " + std::string(part.in_library ? "true" : "false"));
        if (part.in_library) {
            lines.push_back("\"class\": " + quoted(part.part_class));
            lines.push_back("\"assembly_type\": " + quoted(part.assembly_type));
            lines.push_back("\"assembly_mode\": " + quoted(part.assembly_mode));
            lines.push_back("\"pcba_type\": " + quoted(part.pcba_type));
        }
        lines.push_back("\"buyable\": " + std::string(part.buyable ? "true" : "false"));
        if (part.in_library) {
            lines.push_back("\"jlc_stock\": " + std::to_string(part.jlc_stock));
        }
        lines.push_back("\"lcsc_stock\": " + (part.lcsc_stock ? std::to_string(*part.lcsc_stock) : std::string("null")));
        if (part.in_library) {
            lines.push_back("\"msl\": " + (part.msl.empty() ? std::string("null") : quoted(part.msl)));
            lines.push_back("\"audit_flag\": " + std::string(part.audit_flag ? "true" : "false"));
            lines.push_back("\"special_fee\": " + number_text(part.special_fee));
            lines.push_back("\"jlc_package\": " + quoted(part.jlc_package));
            lines.push_back("\"mpn\": " + quoted(part.mpn));
        }
        if (!part.route.empty()) lines.push_back("\"route\": " + quoted(part.route));
        lines.push_back("\"read_utc\": " + quoted(part.read_utc));
        std::string urls = "\"source_urls\": [";
        for (std::size_t index = 0; index < part.source_urls.size(); ++index) urls += (index ? ", " : "") + quoted(part.source_urls[index]);
        lines.push_back(urls + "]");
        for (std::size_t index = 0; index < lines.size(); ++index) out += in3 + lines[index] + (index + 1 < lines.size() ? ",\n" : "\n");
        out += in2 + "}";
    }
    return out + (first_part ? "" : "\n" + in1) + "}\n}\n";
}

}
