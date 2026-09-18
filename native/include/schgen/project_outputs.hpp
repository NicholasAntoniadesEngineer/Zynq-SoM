#pragma once

#include "schgen/circuit.hpp"
#include "schgen/xdc.hpp"

#include <filesystem>
#include <vector>

namespace schgen {
// Supply live ball/pin maps and device/ref fields from the native SoM extractor.
// Policy and consumer ports come only from project JSON and validated circuit IR.
XdcInput load_project_xdc_input(const std::filesystem::path& repository,
                                const std::filesystem::path& project,
                                const std::vector<CircuitSheetIr>& sheets,
                                XdcInput live,
                                const std::filesystem::path& som,
                                const std::filesystem::path& contract = {});
void publish_text(const std::filesystem::path& target, const std::string& text);
}
