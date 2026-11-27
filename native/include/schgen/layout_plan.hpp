#pragma once

#include "schgen/layout_kernel.hpp"

#include <string>
#include <vector>

namespace schgen::layout {

struct BlockFigure {
    std::string name;
    std::size_t parts = 0;
    double area = 0, hull = 0, spread = 0;
    double x = 0, y = 0;
    bool module = false;
};

struct BlockLink {
    std::size_t first = 0, second = 0;
    std::size_t nets = 0;
    double pull = 0, length = 0;
};

struct PlanFigures {
    std::vector<BlockFigure> blocks;
    std::vector<BlockLink> links;
    double length = 0, crossing = 0, pulled = 0, pulled_crossing = 0;
    std::size_t crossings = 0;
    std::string summary() const;
};

PlanFigures plan_figures(const Problem& problem, const Placement& placement);

}
