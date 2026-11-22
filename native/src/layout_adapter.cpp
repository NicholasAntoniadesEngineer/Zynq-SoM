#include "schgen/layout_adapter.hpp"

#include "schgen/board_schematic.hpp"

#include "pcb_checks_internal.hpp"
#include "pcb_placement_gates_internal.hpp"
#include "schgen/mirror.hpp"
#include "schgen/pack.hpp"
#include "schgen/pcb_escape.hpp"
#include "schgen/pcb_scan.hpp"
#include "schgen/placement_integrity.hpp"
#include "schgen/quantize.hpp"
#include "schgen/roles.hpp"
#include "schgen/rules.hpp"
#include "schgen/ratsnest_gate.hpp"
#include "schgen/stackup.hpp"
#include "schgen/thermal_checks.hpp"
#include "schgen/thermal_via_planning.hpp"
#include "schgen/turn.hpp"

#include <algorithm>
#include <cmath>
#include <filesystem>
#include <map>
#include <set>
#include <tuple>

namespace schgen::layout {
namespace {

inline constexpr std::size_t first_field = 1, second_field = 2, form_field = 3;
const char* const foreign_group = "\x01layout-foreign-group";

const SexprList* as_list(const Sexpr& node) { return std::get_if<SexprList>(&node.v); }

std::string as_text(const Sexpr& node) {
    if (const auto* text = std::get_if<std::string>(&node.v)) return *text;
    if (const auto* symbol = std::get_if<Sexpr::Sym>(&node.v)) return symbol->name;
    return {};
}

const SexprList* child(const SexprList& items, std::string_view name) {
    for (const auto& item : items) {
        const auto* list = as_list(item);
        if (list && !list->empty() && as_text(list->front()) == name) return list;
    }
    return nullptr;
}

bool starts_with(const std::string& text, std::string_view head) {
    return text.size() >= head.size() && text.compare(0, head.size(), head) == 0;
}

double number_at(const SexprList& items, std::size_t index, const std::string& what) {
    if (items.size() <= index || !std::holds_alternative<double>(items[index].v))
        throw LayoutError("layout: number required for " + what);
    return std::get<double>(items[index].v);
}

std::size_t face_slot(Face face) { return face == Face::top ? 0 : 1; }

Face face_named(const std::string& side) {
    if (side == "top") return Face::top;
    if (side == "bottom") return Face::bottom;
    throw LayoutError("layout: unknown side " + side);
}

std::string side_name(Face face) { return face == Face::top ? "top" : "bottom"; }

void read_courtyard(const PcbCheckFootprint& footprint, Variant& variant) {
    const auto* root = as_list(footprint.document);
    if (!root) throw LayoutError("layout: footprint document is not a list: " + footprint.source);
    bool other_shapes = false;
    for (const auto& node : *root) {
        const auto* item = as_list(node);
        if (!item || item->empty()) continue;
        const std::string kind = as_text(item->front());
        if (!starts_with(kind, "fp_")) continue;
        const auto* layer = child(*item, "layer");
        if (!layer || layer->size() <= first_field ||
            as_text((*layer)[first_field]).find("CrtYd") == std::string::npos)
            continue;
        const auto* centre = child(*item, "center");
        const auto* rim = child(*item, "end");
        if (kind != "fp_circle" || !centre || !rim) {
            other_shapes = true;
            continue;
        }
        const double x = number_at(*centre, first_field, "circle centre");
        const double y = number_at(*centre, second_field, "circle centre");
        const double radius = std::hypot(number_at(*rim, first_field, "circle end") - x,
                                         number_at(*rim, second_field, "circle end") - y);
        variant.court_discs.push_back({{nearest_nm(x), nearest_nm(y)}, ceil_nm(radius)});
    }
    if (other_shapes || variant.court_discs.empty()) variant.court_boxes.push_back(variant.gate_box);
}

std::vector<std::string> pad_forms(const PcbCheckFootprint& footprint) {
    std::vector<std::string> forms;
    for (const auto& node : *as_list(footprint.document)) {
        const auto* item = as_list(node);
        if (item && item->size() > form_field && as_text(item->front()) == "pad")
            forms.push_back(as_text((*item)[form_field]));
    }
    if (forms.size() != footprint.pads.size())
        throw LayoutError("layout: pad list of " + footprint.source + " disagrees with its document");
    return forms;
}

Variant read_variant(const PcbCheckFootprint& footprint) {
    if (!footprint.bbox) throw LayoutError("layout: footprint has no courtyard extent: " + footprint.source);
    Variant variant;
    variant.gate_box = box_nm(footprint.bbox->x0, footprint.bbox->y0, footprint.bbox->x1, footprint.bbox->y1);
    read_courtyard(footprint, variant);
    const auto forms = pad_forms(footprint);
    const auto drilled = scan_mod_pads(footprint.document);
    if (drilled.size() != footprint.pads.size())
        throw LayoutError("layout: drill list of " + footprint.source + " disagrees with its pad list");
    for (const auto& [name, type, x, y, rotation, width, height] : footprint.pads) {
        const auto half = pad_half_extent(width, height, rotation);
        const Point centre{nearest_nm(x), nearest_nm(y)};
        const Nm reach_x = ceil_nm(half.first), reach_y = ceil_nm(half.second);
        PadShape pad;
        pad.name = name;
        pad.centre = centre;
        pad.box = {centre.x - reach_x, centre.y - reach_y, centre.x + reach_x, centre.y + reach_y};
        pad.through = type == "thru_hole" || type == "np_thru_hole";
        pad.drill = ceil_nm(std::get<6>(drilled[variant.pads.size()]));
        if (forms[variant.pads.size()] == "circle") pad.radius = ceil_nm(std::max(width, height) / 2);
        variant.pad_hull = variant.pad_hull ? united(*variant.pad_hull, pad.box) : pad.box;
        variant.pads.push_back(std::move(pad));
    }
    index_names(variant);
    return variant;
}

bool corner_mark(PartClass part_class) {
    return part_class == PartClass::mounting_hole || part_class == PartClass::fiducial;
}

Category category_of(const PcbModel& model, const PcbEmitPolicy& policy, const AdapterOptions& options,
                     const std::string& net) {
    if (net == options.plane_net) return Category::plane;
    const auto found = model.netclass_of.find(net);
    if (found != model.netclass_of.end() && found->second == policy.power_class) return Category::power;
    return Category::signal;
}

bool model_overridden(const PcbCheckInstance& instance, const PcbEmitPolicy& policy) {
    const ModelOverrideFact* found = part_fact_for(policy.model_overrides, instance.value, instance.footprint);
    return found && found->footprint == instance.footprint;
}

PcbCheckFootprintPtr mirrored_document(const PcbCheckFootprintPtr& source) {
    Sexpr mirrored = mirrored_footprint(source->document);
    const std::filesystem::path origin(source->source);
    std::string library = origin.parent_path().filename().string();
    const std::string suffix = ".pretty";
    if (library.size() >= suffix.size() &&
        library.compare(library.size() - suffix.size(), suffix.size(), suffix) == 0)
        library.resize(library.size() - suffix.size());
    const std::string path =
        (std::filesystem::path(".mirrored_fp") / (library + "__" + origin.stem().string() + ".kicad_mod")).string();
    return pcb_check_footprint(path, sexpr_dumps(mirrored) + "\n", std::move(mirrored));
}

struct Twins {
    PcbCheckFootprintPtr plain, mirrored;
};

std::map<std::string, Twins> twins_by_name(const PcbModel& model) {
    std::map<std::string, Twins> twins;
    for (const auto& instance : model.insts) {
        if (!instance.mod) throw LayoutError("layout: unresolved footprint for " + instance.ref);
        Twins& entry = twins[instance.footprint];
        if (instance.mirror) {
            if (!entry.mirrored) entry.mirrored = instance.mod;
        } else if (!entry.plain) {
            entry.plain = instance.mod;
        }
    }
    return twins;
}

PcbCheckFootprintPtr opposite_document(const PcbCheckInstance& instance, const Twins& twins) {
    if (instance.side == "bottom") return instance.mirror ? twins.plain : instance.mod;
    if (twins.mirrored) return twins.mirrored;
    try {
        return mirrored_document(instance.mod);
    } catch (const MirrorUnsupported&) {
        return nullptr;
    }
}

}

struct Translator {
    Problem& problem;
    std::string sheet;
    const std::map<std::string, std::string>& references;
    const std::map<std::string, std::size_t>& parts;
    std::string source;

    std::size_t part(const std::string& name) const {
        const auto reference = references.find(name);
        const auto found = reference == references.end() ? parts.end() : parts.find(reference->second);
        if (found == parts.end())
            throw LayoutError("layout: contract " + source + " names an unplaced part " + name);
        return found->second;
    }
    std::vector<std::size_t> names(std::size_t index, const std::vector<std::string>& pins) const {
        const auto& known = problem.footprints[problem.parts[index].footprint].top.names;
        std::vector<std::size_t> out;
        for (const auto& pin : pins) {
            const auto found = std::find(known.begin(), known.end(), pin);
            if (found == known.end())
                throw LayoutError("layout: contract " + source + " names an unknown pin " + pin);
            out.push_back(static_cast<std::size_t>(found - known.begin()));
        }
        return out;
    }
    void gap(const std::string& anchor, const std::vector<std::string>& pins, const std::string& member,
             double limit, Sense sense) const {
        const std::size_t index = part(anchor);
        problem.constraints.pad_gaps.push_back({index, part(member), names(index, pins), to_nm(limit), sense, source});
    }
    void together(const std::string& first, const std::string& second) const {
        problem.constraints.face_pairs.push_back({part(first), part(second), source});
    }
};

void translate_structure(const Translator& to, const JsonNode& contract, const JsonNode& entry) {
    using namespace placement_gates;
    const std::string type = str(entry, "type"), chip = str(entry, "ic");
    const double limit = num(entry, "max_pad_to_pin_mm");
    const bool same_side = truth(opt(entry, "same_side"));
    if (type == "hot_loop") {
        const std::size_t anchor = to.part(chip);
        std::vector<std::size_t> members;
        for (const auto& cap : strings(opt(entry, "caps"))) members.push_back(to.part(cap));
        for (const auto& pair : array(opt(entry, "pin_pairs")))
            to.problem.constraints.nearest_gaps.push_back(
                {anchor, to.names(anchor, strings(pair)), members, to_nm(limit), same_side, to.source});
    } else if (type == "bulk_in") {
        for (const auto& cap : strings(opt(entry, "caps")))
            to.gap(chip, strings(opt(entry, "vin_pins")), cap, limit, Sense::at_most);
    } else if (type == "bulk_out") {
        for (const auto& cap : strings(opt(entry, "caps"))) {
            if (same_side) to.together(cap, chip);
            to.gap(str(entry, "inductor"), {str(entry, "inductor_out_pin")}, cap, limit, Sense::at_most);
        }
    } else if (type == "sw_node") {
        to.gap(chip, {str(entry, "sw_pin")}, str(entry, "inductor"), limit, Sense::at_most);
    } else if (type == "fb_cluster") {
        const std::string foreign = str(entry, "foreign_ic"), foreign_coil = str(entry, "foreign_inductor");
        const std::string foreign_pin = str(entry, "foreign_sw_pin");
        for (const auto& member : strings(opt(entry, "members"))) {
            to.gap(chip, {str(entry, "fb_pin")}, member, num(entry, "max_to_fb_mm"), Sense::at_most);
            to.gap(chip, {str(entry, "own_sw_pin")}, member, num(entry, "min_to_own_sw_mm"), Sense::at_least);
            to.gap(str(entry, "own_inductor"), {}, member, num(entry, "min_to_own_sw_mm"), Sense::at_least);
            if (opt(entry, "foreign_ic").kind == JsonKind::Null) continue;
            if (!foreign.empty() && !foreign_pin.empty())
                to.gap(foreign, {foreign_pin}, member, num(entry, "min_to_foreign_sw_mm"), Sense::at_least);
            if (!foreign_coil.empty())
                to.gap(foreign_coil, {}, member, num(entry, "min_to_foreign_sw_mm"), Sense::at_least);
        }
    } else if (type == "boot") {
        to.gap(chip, strings(opt(entry, "pins")), str(entry, "cap"), limit, Sense::at_most);
    } else if (type == "vcc_cap" || type == "bias_cap") {
        to.gap(chip, {str(entry, "pin")}, str(entry, "cap"), limit, Sense::at_most);
    } else if (type == "rt_r") {
        to.gap(chip, {str(entry, "pin")}, str(entry, "resistor"), limit, Sense::at_most);
    } else if (type == "ldo_stage") {
        to.gap(chip, {str(entry, "cin_pin")}, str(entry, "cin"), limit, Sense::at_most);
        to.gap(chip, {str(entry, "cout_pin")}, str(entry, "cout"), limit, Sense::at_most);
    } else if (type == "proximity") {
        const std::string anchor = str(entry, "anchor");
        for (const auto& member : strings(opt(entry, "members"))) {
            to.gap(anchor, strings(opt(entry, "anchor_pins")), member, num(entry, "max_mm"), Sense::at_most);
            if (same_side) to.together(member, anchor);
            for (const auto& apart : array(opt(entry, "min_from"))) {
                const std::string pin = str(apart, "pin");
                to.gap(str(apart, "part"), pin.empty() ? std::vector<std::string>{} : std::vector<std::string>{pin},
                       member, num(apart, "min_mm"), Sense::at_least);
            }
        }
    } else if (type == "same_side") {
        for (const auto& lead : strings(opt(entry, "ics"))) {
            std::set<std::string> followers;
            for (const auto& other : array(opt(contract, "structures"))) {
                if (str(other, "type") == "same_side" || (str(other, "ic") != lead && str(other, "anchor") != lead))
                    continue;
                for (const char* key : {"cap", "inductor", "resistor", "cin", "cout"})
                    if (opt(other, key).kind != JsonKind::Null) followers.insert(str(other, key));
                for (const char* key : {"caps", "members"})
                    for (const auto& name : strings(opt(other, key))) followers.insert(name);
            }
            for (const auto& follower : followers) to.together(follower, lead);
        }
    } else {
        throw LayoutError("layout: contract " + to.source + " has an unknown structure type " + type);
    }
}

void translate_gates(const PcbModel& model, const PcbPlacementGatePolicy& gates, Problem& problem) {
    using namespace placement_gates;
    std::map<std::string, std::map<std::string, std::size_t>> parts;
    for (std::size_t index = 0; index < problem.parts.size(); ++index)
        parts[problem.parts[index].group][problem.parts[index].reference] = index;
    static const std::map<std::string, std::string> no_references;
    for (const auto& sheet : gates.wired_sheets) {
        const auto contract = gates.contracts.find(sheet);
        if (contract == gates.contracts.end()) continue;
        const auto references = gates.ref_maps.find(sheet);
        std::size_t position = 0;
        for (const auto& entry : array(opt(contract->second, "structures"))) {
            const Translator to{problem, sheet, references == gates.ref_maps.end() ? no_references : references->second,
                                parts[sheet], sheet + "/" + str(entry, "type") + "#" + std::to_string(position++)};
            translate_structure(to, contract->second, entry);
        }
    }
    for (const auto& term : check_pcb_placement_flow(PcbCheckInput(model), gates).terms) {
        if (term.advisory || (term.kind != "far" && term.kind != "near_max")) continue;
        GroupGap rule;
        rule.first = term.subject;
        rule.limit = to_nm(term.bound);
        rule.source = term.kind + " " + term.subject + " -> " + term.target;
        if (term.kind == "far") {
            rule.second = root(term.target);
            rule.measure = GroupMeasure::centre_distance;
            rule.sense = Sense::at_least;
        } else {
            rule.second_is_core = term.target == "@som";
            rule.second = rule.second_is_core ? std::string() : term.target;
        }
        problem.constraints.group_gaps.push_back(std::move(rule));
    }
}

void reserve_thermal_fields(const PcbModel& model, const PcbEmitPolicy& policy, const Placement& placement,
                            Problem& problem) {
    const ThermalCopper copper = scan_thermal_copper(render_pcb(model, policy).document, "layout");
    std::set<std::string> outer;
    for (const char* layer : {"F.Cu", "B.Cu"}) outer.insert(layer);
    for (const auto& zone : copper.zones) {
        const bool pour = zone.filled && !zone.keepout && !zone.net_name.empty() && !zone.layers.empty() &&
                          std::all_of(zone.layers.begin(), zone.layers.end(),
                                      [&](const std::string& layer) { return outer.count(layer) != 0; });
        if (!pour) continue;
        const Box box{nearest_nm(zone.bbox[0]), nearest_nm(zone.bbox[1]), nearest_nm(zone.bbox[2]), nearest_nm(zone.bbox.back())};
        if (std::any_of(problem.reserves.begin(), problem.reserves.end(),
                        [&](const Reserve& known) { return known.box == box; }))
            continue;
        problem.reserves.push_back({box, {}, zone.name});
        Reserve& reserve = problem.reserves.back();
        for (std::size_t index = 0; index < problem.parts.size(); ++index) {
            const Variant& variant = problem.footprints[problem.parts[index].footprint].on(placement[index].face);
            Box bound = placed(variant.gate_box, placement[index].at, placement[index].turn);
            if (variant.pad_hull) bound = united(bound, placed(*variant.pad_hull, placement[index].at, placement[index].turn));
            if (overlaps(bound, box)) reserve.members.push_back(index);
        }
        const std::string head = "thermal_pour_";
        if (!starts_with(zone.name, head)) continue;
        const std::string owner_name = zone.name.substr(head.size(), zone.name.rfind('_') - head.size());
        const auto owner = std::find_if(model.insts.begin(), model.insts.end(),
                                        [&](const PcbCheckInstance& instance) { return instance.ref == owner_name; });
        if (owner == model.insts.end()) throw LayoutError("layout: thermal pour " + zone.name + " names no part");
        const auto spec = thermal_copper_spec(policy, owner->value);
        if (!spec)
            throw LayoutError("layout: thermal pour " + zone.name + " has no pour rule for " + owner->value);
        const std::size_t index = static_cast<std::size_t>(owner - model.insts.begin());
        const Box4& local = spec->pour;
        reserve.pour = PourRule{index, {local.x0, local.y0, local.x1, local.y1}, policy.gnd_plane_edge_back, owner->mirror};
        if (std::find(reserve.members.begin(), reserve.members.end(), index) == reserve.members.end())
            reserve.members.push_back(index);
        if (owner->mirror != (placement[index].face == Face::bottom))
            throw LayoutError("layout: thermal pour " + zone.name + " is mirrored on a face its owner is not on");
        if (pour_box(*reserve.pour, placement[index], problem.board) != box)
            throw LayoutError("layout: thermal pour " + zone.name + " is not where its rule puts it");
    }
}

void claim_via_fields(const PcbModel& model, const PcbEmitPolicy& policy, const Placement& placement, Problem& problem) {
    const auto fields = plan_preferred_thermal_vias(model, policy, nullptr);
    if (fields.empty()) return;
    const Nm guard = problem.rules.compare_guard;
    problem.rules.via_pad = ceil_nm(policy.thermal_via_size / 2 + policy.thermal_via_clear) + guard;
    problem.rules.via_ground = ceil_nm(policy.thermal_via_drill / 2 + policy.hole_samenet_pad) + guard;
    problem.rules.via_hole = ceil_nm(policy.thermal_via_drill / 2 + policy.thermal_via_h2h) + guard;
    for (std::size_t net = 0; net < problem.nets.size(); ++net)
        if (problem.nets[net].name == thermal_ground_net()) problem.rules.via_net = static_cast<int>(net);
    for (const auto& field : fields) {
        const auto owner = std::find_if(problem.parts.begin(), problem.parts.end(),
                                        [&](const Part& part) { return part.reference == field.ref; });
        if (owner == problem.parts.end()) throw LayoutError("layout: thermal via field names no part: " + field.ref);
        const std::size_t index = static_cast<std::size_t>(owner - problem.parts.begin());
        const Pose& pose = placement[index];
        const Turn back = static_cast<Turn>((turn_count - static_cast<int>(pose.turn)) % turn_count);
        owner->via_face = pose.face;
        for (const auto& site : field.sites.chosen)
            owner->via_sites.push_back(turned(Point{nearest_nm(site.first) - pose.at.x, nearest_nm(site.second) - pose.at.y}, back));
    }
}

void mark_connectors(const PcbModel& model, const AdapterOptions& options, const Placement& placement,
                     Problem& problem) {
    std::map<std::string, PlacementMechRow> rows;
    for (const auto& row : check_placement_mech(PcbCheckInput(model)).connectors) rows[row.ref] = row;
    for (std::size_t index = 0; index < problem.parts.size(); ++index) {
        Part& part = problem.parts[index];
        const auto row = rows.find(part.reference);
        if (row == rows.end()) continue;
        if (!row->second.ok) throw LayoutError("layout: connector " + part.reference + " is not mounted at an edge");
        const auto back = static_cast<Turn>((turn_count - static_cast<int>(placement[index].turn)) % turn_count);
        part.connector = true;
        part.overmold = std::find(options.overmold_parts.begin(), options.overmold_parts.end(), row->second.mpn) !=
                        options.overmold_parts.end();
        const Point out{row->second.face_dir.first, row->second.face_dir.second};
        const Box outline = problem.board.outline();
        const Point at = placement[index].at;
        const Nm seat = out.y < 0 ? at.y - outline.y0 : out.y > 0 ? outline.y1 - at.y
                        : out.x < 0 ? at.x - outline.x0 : outline.x1 - at.x;
        const Point mouth = turned(out, back);
        const Footprint& footprint = problem.footprints[part.footprint];
        const auto across_x = footprint.flippable ? mirrors_across_x(footprint) : std::nullopt;
        part.top_only = !across_x.has_value();
        const Point rear = !across_x ? mouth : *across_x ? Point{-mouth.x, mouth.y} : Point{mouth.x, -mouth.y};
        part.edge = EdgeRule{mouth, rear, to_nm(constants::edge_reach.value), seat};
        part.top_only = part.top_only || placement[index].face == Face::top;
    }
    std::map<std::string, const PcbCheckInstance*> instances;
    for (const auto& instance : model.insts) instances[instance.ref] = &instance;
    for (Part& part : problem.parts) {
        const auto found = instances.find(part.reference);
        if (found == instances.end()) continue;
        const ConnectorFact* fact = connector_fact(model.connectors, found->second->value);
        if (!fact) continue;
        part.connector = true;
        if (fact->access) {
            part.access = to_nm(fact->access->side_mm);
            part.access_front = to_nm(fact->access->front_mm);
        }
        const auto face = mating_face_vector(*fact);
        if (face != std::pair<int, int>{0, 0}) {
            const PcbCheckInstance& instance = *found->second;
            const auto world = turn_point(face.first, instance.mirror ? -face.second : face.second, instance.rotation);
            const Point out{static_cast<Nm>(std::lround(world.first)), static_cast<Nm>(std::lround(world.second))};
            const std::size_t index = static_cast<std::size_t>(&part - problem.parts.data());
            const auto back = static_cast<Turn>((turn_count - static_cast<int>(placement[index].turn)) % turn_count);
            part.mouth = turned(out, back);
        }
        if (fact->mating && fact->mating->plug_width_mm) part.plug_width = to_nm(*fact->mating->plug_width_mm);
    }
    ConnectorRules& rules = problem.constraints.connectors;
    rules.overlap_slack = to_nm(constants::connector_overlap.value);
    rules.band_share = constants::band_share.value;
    rules.overmold_gap = to_nm(constants::overmold_gap.value);
    rules.boot_gap = to_nm(constants::boot_gap.value);
}

std::array<bool, edge_count> escape_flags(const Variant& variant, const Part& part, const Problem& problem) {
    std::vector<PcbEscapePad> pads;
    for (std::size_t name = 0; name < variant.names.size(); ++name) {
        bool connected = false, through = false, plane = false;
        for (std::size_t pad = 0; pad < variant.pads.size(); ++pad) {
            if (variant.pads[pad].name != variant.names[name]) continue;
            through = through || variant.pads[pad].through;
            if (part.pad_nets[pad] == no_net) continue;
            connected = true;
            plane = plane || problem.nets[static_cast<std::size_t>(part.pad_nets[pad])].name == pcb_ground_plane_net;
        }
        const Box& box = variant.name_boxes[name];
        pads.push_back({Box4{to_mm(box.x0), to_mm(box.y0), to_mm(box.x1), to_mm(box.y1)},
                        connected && !(through && plane)});
    }
    const Box& gate = variant.gate_box;
    const PcbEscapeSides sides = pcb_escape_sides(
        Box4{to_mm(gate.x0), to_mm(gate.y0), to_mm(gate.x1), to_mm(gate.y1)}, pads, constants::escape_tie.value);
    return {sides.north, sides.south, sides.west, sides.east};
}

std::optional<CornerRule> corner_rule(const Board& board, Point at) {
    CornerRule rule;
    rule.east = 2 * (at.x - board.origin.x) > board.width;
    rule.south = 2 * (at.y - board.origin.y) > board.height;
    const std::array<std::pair<Nm, Nm>, 2> choices{
        std::make_pair(to_nm(constants::hole_inset.value), to_nm(quantization_policy::kGridMm)),
        std::make_pair(to_nm(constants::mark_inset.value), Nm{0})};
    for (const auto& [inset, grid] : choices) {
        rule.inset = {rule.east ? -inset : inset, rule.south ? -inset : inset};
        rule.grid = grid;
        if (corner_site(board, rule) == at) return rule;
    }
    return std::nullopt;
}

namespace {

Intent resolved_intent(const Problem& problem, const Placement& placement, const AuthoredIntent& authored,
                       std::vector<std::string>& unresolved) {
    std::map<std::string, std::size_t> index;
    for (std::size_t part = 0; part < problem.parts.size(); ++part) index.emplace(problem.parts[part].reference, part);
    const auto located = [&](const std::string& reference) {
        const auto found = index.find(reference);
        if (found == index.end()) throw LayoutError("layout: " + reference + " has layout intent but is not on the board");
        return found->second;
    };
    const auto slot_of = [&](std::size_t part, const std::string& name) {
        const auto& names = problem.footprints[problem.parts[part].footprint].top.names;
        const auto found = std::find(names.begin(), names.end(), name);
        if (found == names.end())
            throw LayoutError("layout: " + problem.parts[part].reference + " has no pad named " + name);
        return static_cast<std::size_t>(found - names.begin());
    };
    const auto pads_named = [&](std::size_t part, const std::string& name) {
        const auto& pads = problem.footprints[problem.parts[part].footprint].top.pads;
        std::vector<std::size_t> found;
        for (std::size_t pad = 0; pad < pads.size(); ++pad)
            if (pads[pad].name == name) found.push_back(pad);
        return found;
    };
    const auto names_on = [&](std::size_t part, int net) {
        const Footprint& footprint = problem.footprints[problem.parts[part].footprint];
        std::vector<std::size_t> names;
        for (std::size_t pad = 0; pad < footprint.top.pads.size(); ++pad) {
            if (problem.parts[part].pad_nets[pad] != net) continue;
            const std::size_t slot = slot_of(part, footprint.top.pads[pad].name);
            if (std::find(names.begin(), names.end(), slot) == names.end()) names.push_back(slot);
        }
        return names;
    };
    Intent intent;
    for (const auto& service : authored.services) {
        const std::size_t part = located(service.part);
        Claim claim{part, 0, {}, to_nm(role_reach(service.role)), service.role};
        if (!service.owner.empty()) {
            claim.owner = located(service.owner);
            claim.names = {slot_of(claim.owner, service.pin)};
            intent.claims.push_back(std::move(claim));
            continue;
        }
        const auto pads = pads_named(part, service.via);
        if (pads.empty()) throw LayoutError("layout: " + service.part + " has no pad named " + service.via);
        const int net = problem.parts[part].pad_nets[pads.front()];
        std::vector<std::size_t> candidates;
        if (net != no_net)
            for (const auto& pin : problem.nets[static_cast<std::size_t>(net)].pins) {
                const Part& other = problem.parts[pin.part];
                const bool eligible = service.to_module
                                          ? other.module
                                          : other.group != problem.parts[part].group && other.fanout_pins > 2;
                if (pin.part != part && eligible &&
                    std::find(candidates.begin(), candidates.end(), pin.part) == candidates.end())
                    candidates.push_back(pin.part);
            }
        if (candidates.empty()) {
            unresolved.push_back(service.part);
            continue;
        }
        if (!service.to_module && candidates.size() > 1) {
            std::string names;
            for (const std::size_t candidate : candidates) names += " " + problem.parts[candidate].reference;
            throw LayoutError("layout: " + service.part + " (" + service.sheet + ") serves a net that reaches several parts on other sheets:" +
                              names + "; name the owner");
        }
        std::optional<Claim> nearest;
        Nm best = std::numeric_limits<Nm>::max();
        for (const std::size_t candidate : candidates) {
            Claim offer{part, candidate, names_on(candidate, net), claim.reach, service.role};
            const PadGap probe{offer.owner, part, offer.names, claim.reach, Sense::at_most, {}, true, true, claim.reach};
            const Nm gap = pad_gap_length(problem, probe, placement);
            if (gap < best) {
                best = gap;
                nearest = std::move(offer);
            }
        }
        intent.claims.push_back(std::move(*nearest));
    }
    for (const auto& reference : authored.released) intent.released.push_back(located(reference));
    return intent;
}

}

ModelBinding bind_model(const PcbModel& model, const PcbEmitPolicy& policy, const PcbPlacementGatePolicy* gates,
                        const AdapterOptions& options) {
    ModelBinding binding;
    Problem& problem = binding.problem;
    problem.board.origin = {to_nm(model.origin_x), to_nm(model.origin_y)};
    problem.board.width = to_nm(model.board_w);
    problem.board.height = to_nm(model.board_h);
    if (model.som_core)
        problem.board.module_core = box_nm(model.som_core->x0, model.som_core->y0,
                                           model.som_core->x1, model.som_core->y1);
    if (model.som_keepout)
        problem.board.module_body = box_nm(model.som_keepout->x0, model.som_keepout->y0,
                                           model.som_keepout->x1, model.som_keepout->y1);
    problem.rules.edge_setback = to_nm(options.edge_setback);
    problem.rules.module_clearance = to_nm(constants::module_clearance.value);
    problem.rules.module_stack_height = to_nm(constants::module_stack_height.value);
    problem.rules.tall_module_clearance = problem.rules.module_clearance;
    problem.rules.dispersion_limit = ratsnest_dispersion_max;
    problem.rules.dispersion_floor = static_cast<std::size_t>(ratsnest_small_n);

    std::map<std::string, std::size_t> net_index;
    for (const auto& instance : model.insts)
        for (const auto& [pad, net] : instance.pad_nets)
            if (!net.second.empty()) net_index.emplace(net.second, 0);
    for (auto& [name, index] : net_index) {
        index = problem.nets.size();
        const Category category = category_of(model, policy, options, name);
        const double clearance = category == Category::power ? policy.power_clearance : policy.default_clearance;
        problem.nets.push_back({name, category, to_nm(clearance), {}});
    }

    problem.rules.copper_clearance = to_nm(std::max(policy.default_clearance, policy.power_clearance));
    problem.rules.edge_clearance = to_nm(options.edge_clearance);
    problem.rules.plane_margin = to_nm(policy.gnd_plane_edge_back + constants::relief_reach.value);
    for (const auto& copper : model.copper) {
        Obstacle obstacle;
        const auto net = net_index.find(copper.net_name);
        obstacle.net = net == net_index.end() ? no_net : static_cast<int>(net->second);
        if (copper.kind == "via") {
            const Disc disc{{nearest_nm(copper.x), nearest_nm(copper.y)}, ceil_nm(copper.size / 2)};
            obstacle.disc = disc;
            obstacle.box = grown({disc.centre.x, disc.centre.y, disc.centre.x, disc.centre.y}, disc.radius);
            obstacle.top = obstacle.bottom = true;
        } else if (copper.kind == "segment") {
            const Point first{nearest_nm(copper.x1), nearest_nm(copper.y1)};
            const Point second{nearest_nm(copper.x2), nearest_nm(copper.y2)};
            obstacle.box = grown(spanning(first, second), ceil_nm(copper.width / 2));
            obstacle.top = copper.layer == "F.Cu";
            obstacle.bottom = copper.layer == "B.Cu";
        } else {
            throw LayoutError("layout: unknown fixed copper kind " + copper.kind);
        }
        problem.obstacles.push_back(obstacle);
    }

    const auto twins = twins_by_name(model);
    std::map<std::tuple<const PcbCheckFootprint*, Face, bool, bool>, std::size_t> footprint_index;
    for (const auto& instance : model.insts) {
        const Face face = face_named(instance.side);
        const bool overridden = model_overridden(instance, policy);
        const auto key = std::make_tuple(instance.mod.get(), face, instance.mirror, overridden);
        auto found = footprint_index.find(key);
        if (found == footprint_index.end()) {
            Footprint footprint;
            footprint.key = instance.footprint + "@" + side_name(face) + (instance.mirror ? "/mirrored" : "");
            std::array<PcbCheckFootprintPtr, 2> documents;
            documents[face_slot(face)] = instance.mod;
            if (!overridden)
                documents[face_slot(opposite(face))] = opposite_document(instance, twins.at(instance.footprint));
            const auto& other_document = documents[face_slot(opposite(face))];
            const Variant own = read_variant(*instance.mod);
            const Variant other = other_document ? read_variant(*other_document) : own;
            footprint.flippable = other_document != nullptr;
            footprint.top = face == Face::top ? own : other;
            footprint.bottom = face == Face::top ? other : own;
            found = footprint_index.emplace(key, problem.footprints.size()).first;
            problem.footprints.push_back(std::move(footprint));
            binding.documents.push_back(std::move(documents));
            binding.mirrors_bottom.push_back(face == Face::top || instance.mirror);
        }
        const Variant& variant = problem.footprints[found->second].on(face);
        const int pins = static_cast<int>(instance.pad_nets.size());
        const PartClass part_class = part_class_of(instance);
        const bool mezzanine = part_class == PartClass::module_connector;
        const bool foreign = pcb_counts_as_crowder(instance.ref, instance.sheet, instance.module_connector, pins,
                                                   instance.footprint, foreign_group);
        const bool own = pcb_counts_as_crowder(instance.ref, instance.sheet, instance.module_connector, pins,
                                               instance.footprint, instance.sheet);
        Part part;
        part.reference = instance.ref;
        part.group = instance.sheet;
        part.value = instance.value;
        part.footprint_name = instance.footprint;
        part.part_class = part_class;
        part.height = to_nm(part_height_of(instance).mm);
        part.footprint = found->second;
        part.fanout_pins = pins;
        const int escape_nets = pcb_escape_nets(instance);
        part.fanout_need = to_nm(pcb_escape_need(escape_nets).first);
        part.fanout_subject = !mezzanine && escape_nets >= static_cast<int>(constants::fanout_floor.value);
        part.never_crowds = !foreign;
        part.cluster_passive = foreign && !own;
        const bool controlled = !controlled_net(instance, model).empty();
        const bool drilled = drilled_part(instance);
        part.top_only = (controlled && !board_stackup().ground_referenced(true)) || presents_on_top(part_class) ||
                        (face == Face::top && drilled);
        part.core_exempt = module_clearance_exempt(instance);
        part.cohesion_member = !part.core_exempt && !instance.at_module;
        part.fixed = part.core_exempt || mezzanine;
        part.module = mezzanine;
        if (corner_mark(part_class))
            part.corner = corner_rule(problem.board, {to_nm(instance.x), to_nm(instance.y)});
        const std::size_t part_index = problem.parts.size();
        for (std::size_t pad = 0; pad < variant.pads.size(); ++pad) {
            const auto net = instance.pad_nets.find(variant.pads[pad].name);
            if (net == instance.pad_nets.end() || net->second.second.empty()) {
                part.pad_nets.push_back(no_net);
                continue;
            }
            const std::size_t index = net_index.at(net->second.second);
            part.pad_nets.push_back(static_cast<int>(index));
            problem.nets[index].pins.push_back({part_index, pad});
        }
        part.escape_top = escape_flags(problem.footprints[found->second].top, part, problem);
        part.escape_bottom = escape_flags(problem.footprints[found->second].bottom, part, problem);
        problem.parts.push_back(std::move(part));
        binding.placement.push_back({{to_nm(instance.x), to_nm(instance.y)}, turn_of(instance.rotation), face});
    }
    problem.rules.compare_guard = static_cast<Nm>(constants::compare_guard.value);
    problem.rules.group_guard = static_cast<Nm>(constants::group_guard.value);
    mark_connectors(model, options, binding.placement, problem);
    reserve_thermal_fields(model, policy, binding.placement, problem);
    claim_via_fields(model, policy, binding.placement, problem);
    if (gates) translate_gates(model, *gates, problem);
    for (std::size_t index = 0; index < model.insts.size(); ++index) {
        const auto& instance = model.insts[index];
        if (part_class_of(instance) != PartClass::module_connector) continue;
        const Box4 corridor = pcb_escape_corridor_board(*instance.mod, instance.x, instance.y, instance.rotation);
        problem.reserves.push_back({Box{nearest_nm(corridor.x0), nearest_nm(corridor.y0), nearest_nm(corridor.x1),
                                        nearest_nm(corridor.y1)},
                                    {index}, "escape corridor of " + instance.ref, false, true});
    }
    Intent intent = resolved_intent(problem, binding.placement, options.intent, binding.unresolved);
    std::vector<char> regulator(problem.parts.size(), 0), loop_inductor(problem.parts.size(), 0);
    for (const Claim& claim : intent.claims) {
        if (!rules::role_rule(claim.role).marks_regulator) continue;
        regulator[claim.owner] = 1;
        if (problem.parts[claim.part].part_class == PartClass::inductor) loop_inductor[claim.part] = 1;
    }
    for (Claim& claim : intent.claims) {
        const rules::RoleRule& role = rules::role_rule(claim.role);
        const rules::FaceDemand demand =
            rules::face_demand(role, regulator[claim.owner] != 0, loop_inductor[claim.owner] != 0,
                               problem.parts[claim.owner].module);
        claim.same_face = demand.owner_face;
        claim.or_under = demand.or_under;
        claim.first = role.protects_connector;
        if (rules::corridor_guest(role, problem.parts[claim.owner].module))
            for (Reserve& reserve : problem.reserves)
                if (!reserve.pour && reserve.members == std::vector<std::size_t>{claim.owner})
                    reserve.guests.push_back(claim.part);
        for (Reserve& reserve : problem.reserves)
            if (reserve.pour && reserve.pour->owner == claim.owner) reserve.guests.push_back(claim.part);
        Part& part = problem.parts[claim.part];
        part.field_sensitive = part.field_sensitive || role.field_sensitive;
        part.field_source = part.field_source || loop_inductor[claim.part] != 0;
    }
    derive_ownership(problem, binding.placement, hold_policy(), intent);
    validate(problem, binding.placement);
    return binding;
}

double role_reach(const std::string& role) { return rules::role_rule(role).reach->value; }

AuthoredIntent authored_intent(const PcbPlacementInput& inputs) {
    std::map<std::string, std::int64_t> bands;
    for (const auto& [sheet, band] : inputs.floorplan.sheet_index) bands.emplace(sheet, band);
    AuthoredIntent intent;
    for (const auto& sheet : inputs.floorplan.sheets) {
        if (sheet.layout.serves.empty() && sheet.layout.free.empty()) continue;
        const auto band = bands.find(sheet.name);
        if (band == bands.end()) throw LayoutError("layout: sheet " + sheet.name + " has layout intent but no band");
        const auto renamed = [&](const std::string& reference) {
            return board_renamed_ref(reference, band->second, sheet.name);
        };
        for (const auto& service : sheet.layout.serves) {
            ServiceInput entry{renamed(service.part), service.role, {}, {}, {}, sheet.name, service.target == "module"};
            if (!service.owner.ref.empty()) {
                entry.owner = renamed(service.owner.ref);
                entry.pin = service.owner.pin;
            } else {
                for (const auto& net : sheet.nets)
                    if (net.name == service.net)
                        for (const auto& pin : net.pins)
                            if (pin.ref == service.part && entry.via.empty()) entry.via = pin.pin;
                if (entry.via.empty())
                    throw LayoutError("layout: " + sheet.name + " " + service.part + " has no pin on net " + service.net);
            }
            intent.services.push_back(std::move(entry));
        }
        for (const auto& entry : sheet.layout.free) intent.released.push_back(renamed(entry.part));
        for (const auto& part : sheet.parts)
            for (const auto& name : part.pin_names)
                for (const auto& number : name.numbers) intent.pin_names[renamed(part.ref)][number] = name.name;
    }
    return intent;
}

std::set<std::string> module_served(const PcbPlacementInput& inputs) {
    std::set<std::string> references;
    for (const auto& service : authored_intent(inputs).services)
        if (service.to_module) references.insert(service.part);
    return references;
}

HoldPolicy hold_policy() {
    return {to_nm(constants::owner_reach.value), to_nm(constants::hold_slack.value),
            to_nm(constants::tether_slack.value)};
}

double project_edge_clearance(const JsonNode& project_file) {
    const JsonNode* node = &project_file;
    for (const char* key : {"board", "design_settings", "rules", "min_copper_edge_clearance"}) {
        node = object_field(*node, key);
        if (!node) throw LayoutError(std::string("layout: project file lacks ") + key);
    }
    if (node->kind != JsonKind::Number) throw LayoutError("layout: copper edge clearance is not a number");
    return node->number_value;
}

std::string GateVerdict::text() const {
    const auto word = [](bool pass) { return pass ? "pass" : "FAIL"; };
    return std::string("fanout=") + word(fanout) + " mechanical=" + word(mechanical) + " on_board=" +
           word(on_board) + " grouped=" + word(grouped) + " contracts=" + word(contracts) + " spacing=" +
           word(spacing) + " integrity=" + word(integrity);
}

GateVerdict judge_model(const PcbPlacementInput& inputs, const PcbModel& model) {
    const PcbCheckInput input(model);
    const auto ratsnest = check_ratsnest(input);
    const PlacementIntegrityResult integrity = check_placement_integrity(input, model, authored_intent(inputs));
    const ConnectorSpacingResult spacing = check_connector_spacing(input);
    const bool placed_spacing = spacing.ok_as_placed();
    return {check_fanout(input, 0).ok, check_placement_mech(input).ok, ratsnest.off_board.empty(),
            ratsnest.dispersed.empty(), check_pcb_placement_gates(inputs, model).ok(),
            spacing.ok, integrity.ok, integrity.placement_ok, placed_spacing};
}

PcbModel model_with(const PcbModel& base, const ModelBinding& binding, const Placement& placement) {
    return model_with(base, binding, placement, binding.problem.board);
}

PcbModel model_with(const PcbModel& base, const ModelBinding& binding, const Placement& placement,
                    const Board& board) {
    validate(binding.problem, placement);
    if (base.insts.size() != placement.size())
        throw LayoutError("layout: placement does not match the base model");
    PcbModel model = base;
    if (board.outline() != binding.problem.board.outline()) {
        model.origin_x = to_mm(board.origin.x);
        model.origin_y = to_mm(board.origin.y);
        model.board_w = to_mm(board.width);
        model.board_h = to_mm(board.height);
    }
    model.n_top = model.n_bottom = 0;
    for (std::size_t index = 0; index < placement.size(); ++index) {
        const Pose& pose = placement[index];
        auto& instance = model.insts[index];
        if (pose != binding.placement[index]) {
            const std::size_t footprint = binding.problem.parts[index].footprint;
            const auto& document = binding.documents[footprint][face_slot(pose.face)];
            if (!document) throw LayoutError("layout: no footprint variant for " + instance.ref);
            instance.x = to_mm(pose.at.x);
            instance.y = to_mm(pose.at.y);
            instance.rotation = degrees_of(pose.turn);
            if (pose.face != binding.placement[index].face) {
                instance.side = side_name(pose.face);
                instance.mod = document;
                instance.mirror = pose.face == Face::bottom && binding.mirrors_bottom[footprint];
            }
        }
        if (instance.side == "bottom") ++model.n_bottom;
        else ++model.n_top;
    }
    return model;
}

}
