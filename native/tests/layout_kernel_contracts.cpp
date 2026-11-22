#include "schgen/layout_json.hpp"
#include "schgen/layout_kernel.hpp"

#include <algorithm>
#include <iostream>
#include <random>
#include <string>

namespace {

using namespace schgen::layout;

namespace fixture {
constexpr Nm unit = 1000000;
constexpr Nm board_width = 100 * unit, board_height = 80 * unit;
constexpr Box module_core{40 * unit, 30 * unit, 60 * unit, 50 * unit};
constexpr Nm module_clearance = unit;
constexpr double pour_spread = 3.0;
constexpr double dispersion_limit = 9;
constexpr std::size_t dispersion_floor = 3;
constexpr Nm body_half = unit, pad_half = unit / 2, wide_half = 3 * unit;
constexpr Nm subject_need = 3 * unit / 2, passive_need = unit / 5;
constexpr int subject_pins = 3, passive_pins = 2;
constexpr Point first_site{10 * unit, 10 * unit}, crossing_site{21 * unit / 2, 10 * unit};
constexpr Point subject_site{20 * unit, 20 * unit};
constexpr Point starved_site{23 * unit, 20 * unit}, exact_site{47 * unit / 2, 20 * unit};
constexpr Point edge_site{unit / 5, 40 * unit}, core_site{50 * unit, 40 * unit};
constexpr Point cluster_first{70 * unit, 10 * unit}, cluster_second{74 * unit, 10 * unit};
constexpr Point cluster_third{70 * unit, 14 * unit}, cluster_fourth{74 * unit, 14 * unit};
constexpr Point remote_site{90 * unit, 70 * unit};
constexpr Point round_first{30 * unit, 60 * unit}, round_second{33 * unit, 63 * unit};
constexpr Nm round_radius = 2 * unit;
constexpr Nm copper_clearance = unit / 5, via_radius = 3 * unit / 10;
constexpr Point clear_site{21 * unit, 20 * unit}, margin_site{unit, 40 * unit};
constexpr Point touching_site{11 * unit, 10 * unit}, spaced_site{56 * unit / 5, 10 * unit};
constexpr Nm strip_reach = 3 * unit / 2, strip_pad = unit / 4, edge_reach = 3 * unit / 5;
constexpr Point limit_site{91 * unit / 4, 20 * unit}, inside_site{45 * unit / 2, 20 * unit};
constexpr Point outside_site{47 * unit / 2, 20 * unit}, apart_site{20 * unit, 91 * unit / 4};
constexpr Point close_site{20 * unit, 22 * unit}, beside_site{35 * unit / 2, 20 * unit};
constexpr Point north_first{30 * unit, 6 * unit / 5}, north_second{40 * unit, 6 * unit / 5};
constexpr Point inland_site{30 * unit, 3 * unit}, north_slide{20 * unit, 6 * unit / 5};
constexpr Point north_crowd{37 * unit, 6 * unit / 5};
constexpr Point order_lead{16 * unit, 20 * unit}, order_rival{13 * unit, 20 * unit}, order_past{10 * unit, 20 * unit};
constexpr Point via_site{3 * unit, 0}, via_near{24 * unit, 20 * unit}, via_clear{241 * unit / 10, 20 * unit};
constexpr Point via_mirror{16 * unit, 20 * unit};
constexpr Nm via_pad = 11 * unit / 20, via_ground = unit / 4, via_hole = 3 * unit / 5;
constexpr std::uint64_t walk_seed = 20261111;
constexpr int walk_steps = 400;
constexpr Nm walk_range = 4 * unit, walk_grid = unit / 20;
}

void require(bool condition, const std::string& what) {
    if (!condition) throw std::runtime_error("layout kernel contract failed: " + what);
}

Variant square_variant(Nm half, int pads, bool through) {
    Variant variant;
    variant.gate_box = {-half, -half, half, half};
    variant.court_boxes.push_back(variant.gate_box);
    for (int pad = 0; pad < pads; ++pad) {
        const Box box{-fixture::pad_half, -fixture::pad_half, fixture::pad_half, fixture::pad_half};
        variant.pads.push_back({std::to_string(pad + 1), {0, 0}, box, through, 0});
        variant.pad_hull = box;
    }
    index_names(variant);
    return variant;
}

Variant strip_variant() {
    Variant variant;
    variant.gate_box = {-fixture::strip_reach, -fixture::pad_half, fixture::strip_reach, fixture::pad_half};
    variant.court_boxes.push_back(variant.gate_box);
    for (const Nm x : {-fixture::unit, fixture::unit}) {
        const Box box{x - fixture::strip_pad, -fixture::strip_pad, x + fixture::strip_pad, fixture::strip_pad};
        variant.pads.push_back({std::to_string(variant.pads.size() + 1), {x, 0}, box, false, 0});
        variant.pad_hull = variant.pad_hull ? united(*variant.pad_hull, box) : box;
    }
    index_names(variant);
    return variant;
}

Variant round_variant(Nm radius) {
    Variant variant;
    variant.gate_box = {-radius, -radius, radius, radius};
    variant.court_discs.push_back({{0, 0}, radius});
    return variant;
}

struct Scene {
    Problem problem;
    Placement placement;
    Scene() {
        problem.board.width = fixture::board_width;
        problem.board.height = fixture::board_height;
        problem.rules.module_clearance = fixture::module_clearance;
        problem.rules.dispersion_limit = fixture::dispersion_limit;
        problem.rules.dispersion_floor = fixture::dispersion_floor;
    }
    std::size_t footprint(const std::string& key, const Variant& variant, bool flippable = true) {
        problem.footprints.push_back({key, flippable, variant, variant});
        return problem.footprints.size() - 1;
    }
    std::size_t net(const std::string& name, Category category) {
        problem.nets.push_back({name, category, problem.rules.copper_clearance, {}});
        return problem.nets.size() - 1;
    }
    Part& add(const std::string& reference, const std::string& group, std::size_t shape, Point at,
              Face face = Face::top) {
        Part part;
        part.reference = reference;
        part.group = group;
        part.footprint = shape;
        part.pad_nets.assign(problem.footprints[shape].top.pads.size(), no_net);
        part.fanout_pins = static_cast<int>(part.pad_nets.size());
        part.fanout_need = fixture::passive_need;
        part.escape_top.fill(true);
        part.escape_bottom.fill(true);
        problem.parts.push_back(std::move(part));
        placement.push_back({at, Turn::none, face});
        return problem.parts.back();
    }
    void connect(std::size_t net, std::size_t part) {
        problem.parts[part].pad_nets.front() = static_cast<int>(net);
        problem.nets[net].pins.push_back({part, 0});
    }
};

bool has(const std::vector<Violation>& found, Breach kind) {
    return std::any_of(found.begin(), found.end(), [&](const Violation& item) { return item.kind == kind; });
}

void courtyards_block_their_face() {
    Scene scene;
    const auto smd = scene.footprint("smd", square_variant(fixture::body_half, fixture::passive_pins, false));
    const auto pin = scene.footprint("pin", square_variant(fixture::body_half, fixture::passive_pins, true));
    scene.add("A", "one", smd, fixture::first_site);
    scene.add("B", "two", smd, fixture::crossing_site);
    require(has(Kernel(scene.problem, scene.placement).violations(), Breach::overlap), "same face overlap");
    scene.placement.back().face = Face::bottom;
    require(Kernel(scene.problem, scene.placement).violations().empty(), "opposite faces are independent");
    scene.problem.parts.front().footprint = pin;
    require(has(Kernel(scene.problem, scene.placement).violations(), Breach::overlap),
            "through-hole pads block the opposite face");
}

void round_courtyards_use_their_shape() {
    Scene scene;
    const auto round = scene.footprint("round", round_variant(fixture::round_radius));
    scene.add("H", "one", round, fixture::round_first);
    scene.add("F", "two", round, fixture::round_second);
    require(overlaps(placed(scene.problem.footprints[round].top.gate_box, fixture::round_first, Turn::none),
                     placed(scene.problem.footprints[round].top.gate_box, fixture::round_second, Turn::none)),
            "bounding boxes overlap");
    require(Kernel(scene.problem, scene.placement).violations().empty(), "discs beside each other are legal");
}

void fanout_follows_the_gate_rule() {
    Scene scene;
    const auto chip = scene.footprint("chip", square_variant(fixture::body_half, fixture::subject_pins, false));
    const auto small = scene.footprint("small", square_variant(fixture::body_half, fixture::passive_pins, false));
    Part& subject = scene.add("U", "one", chip, fixture::subject_site);
    subject.fanout_subject = true;
    subject.fanout_need = fixture::subject_need;
    scene.add("R", "two", small, fixture::starved_site);
    require(has(Kernel(scene.problem, scene.placement).violations(), Breach::fanout), "foreign part inside the need");
    scene.placement.back().at = fixture::exact_site;
    require(Kernel(scene.problem, scene.placement).violations().empty(), "gap equal to the need is legal");
    scene.placement.back().at = fixture::starved_site;
    scene.problem.parts.back().never_crowds = true;
    require(Kernel(scene.problem, scene.placement).violations().empty(), "exempt part never crowds");
    scene.problem.parts.back().never_crowds = false;
    scene.problem.parts.back().cluster_passive = true;
    require(has(Kernel(scene.problem, scene.placement).violations(), Breach::fanout),
            "another group's passive still crowds");
    scene.problem.parts.back().group = "one";
    require(Kernel(scene.problem, scene.placement).violations().empty(), "own cluster passive may sit close");
    scene.problem.parts.back().group = "two";
    scene.problem.parts.front().escape_top = {true, true, true, false};
    require(Kernel(scene.problem, scene.placement).violations().empty(), "a side without pins needs no ring");
    scene.problem.parts.front().escape_top = {false, false, false, true};
    require(has(Kernel(scene.problem, scene.placement).violations(), Breach::fanout), "a pin side keeps its ring");
}

void pours_follow_their_owner() {
    Scene scene;
    const auto smd = scene.footprint("smd", square_variant(fixture::body_half, fixture::passive_pins, false));
    scene.add("U", "one", smd, fixture::subject_site);
    const double reach = to_mm(fixture::body_half) * fixture::pour_spread;
    const PourRule rule{0, {-reach, -reach / fixture::pour_spread, reach, reach / fixture::pour_spread}, 0.0, false};
    scene.problem.reserves.push_back(
        {pour_box(rule, scene.placement.front(), scene.problem.board), {0}, "thermal_pour_U_F", true, true, rule});
    Kernel kernel(scene.problem, scene.placement);
    const Box before = kernel.reserves().front();
    const Pose swung{fixture::subject_site, Turn::quarter, Face::top};
    require(kernel.move_many({{0, swung}}), "a part with a thermal area may turn");
    require(kernel.reserves().front() == pour_box(rule, swung, scene.problem.board),
            "the thermal area is recomputed for the new orientation");
    require(kernel.reserves().front().width() == before.height() && kernel.reserves().front().height() == before.width(),
            "a quarter turn exchanges the thermal area's sides");
    Pose flipped = swung;
    flipped.face = Face::bottom;
    require(!kernel.move_many({{0, flipped}}), "a thermal area does not change face");
}

void single_part_rules_hold() {
    Scene scene;
    scene.problem.board.module_core = fixture::module_core;
    scene.problem.board.module_body = fixture::module_core;
    const auto smd = scene.footprint("smd", square_variant(fixture::body_half, fixture::passive_pins, false));
    const auto rigid = scene.footprint("rigid", square_variant(fixture::body_half, fixture::passive_pins, false), false);
    scene.add("A", "one", smd, fixture::first_site);
    scene.add("L", "one", rigid, fixture::subject_site);
    scene.add("X", "one", smd, fixture::remote_site).fixed = true;
    const Kernel kernel(scene.problem, scene.placement);
    require(kernel.violations().empty(), "starting scene is legal");
    const auto kind = [&](std::size_t part, Pose pose) {
        const auto found = kernel.rejection(part, pose);
        return found ? std::optional<Breach>(found->kind) : std::nullopt;
    };
    require(kind(0, {fixture::edge_site, Turn::none, Face::top}) == Breach::off_board, "pads leave the board");
    require(kind(0, {fixture::core_site, Turn::none, Face::top}) == Breach::module_core, "top over the module core");
    require(!kind(0, {fixture::core_site, Turn::none, Face::bottom}), "bottom under the module is free");
    const Nm beside = fixture::module_core.x0 - fixture::body_half;
    require(kind(0, {{beside - fixture::module_clearance / 2, 40 * fixture::unit}, Turn::none, Face::top}) ==
                Breach::module_core, "a top part closer to the module than its clearance is rejected");
    require(kind(0, {{beside - 2 * fixture::module_clearance, 40 * fixture::unit}, Turn::none, Face::top}) !=
                Breach::module_core, "a top part beyond the module clearance is not held by the module");
    require(kind(1, {fixture::subject_site, Turn::none, Face::bottom}) == Breach::locked, "rigid footprint cannot flip");
    require(kind(2, {fixture::first_site, Turn::none, Face::top}) == Breach::locked, "fixed part cannot move");
    scene.problem.rules.edge_clearance = fixture::body_half;
    require(Kernel(scene.problem, scene.placement).rejection(0, {fixture::margin_site, Turn::none, Face::top})->kind ==
                Breach::off_board, "pads keep the edge clearance");
    scene.problem.rules.edge_clearance = 0;
    require(!Kernel(scene.problem, scene.placement).rejection(0, {fixture::margin_site, Turn::none, Face::top}),
            "pads inside the outline are legal without an edge clearance");
    scene.problem.parts.front().top_only = true;
    require(Kernel(scene.problem, scene.placement).rejection(0, {fixture::first_site, Turn::none, Face::bottom})->kind ==
                Breach::bottom_face, "user-facing part stays on top");
    scene.problem.parts.front().top_only = false;
    scene.problem.parts.front().core_exempt = true;
    require(!Kernel(scene.problem, scene.placement).rejection(0, {fixture::core_site, Turn::none, Face::top}),
            "exempt part may sit over the core");
}

void fixed_copper_keeps_its_clearance() {
    Scene scene;
    scene.problem.rules.copper_clearance = fixture::copper_clearance;
    const auto smd = scene.footprint("smd", square_variant(fixture::body_half, fixture::passive_pins, false));
    scene.add("A", "one", smd, fixture::first_site);
    const auto ground = scene.net("ground", Category::plane);
    const auto other = scene.net("other", Category::signal);
    scene.connect(other, 0);
    const Disc via{fixture::subject_site, fixture::via_radius};
    scene.problem.obstacles.push_back({grown({via.centre.x, via.centre.y, via.centre.x, via.centre.y}, via.radius),
                                       via, true, true, static_cast<int>(ground)});
    const Kernel kernel(scene.problem, scene.placement);
    require(kernel.violations().empty(), "part away from the via is legal");
    const auto found = kernel.rejection(0, {fixture::subject_site, Turn::none, Face::bottom});
    require(found && found->kind == Breach::copper, "a foreign-net pad may not sit on a via");
    require(!kernel.rejection(0, {fixture::clear_site, Turn::none, Face::top}), "pad beyond the clearance is legal");
    scene.problem.parts.front().pad_nets.assign(scene.problem.parts.front().pad_nets.size(), static_cast<int>(ground));
    require(!Kernel(scene.problem, scene.placement).rejection(0, {fixture::subject_site, Turn::none, Face::top}),
            "a same-net pad may touch the via");
}

void pads_keep_copper_clearance() {
    Scene scene;
    scene.problem.rules.copper_clearance = fixture::copper_clearance;
    const auto pin = scene.footprint("pin", square_variant(fixture::pad_half, fixture::passive_pins, true));
    const auto smd = scene.footprint("smd", square_variant(fixture::pad_half, fixture::passive_pins, false));
    scene.add("J", "one", pin, fixture::first_site);
    scene.add("C", "two", smd, fixture::touching_site, Face::bottom);
    const auto first = scene.net("first", Category::signal);
    const auto second = scene.net("second", Category::signal);
    scene.connect(first, 0);
    scene.connect(second, 1);
    require(has(Kernel(scene.problem, scene.placement).violations(), Breach::copper),
            "a pad beside a hole on the other face breaks the clearance");
    scene.placement.back().at = fixture::spaced_site;
    require(Kernel(scene.problem, scene.placement).violations().empty(), "a pad at the clearance is legal");
    const auto plane = scene.net("plane", Category::plane);
    scene.problem.parts.front().pad_nets.back() = static_cast<int>(plane);
    scene.problem.nets[plane].pins.push_back({0, 1});
    scene.problem.rules.plane_margin = fixture::body_half;
    const Kernel margin(scene.problem, scene.placement);
    require(margin.rejection(0, {fixture::margin_site, Turn::none, Face::top})->kind == Breach::off_board,
            "a plane-net through pad keeps its relief margin from the edge");
    require(!margin.rejection(1, {fixture::margin_site, Turn::none, Face::bottom}),
            "a surface pad may sit inside the relief margin");
    scene.problem.rules.plane_margin = 0;
    scene.problem.nets[plane].pins.clear();
    scene.placement.back().at = fixture::touching_site;
    scene.problem.parts.front().pad_nets.assign(scene.problem.parts.front().pad_nets.size(), static_cast<int>(second));
    scene.problem.parts.back().pad_nets.assign(scene.problem.parts.back().pad_nets.size(), static_cast<int>(second));
    require(Kernel(scene.problem, scene.placement).violations().empty(), "same-net pads may touch");
}

void protection_leads_its_net() {
    Scene scene;
    const auto strip = scene.footprint("strip", strip_variant());
    const auto small = scene.footprint("small", square_variant(fixture::pad_half, fixture::passive_pins, false));
    scene.add("J", "one", strip, fixture::subject_site);
    scene.add("D", "one", small, fixture::order_lead);
    scene.add("U", "one", small, fixture::order_rival);
    const auto net = scene.net("VBUS", Category::signal);
    for (std::size_t part = 0; part < scene.problem.parts.size(); ++part) scene.connect(net, part);
    scene.problem.constraints.net_orders.push_back({0, 1, {0}, static_cast<int>(net), {2}, "order"});
    const Kernel kernel(scene.problem, scene.placement);
    require(kernel.violations().empty(), "a lead nearer the pin than its rival is legal");
    const auto kind = [&](std::size_t part, Point at) {
        const auto found = kernel.rejection(part, {at, Turn::none, Face::top});
        return found ? std::optional<Breach>(found->kind) : std::nullopt;
    };
    require(kind(2, fixture::beside_site) == Breach::contract, "a rival may not pass the protection part");
    require(kind(1, fixture::order_past) == Breach::contract, "the protection part may not fall behind a rival");
    require(!kind(2, fixture::order_past), "a rival may move farther from the pin");
    scene.placement[2].at = fixture::beside_site;
    require(has(Kernel(scene.problem, scene.placement).violations(), Breach::contract),
            "a rival ahead of the protection part is a violation");
}

void contract_rules_bind_pads() {
    Scene scene;
    scene.problem.rules.compare_guard = 1;
    const auto strip = scene.footprint("strip", strip_variant());
    const auto small = scene.footprint("small", square_variant(fixture::pad_half, fixture::passive_pins, false));
    scene.add("U", "one", strip, fixture::subject_site);
    scene.add("C", "one", small, fixture::limit_site);
    scene.add("R", "one", small, fixture::apart_site);
    scene.add("N", "one", small, fixture::beside_site);
    scene.add("F", "two", small, fixture::remote_site);
    Constraints& rules = scene.problem.constraints;
    rules.pad_gaps.push_back({0, 1, {1}, fixture::unit, Sense::at_most, "near"});
    rules.pad_gaps.push_back({0, 2, {}, 2 * fixture::unit, Sense::at_least, "far"});
    rules.nearest_gaps.push_back({0, {0}, {3, 4}, fixture::unit, true, "nearest"});
    rules.face_pairs.push_back({1, 0, "face"});
    const Kernel kernel(scene.problem, scene.placement);
    require(kernel.violations().empty(), "rules at their limits are legal");
    const auto kind = [&](std::size_t part, Pose pose) {
        const auto found = kernel.rejection(part, pose);
        return found ? std::optional<Breach>(found->kind) : std::nullopt;
    };
    require(kind(1, {fixture::limit_site, Turn::none, Face::top}) == Breach::contract,
            "a moved part needs the guard beyond the exact limit");
    require(!kind(1, {fixture::inside_site, Turn::none, Face::top}), "a pad inside the limit is legal");
    require(kind(1, {fixture::outside_site, Turn::none, Face::top}) == Breach::contract, "a pad beyond the limit breaks");
    require(kind(1, {fixture::inside_site, Turn::none, Face::bottom}) == Breach::contract, "paired parts share a face");
    require(kind(2, {fixture::close_site, Turn::none, Face::top}) == Breach::contract, "a part inside its keep-away breaks");
    require(kind(3, {fixture::beside_site, Turn::none, Face::bottom}) == Breach::contract,
            "the nearest same-face member must stay within reach");
    for (const auto& margin : kernel.margins()) require(margin.value >= 0, "margin of " + margin.source);
}

void subsystem_rules_bind_groups() {
    Scene scene;
    scene.problem.rules.group_guard = 1;
    const auto small = scene.footprint("small", square_variant(fixture::pad_half, fixture::passive_pins, false));
    scene.add("A", "one", small, fixture::cluster_first);
    scene.add("B", "two", small, fixture::cluster_second);
    scene.add("C", "three", small, fixture::remote_site);
    Constraints& rules = scene.problem.constraints;
    rules.group_gaps.push_back({"one", "two", false, GroupMeasure::hull_gap, 5 * fixture::unit, Sense::at_most, "near"});
    rules.group_gaps.push_back({"one", "three", false, GroupMeasure::centre_distance, 10 * fixture::unit, Sense::at_least, "far"});
    const Kernel kernel(scene.problem, scene.placement);
    require(kernel.violations().empty(), "groups within their bounds are legal");
    require(kernel.rejection(1, {fixture::remote_site, Turn::none, Face::bottom})->kind == Breach::group_bound,
            "a subsystem may not leave its neighbour");
    require(kernel.rejection(2, {fixture::cluster_third, Turn::none, Face::top})->kind == Breach::group_bound,
            "a subsystem may not approach one it must avoid");
}

void connectors_stay_at_their_edge() {
    Scene scene;
    scene.problem.constraints.connectors = {fixture::unit / 20, 18 * fixture::unit, 3 * fixture::unit, 0.5};
    const auto jack = scene.footprint("jack", square_variant(fixture::body_half, fixture::passive_pins, false));
    for (const Point site : {fixture::north_first, fixture::north_second}) {
        Part& part = scene.add("J", "one", jack, site);
        part.connector = part.overmold = true;
        part.edge = EdgeRule{{0, -1}, {0, 1}, fixture::edge_reach, fixture::north_first.y};
    }
    require(has(Kernel(scene.problem, scene.placement).violations(), Breach::connector_gap),
            "two overmolded plugs need their gap");
    scene.problem.parts.back().overmold = false;
    const Kernel kernel(scene.problem, scene.placement);
    require(kernel.violations().empty(), "a plain neighbour needs only the boot gap");
    const auto kind = [&](Pose pose) {
        const auto found = kernel.rejection(0, pose);
        return found ? std::optional<Breach>(found->kind) : std::nullopt;
    };
    require(kind({fixture::inland_site, Turn::none, Face::top}) == Breach::edge_mount, "a connector may not leave its edge");
    require(kind({fixture::north_first, Turn::half, Face::top}) == Breach::edge_mount, "the mouth must face off the board");
    require(!kind({fixture::north_slide, Turn::none, Face::top}), "a connector may slide along its edge");
    require(!kind({fixture::north_slide, Turn::half, Face::bottom}), "a connector may mount on the rear, mouth outward");
    require(kind({fixture::north_slide, Turn::none, Face::bottom}) == Breach::edge_mount,
            "a rear connector may not face inward");
    require(kind({fixture::north_crowd, Turn::none, Face::top}) == Breach::connector_gap, "sliding into the boot gap breaks");
}

void groups_stay_together() {
    Scene scene;
    const auto smd = scene.footprint("smd", square_variant(fixture::body_half, fixture::passive_pins, false));
    scene.add("A", "one", smd, fixture::cluster_first);
    scene.add("B", "one", smd, fixture::cluster_second);
    scene.add("C", "one", smd, fixture::cluster_third);
    scene.add("D", "one", smd, fixture::cluster_fourth);
    Kernel kernel(scene.problem, scene.placement);
    require(kernel.violations().empty(), "tight group is legal");
    const auto found = kernel.rejection(0, {fixture::first_site, Turn::none, Face::top});
    require(found && found->kind == Breach::dispersion, "a member may not leave its group");
    scene.placement.front().at = fixture::first_site;
    require(has(Kernel(scene.problem, scene.placement).violations(), Breach::dispersion), "dispersed group is reported");
}

Placement random_walk() {
    Scene scene;
    const auto smd = scene.footprint("smd", square_variant(fixture::body_half, fixture::passive_pins, false));
    const auto wide = scene.footprint("wide", square_variant(fixture::wide_half, fixture::passive_pins, true));
    scene.add("A", "one", smd, fixture::cluster_first);
    scene.add("B", "two", smd, fixture::cluster_second);
    scene.add("C", "three", smd, fixture::cluster_third);
    scene.add("D", "four", smd, fixture::cluster_fourth);
    scene.add("J", "five", wide, fixture::subject_site);
    const auto signal = scene.net("signal", Category::signal);
    const auto power = scene.net("power", Category::power);
    const auto plane = scene.net("plane", Category::plane);
    scene.connect(signal, 0);
    scene.connect(signal, 1);
    scene.connect(signal, 4);
    scene.connect(power, 2);
    scene.connect(power, 3);
    scene.problem.parts[1].pad_nets.back() = static_cast<int>(plane);
    scene.problem.nets[plane].pins.push_back({1, 1});
    scene.problem.parts[2].pad_nets.back() = static_cast<int>(plane);
    scene.problem.nets[plane].pins.push_back({2, 1});
    Kernel kernel(scene.problem, scene.placement);
    require(kernel.violations().empty(), "walk starts legal");
    std::mt19937_64 random(fixture::walk_seed);
    int accepted = 0;
    for (int step = 0; step < fixture::walk_steps; ++step) {
        const std::size_t part = random() % scene.problem.parts.size();
        const Nm span = 2 * fixture::walk_range / fixture::walk_grid + 1;
        const Nm dx = (static_cast<Nm>(random() % span) - span / 2) * fixture::walk_grid;
        const Nm dy = (static_cast<Nm>(random() % span) - span / 2) * fixture::walk_grid;
        Pose pose = kernel.placement()[part];
        pose.at = {pose.at.x + dx, pose.at.y + dy};
        pose.turn = static_cast<Turn>(random() % turn_count);
        if (random() % 2 == 0) pose.face = opposite(pose.face);
        if (!kernel.move(part, pose)) continue;
        ++accepted;
        kernel.verify();
        require(kernel.violations().empty(), "accepted move keeps the scene legal");
    }
    require(accepted > 0, "walk accepted some moves");
    const Wirelength measured = kernel.measured_wirelength();
    require(measured.power + measured.signal == kernel.routed_length(), "incremental airwire equals a full recompute");
    const std::string exported = document_json(scene.problem, kernel.placement());
    const Document restored = read_document(schgen::parse_json_text(exported));
    require(document_json(restored.problem, restored.placement) == exported, "export round trip is lossless");
    require(Kernel(restored.problem, restored.placement).routed_length() == kernel.routed_length(),
            "reloaded problem measures the same airwire");
    bool refused = false;
    try {
        read_document(schgen::parse_json_text("{\"schema\":\"other\"}"));
    } catch (const std::exception&) {
        refused = true;
    }
    require(refused, "foreign document is refused");
    require(measured.plane > 0, "plane net is measured but not tracked");
    return kernel.placement();
}

void walks_repeat_exactly() {
    const Placement first = random_walk(), second = random_walk();
    require(first.size() == second.size(), "walk sizes");
    for (std::size_t index = 0; index < first.size(); ++index)
        require(first[index] == second[index], "two walks with one seed agree");
}

}

void via_sites_stay_clear() {
    Scene scene;
    scene.problem.rules.via_pad = fixture::via_pad;
    scene.problem.rules.via_ground = fixture::via_ground;
    scene.problem.rules.via_hole = fixture::via_hole;
    const auto body = scene.footprint("body", square_variant(fixture::body_half, fixture::passive_pins, false));
    const auto smd = scene.footprint("smd", square_variant(fixture::pad_half, fixture::passive_pins, false));
    scene.add("U", "one", body, fixture::subject_site).via_sites.push_back(fixture::via_site);
    scene.add("C", "two", smd, fixture::via_near, Face::bottom);
    const auto signal = scene.net("signal", Category::signal);
    scene.connect(signal, 1);
    scene.problem.parts.back().pad_nets.assign(scene.problem.parts.back().pad_nets.size(), static_cast<int>(signal));
    require(has(Kernel(scene.problem, scene.placement).violations(), Breach::via_field),
            "a pad on either face inside the clearance of a planned thermal via blocks it");
    scene.placement.back().at = fixture::via_clear;
    const Kernel clear(scene.problem, scene.placement);
    require(!has(clear.violations(), Breach::via_field), "a pad at the via clearance leaves the site free");
    require(clear.rejection(1, {fixture::via_near, Turn::none, Face::bottom})->kind == Breach::via_field,
            "a part may not move onto a planned thermal via");
    scene.placement.back().at = fixture::via_near;
    scene.placement.front().turn = Turn::quarter;
    require(!has(Kernel(scene.problem, scene.placement).violations(), Breach::via_field),
            "the planned vias turn with their owner");
    scene.placement.front().turn = Turn::none;
    scene.problem.rules.via_net = static_cast<int>(signal);
    require(!has(Kernel(scene.problem, scene.placement).violations(), Breach::via_field),
            "a pad on the via net needs only the hole-to-pad distance");
    scene.problem.rules.via_net = no_net;
    scene.placement.front().face = Face::bottom;
    require(!has(Kernel(scene.problem, scene.placement).violations(), Breach::via_field),
            "the planned vias mirror with their owner when it goes to the rear");
    scene.placement.back().at = fixture::via_mirror;
    require(has(Kernel(scene.problem, scene.placement).violations(), Breach::via_field),
            "a pad at the mirrored site blocks it from either face");
}

int main() {
    try {
        courtyards_block_their_face();
        round_courtyards_use_their_shape();
        fanout_follows_the_gate_rule();
        pours_follow_their_owner();
    single_part_rules_hold();
        fixed_copper_keeps_its_clearance();
        pads_keep_copper_clearance();
        contract_rules_bind_pads();
        protection_leads_its_net();
        subsystem_rules_bind_groups();
        connectors_stay_at_their_edge();
        groups_stay_together();
        via_sites_stay_clear();
        walks_repeat_exactly();
        std::cout << "layout kernel contracts ok\n";
        return 0;
    } catch (const std::exception& error) {
        std::cerr << error.what() << "\n";
        return 1;
    }
}
