#pragma once

#include "schgen/xdc.hpp"

#include <map>
#include <string>
#include <vector>

namespace schgen {
// Render only after generate_xdc has validated the same live SoM inputs.
std::string render_vivado(const XdcOutput& xdc, const std::string& device,
                          const std::string& zynq_ref, const std::string& xdc_relative,
                          const std::vector<std::string>& refs,
                          const std::map<std::string, double>& clock_periods = {});
}
