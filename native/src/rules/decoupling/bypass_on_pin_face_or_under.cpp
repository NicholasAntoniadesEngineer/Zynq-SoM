#include "schgen/placement_integrity.hpp"

#include <algorithm>
#include <sstream>

namespace schgen::rules {
namespace {

constexpr Rule rule{
    "bypass-on-pin-face-or-under", "decoupling",
    "A bypass capacitor is on the face of the pin it serves, or directly under the served part on the opposite face when both faces have a ground plane as their neighbour.",
    "What limits a bypass capacitor is the inductance of its path to the pin; that path is short only beside the pin or straight through the board beneath it.",
    "AMD/Xilinx UG933, Zynq-7000 SoC PCB Design Guide, https://docs.amd.com/v/u/en-US/ug933-Zynq-7000-PCB; "
    "TI SLUA366, PCB Layout Guidelines for Power Controllers, https://www.ti.com/lit/pdf/slua366",
    "primary vendor document", Enforcement::measured};

RuleResult check(const RuleContext& context) {
    RuleResult result{&rule, 0, context.unresolved({"bypass"}), {}};
    const double reach = layout::role_reach("bypass");
    std::vector<double> gaps;
    std::size_t beside = 0, under = 0;
    for (const Service* service : context.serving({"bypass"})) {
        ++result.checked;
        const std::size_t part = service->part, owner = service->owner;
        gaps.push_back(*context.pad_gap(owner, service->pads, part));
        if (context.rear(part) == context.rear(owner)) {
            ++beside;
            continue;
        }
        const bool beneath = context.overlap(part, owner) > constants::judging_resolution.value;
        if (beneath && context.ground_beneath(part) && context.ground_beneath(owner)) {
            ++under;
            continue;
        }
        const std::size_t ungrounded = context.ground_beneath(part) ? owner : part;
        result.findings.push_back(
            {context.label(part), "is on the " + context.face(part) + " face while the pin " + service->pin +
                                      " it serves is on the " + context.face(owner) +
                                      (beneath ? ", under the part, but the " + context.face(ungrounded) + " face's neighbour " +
                                                     context.neighbour(ungrounded)
                                               : ", and it is not under " + context.parts()[owner].ref)});
    }
    if (gaps.empty()) return result;
    std::sort(gaps.begin(), gaps.end());
    std::ostringstream row;
    row << "bypass distance to the served pin over " << gaps.size() << " capacitors: least " << gaps.front() << " mm, median "
        << gaps[gaps.size() / 2] << " mm, greatest " << gaps.back() << " mm; "
        << std::count_if(gaps.begin(), gaps.end(), [&](double gap) { return gap > reach; }) << " beyond the " << reach
        << " mm bypass reach; " << beside << " on the pin's face, " << under << " directly under";
    result.measurements.push_back(row.str());
    return result;
}

}

extern const RuleEntry bypass_on_pin_face_or_under{rule, check};

}
