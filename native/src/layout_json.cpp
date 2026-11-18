#include "schgen/layout_json.hpp"

#include "schgen/json_text.hpp"

#include <cmath>

namespace schgen::layout {
namespace {

using json_text::array;
using json_text::boolean;
using json_text::integer;
using json_text::object;
using json_text::text_value;

const char* const schema_name = "schgen.layout-problem/5";
inline constexpr std::size_t point_fields = 2, disc_fields = 3, box_fields = 4;

std::string point_json(Point point) { return array({integer(point.x), integer(point.y)}); }

std::string box_json(Box box) {
    return array({integer(box.x0), integer(box.y0), integer(box.x1), integer(box.y1)});
}

std::string disc_json(Disc disc) {
    return array({integer(disc.centre.x), integer(disc.centre.y), integer(disc.radius)});
}

const char* category_name(Category category) {
    switch (category) {
    case Category::plane: return "plane";
    case Category::power: return "power";
    case Category::signal: break;
    }
    return "signal";
}

std::string variant_json(const Variant& variant) {
    std::vector<std::string> boxes, discs, pads;
    for (const auto& box : variant.court_boxes) boxes.push_back(box_json(box));
    for (const auto& disc : variant.court_discs) discs.push_back(disc_json(disc));
    for (const auto& pad : variant.pads)
        pads.push_back(object({{"name", text_value(pad.name)},
                               {"centre", point_json(pad.centre)},
                               {"box", box_json(pad.box)},
                               {"through", boolean(pad.through)},
                               {"radius", integer(pad.radius)}}));
    return object({{"gate_box", box_json(variant.gate_box)},
                   {"court_boxes", array(boxes)},
                   {"court_discs", array(discs)},
                   {"pads", array(pads)}});
}

const JsonNode& field(const JsonNode& node, const std::string& key, JsonKind kind) {
    const JsonNode* value = object_field(node, key);
    if (!value || value->kind != kind) throw LayoutError("layout: field " + key + " is missing or has the wrong type");
    return *value;
}

Nm whole(const JsonNode& node) {
    if (node.kind != JsonKind::Number || node.number_value != std::round(node.number_value) ||
        std::fabs(node.number_value) > constants::span_limit.value * constants::span_limit.value)
        throw LayoutError("layout: whole number required");
    return static_cast<Nm>(node.number_value);
}

const std::vector<JsonNode>& row(const JsonNode& node, std::size_t size) {
    if (node.kind != JsonKind::Array || node.array_value.size() != size)
        throw LayoutError("layout: array of " + std::to_string(size) + " numbers required");
    return node.array_value;
}

Point point_of(const JsonNode& node) {
    const auto& values = row(node, point_fields);
    return {whole(values.front()), whole(values.back())};
}

Box box_of(const JsonNode& node) {
    const auto& values = row(node, box_fields);
    return {whole(values[0]), whole(values[1]), whole(values[2]), whole(values.back())};
}

Disc disc_of(const JsonNode& node) {
    const auto& values = row(node, disc_fields);
    return {{whole(values[0]), whole(values[1])}, whole(values.back())};
}

bool flag(const JsonNode& node, const std::string& key) { return field(node, key, JsonKind::Bool).bool_value; }

std::string text(const JsonNode& node, const std::string& key) {
    return field(node, key, JsonKind::String).string_value;
}

Variant variant_of(const JsonNode& node) {
    reject_unknown_keys(node, {"gate_box", "court_boxes", "court_discs", "pads"}, "layout variant");
    Variant variant;
    variant.gate_box = box_of(field(node, "gate_box", JsonKind::Array));
    for (const auto& entry : field(node, "court_boxes", JsonKind::Array).array_value)
        variant.court_boxes.push_back(box_of(entry));
    for (const auto& entry : field(node, "court_discs", JsonKind::Array).array_value)
        variant.court_discs.push_back(disc_of(entry));
    for (const auto& entry : field(node, "pads", JsonKind::Array).array_value) {
        reject_unknown_keys(entry, {"name", "centre", "box", "through", "radius"}, "layout pad");
        PadShape pad{text(entry, "name"), point_of(field(entry, "centre", JsonKind::Array)),
                     box_of(field(entry, "box", JsonKind::Array)), flag(entry, "through"),
                     whole(field(entry, "radius", JsonKind::Number))};
        variant.pad_hull = variant.pad_hull ? united(*variant.pad_hull, pad.box) : pad.box;
        variant.pads.push_back(std::move(pad));
    }
    index_names(variant);
    return variant;
}

Category category_of(const std::string& name) {
    if (name == "plane") return Category::plane;
    if (name == "power") return Category::power;
    if (name == "signal") return Category::signal;
    throw LayoutError("layout: unknown net category " + name);
}

Face face_of(const std::string& name) {
    if (name == "top") return Face::top;
    if (name == "bottom") return Face::bottom;
    throw LayoutError("layout: unknown face " + name);
}

std::string flags_json(const std::array<bool, edge_count>& flags) {
    std::vector<std::string> items;
    for (const bool flag : flags) items.push_back(boolean(flag));
    return array(items);
}

std::array<bool, edge_count> flags_of(const JsonNode& node) {
    if (node.array_value.size() != edge_count) throw LayoutError("layout: escape flags need one entry per side");
    std::array<bool, edge_count> flags{};
    for (std::size_t side = 0; side < edge_count; ++side) {
        if (node.array_value[side].kind != JsonKind::Bool) throw LayoutError("layout: escape flag is not a boolean");
        flags[side] = node.array_value[side].bool_value;
    }
    return flags;
}

std::string indices_json(const std::vector<std::size_t>& values) {
    std::vector<std::string> rows;
    for (const std::size_t value : values) rows.push_back(integer(static_cast<long long>(value)));
    return array(rows);
}

std::vector<std::size_t> indices_of(const JsonNode& node) {
    if (node.kind != JsonKind::Array) throw LayoutError("layout: index list required");
    std::vector<std::size_t> out;
    for (const auto& entry : node.array_value) {
        const Nm value = whole(entry);
        if (value < 0) throw LayoutError("layout: negative index");
        out.push_back(static_cast<std::size_t>(value));
    }
    return out;
}

std::size_t index_of(const JsonNode& node, const std::string& key) {
    const Nm value = whole(field(node, key, JsonKind::Number));
    if (value < 0) throw LayoutError("layout: negative index in " + key);
    return static_cast<std::size_t>(value);
}

const char* sense_name(Sense sense) { return sense == Sense::at_most ? "at_most" : "at_least"; }

Sense sense_of(const std::string& name) {
    if (name == "at_most") return Sense::at_most;
    if (name == "at_least") return Sense::at_least;
    throw LayoutError("layout: unknown bound sense " + name);
}

std::string constraints_json(const Constraints& rules) {
    std::vector<std::string> pad_gaps, soft_gaps, nearest_gaps, face_pairs, group_gaps;
    const auto gap_json = [](const PadGap& rule) {
        return object({{"anchor", integer(static_cast<long long>(rule.anchor))},
                       {"member", integer(static_cast<long long>(rule.member))},
                       {"anchor_names", indices_json(rule.anchor_names)},
                       {"limit", integer(rule.limit)},
                       {"sense", text_value(sense_name(rule.sense))},
                       {"source", text_value(rule.source)},
                       {"rigid", boolean(rule.rigid)},
                       {"derived", boolean(rule.derived)},
                       {"reach", integer(rule.reach)}});
    };
    for (const auto& rule : rules.pad_gaps) pad_gaps.push_back(gap_json(rule));
    for (const auto& rule : rules.soft_gaps) soft_gaps.push_back(gap_json(rule));
    for (const auto& rule : rules.nearest_gaps)
        nearest_gaps.push_back(object({{"anchor", integer(static_cast<long long>(rule.anchor))},
                                       {"anchor_names", indices_json(rule.anchor_names)},
                                       {"members", indices_json(rule.members)},
                                       {"limit", integer(rule.limit)},
                                       {"same_face", boolean(rule.same_face)},
                                       {"source", text_value(rule.source)}}));
    for (const auto& rule : rules.face_pairs)
        face_pairs.push_back(object({{"first", integer(static_cast<long long>(rule.first))},
                                     {"second", integer(static_cast<long long>(rule.second))},
                                     {"source", text_value(rule.source)}}));
    for (const auto& rule : rules.group_gaps)
        group_gaps.push_back(object({{"first", text_value(rule.first)},
                                     {"second", text_value(rule.second)},
                                     {"second_is_core", boolean(rule.second_is_core)},
                                     {"measure", text_value(rule.measure == GroupMeasure::hull_gap ? "hull_gap" : "centre_distance")},
                                     {"limit", integer(rule.limit)},
                                     {"sense", text_value(sense_name(rule.sense))},
                                     {"source", text_value(rule.source)}}));
    return object({{"pad_gaps", array(pad_gaps)},
                   {"soft_gaps", array(soft_gaps)},
                   {"nearest_gaps", array(nearest_gaps)},
                   {"face_pairs", array(face_pairs)},
                   {"group_gaps", array(group_gaps)},
                   {"connectors", object({{"overlap_slack", integer(rules.connectors.overlap_slack)},
                                          {"overmold_gap", integer(rules.connectors.overmold_gap)},
                                          {"boot_gap", integer(rules.connectors.boot_gap)},
                                          {"band_share", json_text::number(rules.connectors.band_share)}})}});
}

Constraints constraints_of(const JsonNode& node) {
    reject_unknown_keys(node, {"pad_gaps", "soft_gaps", "nearest_gaps", "face_pairs", "group_gaps", "connectors"},
                        "layout constraints");
    Constraints rules;
    const auto gap_of = [](const JsonNode& entry) {
        reject_unknown_keys(entry, {"anchor", "member", "anchor_names", "limit", "sense", "source", "rigid", "derived", "reach"},
                            "layout pad gap");
        return PadGap{index_of(entry, "anchor"), index_of(entry, "member"),
                      indices_of(field(entry, "anchor_names", JsonKind::Array)),
                      whole(field(entry, "limit", JsonKind::Number)), sense_of(text(entry, "sense")),
                      text(entry, "source"), flag(entry, "rigid"), flag(entry, "derived"),
                      whole(field(entry, "reach", JsonKind::Number))};
    };
    for (const auto& entry : field(node, "pad_gaps", JsonKind::Array).array_value) rules.pad_gaps.push_back(gap_of(entry));
    for (const auto& entry : field(node, "soft_gaps", JsonKind::Array).array_value) rules.soft_gaps.push_back(gap_of(entry));
    for (const auto& entry : field(node, "nearest_gaps", JsonKind::Array).array_value) {
        reject_unknown_keys(entry, {"anchor", "anchor_names", "members", "limit", "same_face", "source"},
                            "layout nearest gap");
        rules.nearest_gaps.push_back({index_of(entry, "anchor"),
                                      indices_of(field(entry, "anchor_names", JsonKind::Array)),
                                      indices_of(field(entry, "members", JsonKind::Array)),
                                      whole(field(entry, "limit", JsonKind::Number)), flag(entry, "same_face"),
                                      text(entry, "source")});
    }
    for (const auto& entry : field(node, "face_pairs", JsonKind::Array).array_value) {
        reject_unknown_keys(entry, {"first", "second", "source"}, "layout face pair");
        rules.face_pairs.push_back({index_of(entry, "first"), index_of(entry, "second"), text(entry, "source")});
    }
    for (const auto& entry : field(node, "group_gaps", JsonKind::Array).array_value) {
        reject_unknown_keys(entry, {"first", "second", "second_is_core", "measure", "limit", "sense", "source"},
                            "layout group gap");
        const std::string measure = text(entry, "measure");
        if (measure != "hull_gap" && measure != "centre_distance") throw LayoutError("layout: unknown group measure " + measure);
        rules.group_gaps.push_back({text(entry, "first"), text(entry, "second"), flag(entry, "second_is_core"),
                                    measure == "hull_gap" ? GroupMeasure::hull_gap : GroupMeasure::centre_distance,
                                    whole(field(entry, "limit", JsonKind::Number)), sense_of(text(entry, "sense")),
                                    text(entry, "source")});
    }
    const JsonNode& connectors = field(node, "connectors", JsonKind::Object);
    reject_unknown_keys(connectors, {"overlap_slack", "overmold_gap", "boot_gap", "band_share"}, "layout connector rules");
    rules.connectors.overlap_slack = whole(field(connectors, "overlap_slack", JsonKind::Number));
    rules.connectors.overmold_gap = whole(field(connectors, "overmold_gap", JsonKind::Number));
    rules.connectors.boot_gap = whole(field(connectors, "boot_gap", JsonKind::Number));
    rules.connectors.band_share = field(connectors, "band_share", JsonKind::Number).number_value;
    return rules;
}

}

std::string document_json(const Problem& problem, const Placement& placement) {
    validate(problem, placement);
    std::vector<std::string> nets, footprints, parts, poses;
    for (const auto& net : problem.nets)
        nets.push_back(object({{"name", text_value(net.name)},
                               {"category", text_value(category_name(net.category))},
                               {"clearance", integer(net.clearance)}}));
    for (const auto& footprint : problem.footprints)
        footprints.push_back(object({{"key", text_value(footprint.key)},
                                     {"flippable", boolean(footprint.flippable)},
                                     {"top", variant_json(footprint.top)},
                                     {"bottom", variant_json(footprint.bottom)}}));
    for (const auto& part : problem.parts) {
        std::vector<std::string> pad_nets;
        for (const int net : part.pad_nets) pad_nets.push_back(integer(net));
        parts.push_back(object({{"reference", text_value(part.reference)},
                                {"group", text_value(part.group)},
                                {"value", text_value(part.value)},
                                {"footprint_name", text_value(part.footprint_name)},
                                {"footprint", integer(static_cast<long long>(part.footprint))},
                                {"pad_nets", array(pad_nets)},
                                {"fanout_pins", integer(part.fanout_pins)},
                                {"fanout_need", integer(part.fanout_need)},
                                {"fanout_subject", boolean(part.fanout_subject)},
                                {"escape_top", flags_json(part.escape_top)},
                                {"escape_bottom", flags_json(part.escape_bottom)},
                                {"never_crowds", boolean(part.never_crowds)},
                                {"cluster_passive", boolean(part.cluster_passive)},
                                {"fixed", boolean(part.fixed)},
                                {"top_only", boolean(part.top_only)},
                                {"core_exempt", boolean(part.core_exempt)},
                                {"cohesion_member", boolean(part.cohesion_member)},
                                {"module", boolean(part.module)},
                                {"tie", text_value(tie_name(problem.ownership.empty() ? Tie::none : problem.ownership[parts.size()].tie))},
                                {"owner", integer(problem.ownership.empty() || !problem.ownership[parts.size()].owner
                                                      ? -1 : static_cast<long long>(*problem.ownership[parts.size()].owner))},
                                {"connector", boolean(part.connector)},
                                {"overmold", boolean(part.overmold)},
                                {"edge", part.edge ? object({{"mouth", point_json(part.edge->mouth)},
                                                             {"rear_mouth", point_json(part.edge->rear_mouth)},
                                                             {"reach", integer(part.edge->reach)},
                                                             {"seat", integer(part.edge->seat)}})
                                                   : "null"},
                                {"corner", part.corner ? object({{"east", boolean(part.corner->east)},
                                                                 {"south", boolean(part.corner->south)},
                                                                 {"inset", point_json(part.corner->inset)},
                                                                 {"grid", integer(part.corner->grid)}})
                                                       : "null"}}));
    }
    for (const auto& pose : placement)
        poses.push_back(object({{"at", point_json(pose.at)},
                                {"turn", integer(static_cast<int>(pose.turn))},
                                {"face", text_value(pose.face == Face::top ? "top" : "bottom")}}));
    std::vector<std::string> obstacles;
    for (const auto& obstacle : problem.obstacles)
        obstacles.push_back(object({{"box", box_json(obstacle.box)},
                                    {"disc", obstacle.disc ? disc_json(*obstacle.disc) : "null"},
                                    {"top", boolean(obstacle.top)},
                                    {"bottom", boolean(obstacle.bottom)},
                                    {"net", integer(obstacle.net)}}));
    std::vector<std::string> reserves;
    for (const auto& reserve : problem.reserves)
        reserves.push_back(object({{"box", box_json(reserve.box)},
                                   {"members", indices_json(reserve.members)},
                                   {"source", text_value(reserve.source)},
                                   {"top", boolean(reserve.top)},
                                   {"bottom", boolean(reserve.bottom)}}));
    const Board& board = problem.board;
    return json_text::pretty(object({
        {"schema", text_value(schema_name)},
        {"unit", text_value("nm")},
        {"board", object({{"origin", point_json(board.origin)},
                          {"width", integer(board.width)},
                          {"height", integer(board.height)},
                          {"module_core", board.module_core ? box_json(*board.module_core) : "null"},
                          {"module_body", board.module_body ? box_json(*board.module_body) : "null"}})},
        {"rules", object({{"compare_guard", integer(problem.rules.compare_guard)},
                          {"group_guard", integer(problem.rules.group_guard)},
                          {"core_tolerance", integer(problem.rules.core_tolerance)},
                          {"copper_clearance", integer(problem.rules.copper_clearance)},
                          {"edge_clearance", integer(problem.rules.edge_clearance)},
                          {"edge_setback", integer(problem.rules.edge_setback)},
                          {"plane_margin", integer(problem.rules.plane_margin)},
                          {"dispersion_limit", json_text::number(problem.rules.dispersion_limit)},
                          {"dispersion_floor", integer(static_cast<long long>(problem.rules.dispersion_floor))}})},
        {"nets", array(nets)},
        {"footprints", array(footprints)},
        {"parts", array(parts)},
        {"obstacles", array(obstacles)},
        {"reserves", array(reserves)},
        {"constraints", constraints_json(problem.constraints)},
        {"placement", array(poses)}}));
}

Document read_document(const JsonNode& root) {
    reject_unknown_keys(root, {"schema", "unit", "board", "rules", "nets", "footprints", "parts", "obstacles",
                               "reserves", "constraints", "placement"},
                        "layout document");
    if (text(root, "schema") != schema_name || text(root, "unit") != "nm")
        throw LayoutError("layout: unsupported document schema or unit");
    Document document;
    Problem& problem = document.problem;
    const JsonNode& board = field(root, "board", JsonKind::Object);
    reject_unknown_keys(board, {"origin", "width", "height", "module_core", "module_body"}, "layout board");
    problem.board.origin = point_of(field(board, "origin", JsonKind::Array));
    problem.board.width = whole(field(board, "width", JsonKind::Number));
    problem.board.height = whole(field(board, "height", JsonKind::Number));
    const JsonNode* core = object_field(board, "module_core");
    if (!core) throw LayoutError("layout: field module_core is missing");
    if (core->kind != JsonKind::Null) problem.board.module_core = box_of(*core);
    const JsonNode* body = object_field(board, "module_body");
    if (!body) throw LayoutError("layout: field module_body is missing");
    if (body->kind != JsonKind::Null) problem.board.module_body = box_of(*body);
    const JsonNode& rules = field(root, "rules", JsonKind::Object);
    reject_unknown_keys(rules, {"compare_guard", "group_guard", "core_tolerance", "copper_clearance",
                                "edge_clearance", "edge_setback", "plane_margin", "dispersion_limit",
                                "dispersion_floor"},
                        "layout rules");
    problem.rules.compare_guard = whole(field(rules, "compare_guard", JsonKind::Number));
    problem.rules.group_guard = whole(field(rules, "group_guard", JsonKind::Number));
    problem.rules.copper_clearance = whole(field(rules, "copper_clearance", JsonKind::Number));
    problem.rules.edge_clearance = whole(field(rules, "edge_clearance", JsonKind::Number));
    problem.rules.edge_setback = whole(field(rules, "edge_setback", JsonKind::Number));
    problem.rules.plane_margin = whole(field(rules, "plane_margin", JsonKind::Number));
    problem.rules.core_tolerance = whole(field(rules, "core_tolerance", JsonKind::Number));
    problem.rules.dispersion_limit = field(rules, "dispersion_limit", JsonKind::Number).number_value;
    problem.rules.dispersion_floor = static_cast<std::size_t>(whole(field(rules, "dispersion_floor", JsonKind::Number)));
    for (const auto& entry : field(root, "nets", JsonKind::Array).array_value) {
        reject_unknown_keys(entry, {"name", "category", "clearance"}, "layout net");
        problem.nets.push_back({text(entry, "name"), category_of(text(entry, "category")),
                                whole(field(entry, "clearance", JsonKind::Number)), {}});
    }
    for (const auto& entry : field(root, "footprints", JsonKind::Array).array_value) {
        reject_unknown_keys(entry, {"key", "flippable", "top", "bottom"}, "layout footprint");
        problem.footprints.push_back({text(entry, "key"), flag(entry, "flippable"),
                                      variant_of(field(entry, "top", JsonKind::Object)),
                                      variant_of(field(entry, "bottom", JsonKind::Object))});
    }
    for (const auto& entry : field(root, "parts", JsonKind::Array).array_value) {
        reject_unknown_keys(entry, {"reference", "group", "value", "footprint_name", "footprint", "pad_nets",
                                    "fanout_pins", "fanout_need", "fanout_subject", "escape_top",
                                    "escape_bottom", "never_crowds",
                                    "cluster_passive", "fixed", "top_only", "core_exempt", "cohesion_member", "module",
                                    "connector", "overmold", "edge", "corner", "tie", "owner"},
                            "layout part");
        Part part;
        part.reference = text(entry, "reference");
        part.group = text(entry, "group");
        part.value = text(entry, "value");
        part.footprint_name = text(entry, "footprint_name");
        part.footprint = static_cast<std::size_t>(whole(field(entry, "footprint", JsonKind::Number)));
        part.fanout_pins = static_cast<int>(whole(field(entry, "fanout_pins", JsonKind::Number)));
        part.fanout_need = whole(field(entry, "fanout_need", JsonKind::Number));
        part.fanout_subject = flag(entry, "fanout_subject");
        part.escape_top = flags_of(field(entry, "escape_top", JsonKind::Array));
        part.escape_bottom = flags_of(field(entry, "escape_bottom", JsonKind::Array));
        part.never_crowds = flag(entry, "never_crowds");
        part.cluster_passive = flag(entry, "cluster_passive");
        part.fixed = flag(entry, "fixed");
        part.top_only = flag(entry, "top_only");
        part.core_exempt = flag(entry, "core_exempt");
        part.cohesion_member = flag(entry, "cohesion_member");
        part.module = flag(entry, "module");
        Ownership ownership;
        const std::string tie = text(entry, "tie");
        for (const Tie candidate : {Tie::none, Tie::contract, Tie::authored, Tie::released, Tie::signal, Tie::rail, Tie::shared, Tie::bridge,
                                    Tie::unattached})
            if (tie == tie_name(candidate)) ownership.tie = candidate;
        if (tie != tie_name(ownership.tie)) throw LayoutError("layout: unknown ownership tie " + tie);
        const Nm owner = whole(field(entry, "owner", JsonKind::Number));
        if (owner >= 0) ownership.owner = static_cast<std::size_t>(owner);
        problem.ownership.push_back(ownership);
        part.connector = flag(entry, "connector");
        part.overmold = flag(entry, "overmold");
        const JsonNode* edge = object_field(entry, "edge");
        if (!edge) throw LayoutError("layout: field edge is missing");
        if (edge->kind != JsonKind::Null) {
            reject_unknown_keys(*edge, {"mouth", "rear_mouth", "reach", "seat"}, "layout edge rule");
            part.edge = EdgeRule{point_of(field(*edge, "mouth", JsonKind::Array)),
                                 point_of(field(*edge, "rear_mouth", JsonKind::Array)),
                                 whole(field(*edge, "reach", JsonKind::Number)),
                                 whole(field(*edge, "seat", JsonKind::Number))};
        }
        const JsonNode* corner = object_field(entry, "corner");
        if (!corner) throw LayoutError("layout: field corner is missing");
        if (corner->kind != JsonKind::Null) {
            reject_unknown_keys(*corner, {"east", "south", "inset", "grid"}, "layout corner rule");
            part.corner = CornerRule{flag(*corner, "east"), flag(*corner, "south"),
                                     point_of(field(*corner, "inset", JsonKind::Array)),
                                     whole(field(*corner, "grid", JsonKind::Number))};
        }
        const std::size_t index = problem.parts.size();
        for (const auto& net : field(entry, "pad_nets", JsonKind::Array).array_value) {
            const Nm value = whole(net);
            if (value != no_net && (value < 0 || static_cast<std::size_t>(value) >= problem.nets.size()))
                throw LayoutError("layout: part " + part.reference + " names no net");
            if (value != no_net)
                problem.nets[static_cast<std::size_t>(value)].pins.push_back({index, part.pad_nets.size()});
            part.pad_nets.push_back(static_cast<int>(value));
        }
        problem.parts.push_back(std::move(part));
    }
    for (const auto& entry : field(root, "obstacles", JsonKind::Array).array_value) {
        reject_unknown_keys(entry, {"box", "disc", "top", "bottom", "net"}, "layout obstacle");
        Obstacle obstacle;
        obstacle.box = box_of(field(entry, "box", JsonKind::Array));
        const JsonNode* disc = object_field(entry, "disc");
        if (!disc) throw LayoutError("layout: field disc is missing");
        if (disc->kind != JsonKind::Null) obstacle.disc = disc_of(*disc);
        obstacle.top = flag(entry, "top");
        obstacle.bottom = flag(entry, "bottom");
        const Nm net = whole(field(entry, "net", JsonKind::Number));
        if (net != no_net && (net < 0 || static_cast<std::size_t>(net) >= problem.nets.size()))
            throw LayoutError("layout: obstacle names no net");
        obstacle.net = static_cast<int>(net);
        problem.obstacles.push_back(obstacle);
    }
    for (const auto& entry : field(root, "reserves", JsonKind::Array).array_value) {
        reject_unknown_keys(entry, {"box", "members", "source", "top", "bottom"}, "layout reserve");
        problem.reserves.push_back({box_of(field(entry, "box", JsonKind::Array)),
                                    indices_of(field(entry, "members", JsonKind::Array)), text(entry, "source"),
                                    flag(entry, "top"), flag(entry, "bottom")});
    }
    problem.constraints = constraints_of(field(root, "constraints", JsonKind::Object));
    for (const auto& entry : field(root, "placement", JsonKind::Array).array_value) {
        reject_unknown_keys(entry, {"at", "turn", "face"}, "layout pose");
        const Nm turn = whole(field(entry, "turn", JsonKind::Number));
        if (turn < 0 || turn >= turn_count) throw LayoutError("layout: turn out of range");
        document.placement.push_back({point_of(field(entry, "at", JsonKind::Array)), static_cast<Turn>(turn),
                                      face_of(text(entry, "face"))});
    }
    validate(problem, document.placement);
    return document;
}

}
