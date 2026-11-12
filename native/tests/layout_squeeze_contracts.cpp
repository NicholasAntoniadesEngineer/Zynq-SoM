#include "schgen/layout_sink.hpp"
#include "schgen/layout_squeeze.hpp"

#include <iostream>
#include <string>

namespace {

using namespace schgen::layout;

namespace fixture {
constexpr Nm unit = 1000000;
constexpr Nm board_width = 40 * unit, board_height = 30 * unit;
constexpr Nm edge_clearance = 3 * unit / 10, edge_setback = unit / 2, copper_clearance = unit / 5;
constexpr Nm pad_half = unit / 2, cap_half = unit, plug_half = 2 * unit, post_half = 2 * unit;
constexpr Nm wall_half = unit, wall_reach = 29 * unit / 2, hole_radius = unit;
constexpr Nm plug_reach = 3 * unit / 5, plug_seat = 11 * unit / 5, bond_limit = 3 * unit;
constexpr Point wall_site{20 * unit, 15 * unit}, plug_site{189 * unit / 5, 15 * unit};
constexpr Point cap_site{34 * unit, 15 * unit}, hole_site{37 * unit, 3 * unit}, hole_inset{-3 * unit, 3 * unit};
constexpr Point grid_inset{-5 * unit, -5 * unit}, grid_site{889 * unit / 25, 127 * unit / 5};
constexpr Nm hole_grid = 127 * unit / 100;
constexpr Nm owner_need = 3 * unit / 2, owner_limit = 3 * unit, seat_pitch = unit / 4, seat_reach = 3 * unit;
constexpr int owner_pins = 3;
constexpr Point owner_site{20 * unit, 15 * unit}, stray_site{34 * unit, 22 * unit};
constexpr Point ring_site{23 * unit, 15 * unit}, clear_site{26 * unit, 15 * unit};
constexpr Nm sunk_floor = 101 * unit / 4;
constexpr Point shy_site{38 * unit, 25 * unit};
constexpr Point post_site{20 * unit, 20 * unit}, field_shift{0, unit};
constexpr Box field_box{65 * unit / 2, 13 * unit, 71 * unit / 2, 17 * unit};
constexpr Point guest_site{33 * unit, 22 * unit}, guest_shift{0, -5 * unit}, crowd_shift{0, 5 * unit};
constexpr Point west_shift{-2 * unit, 0}, north_shift{0, -2 * unit};
constexpr Nm square_side = 40 * unit;
constexpr Box post_floor{35 * unit / 2, 35 * unit / 2, 45 * unit / 2, 45 * unit / 2};
constexpr Nm east_floor = 109 * unit / 4, west_floor = 37 * unit / 2;
constexpr Point hole_floor{97 * unit / 4, 3 * unit};
constexpr double loose_limit = 1e9;
}

void require(bool condition, const std::string& what) {
    if (!condition) throw std::runtime_error("layout squeeze contract failed: " + what);
}

Variant block(Nm half_x, Nm half_y) {
    Variant variant;
    variant.gate_box = {-half_x, -half_y, half_x, half_y};
    variant.court_boxes.push_back(variant.gate_box);
    const Box pad{-fixture::pad_half, -fixture::pad_half, fixture::pad_half, fixture::pad_half};
    variant.pads.push_back({"1", {0, 0}, pad, false, 0});
    variant.pad_hull = pad;
    index_names(variant);
    return variant;
}

Variant round(Nm radius) {
    Variant variant;
    variant.gate_box = {-radius, -radius, radius, radius};
    variant.court_discs.push_back({{0, 0}, radius});
    return variant;
}

struct Scene {
    Problem problem;
    Placement placement;
    Scene(Nm width, Nm height) {
        problem.board.width = width;
        problem.board.height = height;
        problem.rules.edge_clearance = fixture::edge_clearance;
        problem.rules.edge_setback = fixture::edge_setback;
        problem.rules.copper_clearance = fixture::copper_clearance;
        problem.rules.compare_guard = 1;
        problem.rules.dispersion_limit = fixture::loose_limit;
    }
    std::size_t add(const std::string& reference, const Variant& variant, Point at, bool fixed,
                    bool flippable = false) {
        problem.footprints.push_back({reference, flippable, variant, variant});
        Part part;
        part.reference = reference;
        part.group = reference;
        part.footprint = problem.footprints.size() - 1;
        part.pad_nets.assign(variant.pads.size(), no_net);
        part.fixed = fixed;
        problem.parts.push_back(std::move(part));
        placement.push_back({at, Turn::none, Face::top});
        return problem.parts.size() - 1;
    }
};

struct Row {
    Scene scene{fixture::board_width, fixture::board_height};
    std::size_t wall = 0, plug = 0, cap = 0, hole = 0;
    Row() {
        wall = scene.add("WALL", block(fixture::wall_half, fixture::wall_reach), fixture::wall_site, true);
        plug = scene.add("PLUG", block(fixture::plug_half, fixture::plug_half), fixture::plug_site, false);
        cap = scene.add("CAP", block(fixture::cap_half, fixture::cap_half), fixture::cap_site, false);
        hole = scene.add("HOLE", round(fixture::hole_radius), fixture::hole_site, true);
        scene.problem.parts[plug].edge = EdgeRule{{1, 0}, {1, 0}, fixture::plug_reach, fixture::plug_seat};
        scene.problem.parts[hole].corner = CornerRule{true, false, fixture::hole_inset, 0};
        scene.problem.constraints.pad_gaps.push_back({plug, cap, {}, fixture::bond_limit, Sense::at_most, "bond"});
        scene.problem.nets.push_back({"LINK", Category::signal, fixture::copper_clearance, {{plug, 0}, {cap, 0}}});
        scene.problem.parts[plug].pad_nets.front() = 0;
        scene.problem.parts[cap].pad_nets.front() = 0;
    }
};

Pose moved(const Kernel& kernel, std::size_t part, Point by) {
    Pose pose = kernel.placement()[part];
    pose.at = shifted(pose.at, by);
    return pose;
}

void bundles_follow_their_rules() {
    Row row;
    const Bundles bundles = bundle(row.scene.problem);
    require(bundles.unit_of[row.plug] == bundles.unit_of[row.cap], "a bound pair is one bundle");
    require(bundles.unit_of[row.wall] != bundles.unit_of[row.plug] &&
            bundles.units.size() + 1 == row.scene.problem.parts.size(), "unbound and fixed parts stay apart");
    Kernel kernel(row.scene.problem, row.scene.placement);
    require(kernel.violations().empty() && kernel.outline_holds(), "the row starts legal");
    require(!kernel.move(row.cap, moved(kernel, row.cap, fixture::west_shift)), "a bound part cannot leave alone");
    const Nm before = kernel.routed_length();
    require(!kernel.move_many({{row.plug, moved(kernel, row.plug, fixture::west_shift)},
                               {row.cap, moved(kernel, row.cap, fixture::west_shift)}}),
            "an edge part cannot leave its edge with its bundle");
    require(kernel.move_many({{row.plug, moved(kernel, row.plug, fixture::north_shift)},
                              {row.cap, moved(kernel, row.cap, fixture::north_shift)}}),
            "a bundle slides along its edge as one");
    require(kernel.routed_length() == before && kernel.violations().empty(), "a rigid move keeps airwire and rules");
    kernel.verify();
}

void reserved_fields_travel() {
    Row row;
    row.scene.problem.reserves.push_back({fixture::field_box, {row.cap}, "field"});
    const std::size_t guest =
        row.scene.add("GUEST", block(fixture::cap_half, fixture::cap_half), fixture::guest_site, false);
    Kernel kernel(row.scene.problem, row.scene.placement);
    require(kernel.violations().empty(), "the field starts legal");
    require(kernel.rejection(row.cap, moved(kernel, row.cap, fixture::field_shift)).has_value(),
            "a single-part query keeps field members locked");
    const auto refusal = kernel.rejection(guest, moved(kernel, guest, fixture::guest_shift));
    require(refusal && refusal->kind == Breach::reserved, "a stranger may not enter the field");
    require(kernel.move_many({{row.cap, moved(kernel, row.cap, fixture::field_shift)}}), "a field follows its members");
    require(kernel.reserves().front() == shifted(fixture::field_box, fixture::field_shift), "the field box moved");
    Pose turned_pose = kernel.placement()[row.cap];
    turned_pose.turn = Turn::quarter;
    require(!kernel.move_many({{row.cap, turned_pose}}), "a field member cannot turn");
    require(!kernel.move_many({{row.cap, moved(kernel, row.cap, fixture::crowd_shift)}}),
            "a field cannot land on a stranger");
    const Probe probe = kernel.probe({{row.cap, moved(kernel, row.cap, fixture::crowd_shift)}});
    require(!probe.placeable, "a probe refuses a move that breaks the bundle rule");
    require(kernel.reserves().front() == shifted(fixture::field_box, fixture::field_shift) &&
            kernel.violations().empty(), "a probe leaves the state untouched");
    kernel.verify();
}

void probes_name_movable_blockers() {
    Scene scene(fixture::board_width, fixture::board_height);
    const std::size_t mover = scene.add("MOVER", block(fixture::cap_half, fixture::cap_half), fixture::cap_site, false);
    const std::size_t guest = scene.add("GUEST", block(fixture::cap_half, fixture::cap_half), fixture::guest_site, false);
    const std::size_t wall = scene.add("WALL", block(fixture::wall_half, fixture::wall_reach), fixture::wall_site, true);
    Kernel kernel(scene.problem, scene.placement);
    const Point onto_guest{fixture::guest_site.x - fixture::cap_site.x, fixture::guest_site.y - fixture::cap_site.y};
    const Probe probe = kernel.probe({{mover, moved(kernel, mover, onto_guest)}});
    require(probe.placeable && probe.blockers == std::vector<std::size_t>{guest}, "a probe names the movable blocker");
    const Point onto_wall{fixture::wall_site.x - fixture::cap_site.x, 0};
    require(!kernel.probe({{mover, moved(kernel, mover, onto_wall)}}).placeable, "a fixed blocker cannot be pushed");
    require(kernel.placement()[mover].at == fixture::cap_site && kernel.placement()[wall].at == fixture::wall_site,
            "probes leave every part in place");
    require(kernel.force({{mover, moved(kernel, mover, onto_guest)}}) && kernel.violations().size() > 0,
            "a forced move may leave the state illegal");
    const auto breach = kernel.breach(guest);
    require(breach && breach->other == mover, "the blocked part reports its breach");
    kernel.verify();
}

void corner_parts_snap_to_their_grid() {
    Board board;
    board.width = fixture::board_width;
    board.height = fixture::board_height;
    require(corner_site(board, {true, true, fixture::grid_inset, fixture::hole_grid}) == fixture::grid_site,
            "a corner part lands on the nearest grid point");
    require(corner_site(board, {true, false, fixture::hole_inset, 0}) == fixture::hole_site,
            "a corner part without a grid keeps its exact inset");
}

void squeeze_first_repairs_its_start() {
    Scene scene(fixture::board_width, fixture::board_height);
    const std::size_t wall = scene.add("WALL", block(fixture::wall_half, fixture::wall_reach), fixture::wall_site, true);
    const std::size_t shy = scene.add("SHY", block(fixture::cap_half, fixture::cap_half), fixture::shy_site, false);
    scene.placement[shy].at.x = fixture::board_width - fixture::cap_half - fixture::edge_setback / 2;
    Kernel kernel(scene.problem, scene.placement);
    require(kernel.violations().size() == 1, "a part inside the setback starts illegal");
    const SqueezeReport report = squeeze(kernel, default_squeeze());
    require(report.attempts.front().step == 0 && report.attempts.front().kept, "the first pass repairs the start");
    require(kernel.violations().empty() && kernel.placement()[wall].at == fixture::wall_site,
            "the repaired and squeezed board is legal");
}

void attraction_seats_a_part_under_its_owner() {
    Scene scene(fixture::board_width, fixture::board_height);
    const std::size_t owner = scene.add("OWNER", block(fixture::plug_half, fixture::plug_half), fixture::owner_site, false);
    const std::size_t stray =
        scene.add("STRAY", block(fixture::cap_half, fixture::cap_half), fixture::stray_site, false, true);
    scene.problem.parts[owner].fanout_subject = true;
    scene.problem.parts[owner].fanout_need = fixture::owner_need;
    scene.problem.parts[owner].fanout_pins = fixture::owner_pins;
    scene.problem.constraints.soft_gaps.push_back({owner, stray, {}, fixture::owner_limit, Sense::at_most, "owner"});
    require(crowds_escape(scene.problem, scene.placement, stray, {fixture::ring_site, Turn::none, Face::bottom}),
            "a rear seat in the escape ring of a top part is refused");
    require(!crowds_escape(scene.problem, scene.placement, stray, {fixture::clear_site, Turn::none, Face::bottom}) &&
            !crowds_escape(scene.problem, scene.placement, stray, {fixture::owner_site, Turn::none, Face::bottom}),
            "rear seats under the body or beyond the ring are allowed");
    Kernel kernel(scene.problem, scene.placement);
    const AttractReport report = attract(kernel, fixture::seat_pitch, fixture::seat_reach);
    require(report.wanted == 1 && report.seated == 1 && report.to_rear == 1, "the stray part is seated on the rear");
    require(report.met_before == 0 && report.met_after == 1, "its preference is met afterwards");
    require(kernel.placement()[stray].at == fixture::owner_site && kernel.placement()[stray].face == Face::bottom,
            "the seat is directly under the owner pin");
    require(kernel.violations().empty(), "attraction keeps every hard rule");
    kernel.verify();
}

void squeeze_sinks_a_jammed_part() {
    Row row;
    row.scene.problem.footprints[row.scene.problem.parts[row.cap].footprint].flippable = true;
    Kernel kernel(row.scene.problem, row.scene.placement);
    const SqueezeReport report = squeeze(kernel, default_squeeze());
    std::size_t sunk = 0;
    for (const auto& attempt : report.attempts) sunk += attempt.kept ? attempt.sunk : 0;
    require(sunk > 0 && kernel.placement()[row.cap].face == Face::bottom, "the jammed part goes to the rear");
    require(kernel.board().outline().x1 == fixture::sunk_floor, "the edge then closes until the plug meets the wall");
    require(kernel.violations().empty() && kernel.outline_holds(), "the sunk row is legal");
    kernel.verify();
}

void squeeze_stops_at_fixed_parts() {
    Scene scene(fixture::square_side, fixture::square_side);
    scene.add("POST", block(fixture::post_half, fixture::post_half), fixture::post_site, true);
    Kernel kernel(scene.problem, scene.placement);
    const SqueezeReport report = squeeze(kernel, default_squeeze());
    require(kernel.board().outline() == fixture::post_floor, "the outline stops at the setback of a fixed part");
    require(report.after.outline() == fixture::post_floor && report.before.width == fixture::square_side,
            "the report carries both outlines");
    require(kernel.violations().empty(), "the squeezed post is legal");
}

Placement squeezed_row(Board& board) {
    Row row;
    Kernel kernel(row.scene.problem, row.scene.placement);
    const SqueezeReport report = squeeze(kernel, default_squeeze());
    require(kernel.violations().empty() && kernel.outline_holds(), "the squeezed row is legal");
    kernel.verify();
    const Box outline = kernel.board().outline();
    require(outline.y0 == 0 && outline.y1 == fixture::board_height, "a full-height wall holds north and south");
    require(outline.x0 == fixture::west_floor, "the west edge stops at the wall setback");
    require(outline.x1 == fixture::east_floor, "the east edge stops when the bundle is packed against the wall");
    require(kernel.placement()[row.hole].at == fixture::hole_floor, "a corner part follows its corner");
    require(kernel.placement()[row.wall].at == fixture::wall_site, "a fixed part never moves");
    std::size_t kept = 0;
    for (const auto& attempt : report.attempts) kept += attempt.kept ? 1 : 0;
    require(kept > 0 && kept < report.attempts.size(), "the report lists kept and refused steps");
    board = kernel.board();
    return kernel.placement();
}

void squeeze_packs_a_bundle_against_a_wall() {
    Board first_board, second_board;
    const Placement first = squeezed_row(first_board), second = squeezed_row(second_board);
    require(first == second && first_board.outline() == second_board.outline(), "two squeezes agree exactly");
    Row row;
    Kernel kernel(row.scene.problem, row.scene.placement);
    const SqueezeReport best = squeeze_best(kernel, default_squeeze());
    require(best.tried.size() == 2 * edge_count && kernel.violations().empty(), "every edge order is tried");
    for (const double area : best.tried)
        require(to_mm(best.after.width) * to_mm(best.after.height) <= area, "the smallest outline is kept");
    require(kernel.board().outline() == best.after.outline(), "the kernel holds the kept outline");
}

}

int main() {
    try {
        bundles_follow_their_rules();
        reserved_fields_travel();
        probes_name_movable_blockers();
        corner_parts_snap_to_their_grid();
        squeeze_first_repairs_its_start();
        attraction_seats_a_part_under_its_owner();
        squeeze_sinks_a_jammed_part();
        squeeze_stops_at_fixed_parts();
        squeeze_packs_a_bundle_against_a_wall();
        std::cout << "layout squeeze contracts ok\n";
        return 0;
    } catch (const std::exception& error) {
        std::cerr << error.what() << "\n";
        return 1;
    }
}
