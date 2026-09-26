#pragma once
#include "schgen/json.hpp"
#include <cstddef>
#include <string>
#include <string_view>

namespace schgen {
struct AuditAstProjectionStats {
    std::size_t input_bytes = 0;
    std::size_t json_values = 0;
    std::size_t retained_values = 0;
    std::size_t retained_fields = 0;
    std::size_t discarded_fields = 0;
};
// Field-only streaming projection of UNFILTERED Clang JSON. Retains EVERY
// inner-tree node, including included-file/global/anonymous/lambda nodes, and
// all fields consumed by native_cpp_audits.cpp's index/visit/finish passes.
// No namespace or source-file exclusion is performed. Key order is irrelevant.
// Skipped values are fully validated, including duplicate keys and strings.
// Malformed/truncated JSON, nonrepresentable numbers, invalid Unicode and
// nesting beyond 1024 levels throw; output/stats commit only after a full parse.
JsonNode parse_audit_ast_projection(std::string_view json,
    const std::string& source = "<compiler AST>", AuditAstProjectionStats* = nullptr);
// Exposed for the independent schema/equivalence contracts, not as a mutable
// allowlist or an audit waiver. Changing the visitor requires checking this set.
bool audit_ast_projection_keeps_field(std::string_view);
}
