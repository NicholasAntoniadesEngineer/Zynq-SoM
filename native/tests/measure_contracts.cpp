#include "schgen/measure.hpp"

#include <cmath>
#include <fstream>
#include <functional>
#include <iostream>
#include <iterator>
#include <stdexcept>

namespace {

using namespace schgen;
using namespace schgen::measure;

struct TurnCase {
    const char* pose;
    Rect court;
    double first_x, first_y, second_x, second_y;
};

namespace expected {
const TurnCase turn_cases[] = {
    {"50 40", {49, 38, 55, 43}, 54, 40, 50, 39},
    {"50 40 90", {48, 35, 53, 41}, 50, 36, 49, 40},
    {"50 40 180", {45, 37, 51, 42}, 46, 40, 50, 41},
    {"50 40 270", {47, 39, 52, 45}, 50, 44, 51, 40}};
constexpr double board_area = 8000;
constexpr double overlap_union = 150, through_block = 4, keepout_area = 200, bottom_court = 36;
constexpr double nested_union = 100;
const std::vector<Rect> overlap_pair{{0, 0, 10, 10}, {5, 0, 15, 10}};
const std::vector<Rect> nested_pair{{0, 0, 10, 10}, {2, 2, 4, 4}};
const std::vector<Rect> empty_sliver{{1, 1, 1, 2}};
constexpr double signal_length = 7, signal_cross = 4;
constexpr double power_euclid = 5, power_manhattan = 7;
constexpr double plane_euclid = 10, plane_manhattan = 14;
constexpr double peak_demand = 0.042, mean_demand = 0.00013125;
constexpr int demand_columns = 20, demand_rows = 16;
constexpr std::size_t peak_slot = 42;
constexpr double north_run = 6, east_run = 4, north_ratio = 0.06;
constexpr int layer_pair = 2;
}

const char* const project_text =
    R"({"net_settings":{"classes":[{"name":"Default","track_width":0.2,"clearance":0.1},)"
    R"({"name":"POWER","track_width":0.4,"clearance":0.2}],)"
    R"("netclass_patterns":[{"netclass":"POWER","pattern":"+*"}]}})";
const char* const power_only_text =
    R"({"net_settings":{"classes":[{"name":"POWER","track_width":0.4,"clearance":0.2}]}})";
const char* const index_text = R"({"alpha":1,"beta":2})";
const char* const outline_text = R"( (gr_rect (start 0 0) (end 100 80) (layer "Edge.Cuts")))";
const char* const module_zone =
    R"( (zone (net 0) (net_name "") (layers "F.Cu" "B.Cu") (name "module"))"
    R"( (polygon (pts (xy 60 60) (xy 80 60) (xy 80 70) (xy 60 70)))))";
const char* const ground_zone =
    R"( (zone (net 3) (net_name "GND") (layer "In1.Cu") (name "ground"))"
    R"( (polygon (pts (xy 0 0) (xy 100 0) (xy 100 80) (xy 0 80)))))";

void require(bool condition, const std::string& what) {
    if (!condition) throw std::runtime_error("measure contract failed: " + what);
}

bool near(double a, double b) { return std::fabs(a - b) < constants::touch_tolerance.value; }

bool same(Rect a, Rect b) {
    return near(a.x0, b.x0) && near(a.y0, b.y0) && near(a.x1, b.x1) && near(a.y1, b.y1);
}

std::string yard(const std::string& layer) { return layer == "F.Cu" ? "F.CrtYd" : "B.CrtYd"; }

std::string board_text(const std::string& body, const std::string& outline = outline_text) {
    return std::string("(kicad_pcb (version 20260206)\n") +
           R"( (layers (0 "F.Cu" signal) (1 "In1.Cu" power) (2 "In2.Cu" power) (31 "B.Cu" signal)))" +
           outline + body + ")\n";
}

std::string asymmetric(const std::string& layer, const std::string& pose) {
    return " (footprint \"ASYM\" (layer \"" + layer + "\") (at " + pose + ")" +
           R"( (property "Reference" "U1001"))" +
           " (fp_rect (start -1 -2) (end 5 3) (layer \"" + yard(layer) + "\"))" +
           R"( (pad "1" smd rect (at 4 0) (size 1 1) (net 1 "A")))" +
           R"( (pad "2" smd rect (at 0 -1) (size 1 1) (net 2 "B"))))";
}

std::string square(const std::string& reference, const std::string& layer, const std::string& pose,
                   const std::string& half, const std::string& kind, const std::string& net) {
    return " (footprint \"SQUARE\" (layer \"" + layer + "\") (at " + pose + ")" +
           " (property \"Reference\" \"" + reference + "\")" +
           " (fp_rect (start -" + half + " -" + half + ") (end " + half + " " + half +
           ") (layer \"" + yard(layer) + "\"))" +
           " (pad \"1\" " + kind + " circle (at 0 0) (size 2 2) (net 1 \"" + net + "\"))" +
           " (pad \"2\" " + kind + " circle (at 0 0) (size 2 2)))";
}

std::string hole(const std::string& reference, const std::string& pose) {
    return " (footprint \"HOLE\" (layer \"F.Cu\") (at " + pose + ")" +
           " (property \"Reference\" \"" + reference + "\")" +
           R"( (fp_rect (start -2 -2) (end 2 2) (layer "F.CrtYd")))" +
           R"( (pad "1" thru_hole circle (at 0 0) (size 2 2) (net 1 "A"))))";
}

Board loaded(const std::string& text, const char* project = project_text) {
    return read_board(sexpr_loads(text), parse_json_text(project), parse_json_text(index_text));
}

void rejects(const std::string& what, const std::function<void()>& action) {
    try {
        action();
    } catch (const MeasureError&) {
        return;
    }
    throw std::runtime_error("measure contract failed: accepted " + what);
}

void turns_follow_board_convention() {
    for (const char* layer : {"F.Cu", "B.Cu"})
        for (const auto& item : expected::turn_cases) {
            const Board board = loaded(board_text(asymmetric(layer, item.pose)));
            require(board.parts.size() == 1, "one part parsed");
            const Part& part = board.parts.front();
            require(part.face == (std::string(layer) == "F.Cu" ? Face::top : Face::bottom), "face");
            require(same(part.courtyard, item.court), std::string("courtyard at ") + item.pose);
            require(near(part.pads.front().x, item.first_x) && near(part.pads.front().y, item.first_y),
                    std::string("first pad at ") + item.pose);
            require(near(part.pads.back().x, item.second_x) && near(part.pads.back().y, item.second_y),
                    std::string("second pad at ") + item.pose);
            require(part.group == "alpha" && part.pin_count == expected::layer_pair, "group and pins");
        }
}

void union_counts_overlap_once() {
    require(near(union_area(expected::overlap_pair), expected::overlap_union), "overlap");
    require(near(union_area(expected::nested_pair), expected::nested_union), "nested");
    require(near(union_area({}), 0) && near(union_area(expected::empty_sliver), 0), "empty");
}

void faces_account_for_holes_and_keepouts() {
    const std::string body = square("U1001", "F.Cu", "20 20", "5", "smd", "A") +
                             square("U1002", "F.Cu", "25 20", "5", "smd", "A") +
                             square("U2001", "B.Cu", "40 40", "3", "thru_hole", "B") + module_zone;
    Options options;
    options.keepouts.push_back({Face::top, "module"});
    const Report report = measure_board(loaded(board_text(body)), options);
    require(near(report.area, expected::board_area), "outline area");
    require(report.top.parts == expected::layer_pair && report.bottom.parts == 1, "face counts");
    require(report.through_parts == 1, "through-hole count");
    require(near(report.top.occupied, expected::overlap_union + expected::through_block),
            "top occupied includes the opposite hole");
    require(near(report.bottom.occupied, expected::bottom_court), "bottom occupied");
    require(near(report.top.keepout, expected::keepout_area), "keepout area");
    require(near(report.top.usable, expected::board_area - expected::keepout_area), "usable area");
    require(near(report.top.utilisation,
                 (expected::overlap_union + expected::through_block) /
                     (expected::board_area - expected::keepout_area)), "utilisation");
    require(report.top.occupied_fanout > report.top.occupied, "fan-out halo grows occupancy");
    require(near(report.bottom.keepout, 0), "keepout applies to the named face only");
}

void airwire_splits_by_category() {
    const std::string body = square("U1001", "F.Cu", "10 10", "1", "smd", "SIG") +
                             square("U2001", "F.Cu", "13 14", "1", "smd", "SIG") +
                             square("U1002", "F.Cu", "13 10", "1", "smd", "SIG") +
                             square("U1003", "F.Cu", "30 30", "1", "smd", "+5V") +
                             square("U1004", "F.Cu", "33 34", "1", "smd", "+5V") +
                             square("U1005", "F.Cu", "50 50", "1", "smd", "GND") +
                             square("U1006", "F.Cu", "56 58", "1", "smd", "GND") + ground_zone;
    Options options;
    options.power_classes.push_back("POWER");
    const Report report = measure_board(loaded(board_text(body)), options);
    const auto& wires = report.airwire;
    require(wires.signal.nets == 1 && wires.power.nets == 1 && wires.plane.nets == 1, "categories");
    require(wires.signal.connections == expected::layer_pair && wires.power.connections == 1, "connections");
    require(near(wires.signal.euclid, expected::signal_length) &&
            near(wires.signal.manhattan, expected::signal_length), "signal length");
    require(near(wires.signal.cross_euclid, expected::signal_cross) &&
            near(wires.signal.cross_manhattan, expected::signal_cross), "cross-group share");
    require(near(wires.power.euclid, expected::power_euclid) &&
            near(wires.power.manhattan, expected::power_manhattan), "power length");
    require(near(wires.plane.euclid, expected::plane_euclid) &&
            near(wires.plane.manhattan, expected::plane_manhattan), "plane length");
    require(wires.longest.size() == 1 && wires.longest.front().net == "SIG", "longest net");
    const auto& demand = report.demand;
    require(demand.columns == expected::demand_columns && demand.rows == expected::demand_rows,
            "demand grid");
    require(near(demand.peak, expected::peak_demand), "demand peak");
    require(near(demand.mean, expected::mean_demand), "demand mean");
    require(near(demand.bins[expected::peak_slot], expected::peak_demand), "demand bin position");
    require(demand.congested == 0, "no congested bin");
    require(report.signal_layers == expected::layer_pair && report.power_layers == expected::layer_pair,
            "layer table");
}

void edges_count_mounted_parts() {
    const std::string body = square("U1001", "F.Cu", "50 2", "3", "smd", "A") +
                             square("U1002", "F.Cu", "96.5 40", "2", "thru_hole", "A") +
                             square("U1003", "F.Cu", "3 40", "2", "smd", "A") +
                             hole("U1004", "50 77");
    const Report report = measure_board(loaded(board_text(body)), {});
    require(report.edges.front().name == "north" && near(report.edges.front().run, expected::north_run),
            "overhanging part counts on its edge");
    require(near(report.edges.front().ratio, expected::north_ratio), "edge ratio");
    require(near(report.edges[1].run, expected::east_run), "through-hole part inside the band");
    require(report.edges.back().parts.empty(), "surface part inside the outline is not edge mounted");
    require(report.edges[2].parts.empty(), "single-pin hole is not edge mounted");
    require(near(report.bounds.perimeter_run, expected::north_run + expected::east_run), "perimeter run");
}

void malformed_inputs_fail() {
    const std::string part = square("U1001", "F.Cu", "20 20", "5", "smd", "A");
    rejects("a board without outline", [&] { loaded(board_text(part, "")); });
    rejects("a reference with no sheet", [&] {
        loaded(board_text(square("U9001", "F.Cu", "20 20", "5", "smd", "A")));
    });
    rejects("an unknown keepout", [&] {
        Options options;
        options.keepouts.push_back({Face::top, "absent"});
        measure_board(loaded(board_text(part)), options);
    });
    rejects("an unknown power class", [&] {
        Options options;
        options.power_classes.push_back("absent");
        measure_board(loaded(board_text(part)), options);
    });
    rejects("an unknown excluded group", [&] {
        Options options;
        options.excluded_groups.push_back("absent");
        measure_board(loaded(board_text(part)), options);
    });
    rejects("a project without the default class", [&] {
        const std::string pair = part + square("U1002", "F.Cu", "40 20", "5", "smd", "A");
        measure_board(loaded(board_text(pair), power_only_text), {});
    });
}

void reports_are_stable() {
    const std::string body = square("U1001", "F.Cu", "20 20", "5", "smd", "A") +
                             square("U2001", "F.Cu", "40 20", "5", "smd", "A");
    const Board board = loaded(board_text(body));
    const Report report = measure_board(board, {});
    const std::string first = report_json(report, {{"board", "hash"}});
    require(first == report_json(measure_board(board, {}), {{"board", "hash"}}), "repeatable report");
    const JsonNode parsed = parse_json_text(first);
    require(parsed.kind == JsonKind::Object && object_field(parsed, "faces") != nullptr &&
            object_field(parsed, "constants") != nullptr, "report structure");
    require(first.find("\"schema\": \"schgen.measure/1\"") != std::string::npos, "schema tag");
    const std::string map = report_map(board, report);
    require(map.rfind("<svg", 0) == 0 && map.find("</svg>") != std::string::npos, "map document");
}

std::string file_text(const std::string& path) {
    std::ifstream stream(path, std::ios::binary);
    if (!stream) throw std::runtime_error("measure contract cannot read " + path);
    return {std::istreambuf_iterator<char>(stream), std::istreambuf_iterator<char>()};
}

void live_board_is_consistent(const std::string& root, const std::string& project) {
    const std::string base = root + "/" + project + "/";
    const std::string pcb = file_text(base + "Zynq_Carrier.kicad_pcb");
    const Board board = read_board(sexpr_loads(pcb), parse_json_text(file_text(base + "Zynq_Carrier.kicad_pro")),
                                   parse_json_text(file_text(base + "sheet_index.json")));
    Options options;
    options.keepouts.push_back({Face::top, "SoM_body_keepout"});
    options.power_classes.push_back("POWER");
    const Report report = measure_board(board, options);
    require(report.parts > 0 && report.without_geometry.empty(), project + " parts have geometry");
    for (const auto* face : {&report.top, &report.bottom})
        require(face->utilisation > 0 && face->utilisation_fanout < 1 &&
                face->occupied <= face->occupied_clearance + constants::touch_tolerance.value,
                project + " face utilisation range");
    require(report.airwire.signal.euclid > 0 &&
            report.airwire.signal.euclid <= report.airwire.signal.manhattan, project + " airwire order");
    require(report.demand.peak >= report.demand.mean && report.demand.mean > 0, project + " demand order");
    const std::vector<InputIdentity> inputs{{"board", "hash"}};
    require(report_json(report, inputs) == report_json(measure_board(board, options), inputs),
            project + " repeatable report");
    const auto& wires = report.airwire;
    std::cout << project << ": " << report.width << " x " << report.height << " mm, " << report.parts
              << " parts, euclid airwire total "
              << wires.plane.euclid + wires.power.euclid + wires.signal.euclid << " mm, cross "
              << wires.plane.cross_euclid + wires.power.cross_euclid + wires.signal.cross_euclid
              << " mm\n";
}

}

int main(int argc, char** argv) {
    try {
        if (argc > 1) {
            live_board_is_consistent(argv[1], "carrier");
            live_board_is_consistent(argv[1], "devkit_mini");
            return 0;
        }
        turns_follow_board_convention();
        union_counts_overlap_once();
        faces_account_for_holes_and_keepouts();
        airwire_splits_by_category();
        edges_count_mounted_parts();
        malformed_inputs_fail();
        reports_are_stable();
        std::cout << "measure contracts ok\n";
        return 0;
    } catch (const std::exception& error) {
        std::cerr << error.what() << "\n";
        return 1;
    }
}
