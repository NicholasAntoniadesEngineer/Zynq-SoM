#pragma once
#include "schgen/verification_audits.hpp"
#include "verification_internal.hpp"
#include <memory>

namespace schgen::audit_detail {
enum class Kind { Other, Name, Constant, Unary, Binary, Call, Attribute, Tuple, Assign, Annotated, Scope };
struct Node;
using Ptr = std::shared_ptr<Node>;
struct Node {
    Kind kind = Kind::Other;
    std::string name, op;
    std::size_t line = 0;
    bool expr = false, numeric = false, credit = false;
    std::vector<Ptr> children, targets, args;
    Ptr left, right, value, function;
};
Ptr syntax(std::string_view, const std::string&);
std::vector<Ptr> walk(const Ptr&);
bool uppercase_name(const std::string&);
std::optional<AuditCounts> load_counts(const std::filesystem::path&, const std::string& key, bool missing_key_empty);
std::string json_quote(const std::string&);
} // namespace schgen::audit_detail
