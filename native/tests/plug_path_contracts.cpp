#include "schgen/pcb_checks.hpp"

#include <algorithm>
#include <iostream>
#include <stdexcept>
#include <string>

namespace {

using namespace schgen;

namespace fixture {
constexpr double board_side = 100, origin = 25;
constexpr double holder_x = 60, holder_y = 60, blocker_x = 56, beside_y = 61.6;
constexpr double path_depth = 6, path_clear = 1, narrow_width = 1;
constexpr double tall = 2, low = 0.5, gap_to_blocker = 2;
constexpr double near_edge_x = 28, edge_room = 2, on_edge_x = 26;
constexpr double half_turn = 180;
constexpr Box4 module_body{50, 55, 58, 65};
constexpr double gap_to_module = 1;
const std::string holder = "HOLD", socket = "SOCK";
const char* const body =
    "(footprint \"fixture\" (fp_rect (start -1 -1) (end 1 1) (layer \"F.CrtYd\")) "
    "(pad \"1\" smd rect (at -0.5 0) (size 0.3 0.6)) (pad \"2\" smd rect (at 0.5 0) (size 0.3 0.6)))";
}

void require(bool condition, const std::string& what) {
    if (!condition) throw std::runtime_error("plug path contract failed: " + what);
}

bool names(const std::vector<std::string>& lines, const std::string& text) {
    return std::any_of(lines.begin(), lines.end(), [&](const std::string& line) { return line.find(text) != std::string::npos; });
}

PcbCheckInstance part(const std::string& ref, const std::string& value, double x, double y, std::optional<double> height) {
    PcbCheckInstance instance;
    instance.ref = ref;
    instance.value = value;
    instance.sheet = "fixture";
    instance.x = x;
    instance.y = y;
    instance.mod = pcb_check_footprint("fixture.kicad_mod", fixture::body);
    if (height) instance.height = PartHeight{*height, "fixture"};
    return instance;
}

PcbCheckModel board() {
    PcbCheckModel model;
    model.board_w = model.board_h = fixture::board_side;
    model.origin_x = model.origin_y = fixture::origin;
    model.plug_paths[fixture::holder] = PlugPathFact{"-X", "fixture", fixture::path_depth, "fixture", std::nullopt, std::nullopt,
                                                     fixture::path_clear, "fixture"};
    model.insts = {part("BT1", fixture::holder, fixture::holder_x, fixture::holder_y, fixture::tall),
                   part("J9", "PINS", fixture::blocker_x, fixture::holder_y, fixture::tall)};
    return model;
}

PlugPathResult judged(const PcbCheckModel& model, const std::optional<Box4>& module_body = std::nullopt) {
    return check_plug_paths(PcbCheckInput(model), module_body);
}

void blocked_paths_fail() {
    PcbCheckModel model = board();
    const PlugPathResult blocked = judged(model);
    require(!blocked.ok && blocked.paths.size() == 1 && !blocked.paths.front().ok, "a tall part in the path fails the gate");
    require(blocked.paths.front().ref == "BT1" && blocked.paths.front().mouth == std::make_pair(-1, 0) &&
                blocked.paths.front().clearance == fixture::gap_to_blocker,
            "the row carries the part, its mouth and the measured clearance");
    require(names(blocked.violations, "BT1") && names(blocked.violations, "J9"), "the failure names the part and what stands in its path");
    require(blocked.summary().find("PLUG PATH GATE: FAIL") == 0 && blocked.summary().find("BLOCKED") != std::string::npos,
            "the report states the failure");
    model.insts.back().height = PartHeight{fixture::low, "fixture"};
    const PlugPathResult under = judged(model);
    require(under.ok && under.paths.front().clearance == fixture::path_depth && under.summary().find("PLUG PATH GATE: PASS") == 0,
            "a part below the clear height leaves the path clear, and the report lists it clear for its whole depth");
    model.insts.back().height = PartHeight{fixture::path_clear, "fixture"};
    require(judged(model).ok, "a part exactly as tall as the clear height may stand in the path");
    model.insts.back().height.reset();
    require(names(judged(model).violations, "height unknown"), "a part of unknown height blocks the path");
    model.insts.back().height = PartHeight{fixture::tall, "fixture"};
    model.insts.back().side = "bottom";
    require(judged(model).ok, "a part on the other face is not in the path");
    model.insts.back().side = "top";
    model.insts.front().rotation = fixture::half_turn;
    require(judged(model).ok && judged(model).paths.front().mouth == std::make_pair(1, 0), "the path turns with the part");
    model.insts.front().rotation = 0;
    model.insts.back().y = fixture::beside_y;
    require(!judged(model).ok, "the path is as wide as the courtyard when no width is stated");
    model.plug_paths.at(fixture::holder).width_mm = fixture::narrow_width;
    model.plug_paths.at(fixture::holder).width_cite = "fixture";
    require(judged(model).ok && judged(model).paths.front().width == fixture::narrow_width, "a stated width narrows the path");
}

void board_and_module_bound_the_path() {
    PcbCheckModel model = board();
    model.insts.pop_back();
    require(judged(model).ok, "a path with nothing in it passes");
    const PlugPathResult under_module = judged(model, fixture::module_body);
    require(!under_module.ok && names(under_module.violations, "the module") &&
                under_module.paths.front().clearance == fixture::gap_to_module,
            "the module body blocks a path on the top face");
    model.insts.front().x = fixture::near_edge_x;
    const PlugPathResult off = judged(model);
    require(!off.ok && names(off.violations, "the board edge") && off.paths.front().clearance == fixture::edge_room,
            "a path that leaves the board fails, measured to the edge");
    ConnectorFact socket;
    socket.mating_face = "-X";
    socket.handling = "none";
    socket.edge_pinned = true;
    model.connectors[fixture::socket] = socket;
    model.plug_paths[fixture::socket] = model.plug_paths.at(fixture::holder);
    model.insts.front().value = fixture::socket;
    model.insts.front().x = fixture::on_edge_x;
    const PlugPathResult edge = judged(model);
    require(edge.ok && edge.paths.front().leaves_board, "an edge-mounted connector keeps its path off the board");
    model.insts.push_back(part("U1", "CHIP", fixture::holder_x, fixture::holder_y, std::nullopt));
    model.insts.back().mod.reset();
    bool threw = false;
    try {
        judged(model);
    } catch (const std::exception&) {
        threw = true;
    }
    require(threw, "a part whose body cannot be measured is not passed over");
}

}

int main() {
    try {
        blocked_paths_fail();
        board_and_module_bound_the_path();
        std::cout << "plug path contracts ok\n";
        return 0;
    } catch (const std::exception& error) {
        std::cerr << error.what() << "\n";
        return 1;
    }
}
