#include "schgen/placement_integrity.hpp"

#include <algorithm>
#include <sstream>

namespace schgen::rules {
namespace {

constexpr Rule rule{
    "input-capacitor-nearest", "power",
    "At every input pin of a switching regulator, the nearest of all the parts authored to serve that regulator is a capacitor serving that pin.",
    "The input capacitor closes the loop with the fastest current edges, so it is placed first and nothing may take its place at the pin.",
    "TI SLYT614, Five steps to a great PCB layout for a step-down converter, https://www.ti.com/lit/an/slyt614/slyt614.pdf; "
    "TI LM61460 datasheet, section 11 Layout, https://www.ti.com/lit/ds/symlink/lm61460.pdf",
    "primary vendor document", Enforcement::measured};

RuleResult check(const RuleContext& context) {
    RuleResult result{&rule, 0, context.unresolved(roles_with(&RoleRule::marks_regulator)), {}};
    for (const Regulator& regulator : context.regulators()) {
        const std::string subject = context.label(regulator.part);
        if (regulator.inputs.empty())
            result.findings.push_back({subject, "has no pin named as a supply input (VIN, PVIN or IN), so its input capacitor cannot be identified"});
        for (const RegulatorInput& input : regulator.inputs) {
            ++result.checked;
            const std::string pin = input.name + " (pad " + input.pad + ")";
            if (input.capacitors.empty()) {
                result.findings.push_back({subject, "has no authored bypass or reservoir capacitor serving its input pin " + pin});
                continue;
            }
            const auto gap = [&](std::size_t member) { return *context.pad_gap(regulator.part, {input.pad}, member); };
            const std::size_t capacitor = input.capacitors.front();
            const std::size_t nearest = *std::min_element(regulator.supports.begin(), regulator.supports.end(),
                [&](std::size_t first, std::size_t second) { return gap(first) < gap(second); });
            std::ostringstream row;
            row << subject << " " << pin << ": input capacitor " << context.parts()[capacitor].ref << " at "
                << gap(capacitor) << " mm";
            result.measurements.push_back(row.str());
            if (gap(capacitor) <= gap(nearest) + constants::judging_resolution.value) continue;
            std::ostringstream detail;
            detail << "input pin " << pin << ": the nearest authored part is " << context.label(nearest) << " at "
                   << gap(nearest) << " mm, nearer than its input capacitor " << context.parts()[capacitor].ref << " at "
                   << gap(capacitor) << " mm";
            result.findings.push_back({subject, detail.str()});
        }
    }
    return result;
}

}

extern const RuleEntry input_capacitor_nearest{rule, check};

}
