#pragma once

#include "schgen/json.hpp"
#include "schgen/named_constant.hpp"
#include "schgen/sexpr.hpp"

#include <array>
#include <optional>
#include <stdexcept>
#include <string>
#include <string_view>
#include <vector>

namespace schgen::measure {

class MeasureError : public std::runtime_error {
public:
    using std::runtime_error::runtime_error;
};

using Constant = NamedConstant;

namespace constants {
inline constexpr Constant reference_stride{"reference_stride", 1000.0, "count", "standard",
    "schgen reference numbering is sheet index times this stride plus the local number"};
inline constexpr Constant straight_angle{"straight_angle", 180.0, "deg", "standard",
    "degrees in half a turn"};
inline constexpr Constant half_turn{"half_turn", 3.14159265358979323846, "rad", "standard",
    "radians in half a turn"};
inline constexpr Constant touch_tolerance{"touch_tolerance", 1e-6, "mm", "policy",
    "geometric comparisons closer than this are treated as equal"};
inline constexpr Constant demand_bin{"demand_bin", 5.0, "mm", "policy",
    "edge length of one routing-demand map bin"};
inline constexpr Constant demand_alert{"demand_alert", 0.5, "ratio", "policy",
    "bin utilisation above which a bin is counted as congested"};
inline constexpr Constant edge_band{"edge_band", 2.5, "mm", "policy",
    "a through-hole part within this distance of the outline counts as edge mounted"};
inline constexpr Constant high_quantile{"high_quantile", 0.99, "ratio", "policy",
    "upper tail reported for demand bins"};
inline constexpr Constant upper_quantile{"upper_quantile", 0.90, "ratio", "policy",
    "second tail reported for demand bins"};
inline constexpr Constant middle_quantile{"middle_quantile", 0.50, "ratio", "standard",
    "median"};
inline constexpr Constant lower_quartile{"lower_quartile", 0.25, "ratio", "standard",
    "first quartile"};
inline constexpr Constant upper_quartile{"upper_quartile", 0.75, "ratio", "standard",
    "third quartile"};
inline constexpr Constant longest_count{"longest_count", 10.0, "count", "policy",
    "number of longest signal nets listed"};
inline constexpr Constant length_decimals{"length_decimals", 3.0, "digits", "policy",
    "decimal places for lengths and areas in the report"};
inline constexpr Constant ratio_decimals{"ratio_decimals", 4.0, "digits", "policy",
    "decimal places for ratios in the report"};
inline constexpr Constant map_scale{"map_scale", 4.0, "px/mm", "policy",
    "rendered size of the map"};
inline constexpr Constant map_margin{"map_margin", 6.0, "mm", "policy",
    "blank border around each map panel"};
inline constexpr Constant map_header{"map_header", 9.0, "mm", "policy",
    "height reserved above each map panel for its caption"};
inline constexpr Constant map_stroke{"map_stroke", 0.15, "mm", "policy",
    "line width of map outlines"};
inline constexpr Constant map_text{"map_text", 3.2, "mm", "policy",
    "caption text height on the map"};
inline constexpr Constant part_opacity{"part_opacity", 0.55, "ratio", "policy",
    "fill opacity of courtyards on the map"};

inline constexpr std::array registry{
    reference_stride, straight_angle, half_turn, touch_tolerance, demand_bin, demand_alert,
    edge_band, high_quantile, upper_quantile, middle_quantile, lower_quartile, upper_quartile,
    longest_count, length_decimals, ratio_decimals, map_scale, map_margin, map_header,
    map_stroke, map_text, part_opacity};
inline constexpr std::array exempt_literals{0, 1, 2};
}

inline constexpr std::size_t edge_count = 4;

enum class Face { top, bottom };

struct Rect {
    double x0 = 0, y0 = 0, x1 = 0, y1 = 0;
    double width() const { return x1 - x0; }
    double height() const { return y1 - y0; }
    double area() const { return width() > 0 && height() > 0 ? width() * height() : 0; }
};

struct Pad {
    std::string number, net;
    double x = 0, y = 0, reach = 0;
    bool through = false;
};

struct Part {
    std::string reference, footprint, group;
    Face face = Face::top;
    Rect courtyard;
    bool courtyard_from_pads = false, electrical = false;
    int pin_count = 0;
    std::vector<Pad> pads;
};

struct Zone {
    std::string name, net;
    std::vector<std::string> layers;
    Rect box;
};

struct NetClass {
    std::string name;
    double track_width = 0, clearance = 0;
};

struct ClassPattern {
    std::string pattern, net_class;
};

struct Layer {
    std::string name, kind;
};

struct Board {
    Rect outline;
    std::vector<Layer> copper;
    std::vector<Part> parts;
    std::vector<Zone> zones;
    std::vector<NetClass> classes;
    std::vector<ClassPattern> patterns;
    std::vector<std::string> without_geometry;
};

struct Keepout {
    Face face = Face::top;
    std::string zone;
};

struct Options {
    std::vector<Keepout> keepouts;
    std::vector<std::string> power_classes, excluded_groups;
};

struct FaceMetrics {
    int parts = 0;
    double courtyard = 0, occupied = 0, occupied_clearance = 0, occupied_fanout = 0;
    double keepout = 0, usable = 0, utilisation = 0, utilisation_fanout = 0;
    double demand_fanout = 0;
};

struct GroupMetrics {
    std::string name;
    int parts = 0, bottom_parts = 0;
    double courtyard = 0, box_ratio = 0, busiest_fill = 0;
    Rect box;
    bool excluded = false;
};

struct SubsystemMetrics {
    std::vector<GroupMetrics> groups;
    double box_total = 0, courtyard_total = 0, box_ratio = 0, median_ratio = 0, box_share = 0;
};

struct WireTotals {
    int nets = 0, connections = 0;
    double euclid = 0, manhattan = 0, cross_euclid = 0, cross_manhattan = 0;
};

struct NetLength {
    std::string net;
    double manhattan = 0;
    int pads = 0;
};

struct AirwireMetrics {
    WireTotals plane, power, signal;
    std::vector<NetLength> longest;
};

struct DemandMetrics {
    int columns = 0, rows = 0, congested = 0;
    double default_pitch = 0, mean = 0, peak = 0, high = 0, upper = 0, median = 0;
    std::vector<double> bins;
};

struct GapTier {
    double need = 0, minimum = 0, lower = 0, median = 0, upper = 0, maximum = 0;
    int parts = 0, below = 0;
};

struct EdgePart {
    std::string reference;
    double width = 0;
};

struct EdgeMetrics {
    std::string name;
    double length = 0, run = 0, ratio = 0;
    std::vector<EdgePart> parts;
};

struct BoundMetrics {
    double top_demand = 0, bottom_demand = 0, balanced_demand = 0, outline_ratio = 0;
    double perimeter_run = 0, perimeter_ratio = 0;
};

struct Report {
    Options options;
    double width = 0, height = 0, area = 0;
    int signal_layers = 0, power_layers = 0, parts = 0, through_parts = 0, pad_courtyards = 0;
    std::vector<std::string> without_geometry;
    FaceMetrics top, bottom;
    SubsystemMetrics subsystems;
    AirwireMetrics airwire;
    DemandMetrics demand;
    std::vector<GapTier> gaps;
    std::array<EdgeMetrics, edge_count> edges;
    BoundMetrics bounds;
};

struct InputIdentity {
    std::string name, sha256;
};

Board read_board(const Sexpr& pcb, const JsonNode& project, const JsonNode& sheet_index);
Report measure_board(const Board& board, const Options& options);
std::string report_json(const Report& report, const std::vector<InputIdentity>& inputs);
std::string report_map(const Board& board, const Report& report);
double union_area(const std::vector<Rect>& rects);

}

namespace schgen {
std::optional<int> run_measure_command(int argc, char** argv);
}
