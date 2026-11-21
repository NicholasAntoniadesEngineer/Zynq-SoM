#include "schgen/land_spacing.hpp"

#include "schgen/pack.hpp"
#include "schgen/manufacturing_checks.hpp"
#include "schgen/power_checks.hpp"

#include <algorithm>
#include <cmath>
#include <limits>
#include <sstream>
#include <stdexcept>

namespace schgen {
namespace {

using land_spacing_constants::land_quantum;

double box_distance(const Box4& a, const Box4& b) {
    const double dx = std::max({0.0, a.x0 - b.x1, b.x0 - a.x1});
    const double dy = std::max({0.0, a.y0 - b.y1, b.y0 - a.y1});
    return std::hypot(dx, dy);
}

std::string millimetres(double value) {
    std::ostringstream text;
    text << value;
    return text.str();
}

}

LandPairNeed land_pair_need(const LandSpacingPolicy& policy, const std::string& first, const std::string& second) {
    LandPairNeed need;
    const auto a = policy.net_volts.find(first), b = policy.net_volts.find(second);
    need.volts_known = a != policy.net_volts.end() && b != policy.net_volts.end();
    need.volts = need.volts_known ? std::fabs(a->second - b->second) : policy.highest_volts;
    double lower = 0.0;
    const ElectricalSpacingRow* row = nullptr;
    for (const auto& candidate : policy.electrical.rows) {
        if (need.volts <= candidate.max_volts) {
            row = &candidate;
            break;
        }
        lower = candidate.max_volts;
    }
    if (!row)
        throw std::runtime_error("land spacing: " + millimetres(need.volts) + " V between " + first + " and " + second +
                                 " is above every row of " + policy.electrical.source);
    need.row = policy.electrical.column + " " + millimetres(lower) + "-" + millimetres(row->max_volts) + " V";
    need.electrical = row->spacing_mm;
    need.fab = policy.fab_minimum;
    need.required = std::max(need.electrical, need.fab);
    return need;
}

double net_class_clearance(const PcbCheckModel& model, const std::string& net) {
    const auto found = model.netclass_of.find(net);
    return net_clearance_rule(found != model.netclass_of.end() && found->second == "POWER");
}

double copper_pair_requirement(const PcbCheckModel& model, bool same_land, const std::string& first, const std::string& second) {
    if (same_land && model.land_spacing) return land_pair_need(*model.land_spacing, first, second).required;
    return std::max(net_class_clearance(model, first), net_class_clearance(model, second));
}

LandSpacingPolicy land_spacing_policy(const PartFacts& facts, double fab_minimum, double fab_minimum_track,
                                      const std::vector<std::pair<std::string, double>>& known_volts, double highest_volts) {
    LandSpacingPolicy policy;
    policy.fab_minimum = fab_minimum;
    policy.fab_minimum_track = fab_minimum_track;
    policy.highest_volts = highest_volts;
    policy.electrical = facts.electrical_spacing;
    for (const auto& [part, fact] : facts.lands)
        if (!policy.lands.emplace(fact.footprint, std::make_pair(part, fact)).second)
            throw std::runtime_error(facts.file.string() + ": two lands rows name footprint " + fact.footprint);
    for (const auto& [net, volts] : known_volts) policy.net_volts[net] = volts;
    return policy;
}

LandSpacingJudgement judge_land_spacing(const PcbCheckInput& input) {
    LandSpacingJudgement out;
    const auto& model = input.model();
    if (!model.land_spacing) {
        if (!model.insts.empty()) out.findings.push_back({"board", "the board model carries no land-spacing policy"});
        return out;
    }
    const LandSpacingPolicy& policy = *model.land_spacing;
    for (std::size_t index = 0; index < model.insts.size(); ++index) {
        const auto& instance = model.insts[index];
        if (!instance.mod) continue;
        struct Land {
            std::string pad, net;
            Box4 box;
        };
        std::vector<Land> lands;
        for (const auto& [pad, box] : input.geometry_at(index).pad_boxes) {
            if (pad.empty()) continue;
            const auto net = instance.pad_nets.find(pad);
            lands.push_back({pad, net == instance.pad_nets.end() ? std::string{} : net->second.second, box});
        }
        bool below_net_class = false;
        LandSpacingRow row;
        row.ref = instance.ref;
        row.footprint = instance.footprint;
        row.gap = std::numeric_limits<double>::infinity();
        double shortfall = -std::numeric_limits<double>::infinity();
        for (std::size_t first = 0; first < lands.size(); ++first)
            for (std::size_t second = first + 1; second < lands.size(); ++second) {
                const Land& a = lands[first];
                const Land& b = lands[second];
                if (a.net == b.net) continue;
                ++out.checked;
                const double gap = box_distance(a.box, b.box);
                const auto need = land_pair_need(policy, a.net, b.net);
                out.board_required = std::max(out.board_required, need.required);
                const double net_class = std::max(net_class_clearance(model, a.net), net_class_clearance(model, b.net));
                if (net_class - gap > shortfall) {
                    shortfall = net_class - gap;
                    row.gap = gap;
                    row.net_class = net_class;
                    row.fab = need.fab;
                    row.required = need.required;
                    row.volts = need.volts;
                    row.volts_known = need.volts_known;
                    row.row = need.row;
                }
                if (gap + land_quantum.value < net_class) below_net_class = true;
                if (gap + land_quantum.value < need.required)
                    out.findings.push_back({instance.ref + " pads " + a.pad + "/" + b.pad,
                                            "land gap " + millimetres(gap) + " mm is below the land spacing " +
                                                millimetres(need.required) + " mm (fabricator " + millimetres(need.fab) + " mm, " +
                                                need.row + " " + millimetres(need.electrical) + " mm)"});
            }
        if (!below_net_class) continue;
        const auto fact = policy.lands.find(instance.footprint);
        if (fact == policy.lands.end()) {
            row.verdict = "FAIL: no lands row backs this land";
            out.findings.push_back({instance.ref, "land gap " + millimetres(row.gap) + " mm is below its net-class clearance " +
                                                      millimetres(row.net_class) + " mm and no lands row in the part facts backs " +
                                                      instance.footprint});
        } else {
            row.part = fact->second.first;
            if (std::fabs(row.gap - fact->second.second.pad_gap_mm) > fact->second.second.tolerance_mm + land_quantum.value) {
                row.verdict = "FAIL: measured gap disagrees with the lands row";
                out.findings.push_back({instance.ref, "land gap " + millimetres(row.gap) + " mm disagrees with the " +
                                                          millimetres(fact->second.second.pad_gap_mm) + " mm of the lands row for " +
                                                          row.part});
            } else {
                row.verdict = "PASS: " + fact->second.second.cite;
            }
        }
        out.rows.push_back(row);
    }
    return out;
}

LandSpacingPolicy board_land_spacing(const PartFacts& facts, const KicadNetlist& netlist, const PowerPolicy& power) {
    std::vector<std::pair<std::string, double>> known;
    double highest = 0.0;
    for (const auto& [rail, source] : power.sources) {
        (void)rail;
        highest = std::max(highest, source.volts);
    }
    for (const auto& [rail, row] : power.rails) {
        (void)rail;
        if (row.volts) highest = std::max(highest, *row.volts);
    }
    if (highest <= 0.0) throw std::runtime_error("land spacing: the board power data states no rail voltage, so unknown nets have no maximum");
    for (const auto& [net, pins] : netlist) {
        (void)pins;
        if (const auto volts = rail_volts(net, power)) known.emplace_back(net, *volts);
    }
    const auto fab = manufacturing_fab_minimums();
    return land_spacing_policy(facts, fab.min_clearance_mm, fab.min_trace_mm, known, highest);
}

std::string land_spacing_kicad_rules(const LandSpacingJudgement& judgement) {
    std::ostringstream text;
    text << "(version 1)\n\n(rule \"land_spacing\"\n  (condition \"A.Type == 'Pad' && B.Type == 'Pad' && A.Parent == B.Parent\")\n"
         << "  (constraint clearance (min " << judgement.board_required << "mm))\n)\n";
    return text.str();
}

}
