#include "schgen/placement_integrity.hpp"

namespace schgen::rules {
namespace {

constexpr Rule rule{
    "regulator-over-ground", "power",
    "A switching regulator and its inductor sit only on a face whose neighbouring copper layer is a ground plane.",
    "The image current in a ground plane directly beneath the switching loop cancels most of the loop's field; without it the loop inductance is many times larger.",
    "Analog Devices AN-139, Power Supply Layout and EMI, https://www.analog.com/media/en/technical-documentation/application-notes/an139f.pdf",
    "primary vendor document", Enforcement::gate};

RuleResult check(const RuleContext& context) {
    RuleResult result{&rule, 0, context.unresolved(roles_with(&RoleRule::marks_regulator)), {}};
    const auto judge = [&](std::size_t part, const std::string& what) {
        ++result.checked;
        if (context.ground_beneath(part)) return;
        result.findings.push_back({context.label(part), what + " sits on the " + context.face(part) + " face, whose neighbour " +
                                                            context.neighbour(part) + ", not a ground plane"});
    };
    for (const Regulator& regulator : context.regulators()) {
        judge(regulator.part, "switching regulator");
        if (regulator.inductors.empty())
            result.findings.push_back({context.label(regulator.part), "has no authored switching inductor to judge"});
        for (const std::size_t inductor : regulator.inductors)
            judge(inductor, "inductor of " + context.parts()[regulator.part].ref);
    }
    return result;
}

}

extern const RuleEntry regulator_over_ground{rule, check};

}
