#include "schgen/stackup.hpp"

#include <algorithm>
#include <sstream>
#include <stdexcept>

namespace schgen {

const CopperLayer& Stackup::reference_of(bool rear) const {
    if (copper.size() < 2) throw std::logic_error(fabricator_name + ": a stack-up needs an outer layer and its neighbour");
    return rear ? copper[copper.size() - 2] : copper[1];
}

bool Stackup::ground_referenced(bool rear) const { return reference_of(rear).role == CopperRole::ground; }

const DifferentialGeometry* Stackup::pair(int impedance) const {
    const auto found = std::find_if(pairs.begin(), pairs.end(),
                                    [&](const DifferentialGeometry& row) { return row.impedance == impedance; });
    return found == pairs.end() ? nullptr : &*found;
}

std::string Stackup::pair_list(const std::string& label, const std::string& unit, const std::string& joint) const {
    std::ostringstream text;
    for (std::size_t index = 0; index < pairs.size(); ++index)
        text << (index ? joint : "") << pairs[index].impedance << label << pairs[index].width_mm << "/"
             << pairs[index].gap_mm << unit;
    return text.str();
}

const char* copper_role_name(CopperRole role) {
    switch (role) {
    case CopperRole::signal: return "signal";
    case CopperRole::ground: return "ground";
    case CopperRole::power: return "power";
    }
    throw std::logic_error("unknown copper role");
}

const Stackup& board_stackup() {
    static const Stackup four_layer{
        "JLC04161H-7628",
        "4-layer 1.6 mm (Sig / GND / PWR / Sig)",
        "4L 1.6mm",
        "7628 prepreg 0.2104mm",
        {{0, "F.Cu", CopperRole::signal, 0.035, "L1 (Sig)"},
         {1, "In1.Cu", CopperRole::ground, 0.0152, "L2 (GND)"},
         {2, "In2.Cu", CopperRole::power, 0.0152, "L3 (PWR)"},
         {31, "B.Cu", CopperRole::signal, 0.035, "L4 (Sig)"}},
        {{"dielectric 1", "prepreg", 0.2104, 4.6},
         {"dielectric 2", "core", 1.065, 4.6},
         {"dielectric 3", "prepreg", 0.2104, 4.6}},
        {{90, 0.2611, 0.2032, "JLCPCB calculator, JLC04161H-7628 outer/L2"},
         {100, 0.2052, 0.2032, "JLCPCB calculator, JLC04161H-7628 outer/L2"}}};
    return four_layer;
}

}
