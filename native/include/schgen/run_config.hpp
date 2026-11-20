#pragma once

#include "schgen/json.hpp"

#include <filesystem>
#include <map>
#include <optional>
#include <string>
#include <vector>

namespace schgen {

struct RunConfig {
    std::vector<std::string> boards;
    std::filesystem::path output;
    bool squeeze = false, arrange = false, renders = false, labels = false, timing = false;
    std::string plane_net;
    int audit_projections = 0;
    std::map<std::string, std::string> stackup;
    std::map<std::string, std::vector<std::string>> overmold_parts;
    const std::string& stackup_of(const std::string& board) const;
    std::vector<std::string> board_arguments(const std::string& board, const std::filesystem::path& file) const;
};

inline constexpr const char* run_config_file = "schgen.json";

RunConfig parse_run_config(const JsonNode& document);
RunConfig load_run_config(const std::filesystem::path& file);
RunConfig apply_run_config(const std::filesystem::path& config_file, const std::string& board);
[[noreturn]] void run_config_failure(const std::string& what);
std::string run_usage();
std::optional<int> run_config_command(int argc, char** argv);

}
