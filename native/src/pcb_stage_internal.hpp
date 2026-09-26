#pragma once
#include "schgen/embed_fp.hpp"
#include "schgen/pack.hpp"
#include "schgen/pack_edges.hpp"
#include "schgen/pcb_stage_templates.hpp"
#include "schgen/quantize.hpp"
#include "schgen/turn.hpp"
#include <algorithm>
#include <cmath>
#include <limits>
#include <numeric>

namespace schgen::pcb_stage {
inline constexpr double clear = .5, zone_pad = .3, slide = 1.2;
using NamedBoxes = std::vector<std::pair<std::string, Box4>>;
using Parts = std::vector<struct Part>;
const JsonNode &field(const JsonNode &, const std::string &);
const JsonNode &optional(const JsonNode &, const std::string &);
std::string text(const JsonNode &, const std::string &, const std::string &fallback = "");
double number(const JsonNode &, const std::string &, double fallback = 0);
std::vector<std::string> strings(const JsonNode &);
std::vector<std::string> strings(const JsonNode &, const std::string &);
std::vector<Box4> values(const NamedBoxes &);
Box4 pinbox(const NamedBoxes &, const std::vector<std::string> &);
const Box4 &at(const NamedBoxes &, const std::string &);
double distance(const NamedBoxes &, const NamedBoxes &, const std::vector<std::string> &pins = {});
std::optional<FloorplanPoint> direction(const std::string &);
bool connector(const PcbCheckFootprint &);
bool connector_value(const std::string &);
double connector_rotation(const PcbCheckFootprint &, const std::string &);
double connector_rotation(const std::string &, const std::string &);
double connector_rotation(const PcbCheckFootprint &, const std::string &, QuantizationCounts &);
double connector_rotation(const std::string &, const std::string &, QuantizationCounts &);
double need(int pins);
bool passive(const std::string &, int);
double normalize(double);
struct Part {
    std::string ref;
    PcbCheckFootprintPtr mod;
    double rot = 0, x = 0, y = 0;
};
struct Attract {
    std::string ref;
    std::vector<std::string> pins;
    double bound = 0;
};
struct Repel {
    std::string ref, pin;
    double minimum = 0;
};
struct Demand {
    std::string ref;
    std::vector<std::string> pins;
    double bound = 0;
    std::vector<std::string> keep;
    double minimum = 0;
};
class Engine {
  public:
    explicit Engine(const PcbStageInput &in) : in(in) {}
    const PcbStageInput &in;
    std::vector<std::string> events;
    std::map<std::string, std::size_t> quantization;
    double credit(double v) {
        checked_quantization_add(quantization, "quant_credit");
        return quant_credit(v);
    }
    double tight_bound(double v) {
        checked_quantization_add(quantization, "snap_erosion_bound");
        return snap_erosion_bound(v);
    }
    double tight_pad(double v) {
        checked_quantization_add(quantization, "snap_erosion_pad");
        return snap_erosion_pad(v);
    }
    double seat_slide() {
        checked_quantization_add(quantization, "seat_slide");
        return slide;
    }
    std::map<std::pair<const PcbCheckFootprint *, double>, NamedBoxes> pad_cache;
    const NamedBoxes &pads(const PcbCheckFootprintPtr &, double = 0);
    NamedBoxes pads(const Part &);
    Box4 body(const Part &) const;
    std::vector<Box4> bodies(const Parts &) const;
    Part part(const std::string &, double = 0, double = 0, double = 0) const;
    bool overlap(const Parts &) const;
    Box4 extent(const Parts &) const;
    FloorplanPoint row_extent(const Parts &) const;
    std::string bref(const std::string &) const;
    Part beside(const std::string &, double, Box4, const std::string &, double,
                std::optional<double> = {});
    std::vector<Part> candidates(const std::string &, const std::vector<Attract> &,
                                 const std::vector<Repel> &, const Parts &, double,
                                 const std::vector<Box4> & = {});
    Parts seat_all(const std::vector<Demand> &, const NamedBoxes &, Box4, const Parts &, double,
                   bool);
    Parts buck(const std::string &, const std::vector<std::string> &,
               const std::vector<std::string> &, const std::vector<std::string> &,
               const std::string &, const std::vector<std::string> &, const std::string &,
               const std::string &, const std::string &, const std::string &, const std::string &,
               const std::map<std::string, std::string> &);
    Parts ldo(const std::string &, const std::string &, const std::string &, const std::string &,
              const std::string &);
    Parts proximity_cluster(const std::string &);
    Parts solve_contract();
    double flip_rotation(const std::string &);
    Parts compose(const std::vector<Parts> &, const std::set<std::string> &);
    Parts turn(const Parts &, double, bool renormalize = true, bool exact_half = false,
               bool account_refit = false);
    Parts face(const Parts &, const std::set<std::string> &, bool media);
    PcbStageResult proximity_zone();
    PcbStageResult hot_zone();
    std::pair<ShelfPacked, ShelfPacked> leftover(const std::vector<std::string> &, double) const;
    std::set<std::string> output_refs() const;
};
inline const Part *find(const Parts &parts, const std::string &ref) {
    auto i = std::find_if(parts.begin(), parts.end(), [&](const Part &p) { return p.ref == ref; });
    return i == parts.end() ? nullptr : &*i;
}
inline Parts shifted(Parts parts, double x, double y) {
    for (auto &p : parts) {
        p.x = py_round(p.x + x, 4);
        p.y = py_round(p.y + y, 4);
    }
    return parts;
}
} // namespace schgen::pcb_stage
