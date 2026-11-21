#include "schgen/land_spacing.hpp"

#include <iostream>
#include <sstream>
#include <stdexcept>

namespace {

using namespace schgen;

constexpr double pad_width = 0.23, pad_length = 0.66, fab_minimum = 0.09, low_rail = 3.3, high_rail = 40.0;
constexpr double native_gap = 0.17, tolerance = 0.02, too_close = 0.05, highest = 30.0;
constexpr double low_row = 15.0, middle_row = 30.0, top_row = 50.0, low_spacing = 0.1, top_spacing = 0.6;
const char* const footprint_id = "Fixture:Land";

std::size_t checks = 0;

void require(bool ok, const std::string& why) {
    ++checks;
    if (!ok) throw std::runtime_error("land spacing contract: " + why);
}

PcbCheckFootprintPtr land(double gap) {
    std::ostringstream text;
    text << "(footprint \"Land\" (layer \"F.Cu\")"
         << " (pad \"1\" smd rect (at 0 0) (size " << pad_width << " " << pad_length << ") (layers \"F.Cu\"))"
         << " (pad \"2\" smd rect (at " << pad_width + gap << " 0) (size " << pad_width << " " << pad_length << ") (layers \"F.Cu\")))";
    return pcb_check_footprint(std::string("land_") + std::to_string(gap) + ".kicad_mod", text.str());
}

PcbCheckModel board(double gap, const std::string& second_net, bool with_fact) {
    PcbCheckModel model;
    model.netclass_of["RAIL"] = "POWER";
    model.netclass_of["HIGH"] = "POWER";
    PcbCheckInstance instance;
    instance.ref = "U1";
    instance.footprint = footprint_id;
    instance.mod = land(gap);
    instance.x = 0;
    instance.y = 0;
    instance.pad_nets["1"] = {1, "RAIL"};
    instance.pad_nets["2"] = {2, second_net};
    model.insts.push_back(instance);
    PartFacts facts;
    facts.electrical_spacing = {"IPC-2221B Table 6-1", "B2", "fixture",
                                {{low_row, low_spacing}, {middle_row, low_spacing}, {top_row, top_spacing}}};
    if (with_fact) facts.lands["Fixture"] = {footprint_id, "fixture citation", native_gap, tolerance};
    model.land_spacing = land_spacing_policy(facts, fab_minimum, fab_minimum, {{"RAIL", low_rail}, {"GND", 0}, {"HIGH", high_rail}}, highest);
    return model;
}

}

int main() {
    try {
        const auto sound = judge_land_spacing(PcbCheckInput(board(native_gap, "GND", true)));
        require(sound.findings.empty() && sound.rows.size() == 1, "a cited land at its own gap passes and is listed");
        require(judge_land_spacing(PcbCheckInput(board(too_close, "GND", true))).findings.size() > 0,
                "a same-footprint pair below the fabricator minimum fails");
        const auto electrical = judge_land_spacing(PcbCheckInput(board(native_gap, "HIGH", true)));
        require(!electrical.findings.empty(), "a same-footprint pair below the electrical minimum for its voltage fails");
        require(!judge_land_spacing(PcbCheckInput(board(native_gap, "GND", false))).findings.empty(),
                "a land below its net-class clearance with no lands row fails");
        const auto disagreeing = judge_land_spacing(PcbCheckInput(board(native_gap - tolerance - tolerance - tolerance, "GND", true)));
        require(!disagreeing.findings.empty() && disagreeing.rows.front().verdict.rfind("FAIL", 0) == 0,
                "a measured gap that disagrees with its lands row fails");
        const auto model = board(native_gap, "GND", true);
        require(copper_pair_requirement(model, false, "RAIL", "GND") > native_gap,
                "a pair from different footprints at the land gap still fails the net-class clearance");
        require(copper_pair_requirement(model, true, "RAIL", "GND") <= native_gap,
                "the same pair inside one land is judged by the land spacing");
        const auto unknown = land_pair_need(*model.land_spacing, "RAIL", "UNNAMED");
        require(!unknown.volts_known && unknown.volts == highest, "an unknown net takes the highest board voltage, never the lowest");
        require(land_spacing_kicad_rules(sound).find("A.Parent == B.Parent") != std::string::npos,
                "the KiCad rule is scoped to pads of one footprint by a generic condition");
        std::cout << "PASS " << checks << " land spacing checks\n";
        return 0;
    } catch (const std::exception& error) {
        std::cerr << error.what() << "\n";
        return 1;
    }
}
