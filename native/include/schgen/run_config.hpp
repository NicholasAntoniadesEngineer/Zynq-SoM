#pragma once

#include "schgen/fabricator.hpp"
#include "schgen/json.hpp"

#include <cstdint>
#include <filesystem>
#include <map>
#include <optional>
#include <set>
#include <string>
#include <vector>

namespace schgen {

struct SearchReliability {
    double pass_rate = 0, area_spread = 0;
    std::string basis;
};

struct SearchConfig {
    std::string mode;
    std::vector<std::uint64_t> seeds;
    std::size_t promote = 0, threads = 0;
    std::vector<std::string> objective;
    std::optional<double> max_minutes;
    std::optional<std::pair<double, double>> max_outline_mm;
    SearchReliability reliability;
};

struct RunConfig {
    SearchConfig search;
    std::vector<std::string> boards;
    std::filesystem::path output;
    bool squeeze = false, arrange = false, construct = false, renders = false, labels = false, timing = false;
    std::string plane_net;
    int audit_projections = 0;
    std::map<std::string, std::string> stackup;
    std::map<std::string, std::vector<std::string>> overmold_parts;
    std::map<std::string, FabricationConfig> fabrication;
    std::vector<std::string> study_stackups;
    const std::string& stackup_of(const std::string& board) const;
    const std::vector<std::string>& overmold_parts_of(const std::string& board) const;
    const FabricationConfig& fabrication_of(const std::string& board) const;
    std::vector<std::string> board_arguments(const std::string& board, const std::filesystem::path& file) const;
};

struct RunArguments {
    std::filesystem::path file;
    std::vector<std::string> boards;
    std::map<std::string, std::string> options;
};

inline constexpr const char* run_config_file = "schgen.json";

RunArguments parse_run_arguments(const std::vector<std::string>& arguments, const std::set<std::string>& valued);
std::vector<std::string> chosen_boards(const RunConfig& config, const std::vector<std::string>& chosen);
void study_stackup(std::optional<std::string> name);
int run_board(const RunConfig& config, const std::string& board, const std::filesystem::path& file);

RunConfig parse_run_config(const JsonNode& document);
RunConfig load_run_config(const std::filesystem::path& file);
RunConfig apply_run_config(const std::filesystem::path& config_file, const std::string& board);
[[noreturn]] void run_config_failure(const std::string& what);
std::string run_usage();
std::optional<int> run_config_command(int argc, char** argv);

}
