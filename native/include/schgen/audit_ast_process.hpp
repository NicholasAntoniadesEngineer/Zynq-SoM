#pragma once
#include "schgen/audit_ast_projection.hpp"
#include "schgen/process.hpp"
#include <mutex>
#include <istream>

namespace schgen {
struct AuditAstProcessResult {
    ProcessConsumedResult process;
    std::optional<JsonNode> ast;
};
// Provisional AST stays private even if parsing finishes before the compiler.
// No partial AST escapes on invalid captures, parser failure or child failure.
inline AuditAstProcessResult run_audit_ast_process(const std::vector<std::string>& command,
    const std::string& source,std::chrono::milliseconds timeout,std::unique_lock<std::mutex>& projection_slot){
    std::optional<JsonNode> provisional;
    auto process=run_process_transactional_stdout(command,[&](std::istream& input){
        // A compiler still in its frontend must not monopolize the projection
        // slot: a ready sibling must finish and advance the dynamic queue.
        (void)input.peek();
        // Compiler has already started. Its pipe applies bounded backpressure
        // until this scan can own the sole live projection. Caller holds the
        // slot through semantic consumption and AST destruction.
        projection_slot.lock();
        provisional=parse_audit_ast_projection(input,source);
    },timeout);
    if(process.exit_code!=0)provisional.reset();
    return {std::move(process),std::move(provisional)};
}
}
