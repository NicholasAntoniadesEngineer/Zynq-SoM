#include "schgen/part_facts.hpp"

#include "schgen/json.hpp"
#include "schgen/board_definition.hpp"
#include "schgen/model3d.hpp"
#include "schgen/pcb_checks.hpp"

#include <algorithm>
#include <cctype>
#include <cmath>
#include <cstdlib>
#include <fstream>
#include <iterator>
#include <limits>
#include <stdexcept>
#include <unordered_map>
#include <vector>

namespace schgen {
namespace {

const char* const facts_schema = "schgen.part_facts/5";
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
const char* const facts_file_name = "part_facts.json";
const char* const part_file_name = "part.json";
const std::string_view face_signs = "+-";
const std::string_view face_axes = "XYZ";
constexpr std::size_t face_length = 2;
constexpr std::size_t pair_length = 2;
const char* const led_boost_kind = "led_boost";
const std::array<std::string_view, 5> regulator_kinds{"buck", "ldo", "load_switch", "efuse", led_boost_kind};

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

namespace {

bool flag_of(const JsonNode& entry, const std::string& key, const std::string& where) {
    const JsonNode* value = object_field(entry, key);
    if (!value || value->kind != JsonKind::Bool) refuse(where + " needs a true or false value named " + key);
    return value->bool_value;
}

std::optional<std::string> text_of(const JsonNode& entry, const std::string& key, const std::string& where) {
    const JsonNode* value = object_field(entry, key);
    if (!value) return std::nullopt;
    if (value->kind != JsonKind::String || value->string_value.empty())
        refuse(where + ": " + key + " must be a non-empty string");
    return value->string_value;
}

constexpr std::size_t box_length = 4;

double number_of(const JsonNode& entry, const std::string& key, const std::string& where, bool positive) {
    const JsonNode* value = object_field(entry, key);
    if (!value || value->kind != JsonKind::Number || !std::isfinite(value->number_value))
        refuse(where + ": " + key + " must be a number");
    if (positive ? !(value->number_value > 0) : value->number_value < 0)
        refuse(where + ": " + key + (positive ? " must be above zero" : " must not be negative"));
    return value->number_value;
}

std::optional<double> optional_number_of(const JsonNode& entry, const std::string& key, const std::string& where) {
    if (!object_field(entry, key)) return std::nullopt;
    return number_of(entry, key, where, true);
}

int count_of(const JsonNode& entry, const std::string& key, const std::string& where) {
    const double value = number_of(entry, key, where, true);
    if (std::floor(value) != value || value > std::numeric_limits<int>::max())
        refuse(where + ": " + key + " must be a whole number");
    return static_cast<int>(value);
}

std::string text_required(const JsonNode& entry, const std::string& key, const std::string& where) {
    return require_string(entry, key, false, where);
}

const JsonNode& object_required(const JsonNode& entry, const std::string& key, const std::string& where) {
    const JsonNode* value = object_field(entry, key);
    if (!value || value->kind != JsonKind::Object) refuse(where + ": " + key + " must be an object");
    return *value;
}

const JsonNode& array_required(const JsonNode& entry, const std::string& key, const std::string& where) {
    const JsonNode* value = object_field(entry, key);
    if (!value || value->kind != JsonKind::Array) refuse(where + ": " + key + " must be an array");
    return *value;
}

std::vector<std::string> texts_of(const JsonNode& entry, const std::string& key, const std::string& where) {
    std::vector<std::string> out;
    for (const JsonNode& item : array_required(entry, key, where).array_value) {
        if (item.kind != JsonKind::String || item.string_value.empty())
            refuse(where + ": " + key + " must hold non-empty strings");
        out.push_back(item.string_value);
    }
    if (out.empty()) refuse(where + ": " + key + " must not be empty");
    return out;
}

std::array<double, box_length> box_of(const JsonNode& entry, const std::string& key, const std::string& where) {
    const JsonNode& list = array_required(entry, key, where);
    if (list.array_value.size() != box_length) refuse(where + ": " + key + " must hold x0, y0, x1, y1");
    std::array<double, box_length> out{};
    for (std::size_t i = 0; i < box_length; ++i) {
        if (list.array_value[i].kind != JsonKind::Number || !std::isfinite(list.array_value[i].number_value))
            refuse(where + ": " + key + " must hold numbers");
        out[i] = list.array_value[i].number_value;
    }
    if (!(out[0] < out[2]) || !(out[1] < out[3])) refuse(where + ": " + key + " must have x0 < x1 and y0 < y1");
    return out;
}

std::vector<std::pair<double, double>> offsets_of(const JsonNode& entry, const std::string& key, const std::string& where) {
    std::vector<std::pair<double, double>> out;
    for (const JsonNode& item : array_required(entry, key, where).array_value) {
        if (item.kind != JsonKind::Array || item.array_value.size() != pair_length ||
            item.array_value.front().kind != JsonKind::Number || item.array_value.back().kind != JsonKind::Number ||
            !std::isfinite(item.array_value.front().number_value) || !std::isfinite(item.array_value.back().number_value))
            refuse(where + ": " + key + " must hold [x, y] pairs of numbers");
        out.emplace_back(item.array_value.front().number_value, item.array_value.back().number_value);
    }
    if (out.empty()) refuse(where + ": " + key + " must not be empty");
    return out;
}

ThermalFact thermal_from(const JsonNode& entry, const std::string& where) {
    reject_unknown_keys(entry, {"rth_ja", "tj_max", "rds_on", "eff", "package", "cite", "pour"}, where);
    ThermalFact fact;
    fact.rth_ja = number_of(entry, "rth_ja", where, true);
    fact.tj_max = number_of(entry, "tj_max", where, true);
    fact.rds_on = number_of(entry, "rds_on", where, false);
    fact.eff = number_of(entry, "eff", where, true);
    if (fact.eff > 1) refuse(where + ": eff must not exceed 1");
    fact.package = text_required(entry, "package", where);
    fact.cite = text_required(entry, "cite", where);
    if (object_field(entry, "pour")) {
        const JsonNode& pour = object_required(entry, "pour", where);
        const std::string pour_where = where + " pour";
        reject_unknown_keys(pour, {"rth_ja", "cite", "evidence"}, pour_where);
        fact.pour = ThermalPourFact{number_of(pour, "rth_ja", pour_where, true), text_required(pour, "cite", pour_where),
                                    text_required(pour, "evidence", pour_where)};
    }
    return fact;
}

ThermalCopperFact thermal_copper_from(const JsonNode& entry, const std::string& where) {
    reject_unknown_keys(entry, {"need", "field"}, where);
    ThermalCopperFact fact;
    const JsonNode& need = object_required(entry, "need", where);
    const std::string need_where = where + " need";
    reject_unknown_keys(need, {"min_vias", "radius_mm", "pour_layers"}, need_where);
    fact.need = ThermalNeedFact{count_of(need, "min_vias", need_where), number_of(need, "radius_mm", need_where, true),
                                texts_of(need, "pour_layers", need_where)};
    const JsonNode& field = object_required(entry, "field", where);
    const std::string field_where = where + " field";
    reject_unknown_keys(field, {"via_offsets_mm", "max_vias", "pour_box_mm", "pour_layers", "cite"}, field_where);
    fact.field.via_offsets_mm = offsets_of(field, "via_offsets_mm", field_where);
    fact.field.max_vias = count_of(field, "max_vias", field_where);
    fact.field.pour_box_mm = box_of(field, "pour_box_mm", field_where);
    fact.field.pour_layers = texts_of(field, "pour_layers", field_where);
    fact.field.cite = text_required(field, "cite", field_where);
    return fact;
}

EpViaFact ep_via_from(const JsonNode& entry, const std::string& where) {
    reject_unknown_keys(entry, {"min_pads", "radius_mm"}, where);
    return EpViaFact{count_of(entry, "min_pads", where), number_of(entry, "radius_mm", where, true)};
}

IsolationFact isolation_from(const JsonNode& entry, const std::string& where) {
    reject_unknown_keys(entry, {"margin_mm"}, where);
    return IsolationFact{number_of(entry, "margin_mm", where, true)};
}

RegulatorEnableFact enable_from(const JsonNode& entry, const std::string& where) {
    reject_unknown_keys(entry, {"direct", "network"}, where);
    RegulatorEnableFact fact;
    if (!object_field(entry, "direct") && !object_field(entry, "network")) refuse(where + " must state direct or network");
    if (object_field(entry, "direct")) {
        const JsonNode& direct = object_required(entry, "direct", where);
        const std::string direct_where = where + " direct";
        reject_unknown_keys(direct, {"en_pin", "vin_pins", "cite"}, direct_where);
        fact.direct = RegulatorDirectEnable{text_required(direct, "en_pin", direct_where), texts_of(direct, "vin_pins", direct_where),
                                            text_required(direct, "cite", direct_where)};
    }
    if (object_field(entry, "network")) {
        const JsonNode& network = object_required(entry, "network", where);
        const std::string network_where = where + " network";
        reject_unknown_keys(network, {"ihys_a", "recommended_max_v", "threshold_v", "cite"}, network_where);
        fact.network = RegulatorEnableNetwork{number_of(network, "ihys_a", network_where, true),
                                              number_of(network, "recommended_max_v", network_where, true),
                                              number_of(network, "threshold_v", network_where, true),
                                              text_required(network, "cite", network_where)};
    }
    return fact;
}

RegulatorFact regulator_from(const JsonNode& entry, const std::string& where) {
    reject_unknown_keys(entry, {"kind", "label", "limit_a", "eff", "in_pin", "out_pin", "iset_pin", "ilim_num", "note", "fb_vref",
                                "iset_v", "out_v", "enable"}, where);
    RegulatorFact fact;
    fact.kind = text_required(entry, "kind", where);
    if (std::find(regulator_kinds.begin(), regulator_kinds.end(), fact.kind) == regulator_kinds.end())
        refuse(where + ": kind " + fact.kind + " is not one of buck, ldo, load_switch, efuse, led_boost");
    fact.label = text_required(entry, "label", where);
    if (fact.kind == led_boost_kind) {
        for (const char* key : {"limit_a", "eff", "in_pin", "out_pin", "iset_pin", "ilim_num", "note", "fb_vref", "out_v", "enable"})
            if (object_field(entry, key)) refuse(where + ": " + key + " does not apply to a led_boost");
        fact.iset_v = number_of(entry, "iset_v", where, true);
        return fact;
    }
    fact.limit_a = optional_number_of(entry, "limit_a", where);
    fact.eff = number_of(entry, "eff", where, true);
    if (fact.eff > 1) refuse(where + ": eff must not exceed 1");
    fact.in_pin = text_required(entry, "in_pin", where);
    fact.out_pin = text_required(entry, "out_pin", where);
    fact.iset_pin = text_of(entry, "iset_pin", where);
    fact.ilim_num = number_of(entry, "ilim_num", where, true);
    fact.note = text_required(entry, "note", where);
    fact.fb_vref = optional_number_of(entry, "fb_vref", where);
    fact.iset_v = optional_number_of(entry, "iset_v", where);
    fact.out_v = optional_number_of(entry, "out_v", where);
    if (fact.out_v && fact.fb_vref) refuse(where + ": out_v (fixed output) and fb_vref (adjustable output) exclude each other");
    if (object_field(entry, "enable")) fact.enable = enable_from(object_required(entry, "enable", where), where + " enable");
    return fact;
}

ZenerFact zener_from(const JsonNode& entry, const std::string& where) {
    reject_unknown_keys(entry, {"vz_min_v", "vz_max_v", "izt_a", "zzt_ohm"}, where);
    ZenerFact fact{number_of(entry, "vz_min_v", where, true), number_of(entry, "vz_max_v", where, true),
                   number_of(entry, "izt_a", where, true), number_of(entry, "zzt_ohm", where, true)};
    if (!(fact.vz_min_v < fact.vz_max_v)) refuse(where + ": vz_min_v must be below vz_max_v");
    return fact;
}

ReferencePinFact reference_pin_from(const JsonNode& entry, const std::string& where) {
    reject_unknown_keys(entry, {"label", "vref1_pin", "vref2_pin"}, where);
    ReferencePinFact fact{text_required(entry, "label", where), text_required(entry, "vref1_pin", where),
                          text_required(entry, "vref2_pin", where)};
    if (fact.vref1_pin == fact.vref2_pin) refuse(where + ": vref1_pin and vref2_pin must differ");
    return fact;
}

ControlGridFact control_grid_from(const JsonNode& entry, const std::string& where) {
    reject_unknown_keys(entry, {"button_gap_mm"}, where);
    return ControlGridFact{number_of(entry, "button_gap_mm", where, true)};
}

ModelOverrideFact model_override_from(const JsonNode& entry, const std::string& where) {
    reject_unknown_keys(entry, {"footprint", "path", "rotation_z_deg"}, where);
    ModelOverrideFact fact;
    fact.footprint = text_required(entry, "footprint", where);
    fact.path = text_required(entry, "path", where);
    const JsonNode* turn = object_field(entry, "rotation_z_deg");
    if (!turn || turn->kind != JsonKind::Number || !std::isfinite(turn->number_value))
        refuse(where + ": rotation_z_deg must be a number");
    fact.rotation_z_deg = turn->number_value;
    return fact;
}

LandFact land_from(const JsonNode& entry, const std::string& where) {
    reject_unknown_keys(entry, {"footprint", "pad_gap_mm", "tolerance_mm", "cite"}, where);
    LandFact fact;
    fact.footprint = text_required(entry, "footprint", where);
    fact.pad_gap_mm = number_of(entry, "pad_gap_mm", where, true);
    fact.tolerance_mm = number_of(entry, "tolerance_mm", where, true);
    fact.cite = text_required(entry, "cite", where);
    return fact;
}

ElectricalSpacingFact electrical_spacing_from(const JsonNode& root, const std::filesystem::path& file) {
    const std::string where = file.string() + " electrical_spacing";
    const JsonNode* node = object_field(root, "electrical_spacing");
    if (!node || node->kind != JsonKind::Object) refuse(file.string() + " needs an object named electrical_spacing");
    reject_unknown_keys(*node, {"source", "column", "basis", "rows"}, where);
    ElectricalSpacingFact fact;
    fact.source = text_required(*node, "source", where);
    fact.column = text_required(*node, "column", where);
    fact.basis = text_required(*node, "basis", where);
    const JsonNode* rows = object_field(*node, "rows");
    if (!rows || rows->kind != JsonKind::Array || rows->array_value.empty()) refuse(where + ": rows must be a non-empty array");
    for (const auto& row : rows->array_value) {
        if (row.kind != JsonKind::Object) refuse(where + ": a row must be an object");
        reject_unknown_keys(row, {"max_volts", "spacing_mm"}, where + " row");
        const ElectricalSpacingRow parsed{number_of(row, "max_volts", where + " row", true), number_of(row, "spacing_mm", where + " row", true)};
        if (!fact.rows.empty() && parsed.max_volts <= fact.rows.back().max_volts)
            refuse(where + ": rows must rise in max_volts");
        fact.rows.push_back(parsed);
    }
    return fact;
}

FootprintAliasFact footprint_alias_from(const JsonNode& entry, const std::string& where) {
    reject_unknown_keys(entry, {"footprint"}, where);
    return FootprintAliasFact{text_required(entry, "footprint", where)};
}

bool plain_folder_name(const std::string& name) {
    return name != "." && name != ".." && std::filesystem::path(name).filename() == std::filesystem::path(name);
}

template <typename Fact, typename Read>
std::map<std::string, Fact> section_from(const JsonNode& root, const std::filesystem::path& file, const std::string& section,
                                         bool names_a_part, Read read) {
    const JsonNode* node = object_field(root, section);
    if (!node || node->kind != JsonKind::Object) refuse(file.string() + " needs an object named " + section);
    std::map<std::string, Fact> out;
    for (const auto& [key, entry] : node->object_value) {
        const std::string where = file.string() + " " + section + " " + key;
        if (entry.kind != JsonKind::Object) refuse(where + " must be an object");
        if (names_a_part && (!plain_folder_name(key) || !std::filesystem::is_directory(file.parent_path() / key)))
            refuse(where + " names a part with no folder in " + file.parent_path().string());
        out.emplace(key, read(entry, where));
    }
    return out;
}

using PinTable = std::map<std::string, std::vector<std::string>>;

PinTable pin_table(const std::filesystem::path& part_file, const std::string& where) {
    if (!std::filesystem::is_regular_file(part_file)) refuse(where + " needs the catalogue file " + part_file.string());
    const JsonNode part = parse_json_file(part_file.string());
    const JsonNode& pins = array_required(part, "pins", part_file.string());
    PinTable out;
    for (const JsonNode& pin : pins.array_value) {
        if (pin.kind != JsonKind::Object) refuse(part_file.string() + ": every pin must be an object");
        out[text_required(pin, "name", part_file.string())].push_back(text_required(pin, "num", part_file.string()));
    }
    return out;
}

I2cPinFact pin_named(const PinTable& pins, const std::string& name, const std::string& where) {
    const auto found = pins.find(name);
    if (found == pins.end()) refuse(where + ": the part has no pin named " + name);
    if (found->second.size() != 1) refuse(where + ": " + std::to_string(found->second.size()) + " pins are named " + name + ", so the name does not pick one");
    return I2cPinFact{name, found->second.front()};
}

int whole_of(const JsonNode& value, const std::string& key, const std::string& where) {
    if (value.kind != JsonKind::Number || !std::isfinite(value.number_value) || value.number_value < 0 ||
        std::floor(value.number_value) != value.number_value || value.number_value > part_fact_constants::i2c_address_max.value)
        refuse(where + ": " + key + " must be a whole number from 0 to " + std::to_string(static_cast<int>(part_fact_constants::i2c_address_max.value)));
    return static_cast<int>(value.number_value);
}

I2cDeviceFact i2c_device_from(const JsonNode& entry, const std::string& where, const PinTable& pins) {
    reject_unknown_keys(entry, {"label", "base", "data_pin", "clock_pin", "straps", "cite"}, where);
    I2cDeviceFact fact;
    fact.label = text_required(entry, "label", where);
    const JsonNode* base = object_field(entry, "base");
    if (!base) refuse(where + ": base must be a number");
    fact.base = whole_of(*base, "base", where);
    fact.data = pin_named(pins, text_required(entry, "data_pin", where), where + " data_pin");
    fact.clock = pin_named(pins, text_required(entry, "clock_pin", where), where + " clock_pin");
    if (fact.data.number == fact.clock.number) refuse(where + ": data_pin and clock_pin must differ");
    fact.cite = text_required(entry, "cite", where);
    int highest = fact.base;
    for (const JsonNode& row : array_required(entry, "straps", where).array_value) {
        const std::string strap_where = where + " straps";
        if (row.kind != JsonKind::Object) refuse(strap_where + ": every strap must be an object");
        reject_unknown_keys(row, {"pin", "selects"}, strap_where);
        I2cStrapFact strap;
        strap.pin = pin_named(pins, text_required(row, "pin", strap_where), strap_where + " pin");
        if (strap.pin.number == fact.data.number || strap.pin.number == fact.clock.number)
            refuse(strap_where + ": strap pin " + strap.pin.name + " is the data or clock pin");
        if (std::any_of(fact.straps.begin(), fact.straps.end(), [&](const I2cStrapFact& s) { return s.pin.number == strap.pin.number; }))
            refuse(strap_where + ": strap pin " + strap.pin.name + " is listed twice");
        const JsonNode& selects = object_required(row, "selects", strap_where);
        if (selects.object_value.empty()) refuse(strap_where + " " + strap.pin.name + ": selects must not be empty");
        int most = 0;
        for (const auto& [target, value] : selects.object_value) {
            const std::string select_where = strap_where + " " + strap.pin.name + " selects";
            const int chosen = whole_of(value, target, select_where);
            strap.selects.emplace_back(pin_named(pins, target, select_where), chosen);
            most = std::max(most, chosen);
        }
        highest += most;
        fact.straps.push_back(std::move(strap));
    }
    if (highest > part_fact_constants::i2c_address_max.value)
        refuse(where + ": base plus the largest strap values reaches " + std::to_string(highest) + ", beyond a seven-bit address");
    return fact;
}

I2cBridgeFact i2c_bridge_from(const JsonNode& entry, const std::string& where, const PinTable& pins) {
    reject_unknown_keys(entry, {"joins", "shares_addresses", "cite"}, where);
    I2cBridgeFact fact;
    for (const JsonNode& pair : array_required(entry, "joins", where).array_value) {
        if (pair.kind != JsonKind::Array || pair.array_value.size() != pair_length || pair.array_value.front().kind != JsonKind::String ||
            pair.array_value.back().kind != JsonKind::String)
            refuse(where + ": joins must hold pairs of pin names");
        const I2cPinFact from = pin_named(pins, pair.array_value.front().string_value, where + " joins");
        const I2cPinFact to = pin_named(pins, pair.array_value.back().string_value, where + " joins");
        if (from.number == to.number) refuse(where + ": a join must name two different pins");
        fact.joins.emplace_back(from, to);
    }
    if (fact.joins.empty()) refuse(where + ": joins must not be empty");
    fact.shares_addresses = flag_of(entry, "shares_addresses", where);
    fact.cite = text_required(entry, "cite", where);
    return fact;
}

template <typename Fact, typename Read>
std::map<std::string, Fact> pinned_section_from(const JsonNode& root, const std::filesystem::path& file, const std::string& section, Read read) {
    const JsonNode* node = object_field(root, section);
    if (!node || node->kind != JsonKind::Object) refuse(file.string() + " needs an object named " + section);
    std::map<std::string, Fact> out;
    for (const auto& [key, entry] : node->object_value) {
        const std::string where = file.string() + " " + section + " " + key;
        if (entry.kind != JsonKind::Object) refuse(where + " must be an object");
        if (!plain_folder_name(key) || !std::filesystem::is_directory(file.parent_path() / key))
            refuse(where + " names a part with no folder in " + file.parent_path().string());
        out.emplace(key, read(entry, where, pin_table(file.parent_path() / key / part_file_name, where)));
    }
    return out;
}

ConnectorFacts connectors_from(const JsonNode& section, const std::map<std::string, PartClass>& classes,
                               const std::string& file) {
    ConnectorFacts out;
    for (const auto& [name, entry] : section.object_value) {
        const std::string where = file + " connectors " + name;
        if (entry.kind != JsonKind::Object) refuse(where + " must be an object");
        reject_unknown_keys(entry, {"mating_face", "edge_pinned", "overmold", "pad_row_face_check", "description",
                                    "numbered_label", "pair_label", "handling", "mating", "access"}, where);
        ConnectorFact fact;
        fact.mating_face = require_string(entry, "mating_face", false, where);
        if (fact.mating_face.size() != face_length || face_signs.find(fact.mating_face.front()) == std::string_view::npos ||
            face_axes.find(fact.mating_face.back()) == std::string_view::npos)
            refuse(where + ": mating_face must be one of +X, -X, +Y, -Y, +Z");
        if (fact.mating_face == "-Z") refuse(where + ": mating_face -Z would mate through the board");
        fact.edge_pinned = flag_of(entry, "edge_pinned", where);
        fact.overmold = flag_of(entry, "overmold", where);
        fact.pad_row_face_check = flag_of(entry, "pad_row_face_check", where);
        fact.description = text_of(entry, "description", where);
        fact.numbered_label = text_of(entry, "numbered_label", where);
        fact.pair_label = text_of(entry, "pair_label", where);
        if (fact.edge_pinned && !fact.description) refuse(where + ": an edge-pinned connector needs a description");
        if (fact.edge_pinned && fact.mating_face.back() == face_axes.back()) refuse(where + ": a connector mated from above (+Z) cannot be edge-pinned");
        fact.handling = require_string(entry, "handling", false, where);
        const auto& handling = connector_handling_classes();
        if (std::find(handling.begin(), handling.end(), fact.handling) == handling.end())
            refuse(where + ": handling must be one of grip_sides, latch, card, flat_cable, pins, none");
        if (const JsonNode* mating = object_field(entry, "mating")) {
            const std::string at = where + " mating";
            if (mating->kind != JsonKind::Object) refuse(at + " must be an object");
            reject_unknown_keys(*mating, {"plug_width_mm", "plug_depth_mm", "plug_height_mm", "cite"}, at);
            ConnectorMating row;
            const auto nullable = [&](const std::string& key) -> std::optional<double> {
                const JsonNode* value = object_field(*mating, key);
                if (!value) refuse(at + " needs " + key + " (a number, or null when not determined)");
                if (value->kind == JsonKind::Null) return std::nullopt;
                return number_of(*mating, key, at, true);
            };
            row.plug_width_mm = nullable("plug_width_mm");
            row.plug_depth_mm = nullable("plug_depth_mm");
            row.plug_height_mm = nullable("plug_height_mm");
            const JsonNode* cite = object_field(*mating, "cite");
            if (!cite) refuse(at + " needs cite (a string, or null when not determined)");
            if (cite->kind != JsonKind::Null) row.cite = text_of(*mating, "cite", at);
            if ((row.plug_width_mm || row.plug_depth_mm || row.plug_height_mm) && !row.cite)
                refuse(at + ": a stated plug dimension needs a cite");
            fact.mating = row;
        }
        const JsonNode* access = object_field(entry, "access");
        if (!access) refuse(where + ": a connector must state access (side_mm, front_mm and cite; zero is stated, never implied)");
        {
            const std::string at = where + " access";
            if (access->kind != JsonKind::Object) refuse(at + " must be an object");
            reject_unknown_keys(*access, {"side_mm", "front_mm", "cite"}, at);
            fact.access = ConnectorAccess{number_of(*access, "side_mm", at, false), number_of(*access, "front_mm", at, false),
                                          text_required(*access, "cite", at)};
        }
        const auto symbol = classes.find(name + ":" + name);
        if (symbol == classes.end() || symbol->second != PartClass::connector)
            refuse(where + " must name a symbol of class connector in classes");
        out.emplace(name, std::move(fact));
    }
    for (const auto& [symbol, part_class] : classes) {
        if (part_class != PartClass::connector) continue;
        const std::string name = symbol.substr(symbol.find(':') + 1);
        if (!out.count(name)) refuse(file + " gives " + symbol + " the class connector but no connectors entry");
    }
    return out;
}

}

const ConnectorFact* connector_fact(const ConnectorFacts& facts, const std::string& name) {
    const auto found = facts.find(name);
    return found == facts.end() ? nullptr : &found->second;
}

const ConnectorFact& connector_fact_of(const ConnectorFacts& facts, const std::string& name) {
    const ConnectorFact* fact = connector_fact(facts, name);
    if (!fact) refuse(name + " has no connectors entry in the part facts");
    return *fact;
}

std::pair<int, int> mating_face_vector(const ConnectorFact& fact) {
    const int sign = fact.mating_face.front() == face_signs.front() ? 1 : -1;
    if (fact.mating_face.back() == face_axes.back()) return {0, 0};
    return fact.mating_face.back() == face_axes.front() ? std::pair<int, int>{sign, 0} : std::pair<int, int>{0, sign};
}

ConnectorFacts load_connector_facts(const std::filesystem::path& parts_directory) {
    return load_part_facts(parts_directory / facts_file_name).connectors;
}

PartFacts load_part_facts(const std::filesystem::path& file) {
    if (!std::filesystem::is_regular_file(file)) refuse("the part facts file is missing: " + file.string());
    const JsonNode root = parse_json_file(file.string());
    reject_unknown_keys(root, {"schema", "classes", "stated_heights", "connectors", "thermal", "thermal_copper", "ep_vias", "isolation", "regulators", "zeners", "reference_pins", "control_grid", "model_overrides", "footprint_aliases", "lands", "electrical_spacing", "i2c_devices", "i2c_bridges"}, file.string());
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
    const JsonNode* connectors = object_field(root, "connectors");
    if (!connectors || connectors->kind != JsonKind::Object) refuse(file.string() + " needs an object named connectors");
    facts.connectors = connectors_from(*connectors, facts.classes, file.string());
    facts.thermal = section_from<ThermalFact>(root, file, "thermal", true, thermal_from);
    facts.thermal_copper = section_from<ThermalCopperFact>(root, file, "thermal_copper", true, thermal_copper_from);
    facts.ep_vias = section_from<EpViaFact>(root, file, "ep_vias", true, ep_via_from);
    facts.isolation = section_from<IsolationFact>(root, file, "isolation", true, isolation_from);
    facts.regulators = section_from<RegulatorFact>(root, file, "regulators", true, regulator_from);
    facts.zeners = section_from<ZenerFact>(root, file, "zeners", false, zener_from);
    facts.reference_pins = section_from<ReferencePinFact>(root, file, "reference_pins", true, reference_pin_from);
    facts.control_grid = section_from<ControlGridFact>(root, file, "control_grid", true, control_grid_from);
    facts.model_overrides = section_from<ModelOverrideFact>(root, file, "model_overrides", true, model_override_from);
    facts.footprint_aliases = section_from<FootprintAliasFact>(root, file, "footprint_aliases", false, footprint_alias_from);
    facts.lands = section_from<LandFact>(root, file, "lands", true, land_from);
    facts.electrical_spacing = electrical_spacing_from(root, file);
    facts.i2c_devices = pinned_section_from<I2cDeviceFact>(root, file, "i2c_devices", i2c_device_from);
    facts.i2c_bridges = pinned_section_from<I2cBridgeFact>(root, file, "i2c_bridges", i2c_bridge_from);
    return facts;
}

PartFacts load_part_facts_in(const std::filesystem::path& parts_directory) {
    return load_part_facts(parts_directory / facts_file_name);
}

ModelOverrideFacts model_overrides_by_part_number(const PartFacts& facts) {
    ModelOverrideFacts out;
    for (const auto& [folder, fact] : facts.model_overrides) {
        const auto record = facts.file.parent_path() / folder / "part.json";
        const JsonNode part = parse_json_file(record.string());
        const std::string mpn = require_string(part, "mpn", false, record.string());
        if (!out.emplace(mpn, fact).second) refuse(facts.file.string() + ": two model overrides name part number " + mpn);
    }
    return out;
}

namespace {
template <typename Fact>
const Fact* fact_by_label_prefix(const std::map<std::string, Fact>& rows, const RegulatorFacts& regulators, const std::string& value) {
    for (const auto& [part, fact] : rows) {
        const std::string& label = part_fact_of(regulators, part, "regulators").label;
        if (label.empty()) refuse("the part facts regulators entry of " + part + " has an empty label");
        if (value.compare(0, label.size(), label) == 0) return &fact;
    }
    return nullptr;
}
}

const ThermalFieldFact* thermal_field_for(const ThermalCopperFacts& rows, const RegulatorFacts& regulators, const std::string& value) {
    const ThermalCopperFact* row = fact_by_label_prefix(rows, regulators, value);
    return row ? &row->field : nullptr;
}

const EpViaFact* ep_via_for(const EpViaFacts& rows, const RegulatorFacts& regulators, const std::string& value) {
    return fact_by_label_prefix(rows, regulators, value);
}

const PartFacts& default_part_facts() {
    static const PartFacts facts = load_part_facts(SCHGEN_PART_FACTS);
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
