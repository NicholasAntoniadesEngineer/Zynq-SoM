#include "schgen/part_facts.hpp"

#include "schgen/json.hpp"
#include "schgen/model3d.hpp"
#include "schgen/pcb_checks.hpp"

#include <algorithm>
#include <cctype>
#include <cmath>
#include <cstdlib>
#include <fstream>
#include <iterator>
#include <stdexcept>
#include <unordered_map>
#include <vector>

namespace schgen {
namespace {

const char* const facts_schema = "schgen.part_facts/1";
const char* const vrml_extension = ".wrl";
const char* const step_extension = ".step";
const std::string_view vrml_points = "point";
const std::string_view vrml_transform = "Transform";
const std::string_view step_point = "CARTESIAN_POINT";
const std::string_view step_vertex = "VERTEX_POINT";
const std::string_view step_unit = "SI_UNIT";
const std::string_view step_metre = ".METRE.";
const std::string_view step_milli = ".MILLI.";
const std::array<std::string_view, 2> step_placements{"ITEM_DEFINED_TRANSFORMATION", "MAPPED_ITEM"};
const std::string_view catalog_models = "${KIPRJMOD}/../parts/";
const std::string_view blanks = " \t\r\n";
const std::string_view separators = " \t\r\n,";
constexpr std::size_t axis_count = 3;

const std::pair<PartClass, std::string_view> class_names[] = {
    {PartClass::resistor, "resistor"},
    {PartClass::capacitor, "capacitor"},
    {PartClass::inductor, "inductor"},
    {PartClass::ferrite, "ferrite"},
    {PartClass::transformer, "transformer"},
    {PartClass::diode, "diode"},
    {PartClass::led, "led"},
    {PartClass::transistor, "transistor"},
    {PartClass::integrated_circuit, "integrated_circuit"},
    {PartClass::connector, "connector"},
    {PartClass::header, "header"},
    {PartClass::module_connector, "module_connector"},
    {PartClass::control_switch, "switch"},
    {PartClass::test_point, "test_point"},
    {PartClass::crystal, "crystal"},
    {PartClass::battery_holder, "battery_holder"},
    {PartClass::mounting_hole, "mounting_hole"},
    {PartClass::fiducial, "fiducial"},
};

[[noreturn]] void refuse(const std::string& why) { throw std::runtime_error("part facts: " + why); }

std::string file_text(const std::filesystem::path& path) {
    std::ifstream stream(path, std::ios::binary);
    if (!stream) refuse("cannot read " + path.string());
    return {std::istreambuf_iterator<char>(stream), std::istreambuf_iterator<char>()};
}

std::string lowered(std::string text) {
    std::transform(text.begin(), text.end(), text.begin(),
                   [](unsigned char letter) { return static_cast<char>(std::tolower(letter)); });
    return text;
}

double number_from(const std::string& text, std::size_t& cursor, std::size_t limit, const std::string& model) {
    cursor = text.find_first_not_of(separators, cursor);
    if (cursor == std::string::npos || cursor >= limit) refuse("a coordinate is missing in " + model);
    char* end = nullptr;
    const double value = std::strtod(text.c_str() + cursor, &end);
    const auto used = static_cast<std::size_t>(end - (text.c_str() + cursor));
    if (used == 0 || cursor + used > limit || !std::isfinite(value)) refuse("a coordinate cannot be read in " + model);
    cursor += used;
    return value;
}

double vrml_top(const std::string& text, const std::string& model) {
    if (text.find(vrml_transform) != std::string::npos)
        refuse(model + " places its geometry with scene transforms, which are not evaluated");
    std::optional<double> top;
    for (std::size_t at = text.find(vrml_points); at != std::string::npos; at = text.find(vrml_points, at)) {
        at += vrml_points.size();
        const std::size_t open = text.find_first_not_of(blanks, at);
        if (open == std::string::npos || text[open] != '[') continue;
        const std::size_t close = text.find(']', open);
        if (close == std::string::npos) refuse("an unclosed point list in " + model);
        std::size_t cursor = open + 1;
        while (text.find_first_not_of(separators, cursor) < close) {
            number_from(text, cursor, close, model);
            number_from(text, cursor, close, model);
            const double z = number_from(text, cursor, close, model);
            if (!top || z > *top) top = z;
        }
        at = close;
    }
    if (!top) refuse(model + " holds no mesh points");
    return *top * part_fact_constants::vrml_unit.value;
}

std::optional<long long> step_identifier(const std::string& text, std::size_t keyword) {
    std::size_t at = keyword;
    const auto back_over = [&](std::string_view set) {
        while (at > 0 && set.find(text[at - 1]) != std::string_view::npos) --at;
    };
    back_over(blanks);
    if (at == 0 || text[at - 1] != '=') return std::nullopt;
    --at;
    back_over(blanks);
    const std::size_t end = at;
    while (at > 0 && std::isdigit(static_cast<unsigned char>(text[at - 1]))) --at;
    if (at == end || at == 0 || text[at - 1] != '#') return std::nullopt;
    return std::stoll(text.substr(at, end - at));
}

std::size_t after_label(const std::string& text, std::size_t keyword, const std::string& model) {
    const std::size_t opened = text.find('\'', keyword);
    const std::size_t closed = opened == std::string::npos ? opened : text.find('\'', opened + 1);
    if (closed == std::string::npos) refuse("an entity without a label in " + model);
    return closed + 1;
}

double step_top(const std::string& text, const std::string& model) {
    for (const std::string_view placement : step_placements)
        if (text.find(placement) != std::string::npos)
            refuse(model + " places its solids with assembly transforms (" + std::string(placement) +
                   "), which are not evaluated");
    bool metric = false;
    for (std::size_t at = text.find(step_metre); at != std::string::npos; at = text.find(step_metre, at + 1)) {
        const std::size_t unit = text.rfind(step_unit, at);
        if (unit == std::string::npos || text.substr(unit, at - unit).find(step_milli) == std::string::npos)
            refuse(model + " is not drawn in millimetres");
        metric = true;
    }
    if (!metric) refuse(model + " states no length unit");
    std::unordered_map<long long, double> heights;
    for (std::size_t at = text.find(step_point); at != std::string::npos; at = text.find(step_point, at + 1)) {
        const auto identifier = step_identifier(text, at);
        if (!identifier) continue;
        std::size_t cursor = text.find('(', after_label(text, at, model));
        const std::size_t close = cursor == std::string::npos ? cursor : text.find(')', cursor);
        if (close == std::string::npos) refuse("an unclosed point in " + model);
        ++cursor;
        number_from(text, cursor, close, model);
        number_from(text, cursor, close, model);
        heights[*identifier] = number_from(text, cursor, close, model);
    }
    std::optional<double> top;
    for (std::size_t at = text.find(step_vertex); at != std::string::npos; at = text.find(step_vertex, at + 1)) {
        if (!step_identifier(text, at)) continue;
        std::size_t cursor = text.find('#', after_label(text, at, model));
        if (cursor == std::string::npos) refuse("a vertex without a point in " + model);
        ++cursor;
        std::size_t end = cursor;
        while (end < text.size() && std::isdigit(static_cast<unsigned char>(text[end]))) ++end;
        if (end == cursor) refuse("a vertex without a point in " + model);
        const auto point = heights.find(std::stoll(text.substr(cursor, end - cursor)));
        if (point == heights.end()) refuse("a vertex names a point that " + model + " does not define");
        if (!top || point->second > *top) top = point->second;
    }
    if (!top) refuse(model + " holds no solid vertices");
    return *top;
}

const SexprList* as_list(const Sexpr& node) { return std::get_if<SexprList>(&node.v); }

std::string as_text(const Sexpr& node) {
    if (const auto* text = std::get_if<std::string>(&node.v)) return *text;
    if (const auto* symbol = std::get_if<Sexpr::Sym>(&node.v)) return symbol->name;
    return {};
}

struct Triple {
    double x = 0, y = 0, z = 0;
};

std::optional<Triple> triple_named(const SexprList& clause, std::string_view name, const std::string& part) {
    for (const auto& node : clause) {
        const auto* item = as_list(node);
        if (!item || item->empty() || as_text(item->front()) != name) continue;
        for (const auto& inner : *item) {
            const auto* xyz = as_list(inner);
            if (!xyz || xyz->empty() || as_text(xyz->front()) != "xyz") continue;
            std::vector<double> values;
            for (const auto& value : *xyz)
                if (const auto* number = std::get_if<double>(&value.v)) values.push_back(*number);
            if (values.size() != axis_count)
                refuse(part + ": the model clause has a malformed " + std::string(name));
            return Triple{values.front(), values[1], values.back()};
        }
    }
    return std::nullopt;
}

double placed_top(const std::string& raw_path, const ModelRoots& roots, const std::string& part) {
    const bool catalogued = raw_path.compare(0, catalog_models.size(), catalog_models) == 0;
    const auto path = catalogued
                          ? std::optional<std::filesystem::path>(roots.parts_directory / raw_path.substr(catalog_models.size()))
                          : resolve_model3d_path(raw_path, roots.model_directory, roots.project_root);
    if (!path || !std::filesystem::is_regular_file(*path))
        refuse(part + ": its 3D model " + raw_path + " does not resolve to a file, so its height cannot be measured");
    return model_top(file_text(*path), path->extension().string(), raw_path);
}

PartHeight measured(double top, const std::string& raw_path, const std::string& part) {
    if (!(top > 0)) refuse(part + ": its 3D model " + raw_path + " does not rise above the board face");
    return {top, "highest point of the 3D model " + raw_path};
}

}

std::string_view part_class_name(PartClass part_class) {
    for (const auto& [value, name] : class_names)
        if (value == part_class) return name;
    refuse("a part class has no name");
}

PartClass part_class_named(std::string_view name) {
    for (const auto& [value, known] : class_names)
        if (known == name) return value;
    refuse("unknown part class " + std::string(name));
}

bool presents_on_top(PartClass part_class) {
    switch (part_class) {
    case PartClass::test_point:
    case PartClass::led:
    case PartClass::control_switch:
    case PartClass::connector:
    case PartClass::header:
    case PartClass::module_connector:
    case PartClass::battery_holder:
        return true;
    case PartClass::resistor:
    case PartClass::capacitor:
    case PartClass::inductor:
    case PartClass::ferrite:
    case PartClass::transformer:
    case PartClass::diode:
    case PartClass::transistor:
    case PartClass::integrated_circuit:
    case PartClass::crystal:
    case PartClass::mounting_hole:
    case PartClass::fiducial:
        return false;
    }
    refuse("a part class has no face rule");
}

PartClass part_class_of(const PcbCheckInstance& instance) {
    if (!instance.part_class) refuse(instance.ref + " (" + instance.sheet + ") carries no part class");
    return *instance.part_class;
}

const PartHeight& part_height_of(const PcbCheckInstance& instance) {
    if (!instance.height) refuse(instance.ref + " (" + instance.sheet + ") carries no height");
    return *instance.height;
}

PartFacts load_part_facts(const std::filesystem::path& file) {
    if (!std::filesystem::is_regular_file(file)) refuse("the part facts file is missing: " + file.string());
    const JsonNode root = parse_json_file(file.string());
    reject_unknown_keys(root, {"schema", "classes", "stated_heights"}, file.string());
    if (require_string(root, "schema", false, "part facts") != facts_schema)
        refuse(file.string() + " schema must be " + facts_schema);
    PartFacts facts;
    facts.file = file;
    const JsonNode* classes = object_field(root, "classes");
    if (!classes || classes->kind != JsonKind::Object) refuse(file.string() + " needs an object named classes");
    for (const auto& [symbol, name] : classes->object_value) {
        if (name.kind != JsonKind::String) refuse(file.string() + ": the class of " + symbol + " must be a string");
        if (!facts.classes.emplace(symbol, part_class_named(name.string_value)).second)
            refuse(file.string() + " gives " + symbol + " a class twice");
    }
    const JsonNode* heights = object_field(root, "stated_heights");
    if (!heights || heights->kind != JsonKind::Object) refuse(file.string() + " needs an object named stated_heights");
    for (const auto& [footprint, entry] : heights->object_value) {
        reject_unknown_keys(entry, {"mm", "basis", "reviewed"}, file.string() + " " + footprint);
        const JsonNode* value = object_field(entry, "mm");
        if (!value || value->kind != JsonKind::Number || !std::isfinite(value->number_value) || value->number_value < 0)
            refuse(file.string() + ": the stated height of " + footprint + " must be a number of millimetres");
        const std::string basis = require_string(entry, "basis", false, "part facts");
        const std::string reviewed = require_string(entry, "reviewed", false, "part facts");
        if (!facts.stated_heights
                 .emplace(footprint, PartHeight{value->number_value, "stated in " + file.filename().string() +
                                                                         ", reviewed " + reviewed + ": " + basis})
                 .second)
            refuse(file.string() + " states the height of " + footprint + " twice");
    }
    return facts;
}

PartClass symbol_class(const PartFacts& facts, const std::string& symbol, const std::string& part) {
    const auto found = facts.classes.find(symbol);
    if (found == facts.classes.end())
        refuse(part + ": its symbol " + symbol + " has no class in " + facts.file.string());
    return found->second;
}

double model_top(const std::string& text, const std::string& extension, const std::string& model) {
    const std::string kind = lowered(extension);
    if (kind == vrml_extension) return vrml_top(text, model);
    if (kind == step_extension) return step_top(text, model);
    refuse(model + " is neither a VRML nor a STEP model");
}

PartHeight model_height(const std::string& raw_path, const ModelRoots& roots, const std::string& part) {
    return measured(placed_top(raw_path, roots, part), raw_path, part);
}

PartHeight footprint_height(const PartFacts& facts, const std::string& footprint, const Sexpr& document,
                            const ModelRoots& roots, const std::string& part) {
    const auto* root = as_list(document);
    if (!root) refuse(part + ": the footprint " + footprint + " is not a list");
    const auto stated = facts.stated_heights.find(footprint);
    std::optional<double> top;
    std::string tallest;
    for (const auto& node : *root) {
        const auto* clause = as_list(node);
        if (!clause || clause->size() < 2 || as_text(clause->front()) != "model") continue;
        const std::string raw_path = as_text((*clause)[1]);
        const Triple scale = triple_named(*clause, "scale", part).value_or(Triple{1, 1, 1});
        const Triple turn = triple_named(*clause, "rotate", part).value_or(Triple{});
        const Triple offset = triple_named(*clause, "offset", part).value_or(Triple{});
        if (turn.x != 0 || turn.y != 0)
            refuse(part + ": the footprint " + footprint + " tilts its 3D model " + raw_path +
                   ", which is not evaluated");
        if (!(scale.z > 0))
            refuse(part + ": the footprint " + footprint + " scales its 3D model " + raw_path +
                   " by a height that is not positive");
        const double placed = placed_top(raw_path, roots, part) * scale.z + offset.z;
        if (!top || placed > *top) {
            top = placed;
            tallest = raw_path;
        }
    }
    if (top && stated != facts.stated_heights.end())
        refuse(part + ": the footprint " + footprint + " names a 3D model and " + facts.file.string() +
               " also states its height; a height has one source");
    if (top) return measured(*top, tallest, part);
    if (stated == facts.stated_heights.end())
        refuse(part + ": the footprint " + footprint + " names no 3D model and " + facts.file.string() +
               " states no height for it");
    return stated->second;
}

}
