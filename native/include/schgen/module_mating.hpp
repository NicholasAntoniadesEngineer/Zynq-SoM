#pragma once

#include "schgen/named_constant.hpp"
#include "schgen/pcb_checks.hpp"
#include "schgen/pcb_scan.hpp"

#include <array>
#include <map>
#include <optional>
#include <set>
#include <string>
#include <utility>
#include <vector>

namespace schgen {

namespace mating_constants {
inline constexpr NamedConstant mate_quantum{"mate_quantum", 1e-4, "mm", "physical",
    "emitted board coordinates carry four decimals, so a pad pair that coincides before emission differs by at most this much after it"};
inline constexpr NamedConstant self_alignment{"self_alignment", 0.33, "mm", "datasheet",
    "Hirose DF40 catalogue 2013.11, feature 4: guide ribs allow 0.33 mm of self-alignment while mating; reported as context, never used as an allowance"};
inline constexpr NamedConstant quarter_turn{"quarter_turn", 90, "degrees", "physical",
    "a connector lands on the board in one of four quarter-turn orientations"};
inline constexpr std::array mating_registry{mate_quantum, self_alignment, quarter_turn};
}

struct MatePadFinding {
    std::string pin, detail;
};

struct ModuleMate {
    std::string connector, ref;
    double turn = 0.0;
    std::vector<SomPad> receptacle, mate;
};

struct MateConnectorJudgement {
    std::string connector, ref;
    std::size_t pins = 0;
    double worst_pad_error = 0.0, row_inset = 0.0;
    std::vector<MatePadFinding> findings;
};

struct ModuleMatingJudgement {
    std::vector<MateConnectorJudgement> connectors;
    std::pair<double, double> origin{0.0, 0.0};
    bool ok() const;
};

std::vector<SomPad> posed_footprint_pads(const PcbCheckFootprint& footprint, double x, double y, double turn);
ModuleConnectorGeom fit_module_mate(const ModuleConnectorGeom& receptacle, const PcbCheckFootprint& mate, const std::set<std::string>& pins);
std::vector<MatePadFinding> module_row_consistency(const ModuleMate& mate, double* row_inset);
ModuleMatingJudgement judge_module_mating(const std::vector<ModuleMate>& mates,
                                          const std::map<std::string, const PcbCheckInstance*>& mating_parts,
                                          const std::optional<std::pair<double, double>>& origin);

}
