#include "schgen/placement_integrity.hpp"

namespace schgen::rules {
namespace {

constexpr Rule rule{
    "timing-parts-on-crystal-face", "timing",
    "A crystal and its load capacitors are on the same face as the pin they serve.",
    "A via in an oscillator node adds stray capacitance that detunes it and length that picks up and radiates noise.",
    "ST AN2867, Oscillator design guide for STM8/STM32, section 7.1, "
    "https://www.st.com/resource/en/application_note/an2867-oscillator-design-guide-for-stm8afals-stm32-mcus-and-mpus-stmicroelectronics.pdf",
    "primary vendor document", Enforcement::gate, Stage::placement};

RuleResult check(const RuleContext& context) {
    RuleResult result{&rule, 0, context.unresolved(roles_with(&RoleRule::owner_face)), {}};
    for (const Service* service : context.serving(roles_with(&RoleRule::owner_face))) {
        ++result.checked;
        if (context.rear(service->part) == context.rear(service->owner)) continue;
        result.findings.push_back({context.label(service->part), "is on the " + context.face(service->part) +
                                                                     " face, but the pin " + service->pin +
                                                                     " it serves is on the " + context.face(service->owner)});
    }
    return result;
}

}

extern const RuleEntry timing_parts_on_crystal_face{rule, check};

}
