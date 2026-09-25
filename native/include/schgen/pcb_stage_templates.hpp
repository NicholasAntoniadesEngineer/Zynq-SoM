#pragma once

#include "schgen/floorplan.hpp"
#include "schgen/pcb_model.hpp"
#include "schgen/ratsnest.hpp"

namespace schgen {

class PcbZoneInfeasible : public std::runtime_error {
  public:
    using std::runtime_error::runtime_error;
};
using PcbPadNets = std::map<std::pair<std::string, std::string>, std::string>;
using PcbInterNets = std::map<std::string, std::map<std::string, std::vector<std::string>>>;
struct PcbStagePartner {
    PcbCheckFootprintPtr footprint;
    double rotation = 0;
    std::map<std::string, std::vector<std::string>> nets;
};
// Complete invocation-owned source inputs; no source loader or process cache.
// refs and contract object fields retain authoring order for solver ties.
struct PcbStageInput {
    std::string sheet;
    JsonNode contract;
    std::vector<std::string> refs;
    std::map<std::string, std::string> side_of, board_refs;
    std::map<std::string, Box4> bbox_of;
    std::map<std::string, PcbCheckFootprintPtr> footprints;
    PcbPadNets pad_nets;
    PcbInterNets inter_nets;
    std::map<std::string, PcbStagePartner> partners;
    bool pilot = false;
    std::string facing, outer_dir;
    double place_clear = .5;
};
struct PcbStageResult {
    FloorplanOffsets top, bottom;
    FloorplanRotations rotations;
    double w = 0, h = 0;
    std::vector<std::string> fallback_events;
    std::map<std::string, std::size_t> quantization_engagements;
};
std::set<std::string> pcb_contract_members(const PcbStageInput &);
PcbStageResult build_pcb_stage_zone(const PcbStageInput &);
// Board-frame downstream-facing refit: returns nullopt when the original pose
// wins. Existing native MST ties and the strict facing gate are retained.
std::optional<std::map<std::string, std::tuple<double, double, double>>> refit_pcb_stage_facing(
    const PcbStageInput &, const FloorplanOffsets &, const FloorplanRotations &,
    FloorplanPoint downstream,
    const std::map<std::string, std::vector<std::pair<std::string, std::string>>> &net_pins,
    const std::map<std::string, std::vector<std::tuple<double, double, std::string>>> &foreign);

} // namespace schgen
