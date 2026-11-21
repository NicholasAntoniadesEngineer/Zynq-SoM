#include "schgen/land_spacing.hpp"
#include "schgen/placement_integrity.hpp"

#include <sstream>

namespace schgen::rules {
namespace {

constexpr Rule rule{
    "land-spacing", "mechanical",
    "Two copper items of the same footprint's land on different nets keep the larger of the fabricator's minimum spacing and the electrical spacing for the voltage between them; a land whose own gap is below its net-class clearance is backed by the manufacturer's recommended land in the part facts.",
    "The net-class clearance is a routing rule. The spacing between the pads of one part is fixed by the part's land pattern and is limited by what the fabricator can etch and by the voltage across the gap, not by the net class.",
    "owner decision, 2026-11-21; IPC-2221B Table 6-1 (column and rows in parts/part_facts.json electrical_spacing); fabricator minimum from the board's fab profile",
    "owner decision", Enforcement::gate, Stage::placement};

RuleResult check(const RuleContext& context) {
    RuleResult result{&rule, 0, {}, {}};
    const auto judged = judge_land_spacing(context.input());
    result.checked = judged.checked;
    for (const auto& row : judged.rows) {
        std::ostringstream text;
        text << row.ref << " (" << (row.part.empty() ? row.footprint : row.part) << "): land gap " << row.gap
             << " mm below its net-class clearance " << row.net_class << " mm; fabricator minimum " << row.fab << " mm; "
             << row.row << (row.volts_known ? "" : " (voltage unknown, highest board voltage used)") << "; required "
             << row.required << " mm; " << row.verdict;
        result.measurements.push_back(text.str());
    }
    for (const auto& finding : judged.findings) result.findings.push_back({finding.subject, finding.detail});
    return result;
}

}

extern const RuleEntry land_spacing{rule, check};

}
