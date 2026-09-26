#pragma once
#include <chrono>
#include <filesystem>
#include <optional>
#include <stdexcept>
#include <string>
#include <vector>

namespace schgen {
class ProcessError : public std::runtime_error {public:using std::runtime_error::runtime_error;};
class ProcessTimeout : public ProcessError {public:using ProcessError::ProcessError;};
struct ProcessResult {int exit_code=0;std::string stdout_text,stderr_text;};
std::optional<std::filesystem::path> find_executable(const std::string& command);
// Shared shell-free POSIX boundary. Private 0700 scratch, stdin=/dev/null,
// captured stdout/stderr, signed signal return code, EINTR-safe reap. Timeout
// kills the child's isolated process group and throws; no success fallback.
ProcessResult run_process(const std::vector<std::string>& argv,
    std::chrono::milliseconds timeout=std::chrono::milliseconds{30000});
// Same isolation, timeout and exit semantics, but result strings contain exact
// bytes: no UTF-8 validation or newline conversion. Required for compressed CAD
// downloads and other binary subprocess protocols. Never use text mode for them.
ProcessResult run_process_bytes(const std::vector<std::string>& argv,
    std::chrono::milliseconds timeout=std::chrono::milliseconds{30000});
}  // namespace schgen
