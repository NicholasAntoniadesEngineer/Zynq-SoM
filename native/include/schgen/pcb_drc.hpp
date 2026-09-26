#pragma once
#include "schgen/process.hpp"
#include <map>

namespace schgen {
struct PcbDrcResult {
    int returncode = 0;
    std::size_t n_violations = 0, n_unconnected = 0;
    // Absent when an older report omits severity; callers must obtain errors separately.
    std::optional<std::size_t> n_errors = 0;
    std::map<std::string, std::size_t> by_type;
    std::vector<std::string> other_sample;
    std::string stderr_tail;
};
// Missing/malformed reports and tool errors throw, never imply zero violations.
PcbDrcResult parse_pcb_drc_report(const std::string& report, const ProcessResult& process);
std::vector<std::string> pcb_drc_arguments(const std::filesystem::path& board,
    const std::filesystem::path& report, bool include_warnings);
PcbDrcResult run_pcb_drc(const std::filesystem::path& board,
    std::chrono::milliseconds timeout = std::chrono::minutes{5}, bool include_warnings = true);
}
