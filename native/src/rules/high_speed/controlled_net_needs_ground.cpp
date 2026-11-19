#include "schgen/placement_integrity.hpp"

namespace schgen::rules {
namespace {

constexpr Rule rule{
    "controlled-net-needs-ground", "high_speed",
    "A part on an impedance-controlled net sits only on a face whose neighbouring copper layer is a ground plane.",
    "A controlled trace takes its impedance and its return current from the plane beside it; a power or signal neighbour gives neither.",
    "TI SPRAAR7J, High-Speed Interface Layout Guidelines, section 2.4, https://www.ti.com/lit/an/spraar7j/spraar7j.pdf; "
    "AMD/Xilinx UG483, 7 Series FPGAs PCB Design Guide, chapter 4, https://docs.amd.com/go/en-US/ug483_7Series_PCB",
    "primary vendor document", Enforcement::gate, Stage::placement};

RuleResult check(const RuleContext& context) {
    RuleResult result{&rule, 0, {}, {}};
    for (std::size_t part = 0; part < context.parts().size(); ++part) {
        const std::string net = controlled_net(context.parts()[part], context.model());
        if (net.empty()) continue;
        ++result.checked;
        if (context.ground_beneath(part)) continue;
        const CopperLayer& reference = context.stackup().reference_of(context.rear(part));
        result.findings.push_back({context.label(part),
                                   "carries impedance-controlled net " + net + " on the " + context.face(part) +
                                       " copper, whose neighbour " + reference.name + " is a " +
                                       copper_role_name(reference.role) + " layer, not a ground plane"});
    }
    return result;
}

}

extern const RuleEntry controlled_net_needs_ground{rule, check};

}
