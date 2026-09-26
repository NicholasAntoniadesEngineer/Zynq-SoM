#pragma once
#include "pcb_stage_internal.hpp"
#include "schgen/board_schematic.hpp"
#include "schgen/mirror.hpp"
#include "schgen/pcb_placement.hpp"
#include "schgen/experiment_observers.hpp"
#include "schgen/reorder.hpp"

namespace schgen::pcb_placement {
using namespace pcb_stage;
using Geometry = FloorplanZoneGeometry;
using Shape = FloorplanZoneShape;
using Offsets = FloorplanOffsets;
using Rotations = FloorplanRotations;
struct BoardPart {
    std::string ref, lib_ref, sheet, footprint, value, lib_id;
};
struct Context {
    explicit Context(const PcbPlacementInput &);
    const PcbPlacementInput &in;
    std::vector<BoardPart> parts;
    std::map<std::string, BoardPart> by_ref;
    std::map<std::string, std::map<std::string, std::string>> board_refs;
    PcbFootprintPool pool;
    std::map<std::string, std::optional<DifferentialGeometry>> classes;
    std::map<std::string, std::string> netclass_of;
    std::map<std::string, PcbStagePartner> partners;
    std::set<std::string> wired, pilot, l4_exempt;
    double clearance;
    mutable std::map<std::string, std::size_t> quantization;
    double credit(double v) const {
        checked_quantization_add(quantization, "quant_credit");
        return quant_credit(v);
    }
    double fixed_grid(double value, const std::string& label = "fixed_part_grid") const {
        checked_quantization_add(quantization, label);
        return fixed_part_grid(value);
    }
    double corridor_grid(double origin, double value) const {
        checked_quantization_add(quantization, "evict_corridor_grid");
        return evict_corridor_grid(origin, value);
    }
    PcbCheckFootprintPtr resolve(const std::string &) const;
    std::string key(const std::string &) const;
    PcbStageInput stage_input(const std::string &, const Geometry &) const;
};
bool face_top(const BoardPart &);
bool edge_family(const std::string &);
PcbStageResult pack_zone(const Context &, const Geometry &, const std::vector<std::string> &,
                         double, const Rotations & = {}, const std::string & = "",
                         const std::set<std::string> & = {},
                         const std::map<std::string, std::string> * = nullptr);
bool mirror_holds(const Context &, const Geometry &, const std::string &, const Shape &);
std::optional<Shape> member_mirror(const Context &, const Geometry &, const std::string &,
                                   const PcbStageResult &, const Rotations &);
std::vector<Shape> bottom_shapes(Context &, const Geometry &, const std::string &,
                                 const std::set<std::string> &,
                                 const std::optional<PcbStageResult> &,
                                 const std::set<std::string> &, std::vector<std::string> &);
Shape turned(const Shape &);

struct Placer {
    Placer(const PcbPlacementInput &, const PcbZoneResult &, const FloorplanStage &);
    Context ctx;
    Geometry geometry;
    const FloorplanPlan &plan;
    PcbPlacementResult out;
    Offsets pos, origins;
    Rotations rotations;
    std::map<std::string, std::string> som_refs;
    std::set<std::string> grid_placed, fixed, contract_members;
    std::map<std::pair<std::string, std::string>, std::pair<int, std::string>> pin_net;
    std::map<std::string, int> net_numbers;
    Box4 keepout;
    double width, height;
    std::map<std::string, PcbPlacementPose> previous;
    std::string previous_domain;
    double rot(const std::string &) const;
    std::string side(const std::string &) const;
    PcbCheckFootprintPtr mod(const std::string &) const;
    Box4 box(const std::string &, FloorplanPoint) const;
    int pins(const std::string &) const;
    void checkpoint(const std::string &, bool = false);
    void observe_checkpoint(const std::string &) const;
    void seed();
    void l4_pull();
    void edge_seat();
    void breathe(const std::string &);
    void refit();
    void reorder();
    void evict();
    void instantiate();
    void escape();
};
} // namespace schgen::pcb_placement
