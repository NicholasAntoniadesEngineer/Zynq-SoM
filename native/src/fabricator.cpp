#include "schgen/fabricator.hpp"

#include <algorithm>
#include <cctype>
#include <cmath>
#include <optional>
#include <set>
#include <sstream>

namespace schgen {
namespace {

enum class Kind { number, numbers, text, texts, flag };

struct Row {
    std::string path, unit;
    Kind kind;
};

const char* const path_separator = ".";
const char* const timestamp_shape = "0000-00-00T00:00:00Z";
const char schema_digit = '0';
const std::string schema_name = "schgen.fabricator/1";
const char* const unit_length = "mm";
const char* const unit_flag = "flag";
const char* const unit_text = "text";
const char* const unit_count = "pcs";
const char* const unit_layers = "layers";
const char* const unit_ratio = "ratio";
const char* const unit_usd = "usd";
const char* const unit_oz = "oz";
const char* const unit_designators = "designators";
const double tolerance_oz = 1e-9;

[[noreturn]] void fail(const std::string& file, const std::string& where, const std::string& what) {
    throw std::runtime_error(file + (where.empty() ? "" : " " + where) + ": " + what);
}

std::vector<Row> schema_rows() {
    std::vector<Row> rows;
    const auto add = [&](const std::string& path, const char* unit, Kind kind) { rows.push_back({path, unit, kind}); };
    for (const std::string service : {"economic", "standard"}) {
        const std::string base = "assembly.services." + service + ".";
        add(base + "double_sided", unit_flag, Kind::flag);
        add(base + "layers_min", unit_layers, Kind::number);
        add(base + "layers_max", unit_layers, Kind::number);
        add(base + "board_min_mm", unit_length, Kind::numbers);
        add(base + "board_max_mm", unit_length, Kind::numbers);
        add(base + "quantity_min", unit_count, Kind::number);
        add(base + "quantity_max", unit_count, Kind::number);
        add(base + "edge_rails_required", unit_flag, Kind::flag);
        add(base + "fiducials_required", unit_flag, Kind::flag);
        add(base + "min_ic_pitch_mm", unit_length, Kind::number);
        add(base + "min_bga_pitch_mm", unit_length, Kind::number);
    }
    add("assembly.edge_rail_min_mm", unit_length, Kind::number);
    add("assembly.fiducial.dia_mm", unit_length, Kind::number);
    add("assembly.fiducial.mask_ratio", unit_ratio, Kind::number);
    add("assembly.fiducial.edge_min_mm", unit_length, Kind::number);
    add("assembly.fiducial.count_min", unit_count, Kind::number);
    add("assembly.body_to_edge_mm", unit_length, Kind::number);
    add("assembly.cpl_point_spacing_mm", unit_length, Kind::number);
    add("assembly.max_designators_per_line", unit_designators, Kind::number);
    for (const char* pair : {"chip0402_chip0402", "chip0603_chip0603", "chip0603_qfn", "chip1206_sop", "qfn_qfn", "qfn_qfp",
                             "qfp_qfp", "sop_sop", "sot_sot", "bga_bga"})
        add(std::string("assembly.spacing_table.") + pair, unit_length, Kind::number);
    for (const char* fee : {"setup_double_side_usd", "stencil_double_side_usd", "smt_per_joint_usd", "manual_per_joint_usd",
                            "hand_soldering_labour_usd", "feeder_loading_per_part_usd"})
        add(std::string("assembly.fees.") + fee, unit_usd, Kind::number);
    add("assembly.component_height_max_mm", unit_length, Kind::number);
    add("assembly.placement_accuracy_mm", unit_length, Kind::number);
    for (const char* oz : {"1", "2"})
        for (const char* key : {"trace_mm", "space_mm", "mask_bridge_mm", "pth_annular_min_mm", "pth_annular_recommended_mm"})
            add(std::string("fab.by_copper_oz.") + oz + path_separator + key, unit_length, Kind::number);
    add("fab.hole_to_hole.via_mm", unit_length, Kind::number);
    add("fab.hole_to_hole.pad_mm", unit_length, Kind::number);
    add("fab.npth_min_mm", unit_length, Kind::number);
    add("fab.via.min_hole_mm", unit_length, Kind::number);
    add("fab.via.min_diameter_mm", unit_length, Kind::number);
    add("fab.via.diameter_over_hole_mm", unit_length, Kind::number);
    add("fab.via.diameter_over_hole_preferred_mm", unit_length, Kind::number);
    add("fab.plated_slot.width_min_mm", unit_length, Kind::number);
    add("fab.plated_slot.length_ratio_min", unit_ratio, Kind::number);
    add("fab.npth_slot_min_mm", unit_length, Kind::number);
    add("fab.copper_to_edge_mm", unit_length, Kind::number);
    add("fab.silk.text_height_min_mm", unit_length, Kind::number);
    add("fab.silk.line_min_mm", unit_length, Kind::number);
    add("fab.silk.pad_clearance_mm", unit_length, Kind::number);
    add("fab.finish.allowed", unit_text, Kind::texts);
    add("fab.finish.hasl_unsupported_from_layers", unit_layers, Kind::number);
    add("fab.copper.outer_oz_allowed", unit_oz, Kind::numbers);
    add("fab.copper.inner_oz_allowed", unit_oz, Kind::numbers);
    add("fab.copper.six_layer_two_oz_stackups", unit_text, Kind::text);
    add("order_files.bom_columns", unit_text, Kind::texts);
    add("order_files.cpl_columns", unit_text, Kind::texts);
    add("order_files.layer_tokens", unit_text, Kind::texts);
    add("order_files.coordinate_suffix", unit_text, Kind::text);
    add("order_files.rotation_direction", unit_text, Kind::text);
    add("order_files.cpl_negative_coordinates_accepted", unit_flag, Kind::flag);
    return rows;
}

std::vector<std::string> split(const std::string& path) {
    std::vector<std::string> parts;
    std::size_t begin = 0;
    for (;;) {
        const std::size_t end = path.find(path_separator, begin);
        parts.push_back(path.substr(begin, end == std::string::npos ? end : end - begin));
        if (end == std::string::npos) return parts;
        begin = end + 1;
    }
}

bool timestamp_ok(const std::string& text) {
    const std::string shape = timestamp_shape;
    if (text.size() != shape.size()) return false;
    for (std::size_t index = 0; index < shape.size(); ++index) {
        if (shape[index] == schema_digit ? !std::isdigit(static_cast<unsigned char>(text[index])) : text[index] != shape[index])
            return false;
    }
    return true;
}

bool kind_ok(const JsonNode& value, Kind kind) {
    const auto all = [&](JsonKind element) {
        return value.kind == JsonKind::Array && !value.array_value.empty() &&
               std::all_of(value.array_value.begin(), value.array_value.end(), [&](const JsonNode& item) { return item.kind == element; });
    };
    switch (kind) {
    case Kind::number: return value.kind == JsonKind::Number;
    case Kind::numbers: return all(JsonKind::Number);
    case Kind::text: return value.kind == JsonKind::String && !value.string_value.empty();
    case Kind::texts: return all(JsonKind::String);
    case Kind::flag: return value.kind == JsonKind::Bool;
    }
    return false;
}

std::string text_of(const JsonNode& node, const std::string& file, const std::string& path, const std::string& key) {
    const JsonNode* found = object_field(node, key);
    if (!found || found->kind != JsonKind::String || found->string_value.empty())
        fail(file, path, "key '" + key + "' is missing or is not a non-empty string");
    return found->string_value;
}

FabricatorValue parse_leaf(const JsonNode& node, const Row& row, const std::string& file) {
    if (node.kind != JsonKind::Object) fail(file, row.path, "must be an object holding value, unit and its source");
    const JsonNode* value = object_field(node, "value");
    if (!value) fail(file, row.path, "key 'value' is missing");
    FabricatorValue out;
    out.unit = text_of(node, file, row.path, "unit");
    if (out.unit != row.unit) fail(file, row.path, "unit '" + out.unit + "' is wrong, the key is measured in '" + row.unit + "'");
    if (value->kind == JsonKind::Null) {
        reject_unknown_keys(node, {"value", "unit", "unverified"}, file + " " + row.path);
        out.unverified = text_of(node, file, row.path, "unverified");
        return out;
    }
    reject_unknown_keys(node, {"value", "unit", "source_url", "read_utc", "quote"}, file + " " + row.path);
    if (!kind_ok(*value, row.kind)) fail(file, row.path, "value has the wrong type");
    out.value = *value;
    out.source_url = text_of(node, file, row.path, "source_url");
    out.read_utc = text_of(node, file, row.path, "read_utc");
    out.quote = text_of(node, file, row.path, "quote");
    if (!timestamp_ok(out.read_utc)) fail(file, row.path, "read_utc '" + out.read_utc + "' is not a UTC time stamp");
    return out;
}

void walk(const JsonNode& node, const std::string& prefix, const std::vector<Row>& rows, const std::string& file,
          std::map<std::string, FabricatorValue>& out) {
    std::vector<std::string> children;
    for (const Row& row : rows) {
        if (!prefix.empty() && row.path.rfind(prefix + path_separator, 0) != 0) continue;
        const std::vector<std::string> parts = split(prefix.empty() ? row.path : row.path.substr(prefix.size() + 1));
        if (std::find(children.begin(), children.end(), parts.front()) == children.end()) children.push_back(parts.front());
    }
    std::set<std::string> allowed(children.begin(), children.end());
    if (prefix.empty()) allowed.insert({"schema", "name"});
    if (node.kind != JsonKind::Object) fail(file, prefix, "must be an object");
    reject_unknown_keys(node, allowed, file + (prefix.empty() ? "" : " " + prefix));
    for (const std::string& child : children) {
        const std::string path = prefix.empty() ? child : prefix + path_separator + child;
        const JsonNode* member = object_field(node, child);
        if (!member) fail(file, path, "key is missing");
        const auto leaf = std::find_if(rows.begin(), rows.end(), [&](const Row& row) { return row.path == path; });
        if (leaf != rows.end()) out.emplace(path, parse_leaf(*member, *leaf, file));
        else walk(*member, path, rows, file, out);
    }
}

std::optional<FabricationSelection>& selection() {
    static std::optional<FabricationSelection> chosen;
    return chosen;
}

}

FabricatorProfile parse_fabricator(const JsonNode& document, const std::string& file) {
    if (document.kind != JsonKind::Object) fail(file, "", "the file must hold one object");
    if (text_of(document, file, "", "schema") != schema_name) fail(file, "", "unknown schema");
    FabricatorProfile profile;
    profile.file = file;
    profile.name = text_of(document, file, "", "name");
    walk(document, "", schema_rows(), file, profile.values);
    return profile;
}

FabricatorProfile load_fabricator(const std::filesystem::path& file) {
    if (!std::filesystem::exists(file)) throw std::runtime_error("fabricator profile not found at " + file.string());
    return parse_fabricator(parse_json_file(file.string()), file.string());
}

std::filesystem::path fabricator_file(const std::string& fabricator) {
    return std::filesystem::path(SCHGEN_FABRICATOR_DIR) / (fabricator + ".json");
}

std::string fabricator_copper_key(double oz) {
    std::ostringstream text;
    text << oz;
    return text.str();
}

const FabricatorValue& FabricatorProfile::at(const std::string& path) const {
    const auto found = values.find(path);
    if (found == values.end()) fail(file, path, "key is not in the profile");
    return found->second;
}

bool FabricatorProfile::known(const std::string& path) const { return at(path).known(); }

double FabricatorProfile::number(const std::string& path) const {
    const FabricatorValue& value = at(path);
    if (!value.known()) throw FabricatorUnverified(file + " " + path + ": UNVERIFIED: " + value.unverified);
    return value.value.number_value;
}

std::vector<double> FabricatorProfile::numbers(const std::string& path) const {
    const FabricatorValue& value = at(path);
    if (!value.known()) throw FabricatorUnverified(file + " " + path + ": UNVERIFIED: " + value.unverified);
    std::vector<double> out;
    for (const JsonNode& item : value.value.array_value) out.push_back(item.number_value);
    return out;
}

std::string FabricatorProfile::text(const std::string& path) const {
    const FabricatorValue& value = at(path);
    if (!value.known()) throw FabricatorUnverified(file + " " + path + ": UNVERIFIED: " + value.unverified);
    return value.value.string_value;
}

std::vector<std::string> FabricatorProfile::texts(const std::string& path) const {
    const FabricatorValue& value = at(path);
    if (!value.known()) throw FabricatorUnverified(file + " " + path + ": UNVERIFIED: " + value.unverified);
    std::vector<std::string> out;
    for (const JsonNode& item : value.value.array_value) out.push_back(item.string_value);
    return out;
}

bool FabricatorProfile::flag(const std::string& path) const {
    const FabricatorValue& value = at(path);
    if (!value.known()) throw FabricatorUnverified(file + " " + path + ": UNVERIFIED: " + value.unverified);
    return value.value.bool_value;
}

double FabricatorProfile::for_copper(double oz, const std::string& key) const {
    const std::string path = "fab.by_copper_oz." + fabricator_copper_key(oz) + path_separator + key;
    if (!values.count(path)) fail(file, path, "the profile publishes no rules for " + fabricator_copper_key(oz) + " oz outer copper");
    return number(path);
}

void validate_fabrication(const FabricationConfig& config, const FabricatorProfile& profile, std::size_t copper_layers,
                          double stackup_outer_oz, double stackup_inner_oz, const std::string& board) {
    const std::string where = "fabrication of board '" + board + "'";
    const auto listed = [&](const std::vector<double>& allowed, double oz) {
        return std::any_of(allowed.begin(), allowed.end(), [&](double item) { return std::fabs(item - oz) < tolerance_oz; });
    };
    if (!listed(profile.numbers("fab.copper.outer_oz_allowed"), config.outer_oz))
        fail(profile.file, where, "outer copper " + fabricator_copper_key(config.outer_oz) + " oz is not offered");
    if (!listed(profile.numbers("fab.copper.inner_oz_allowed"), config.inner_oz))
        fail(profile.file, where, "inner copper " + fabricator_copper_key(config.inner_oz) + " oz is not offered");
    if (std::fabs(stackup_outer_oz - config.outer_oz) > tolerance_oz || std::fabs(stackup_inner_oz - config.inner_oz) > tolerance_oz)
        fail(profile.file, where, "the selected stack-up is published for " + fabricator_copper_key(stackup_outer_oz) + " oz outer and " +
                                      fabricator_copper_key(stackup_inner_oz) + " oz inner copper, the run config asks for " +
                                      fabricator_copper_key(config.outer_oz) + " and " + fabricator_copper_key(config.inner_oz));
    (void)profile.for_copper(config.outer_oz, fabricator_key::trace);
    const std::vector<std::string> finishes = profile.texts("fab.finish.allowed");
    if (std::find(finishes.begin(), finishes.end(), config.finish) == finishes.end())
        fail(profile.file, where, "finish '" + config.finish + "' is not offered");
    const bool hasl = config.finish == "HASL";
    if (hasl && static_cast<double>(copper_layers) >= profile.number("fab.finish.hasl_unsupported_from_layers"))
        fail(profile.file, where, "boards of " + std::to_string(copper_layers) + " layers do not support HASL");
    const std::string service = "assembly.services." + config.assembly_service + path_separator;
    if (!profile.values.count(service + "double_sided"))
        fail(profile.file, where, "assembly service '" + config.assembly_service + "' is not in the profile");
    const double layers = static_cast<double>(copper_layers);
    if (layers < profile.number(service + "layers_min") || layers > profile.number(service + "layers_max"))
        fail(profile.file, where, "the " + config.assembly_service + " service does not take " + std::to_string(copper_layers) + " layers");
    if (config.build_count < 1) fail(profile.file, where, "build_count must be at least 1");
}

void select_fabrication(FabricationSelection chosen) { selection() = std::move(chosen); }

const FabricationSelection& board_fabrication() {
    if (!selection()) throw std::runtime_error("no fabrication profile is selected; a board is built only from an explicit configuration (schgen.json)");
    return *selection();
}

}
