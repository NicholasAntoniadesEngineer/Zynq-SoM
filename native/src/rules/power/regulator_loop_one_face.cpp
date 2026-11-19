#include "schgen/placement_integrity.hpp"

namespace schgen::rules {
namespace {

constexpr Rule rule{
    "regulator-loop-one-face", "power",
    "A switching regulator, the input capacitor nearest each of its input pins, its inductor and its nearest output capacitor are all on one face.",
    "A via inside a switching current loop adds inductance exactly where the current changes fastest, which becomes ringing and radiated noise.",
    "TI SLYT614, Five steps to a great PCB layout for a step-down converter, https://www.ti.com/lit/an/slyt614/slyt614.pdf; "
    "TI LM61460 datasheet, section 11 Layout, https://www.ti.com/lit/ds/symlink/lm61460.pdf",
    "primary vendor document", Enforcement::measured};

RuleResult check(const RuleContext& context) {
    RuleResult result{&rule, 0, context.unresolved(roles_with(&RoleRule::marks_regulator)), {}};
    for (const Regulator& regulator : context.regulators()) {
        ++result.checked;
        const std::string subject = context.label(regulator.part);
        const auto same_face = [&](std::size_t member, const std::string& what) {
            if (context.rear(member) == context.rear(regulator.part)) return;
            result.findings.push_back({subject, "is on the " + context.face(regulator.part) + " face, but " + what + " " +
                                                    context.label(member) + " is on the " + context.face(member)});
        };
        if (regulator.inputs.empty())
            result.findings.push_back({subject, "has no pin named as a supply input (VIN, PVIN or IN), so its input capacitor cannot be identified"});
        for (const RegulatorInput& input : regulator.inputs) {
            if (input.capacitors.empty()) {
                result.findings.push_back({subject, "has no authored bypass or reservoir capacitor serving its input pin " +
                                                        input.name + " (pad " + input.pad + ")"});
                continue;
            }
            same_face(input.capacitors.front(), "the input capacitor nearest " + input.name);
        }
        if (regulator.inductors.empty())
            result.findings.push_back({subject, "has no authored switching inductor, so its loop cannot be identified"});
        for (const std::size_t inductor : regulator.inductors) same_face(inductor, "its inductor");
        if (regulator.outputs.empty())
            result.findings.push_back({subject, "has no capacitor serving its inductor or diode, so its output capacitor cannot be identified"});
        for (const RegulatorOutput& output : regulator.outputs)
            same_face(output.capacitors.front(), "the output capacitor nearest " + context.parts()[output.member].ref);
    }
    return result;
}

}

extern const RuleEntry regulator_loop_one_face{rule, check};

}
