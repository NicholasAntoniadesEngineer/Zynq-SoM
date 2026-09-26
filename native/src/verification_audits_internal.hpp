#pragma once
#include "schgen/verification_audits.hpp"
#include "verification_internal.hpp"

namespace schgen::audit_detail {
std::optional<AuditCounts> load_counts(const std::filesystem::path&, const std::string& key, bool missing_key_empty);
std::string json_quote(const std::string&);
} // namespace schgen::audit_detail
