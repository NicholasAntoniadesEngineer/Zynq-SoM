#pragma once

#include "schgen/layout_geometry.hpp"

#include <optional>
#include <string>
#include <utility>
#include <vector>

namespace schgen::layout {

inline constexpr int no_net = -1;

enum class Category : std::uint8_t { plane, power, signal };

struct PadShape {
    std::string name;
    Point centre;
    Box box;
    bool through = false;
    Nm radius = 0;
};

struct Variant {
    Box gate_box;
    std::vector<Box> court_boxes;
    std::vector<Disc> court_discs;
    std::vector<PadShape> pads;
    std::optional<Box> pad_hull;
};

struct Footprint {
    std::string key;
    bool flippable = false;
    Variant top, bottom;
    const Variant& on(Face face) const { return face == Face::top ? top : bottom; }
};

struct Part {
    std::string reference, group, value, footprint_name;
    std::size_t footprint = 0;
    std::vector<int> pad_nets;
    int fanout_pins = 0;
    Nm fanout_need = 0;
    bool fanout_subject = false, never_crowds = false, cluster_passive = false;
    bool fixed = false, top_only = false, core_exempt = false, cohesion_member = true;
};

struct Pin {
    std::size_t part = 0, pad = 0;
};

struct Net {
    std::string name;
    Category category = Category::signal;
    Nm clearance = 0;
    std::vector<Pin> pins;
};

struct Board {
    Point origin;
    Nm width = 0, height = 0;
    std::optional<Box> module_core;
    Box outline() const { return {origin.x, origin.y, origin.x + width, origin.y + height}; }
};

struct Obstacle {
    Box box;
    std::optional<Disc> disc;
    bool top = false, bottom = false;
    int net = no_net;
};

struct Rules {
    Nm core_tolerance = 0, copper_clearance = 0, edge_clearance = 0, plane_margin = 0;
    double dispersion_limit = 0;
    std::size_t dispersion_floor = 0;
};

struct Pose {
    Point at;
    Turn turn = Turn::none;
    Face face = Face::top;
};

constexpr bool operator==(const Pose& a, const Pose& b) {
    return a.at == b.at && a.turn == b.turn && a.face == b.face;
}
constexpr bool operator!=(const Pose& a, const Pose& b) { return !(a == b); }

using Placement = std::vector<Pose>;

struct Problem {
    Board board;
    Rules rules;
    std::vector<Footprint> footprints;
    std::vector<Part> parts;
    std::vector<Net> nets;
    std::vector<Obstacle> obstacles;
};

void validate(const Problem& problem, const Placement& placement);

}
