#pragma once
#include "schgen/experiment_tools.hpp"
#include "compose_repair_internal.hpp"

namespace schgen::experiment_detail {
using namespace compose_detail;
std::string universal_newlines(const std::string &);
std::string diagnostic_md5(const std::string &);
std::string repr_value(const ExperimentDocument &, const JsonNode &, const std::string &);
std::string tail_lines(const std::string &, std::size_t);
std::string tail_characters(const std::string &, std::size_t);
void apply_layers(PcbPlacementInput &, const std::vector<std::string> &);
} // namespace schgen::experiment_detail
