#pragma once

#include <cstdint>
#include <string>
#include <vector>

namespace schgen {

enum class CopperRole : std::uint8_t { signal, ground, power };

struct CopperLayer {
    int ordinal = 0;
    std::string name;
    CopperRole role = CopperRole::signal;
    double thickness_mm = 0.0;
    std::string label;
};

struct DielectricLayer {
    std::string name, kind;
    double thickness_mm = 0.0, permittivity = 0.0;
};

struct DifferentialGeometry {
    int impedance = 0;
    double width_mm = 0.0, gap_mm = 0.0;
    std::string source;
};

struct Stackup {
    std::string fabricator_name, summary, brief, prepreg;
    std::vector<CopperLayer> copper;
    std::vector<DielectricLayer> dielectric;
    std::vector<DifferentialGeometry> pairs;
    const CopperLayer& reference_of(bool rear) const;
    bool ground_referenced(bool rear) const;
    const DifferentialGeometry* pair(int impedance) const;
    std::string pair_list(const std::string& label, const std::string& unit, const std::string& joint) const;
};

const Stackup& board_stackup();
const char* copper_role_name(CopperRole role);

}
