#pragma once
#include <chrono>
#include <filesystem>
#include <functional>
#include <iosfwd>
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
struct ProcessConsumedResult {int exit_code=0;std::string stderr_text;};
using ProcessStdoutConsumer=std::function<void(std::istream&)>;
// Text-only capture consumer, called exactly once on exit 0 and never otherwise.
// Both complete captures pass strict UTF-8 validation BEFORE the consumer runs.
// The borrowed non-seekable stream normalizes CRLF/CR like run_process; stdout
// is never materialized as one string. The stream may not escape the callback.
// Scratch lifetime encloses the call and cleanup also runs if it throws. Child
// isolation, signed exits, timeout/group killing and stderr semantics are shared
// with run_process. The child timeout does not impose a parser execution timeout.
ProcessConsumedResult run_process_consume_stdout(const std::vector<std::string>& argv,
    const ProcessStdoutConsumer&,std::chrono::milliseconds timeout=std::chrono::milliseconds{30000});
}  // namespace schgen
