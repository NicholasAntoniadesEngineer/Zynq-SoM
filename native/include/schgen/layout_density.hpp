#pragma once

#include "schgen/board_definition.hpp"
#include "schgen/layout_problem.hpp"

#include <map>
#include <optional>
#include <string>

namespace schgen::layout {

namespace constants {
inline constexpr NamedConstant density_dense{"density_dense", densest_density, "level", "policy",
    "the densest level and the stated default: courtyards may touch and nothing is added. PCB Libraries, Footprint Expert "
    "Guideline edition 1.8 (2026-11-09), section 10.0: 'In the average case, courtyards can be bumped next to each other'"};
inline constexpr NamedConstant density_sparse{"density_sparse", sparsest_density, "level", "policy",
    "the sparsest level the setting accepts; the scale is the one to ten the integrator asked for on 2026-11-22"};
inline constexpr NamedConstant density_step{"density_step", 0.25, "mm", "standard",
    "courtyard gap added for each level below the densest: one nominal courtyard excess of IPC-7351 density level B. "
    "Read 2026-11-23 from the IPC-7351 lead table reproduced in PCB Libraries, Footprint Expert Guideline edition 1.8 "
    "(courtyard excess 0.50 most, 0.25 nominal, 0.10 least) and from T. Hausherr, PCB Libraries forum topics 1905 and 3372; "
    "the IPC standard itself was not opened. It is also one pitch of the relocation search"};
inline constexpr NamedConstant most_excess{"most_excess", 0.5, "mm", "standard",
    "gap gained when two neighbours each go from the nominal (0.25 mm) to the most (0.50 mm) courtyard excess of IPC-7351, "
    "same sources as density_step"};
inline constexpr NamedConstant inspect_gap{"inspect_gap", 1.0, "mm", "standard",
    "clearance given to a ball-grid package for inspection and rework heat in PCB Libraries, Footprint Expert Guideline "
    "edition 1.8, section 10.0, and the smallest gap JLCPCB accepts from a no-lead package to any other part "
    "(jlcpcb.com/help/article/minimum-spacing-for-smd-components, read 2026-11-23)"};
inline constexpr NamedConstant iron_gap{"iron_gap", 2.0, "mm", "standard",
    "smallest gap JLCPCB accepts between two ball-grid packages (same page) and the upper end of the 1 to 2 mm allowed "
    "around parts soldered with an iron (applied-ee.github.io ee-notebook, design for assembly, read 2026-11-23)"};
inline constexpr std::array density_registry{density_dense, density_sparse, density_step, most_excess, inspect_gap, iron_gap};
}

struct DensityChoice {
    int board = 0;
    std::map<std::string, int> sheets;
    int of(const std::string& sheet) const;
    bool spaced() const;
};

Nm density_spacing(int level);
void apply_density(Problem& problem, const DensityChoice& choice);
Problem without_density(const Problem& problem);
Nm spacing_between(const Problem& problem, std::size_t first, std::size_t second);
double courtyard_gap(const Problem& problem, std::size_t first, const Pose& first_pose, std::size_t second,
                     const Pose& second_pose);
std::string density_table();
std::string density_statement(const DensityChoice& choice);
std::string density_report(const Problem& problem, const Placement& placement, const DensityChoice& choice);

}
