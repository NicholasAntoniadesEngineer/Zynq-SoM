#pragma once

#include "schgen/floorplan.hpp"
#include "schgen/legalize.hpp"
#include "schgen/pack.hpp"
#include "schgen/pack_anchor.hpp"
#include "schgen/pack_edges.hpp"
#include "schgen/pack_refine.hpp"
#include "schgen/quantize.hpp"
#include "schgen/turn.hpp"

#include <array>
#include <memory>

namespace schgen::floorplan_detail {

inline constexpr double clear = .3, edge_margin = 10, mh_corner = 10;
inline constexpr double edge_inset = 1.5, cable_gap = 20, overmold_gap = 3;
inline constexpr double som_halo = 7, edge_band = 11, perimeter = 3, fill = .60;
inline constexpr double som_pad = 1.5, som_seat_band = 6, dec_inset = 6;
inline constexpr double mh_inset = 5, edge_pad_clear = .4;
inline constexpr int occ_top = 1, occ_bottom = 2, occ_punch = 3;
inline constexpr int min_subject_pins = 3;

bool starts(const std::string& value, const std::string& prefix);
std::string number(double value, int precision = -1);
std::string repr(const std::string& value);
JsonNode jvalue(const std::string& value);
JsonNode jvalue(const char* value);
JsonNode jvalue(double value);
JsonNode jvalue(int value);
JsonNode jvalue(bool value);
JsonNode jobject(std::vector<std::pair<std::string, JsonNode>> fields);
JsonNode jarray(std::vector<JsonNode> values);
JsonNode point_json(FloorplanPoint point);
JsonNode halo_json(Halo halo);
int side_mask(const std::string& side);
bool overmold(const FloorplanBlock& block);

struct CachedFootprint {
    Box4 bbox;
    int pins = 0;
    bool has_thru = false;
    // name,type,x,y,angle,width,height, as returned by scan_mod_pads.
    std::vector<std::tuple<std::string, std::string, double, double, double,
                           double, double>> pads;
};
struct Shape {
    double w = 0, h = 0;
    Halo reach, inset;
    std::string side = "top";
    std::vector<Comp> comps;
};
struct SideOffer {
    std::string offered, chosen;
    int shape = 0;
    std::optional<double> incumbent, challenger;
};
struct CrossPart {
    enum class Owner { Zone, SomJack, Decoupling, MountingHole } owner;
    std::string ref, sheet, key, footprint, base_side;
    int owner_index = 0;
    FloorplanPoint offset{};
    std::map<int, FloorplanPoint> shape_offsets;
    std::map<int, std::map<std::string, std::vector<FloorplanPoint>>> pad_positions;
};
struct CrossNetPin {
    std::size_t part;
    std::string pin;
};
struct CrossNet {
    std::string name;
    std::vector<CrossNetPin> pins;
    double via_cost = 0;
};

class Engine {
public:
    explicit Engine(const FloorplanInput& input);
    FloorplanPlan run();
    const FloorplanInput& in;
    FloorplanPlan plan;
    std::map<std::string, const CircuitSheetIr*> sheets;
    std::map<std::string, CachedFootprint> footprint_cache;
    std::map<std::string, FloorplanPoint> zbox;
    std::map<std::string, std::string> edge_of;
    std::map<std::string, std::vector<std::pair<std::string, double>>> affinity;
    std::map<std::string, double> som_pull;
    std::map<std::pair<std::string, std::string>, int> channel_demand;
    std::array<std::map<FloorplanShapeKey, std::vector<Comp>>, 2> components;
    std::array<std::map<std::string, std::vector<Shape>>, 2> shape_sets;
    std::map<std::string, SideOffer> side_offers;
    std::vector<CrossPart> cross_parts;
    std::vector<CrossNet> cross_nets;
    std::map<std::string, std::vector<std::size_t>> nets_by_sheet;
    std::map<std::string, Box4> connector_pad_boxes;
    double far_ceil = 0, max_reach = 0, raw_area = 0;
    int n_sub = 0, n_impedance = 0;
    std::string impedance_classes;
    FloorplanPoint offset{};

    std::vector<FloorplanBlock*> blocks();
    const CachedFootprint& footprint(const std::string& key) const;
    std::optional<std::string> resolved(const CircuitPartIr& part) const;
    FloorplanPoint part_dims(const std::string& footprint) const;
    double sheet_area(const CircuitSheetIr& sheet, double factor) const;
    std::vector<const CircuitPartIr*> zone_parts(const CircuitSheetIr& sheet) const;
    void initialize();
    void prepare_geometry();
    void prepare_cross();
    double estimate(const std::vector<const FloorplanBlock*>& blocks,
                    const std::string& only_sheet = {});
    double estimate();
    std::pair<Halo, Halo> fanout(const FloorplanZoneShape& shape, bool base);
    std::vector<Comp> zone_components(const FloorplanZoneShape& shape,
                                      bool pad_punch) const;
    std::vector<Box4> pad_boxes(const std::string& key, double rotation,
                                bool thru_only = false) const;
    void board_size(double w, double h);
    bool attempt_pack(bool compact);
    void choose_connector_shapes();
    PackAnchorIn anchor_row(const FloorplanBlock& b,
                            const std::map<std::string, FloorplanPoint>& centers) const;
    std::vector<Box4> som_keepouts() const;
    void ledger_initial(double seed_w, double seed_h);
    void ledger_open();
    void ledger_pass(bool free);
    void ledger_sides();
    void calc(const std::string& name, JsonNode value,
              std::vector<std::pair<std::string, JsonNode>> inputs,
              const std::string& step = "floorplan.sizing");
    void fallback(const std::string& name);
    double quantize(const std::string& name, double value);
};

}  // namespace schgen::floorplan_detail
