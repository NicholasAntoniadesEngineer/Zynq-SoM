#include "pcb_checks_internal.hpp"
#include "schgen/layout_geometry.hpp"

namespace schgen {
using namespace pcb_checks;

namespace {

const char* const board_edge_name = "the board edge";
const char* const module_name = "the module";

double ahead_of(const Box4& mouth_side, const Box4& body, int out_x, int out_y) {
    if (out_x > 0) return body.x0 - mouth_side.x1;
    if (out_x < 0) return mouth_side.x0 - body.x1;
    if (out_y > 0) return body.y0 - mouth_side.y1;
    return mouth_side.y0 - body.y1;
}

bool intrudes(const Box4& path, const Box4& body, double slack) {
    return std::min(path.x1, body.x1) - std::max(path.x0, body.x0) > slack &&
           std::min(path.y1, body.y1) - std::max(path.y0, body.y0) > slack;
}

}

PlugPathResult check_plug_paths(const PcbCheckInput& input, const std::optional<Box4>& module_body) {
    const auto& model = input.model();
    const double slack = plug_path_constants::gate_slack.value;
    PlugPathResult res;
    res.board_w = model.board_w;
    res.board_h = model.board_h;
    const Box4 outline{model.origin_x, model.origin_y, model.origin_x + model.board_w, model.origin_y + model.board_h};
    for (std::size_t i = 0; i < model.insts.size(); ++i) {
        const auto& inst = model.insts[i];
        const PlugPathFact* fact = part_fact_for(model.plug_paths, inst.value, inst.footprint);
        if (!fact) continue;
        const auto face = plug_path_vector(*fact);
        const auto turned = turn_point(face.first, inst.mirror ? -face.second : face.second, inst.rotation);
        const int out_x = static_cast<int>(std::lround(turned.first)), out_y = static_cast<int>(std::lround(turned.second));
        const Box4 body = input.courtyard_at(i);
        const Box4 path = layout::path_ahead(body, out_x, out_y, fact->depth_mm, fact->width_mm.value_or(0.0));
        const auto connector = mpn(model.connectors, inst);
        PlugPathRow row;
        row.ref = inst.ref;
        row.part = inst.value;
        row.mouth = {out_x, out_y};
        row.depth = fact->depth_mm;
        row.width = out_x != 0 ? path.y1 - path.y0 : path.x1 - path.x0;
        row.clear_height = fact->clear_height_mm;
        row.leaves_board = !connector.empty() &&
                           (model.connectors.at(connector).edge_pinned || model.edge_sheets.count(inst.sheet) != 0) &&
                           mating_face_vector(model.connectors.at(connector)) == face;
        row.clearance = row.depth;
        std::vector<std::string> why;
        const auto nearer = [&](double distance, const std::string& name) {
            const double ahead = std::max(distance, 0.0);
            if (ahead >= row.clearance - slack) return;
            row.clearance = ahead;
            row.blocker = name;
        };
        if (!row.leaves_board) {
            const Box4 rim{outline.x1, outline.y1, outline.x0, outline.y0};
            nearer(ahead_of(body, rim, out_x, out_y), board_edge_name);
            const bool beside = out_x != 0 ? path.y0 < outline.y0 - slack || path.y1 > outline.y1 + slack
                                           : path.x0 < outline.x0 - slack || path.x1 > outline.x1 + slack;
            if (beside) why.push_back("the path is wider than the board beside it");
        }
        if (module_body && inst.side == "top" && intrudes(path, *module_body, slack))
            nearer(ahead_of(body, *module_body, out_x, out_y), module_name);
        for (std::size_t j = 0; j < model.insts.size(); ++j) {
            const auto& other = model.insts[j];
            if (j == i || other.side != inst.side) continue;
            const Box4 box = input.courtyard_at(j);
            if (!intrudes(path, box, slack)) continue;
            if (other.height && other.height->mm <= row.clear_height) continue;
            nearer(ahead_of(body, box, out_x, out_y),
                   other.ref + " (" + other.value + ", " + (other.height ? f(other.height->mm, 2) + " mm high" : std::string("height unknown")) + ")");
        }
        if (row.clearance < row.depth - slack)
            why.push_back(row.blocker + " stands " + f(row.clearance, 2) + " mm in front of the mouth; the path needs " + f(row.depth, 2) +
                          " mm clear of anything taller than " + f(row.clear_height, 2) + " mm");
        row.ok = why.empty();
        if (!row.ok) res.violations.push_back(inst.ref + " (" + inst.sheet + ") " + inst.value + ": " + join(why, "; "));
        res.paths.push_back(std::move(row));
    }
    res.ok = res.violations.empty();
    return res;
}

std::string PlugPathResult::summary() const {
    std::vector<std::string> l = {"PLUG PATH GATE: " + verdict(ok) + " (board " + g(board_w) + " x " + g(board_h) + " mm)",
                                  "  parts entered from the side: " + std::to_string(paths.size()) + " (" + std::to_string(violations.size()) + " blocked)"};
    for (const auto& r : paths)
        l.push_back("    " + std::string(r.ok ? "OK " : "BAD") + " " + pad(r.ref, 9) + " " + pad(r.part, 16) + " mouth->" + pair_repr(r.mouth) +
                    " path " + f(r.depth, 2) + " x " + f(r.width, 2) + " mm above " + f(r.clear_height, 2) + " mm; clear for " +
                    f(r.clearance, 2) + " mm" + (r.blocker.empty() ? std::string() : " up to " + r.blocker) +
                    (r.leaves_board ? "; edge-mounted, the path leaves the board" : ""));
    for (const auto& s : violations) l.push_back("    BLOCKED " + s);
    return join(l);
}

}
