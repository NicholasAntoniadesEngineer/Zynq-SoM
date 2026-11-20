#include "schgen/module_mating.hpp"
#include "schgen/placement_integrity.hpp"

#include <sstream>

namespace schgen::rules {
namespace {

constexpr Rule rule{
    "module-mating", "mechanical",
    "Every pad of every module connector on the board sits on the pad of the same number of the module's declared mate footprint, posed where the module's own board file puts that connector; the mate footprint's pads lie on the receptacle pads of the same number.",
    "The module plugs onto these connectors. A pad that is off its mate, or a pin number that lands on another pin, leaves the module unmated or connects every net to the wrong contact.",
    "owner decision, 2026-11-21 (the module is the fixed reference and the board must match it); Hirose DF40 catalogue 2013.11 feature 4 (0.33 mm self-alignment, context only)",
    "owner decision", Enforcement::gate, Stage::placement};

RuleResult check(const RuleContext& context) {
    RuleResult result{&rule, 0, {}, {}};
    const auto& mates = context.model().module_mates;
    std::map<std::string, const PcbCheckInstance*> mating_parts;
    for (const auto& mate : mates)
        for (const auto& instance : context.parts())
            if (instance.ref == mate.ref) mating_parts[mate.connector] = &instance;
    for (std::size_t part = 0; part < context.parts().size(); ++part) {
        if (!context.module_connector(part)) continue;
        const bool declared = std::any_of(mates.begin(), mates.end(),
                                          [&](const ModuleMate& mate) { return mate.ref == context.parts()[part].ref; });
        if (!declared) result.findings.push_back({context.label(part), "is a module connector with no declared module mate"});
    }
    if (mates.empty()) return result;
    if (!context.model().module_origin) {
        result.findings.push_back({"module", "the board model does not state where the module sits"});
        return result;
    }
    const auto judged = judge_module_mating(mates, mating_parts, context.model().module_origin);
    for (const auto& connector : judged.connectors) {
        result.checked += connector.pins;
        std::ostringstream row;
        row << connector.ref << " mates module " << connector.connector << ": worst pad error " << connector.worst_pad_error
            << " mm over " << connector.pins << " pins, mate-to-receptacle row inset " << connector.row_inset
            << " mm (the module's own land patterns; self-alignment " << mating_constants::self_alignment.value << " mm)";
        result.measurements.push_back(row.str());
        for (const auto& finding : connector.findings)
            result.findings.push_back({connector.ref + " pin " + finding.pin, finding.detail});
    }
    return result;
}

}

extern const RuleEntry module_mating{rule, check};

}
