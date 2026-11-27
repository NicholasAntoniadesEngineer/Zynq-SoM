#include "schgen/route_board.hpp"
#include "schgen/route_bridge.hpp"
#include "schgen/route_check.hpp"
#include "schgen/route_run.hpp"

#include <algorithm>
#include <iostream>
#include <stdexcept>
#include <string>

namespace {

using namespace schgen::route;

namespace fixture {
constexpr Nm unit = 1000000;
constexpr Nm track_width = unit / 5, clearance = 3 * unit / 20, pad_half = unit / 2;
constexpr Nm via_pad = 9 * unit / 20, via_drill = unit / 5;
constexpr Nm edge = 3 * unit / 10, hole_clear = unit / 5, hole_space = 9 * unit / 20;
constexpr Box outline{0, 0, 40 * unit, 30 * unit};
constexpr Nm wall_inset = unit;
constexpr std::size_t six = 6, twelve = 12, thirteen = 13, plane_layer = 1;
constexpr int first_net = 0, second_net = 1, ground = 2;
constexpr Point left{5 * unit, 10 * unit}, right{25 * unit, 10 * unit};
constexpr Point low_left{5 * unit, 14 * unit}, low_right{25 * unit, 14 * unit};
constexpr Point ground_left{5 * unit, 20 * unit}, ground_right{25 * unit, 20 * unit};
}

int checks = 0;

void require(bool condition, const std::string& what) {
    ++checks;
    if (!condition) throw std::runtime_error("route contract failed: " + what);
}

template <typename Call> void refuses(const Call& call, const std::string& what) {
    bool refused = false;
    try {
        call();
    } catch (const RouteError&) {
        refused = true;
    }
    require(refused, what);
}

Item pad(int net, Point at, const std::string& owner, std::size_t first = 0, std::size_t last = 0) {
    using namespace fixture;
    return {ItemKind::pad, net, first, last, rectangle({at.x - pad_half, at.y - pad_half, at.x + pad_half, at.y + pad_half}), 0, owner};
}

Board board_of(std::size_t layers) {
    using namespace fixture;
    Board board;
    board.outline = outline;
    for (std::size_t layer = 0; layer < layers; ++layer)
        board.rules.layers.push_back(layer == plane_layer && layers > 2 ? Layer{"plane", LayerKind::plane, ground} : Layer{"signal " + std::to_string(layer), LayerKind::signal, no_net});
    board.rules.classes = {{"signal", track_width, clearance, 0}};
    board.rules.vias = {{"through", via_pad, via_drill, 0, layers - 1}};
    board.rules.edge_clearance = edge;
    board.rules.hole_clearance = hole_clear;
    board.rules.hole_spacing = hole_space;
    board.nets = {{"first", 0}, {"second", 0}, {"ground", 0}};
    board.fixed = {pad(first_net, left, "A.1"), pad(first_net, right, "B.1"), pad(second_net, low_left, "A.2"), pad(second_net, low_right, "B.2"),
                   pad(ground, ground_left, "A.3"), pad(ground, ground_right, "B.3")};
    return board;
}

void geometry_is_exact() {
    using namespace fixture;
    const Shape a = capsule({0, 0}, {10 * unit, 0}, track_width / 2), b = capsule({0, unit}, {10 * unit, unit}, track_width / 2);
    require(apart(a, b, unit - track_width), "parallel tracks at exactly their gap are apart");
    require(!apart(a, b, unit - track_width + 1), "one nanometre more clearance is not met");
    const Shape slanted = capsule({0, 3 * unit}, {3 * unit, 0}, 0);
    require(closer(slanted, disc({0, 0}, 0), 2121321) && !closer(slanted, disc({0, 0}, 2121320), 0), "distance to a slanted segment is compared without rounding");
    require(!closer(slanted, disc({0, 0}, 0), 2121320), "a point just outside the reach is not closer");
    const Shape box = rectangle({0, 0, 2 * unit, 2 * unit});
    require(touching(box, disc({unit, unit}, 0)) && !apart(box, disc({unit, unit}, 0), 1), "a point inside a rectangle touches it");
    require(touching(box, capsule({2 * unit, unit}, {5 * unit, unit}, 0)) && !touching(box, capsule({2 * unit + 2, unit}, {5 * unit, unit}, 0)),
            "contact is judged to the nanometre");
    require(touching(capsule({0, 0}, {4 * unit, 4 * unit}, 0), capsule({0, 4 * unit}, {4 * unit, 0}, 0)), "crossing segments touch");
    require(within(disc({unit, unit}, unit / 2), {0, 0, 2 * unit, 2 * unit}, unit / 2) && !within(disc({unit, unit}, unit / 2), {0, 0, 2 * unit, 2 * unit}, unit / 2 + 1),
            "edge margin is judged to the nanometre");
}

void layer_counts_are_input() {
    using namespace fixture;
    for (const std::size_t layers : {std::size_t{1}, std::size_t{2}, six, twelve}) {
        const Board board = board_of(layers);
        board.validate();
        require(board.rules.layers.size() == layers, "a board of " + std::to_string(layers) + " layers is accepted");
    }
    refuses([] { board_of(fixture::thirteen).validate(); }, "thirteen layers are refused");
    refuses([] {
        Board board = board_of(fixture::six);
        board.rules.layers.clear();
        board.validate();
    }, "no layers are refused");
}

void world_judges_and_undoes() {
    using namespace fixture;
    const Board board = board_of(six);
    World world(board);
    const Item joining = track(board, first_net, 0, left, right);
    require(!world.conflict(joining), "a track between its own pads is legal");
    const std::size_t start = world.mark();
    world.add(joining);
    const Item crossing = track(board, second_net, 0, {15 * unit, 5 * unit}, {15 * unit, 14 * unit});
    require(world.conflict(crossing).has_value(), "a track of another net across it is refused");
    require(!world.conflict(track(board, second_net, 2, {15 * unit, 5 * unit}, {15 * unit, 14 * unit})), "the same track on another layer is legal");
    const Nm gap = track_width + clearance;
    require(!world.conflict(track(board, second_net, 0, {7 * unit, 10 * unit + gap}, {23 * unit, 10 * unit + gap})), "a parallel track at exactly the clearance is legal");
    require(world.conflict(track(board, second_net, 0, {7 * unit, 10 * unit + gap - 1}, {23 * unit, 10 * unit + gap - 1})).has_value(), "one nanometre nearer is refused");
    require(world.conflict(track(board, second_net, 0, {unit / 5, unit}, {unit / 5, 5 * unit}))->edge, "a track inside the edge clearance is refused as an edge breach");
    const Item drilled = via(board, second_net, {15 * unit, 10 * unit + track_width / 2 + hole_clear + via_drill / 2 - 1});
    require(world.conflict(drilled).has_value(), "a via whose hole is too near other copper is refused");
    world.rollback(start);
    require(!world.conflict(crossing) && world.routed().empty(), "undo restores the board exactly");
    const std::size_t added = world.add(joining);
    world.remove(added);
    require(world.routed().empty() && !world.conflict(crossing), "a removed track no longer blocks");
    world.rollback(start);
    require(world.routed().empty(), "undoing an add and a remove leaves nothing");
    refuses([&] { world.remove(0); }, "fixed copper cannot be removed");
}

void verifier_finds_every_fault() {
    using namespace fixture;
    const Board board = board_of(six);
    require(verify(board, {}).opens.size() == 3, "an unrouted board reports every net open");
    std::vector<Item> copper{track(board, first_net, 0, left, right), track(board, second_net, 0, low_left, low_right),
                             via(board, ground, ground_left), via(board, ground, ground_right)};
    const CheckReport clean = verify(board, copper);
    require(clean.ok() && clean.joined == 3, "tracks and plane vias join every net: " + clean.summary());
    auto broken = copper;
    broken[0] = track(board, first_net, 0, left, {15 * unit, 10 * unit});
    require(verify(board, broken).opens.size() == 1 && !verify(board, broken).ok(), "a track that stops short leaves its net open");
    broken = copper;
    broken.push_back(track(board, second_net, 0, {15 * unit, 14 * unit}, {15 * unit, 10 * unit}));
    require(verify(board, broken).shorts.size() == 1, "a track onto another net is a short");
    broken = copper;
    broken.push_back(track(board, second_net, 0, {15 * unit, 14 * unit}, {15 * unit, 10 * unit + track_width + clearance - 1}));
    const CheckReport near = verify(board, broken);
    require(near.shorts.empty() && near.clearances.size() == 1, "one nanometre inside the clearance is a clearance fault: " + near.summary());
    broken.back() = track(board, second_net, 0, {15 * unit, 14 * unit}, {15 * unit, 10 * unit + track_width + clearance});
    require(verify(board, broken).ok(), "exactly the clearance passes");
    broken = copper;
    broken.push_back(track(board, first_net, 2, {30 * unit, 5 * unit}, {35 * unit, 5 * unit}));
    require(verify(board, broken).strays.size() == 1, "copper that reaches no pad of its net is reported");
    broken = copper;
    broken[2] = via(board, first_net, ground_left);
    const CheckReport wrong = verify(board, broken);
    require(!wrong.ok() && wrong.opens.size() == 1 && wrong.shorts.size() == 1, "a via of the wrong net on a pad shorts it and leaves ground open: " + wrong.summary());
    broken = copper;
    broken.push_back(track(board, ground, plane_layer, ground_left, ground_right));
    require(verify(board, broken).strays.size() == 1, "a track on a plane layer is reported");
    broken = copper;
    broken.push_back(via(board, first_net, {left.x + pad_half, left.y}));
    broken.push_back(via(board, second_net, {left.x + pad_half, left.y + hole_space + via_drill - 1}));
    require(!verify(board, broken).holes.empty(), "holes nearer than the hole spacing are reported");
    Board fenced = board;
    fenced.fixed.push_back({ItemKind::keepout, no_net, 0, 0, rectangle({14 * unit, 9 * unit, 16 * unit, 11 * unit}), 0, "fence"});
    require(verify(fenced, copper).keepouts.size() == 1, "copper in a keep-out is reported");
    World world(fenced);
    require(world.conflict(copper[0]).has_value() && !world.conflict(track(fenced, first_net, 2, left, right)), "the world refuses the same keep-out on its layer only");
    const Board single = board_of(1);
    require(verify(single, {track(single, first_net, 0, left, right), track(single, second_net, 0, low_left, low_right),
                            track(single, ground, 0, ground_left, ground_right)}).ok(), "a one-layer board routes its ground as a track");
}

void router_joins_a_board() {
    using namespace fixture;
    for (const std::size_t layers : {std::size_t{2}, six}) {
        Board board = board_of(layers);
        board.fixed.push_back(pad(second_net, {15 * unit, 6 * unit}, "C.2"));
        board.fixed.push_back({ItemKind::keepout, no_net, 0, 0, rectangle({14 * unit, 8 * unit, 16 * unit, 9 * unit}), 0, "fence"});
        if (layers == 2) {
            board.nets.pop_back();
            board.fixed.erase(std::remove_if(board.fixed.begin(), board.fixed.end(), [](const Item& item) { return item.net == ground; }), board.fixed.end());
        }
        World world(board);
        const RunReport run = route_all(world, RunSetup{});
        const CheckReport judged = verify(board, world.routed());
        require(run.complete() && judged.ok(), std::to_string(layers) + " layers: every connection made and the verifier agrees: " + run.summary(board) + judged.summary());
        if (layers == six) require(run.vias >= 2, "six layers: the ground pads reach their plane through vias");
    }
    Board walled = board_of(1);
    walled.nets.pop_back();
    walled.fixed = {pad(first_net, {wall_inset, outline.y1 / 2}, "A.1"), pad(first_net, {outline.x1 - wall_inset, outline.y1 / 2}, "B.1"),
                    pad(second_net, {outline.x1 / 2, wall_inset}, "A.2"), pad(second_net, {outline.x1 / 2, outline.y1 - wall_inset}, "B.2")};
    World world(walled);
    const RunReport run = route_all(world, RunSetup{});
    const CheckReport judged = verify(walled, world.routed());
    require(!run.complete() && judged.shorts.empty() && judged.clearances.empty() && judged.opens.size() == 1,
            "one layer cannot cross: the router reports the open net and leaves no short: " + run.summary(walled) + judged.summary());
}

const char* const sample_board = R"board((kicad_pcb
	(version 20241229)
	(layers
		(0 "F.Cu" signal)
		(1 "In1.Cu" power)
		(2 "In2.Cu" signal)
		(31 "B.Cu" signal)
		(25 "Edge.Cuts" user)
	)
	(net 0 "")
	(net 1 "GND")
	(net 2 "LINK")
	(net 3 "RAIL")
	(gr_rect (start 0 0) (end 30 20) (layer "Edge.Cuts"))
	(footprint "sample:two"
		(layer "F.Cu")
		(at 5 10 90)
		(property "Reference" "U1")
		(pad "1" smd rect (at 0 -1 90) (size 0.6 0.4) (layers "F.Cu") (net 2 "LINK"))
		(pad "2" smd roundrect (at 0 1 90) (size 0.6 0.4) (layers "F.Cu") (roundrect_rratio 0.25) (net 1 "GND"))
		(pad "3" thru_hole circle (at 2 0 90) (size 1.2 1.2) (drill 0.6) (layers "*.Cu") (net 3 "RAIL"))
	)
	(footprint "sample:two"
		(layer "B.Cu")
		(at 25 10)
		(property "Reference" "U2")
		(pad "1" smd rect (at 0 -1) (size 0.6 0.4) (layers "B.Cu") (net 2 "LINK"))
		(pad "2" smd oval (at 0 1) (size 0.8 0.4) (layers "B.Cu") (net 1 "GND"))
		(pad "3" thru_hole circle (at 2 0) (size 1.2 1.2) (drill 0.6) (layers "*.Cu") (net 3 "RAIL"))
		(pad "" np_thru_hole circle (at -3 0) (size 1 1) (drill 1) (layers "*.Cu"))
	)
	(zone (net 1) (net_name "GND") (layer "In1.Cu") (polygon (pts (xy 0 0) (xy 30 0) (xy 30 20) (xy 0 20))))
	(zone (net 0) (net_name "") (layers "F.Cu") (name "fence") (keepout (tracks not_allowed) (vias allowed)) (polygon (pts (xy 14 0) (xy 16 0) (xy 16 12) (xy 14 12))))
)
)board";

const char* const sample_project = R"project({
 "board": {"design_settings": {"rules": {"min_copper_edge_clearance": 0.3, "min_hole_clearance": 0.2, "min_hole_to_hole": 0.45, "min_track_width": 0.09}}},
 "net_settings": {
  "classes": [
   {"name": "WIDE", "clearance": 0.2, "track_width": 0.4, "via_diameter": 0.6, "via_drill": 0.3},
   {"name": "Default", "clearance": 0.15, "track_width": 0.2, "via_diameter": 0.6, "via_drill": 0.3}
  ],
  "netclass_patterns": [{"netclass": "WIDE", "pattern": "RAIL"}]
 }
})project";

void board_file_is_the_input() {
    using namespace fixture;
    ReadNotes notes;
    const Board board = board_from_pcb(schgen::sexpr_loads(sample_board), schgen::parse_json_text(sample_project), &notes);
    require(board.rules.layers.size() == 4 && notes.planes == 1 && board.rules.layers[1].kind == LayerKind::plane, "four copper layers are read and the inner zone makes its layer a plane");
    require(board.rules.classes.front().name == "Default" && board.rules.classes.size() == 2 && board.nets.size() == 3, "classes and nets come from the two files");
    require(board.rules.classes[board.nets[2].net_class].name == "WIDE" && board.rules.classes[board.nets[1].net_class].name == "Default", "a net takes the class its pattern names");
    require(notes.pads == 7 && notes.keepouts == 1 && notes.footprints == 2, "pads, footprints and track keep-outs are counted");
    const auto pad_named = [&](const std::string& owner) {
        for (const Item& item : board.fixed)
            if (item.owner == owner) return item;
        throw std::runtime_error("route contract failed: no pad " + owner);
    };
    const Box turned_pad = pad_named("U1.1").shape.bound();
    require(turned_pad.x0 == 4 * unit - unit / 5 && turned_pad.x1 == 4 * unit + unit / 5 && turned_pad.y0 == 10 * unit - 3 * unit / 10 && turned_pad.y1 == 10 * unit + 3 * unit / 10,
            "a pad of a footprint turned a quarter is where KiCad puts it");
    require(pad_named("U2.1").first == 3 && pad_named("U1.3").first == 0 && pad_named("U1.3").last == 3 && pad_named("U1.3").drill == 3 * unit / 5,
            "a rear pad is on the last layer and a drilled pad on all of them");
    World world(board);
    const RunReport run = route_all(world, RunSetup{});
    const CheckReport judged = verify(board, world.routed());
    require(run.complete() && judged.ok(), "the sample board routes completely: " + run.summary(board) + judged.summary());
    const std::string routed = with_copper(sample_board, board, world.routed());
    const Board again = board_from_pcb(schgen::sexpr_loads(routed), schgen::parse_json_text(sample_project));
    require(again.fixed.size() == board.fixed.size() + world.routed().size(), "the copper written into the board file is read back");
    const CheckReport kept = verify(again, {});
    require(kept.ok(), "the board file with its copper needs nothing more: " + kept.summary());
    refuses([&] { board_from_pcb(schgen::sexpr_loads("(kicad_pcb (net 1 \"A\"))"), schgen::parse_json_text(sample_project)); }, "a board file without layers is refused");
}

}

int main() {
    try {
        geometry_is_exact();
        layer_counts_are_input();
        world_judges_and_undoes();
        verifier_finds_every_fault();
        router_joins_a_board();
        board_file_is_the_input();
        std::cout << "route contracts: " << checks << " checks passed\n";
        return 0;
    } catch (const std::exception& error) {
        std::cerr << error.what() << "\n";
        return 1;
    }
}
