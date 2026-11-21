#pragma once

#include "schgen/named_constant.hpp"

#include <array>
#include <string>
#include <vector>

namespace schgen::placement_report_constants {
inline constexpr NamedConstant report_decimals{"placement_report_decimals", 3.0, "digits", "policy",
    "positions and distances in the placement reports are printed to a micrometre"};
inline constexpr std::array placement_report_registry{report_decimals};
}

namespace schgen {

std::string placement_report_number(double value);
std::string placement_report_row(const std::vector<std::string>& cells);

}
