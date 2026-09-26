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
struct LedgerModuleSymbols {
    // Live native providers supply these; source declarations alone cannot
    // establish that a symbol exists or has a numeric runtime value.
    std::set<std::string> numeric_names, attributes;
};
using LedgerModuleResolver = std::function<LedgerModuleSymbols(const std::string& alias)>;
struct LedgerAuditFile { std::string alias, path; };
const std::vector<LedgerAuditFile>& ledger_audit_files();
struct LedgerSourceCensus { std::vector<std::string> constants, buried; };
// Parses exact caller bytes with a native syntax parser. No code is evaluated.
// known includes imported numeric names, including lowercase names; booleans
// must be omitted by the provider. Display paths are independent of disk paths.
LedgerSourceCensus scan_ledger_source(std::string_view source, const std::string& alias,
    const std::string& display_path, const std::set<std::string>& known);
struct LedgerAuditResult {
    bool ok = true;
    std::size_t n_declared = 0, n_recorded = 0, n_lines = 0, n_constants = 0, n_files = 0;
    std::vector<std::string> absent, undeclared, buried, stale, divergences;
    std::string summary() const;
};
LedgerAuditResult check_build_ledger(const std::filesystem::path& root, const LedgerAuditState&,
    const LedgerModuleResolver&, const std::vector<LedgerAuditFile>& files = ledger_audit_files());

const std::vector<std::string>& quantize_audit_files();
std::vector<std::string> scan_quantize_source(std::string_view source, const std::string& display_path);
struct QuantizeSourceCensus { std::vector<std::string> sites; std::size_t n_files = 0; };
// nullopt selects the normal file list; an explicitly empty list scans nothing.
QuantizeSourceCensus scan_quantize_sources(const std::filesystem::path& root,
    const std::optional<std::vector<std::string>>& files = std::nullopt);
AuditCounts load_quantize_baseline(const std::filesystem::path&);
struct QuantizeAuditResult {
    bool ok = true;
    std::size_t n_registered = 0, n_files = 0, n_sites = 0, n_new = 0;
    std::vector<std::string> sites, new_sites;
    std::string summary() const;
};
QuantizeAuditResult check_quantize_census(const std::filesystem::path& root,
    const std::optional<std::vector<std::string>>& files,
    const std::filesystem::path& baseline, std::size_t n_registered);
} // namespace schgen
