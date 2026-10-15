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
struct AuditAstProcessTiming {
    double first_byte_seconds=0, projection_wait_seconds=0, parsing_seconds=0;
};
// Provisional AST stays private even if parsing finishes before the compiler.
// No partial AST escapes on invalid captures, parser failure or child failure.
inline AuditAstProcessResult run_audit_ast_process(const std::vector<std::string>& command,
    const std::string& source,std::chrono::milliseconds timeout,std::unique_lock<std::mutex>& projection_slot,
    AuditAstProcessTiming* timing=nullptr){
    std::optional<JsonNode> provisional;
    AuditAstProcessTiming measured;
    auto process=run_process_transactional_stdout(command,[&](std::istream& input){
        using Clock=std::chrono::steady_clock;
        auto start=Clock::now();
        const auto elapsed=[&]{return std::chrono::duration<double>(Clock::now()-start).count();};
        // A compiler still in its frontend must not monopolize the projection
        // slot: a ready sibling must finish and advance the dynamic queue.
        (void)input.peek();
        measured.first_byte_seconds=elapsed();start=Clock::now();
        // Compiler has already started. Its pipe applies bounded backpressure
        // until this scan can own a bounded projection slot. Caller holds the
        // slot through semantic consumption and AST destruction.
        projection_slot.lock();
        measured.projection_wait_seconds=elapsed();start=Clock::now();
        provisional=parse_audit_ast_projection(input,source);
        measured.parsing_seconds=elapsed();
    },timeout);
    if(process.exit_code!=0)provisional.reset();
    else if(timing)*timing=measured;
    return {std::move(process),std::move(provisional)};
}
}
