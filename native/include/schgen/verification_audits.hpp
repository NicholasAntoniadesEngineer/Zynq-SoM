#pragma once

#include <cstdint>
#include <filesystem>
#include <functional>
#include <map>
#include <optional>
#include <set>
#include <stdexcept>
#include <string>
#include <string_view>
#include <vector>

namespace schgen {
class AuditSyntaxError : public std::runtime_error { public: using std::runtime_error::runtime_error; };
// Decimal integers retain Python's unbounded ratchet ceilings. No float
// narrowing, overflow-to-first-run pin, or silent saturation at INT64_MAX.
class AuditInteger {
public:
    AuditInteger(std::int64_t value = 0);
    static AuditInteger decimal(std::string value);
    const std::string& str() const { return digits_; }
    bool nonzero() const { return digits_ != "0"; }
    friend bool operator<(const AuditInteger&, const AuditInteger&);
    friend bool operator==(const AuditInteger& a, const AuditInteger& b) { return a.digits_ == b.digits_; }
    friend bool operator!=(const AuditInteger& a, const AuditInteger& b) { return !(a == b); }
private:
    std::string digits_;
};
using AuditCounts = std::map<std::string, AuditInteger>;

struct FallbackAuditResult {
    bool ok = true, pinned = false;
    std::size_t n_names = 0, n_fired = 0;
    std::vector<std::string> regressions;
    std::string summary() const;
};
// Caller resolves the project baseline path. Absent/corrupt baseline pins the
// measured census as before; valid baselines only decrease on a passing run.
// Read errors have original first-run semantics; publication errors propagate.
std::optional<AuditCounts> load_fallback_baseline(const std::filesystem::path&);
std::string fallback_baseline_text(const AuditCounts&);
FallbackAuditResult check_fallback_ratchet(const AuditCounts&, const std::filesystem::path& baseline);
// Separate the authoritative input ceiling from an isolated build's output.
// Failed checks never publish; successful runs cannot relax the source ceiling.
FallbackAuditResult check_fallback_ratchet(const AuditCounts&, const std::filesystem::path& baseline,
                                         const std::filesystem::path& output);

struct LedgerAuditDeclaration {
    std::string name;
    bool repeated = false;
    std::vector<std::string> covers;
};
struct LedgerAuditState {
    std::vector<LedgerAuditDeclaration> declarations;
    std::set<std::string> recorded;
    std::size_t n_lines = 0;
    std::vector<std::string> problems;
};
} // namespace schgen
