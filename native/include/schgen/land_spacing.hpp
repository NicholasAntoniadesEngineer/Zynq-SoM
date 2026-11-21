#pragma once

#include "schgen/named_constant.hpp"
#include "schgen/pcb_checks.hpp"

#include <array>
#include <string>
#include <vector>

namespace schgen {

namespace land_spacing_constants {
inline constexpr NamedConstant land_quantum{"land_quantum", 1e-4, "mm", "physical",
    "emitted copper carries four decimals, so a spacing that holds before emission holds within this after it"};
inline constexpr std::array land_spacing_registry{land_quantum};
}

struct LandPairNeed {
    double required = 0.0, volts = 0.0, electrical = 0.0, fab = 0.0;
    std::string row;
    bool volts_known = false;
};

LandPairNeed land_pair_need(const LandSpacingPolicy& policy, const std::string& first, const std::string& second);
double net_class_clearance(const PcbCheckModel& model, const std::string& net);
double copper_pair_requirement(const PcbCheckModel& model, bool same_land, const std::string& first, const std::string& second);

struct LandSpacingRow {
    std::string ref, footprint, part, row;
    double gap = 0.0, net_class = 0.0, fab = 0.0, required = 0.0, volts = 0.0;
    bool volts_known = false;
    std::string verdict;
};

struct LandSpacingFinding {
    std::string subject, detail;
};

struct LandSpacingJudgement {
    std::size_t checked = 0;
    double board_required = 0.0;
    std::vector<LandSpacingRow> rows;
    std::vector<LandSpacingFinding> findings;
};

LandSpacingJudgement judge_land_spacing(const PcbCheckInput& input);
LandSpacingPolicy land_spacing_policy(const PartFacts& facts, double fab_minimum, double fab_minimum_track,
                                      const std::vector<std::pair<std::string, double>>& known_volts, double highest_volts);
std::string land_spacing_kicad_rules(const LandSpacingJudgement& judgement);
LandSpacingPolicy board_land_spacing(const PartFacts& facts, const KicadNetlist& netlist);

}
