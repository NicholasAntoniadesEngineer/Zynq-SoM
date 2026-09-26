#pragma once
#include "schgen/json.hpp"
#include "schgen/verification_audits.hpp"
#include <chrono>
#include <mutex>
#include <limits>
#include <type_traits>

namespace schgen {
// Owned by one build, not global adapter state. Callbacks resolve live values
// at step entry; no source parsing or frozen outputs populate the ledger.
struct NativeLedgerDeclaration {
    std::string name, kind, step, unit, basis, source;
    std::vector<std::string> covers, inputs;
    std::string expression;
    bool repeated=false;
    std::function<JsonNode()> resolve;
};
struct NativeLedgerEntry { std::string kind, name, text; std::size_t depth=0; };
class NativeLedger {
public:
    NativeLedger();
    void declare(NativeLedgerDeclaration);
    void open_step(const std::string& name,const std::string& label={});
    void close_step(const std::string& name);
    void calc(const std::string& name,const JsonNode& result,
        const std::vector<std::pair<std::string,JsonNode>>& inputs,const std::string& label={});
    void reset(); // retains declarations, clears all build state
    LedgerAuditState audit_state() const;
    const std::vector<NativeLedgerEntry>& entries() const { return entries_; }
    std::string render() const;
private:
    std::vector<NativeLedgerDeclaration> declarations_;
    std::vector<NativeLedgerEntry> entries_, shadow_entries_;
    std::vector<std::pair<std::string,std::size_t>> stack_;
    std::map<std::string,std::vector<std::pair<std::size_t,std::string>>> done_;
    std::set<std::string> seen_;
    std::vector<std::string> problems_;
    std::string shadow_;
    std::vector<NativeLedgerEntry>& sink();
    void append(const std::string& kind,const std::string& name,const std::string& body);
};

struct NativeFallbackDeclaration { std::string name,stage,meaning; };
using NativeCounterMap = std::map<std::string,std::uint64_t>;
template<class Integer> std::uint64_t native_checked_count(Integer count){
    static_assert(std::is_integral_v<Integer> && !std::is_same_v<Integer,bool>,"native counters require integral counts");
    static_assert(std::numeric_limits<Integer>::digits<=64,"native counter exceeds uint64_t width");
    if constexpr(std::is_signed_v<Integer>)if(count<0)throw std::invalid_argument("native accounting: negative count");
    return static_cast<std::uint64_t>(count);
}
template<class Integer> NativeCounterMap native_counter_batch(const std::map<std::string,Integer>& counts){
    NativeCounterMap out;for(const auto& [name,count]:counts)out.emplace(name,native_checked_count(count));return out;
}
struct NativeFallbackCheckpoint { NativeCounterMap counts; std::vector<std::string> events; };
class NativeAccountingInbox;
class NativeFallbacks {
public:
    void declare(NativeFallbackDeclaration);
    void record(const std::string&);
    // Add measured deltas without constructing count copies of an event. A
    // whole batch validates before mutation; unknown labels (even zero) fail.
    void record_count(const std::string&,std::uint64_t);
    template<class Integer> void record_count(const std::string& name,Integer count){record_count(name,native_checked_count(count));}
    void merge_counts(const NativeCounterMap&);
    template<class Integer> void merge_counts(const std::map<std::string,Integer>& counts){merge_counts(native_counter_batch(counts));}
    void merge_events(const std::vector<std::string>&);
    // Legacy event snapshots remain exact; they throw after compact count
    // imports, instead of silently omitting those imports. Use checkpoint then.
    std::vector<std::string> snapshot() const;
    void restore(const std::vector<std::string>&);
    NativeFallbackCheckpoint checkpoint() const;
    void restore_checkpoint(const NativeFallbackCheckpoint&);
    AuditCounts census() const;
    void reset();
private:
    friend class NativeAccountingInbox;
    mutable std::mutex mutex_;
    std::map<std::string,NativeFallbackDeclaration> declarations_;
    std::vector<std::string> events_;
    NativeCounterMap counts_;
    std::uint64_t epoch_=0;
};
void register_native_fallbacks(NativeFallbacks&);

struct NativeQuantizationDeclaration {
    std::string name, symbol, value, basis, proof_class;
    std::size_t arity=0;
    std::function<double(const std::vector<double>&)> evaluate;
};
class NativeQuantizations {
public:
    void declare(NativeQuantizationDeclaration);
    double invoke(const std::string&,const std::vector<double>& arguments);
    // Instrumentation only: evaluate is NEVER called by these APIs.
    void record_count(const std::string&,std::uint64_t);
    template<class Integer> void record_count(const std::string& name,Integer count){record_count(name,native_checked_count(count));}
    void merge_counts(const NativeCounterMap&);
    template<class Integer> void merge_counts(const std::map<std::string,Integer>& counts){merge_counts(native_counter_batch(counts));}
    AuditCounts engagements() const;
    std::vector<NativeQuantizationDeclaration> declarations() const;
    void reset_engagements();
private:
    friend class NativeAccountingInbox;
    mutable std::mutex mutex_;
    std::map<std::string,NativeQuantizationDeclaration> declarations_;
    std::map<std::string,std::uint64_t> counts_;
    std::uint64_t epoch_=0;
};
// Binds the existing compiled algorithms; caller arguments are never replaced
// by defaults. Floating/int/bool boundaries are checked before invocation.
void register_native_quantizations(NativeQuantizations&);

struct NativeAccountingBatch {
    NativeCounterMap quantization_engagements;
    std::vector<std::string> fallback_events;
};
// One inbox per build. An ID denotes one actual invocation-owned, disjoint
// accounting aggregate, never a board filename or an individual label.
// Identical replay returns false; changed payload for that ID throws. Both
// registries and receipt commit atomically, after label/overflow validation.
// Child results must NOT also be imported when their parent already owns them.
class NativeAccountingInbox {
public:
    NativeAccountingInbox(NativeQuantizations& q,NativeFallbacks& f):quantize_(q),fallbacks_(f){}
    bool merge_once(const std::string& invocation_id,const NativeAccountingBatch&);
    // Directly accepts FloorplanAccounting, PcbZoneResult, PcbStageResult.
    template<class Accounting> bool merge_once(const std::string& id,const Accounting& result){
        return merge_once(id,NativeAccountingBatch{native_counter_batch(result.quantization_engagements),result.fallback_events});
    }
    void reset(); // resets both registries' build state and all receipts
private:
    NativeQuantizations& quantize_;
    NativeFallbacks& fallbacks_;
    std::mutex mutex_;
    std::map<std::string,NativeAccountingBatch> receipts_;
    std::uint64_t quantize_epoch_=0,fallback_epoch_=0;
};

struct CppAuditOptions {
    std::string compiler="clang++";
    std::vector<std::string> flags; // same include paths/defines/target as build
    std::chrono::milliseconds timeout{30000};
};
struct CppAuditSource { std::string path; }; // repo-relative .cpp OR header
struct CppAuditConstant { std::string symbol, site; bool buried=false; };
struct CppAuditSite { std::string site, function, detector; };
struct CppSourceCensus {
    std::size_t n_files=0;
    std::vector<CppAuditConstant> constants;
    std::set<std::string> functions;
    std::vector<CppAuditSite> quantization;
};
// Uses a real C++17 compiler AST, not Python inputs or a token approximation.
// Symbol keys are "relative/path.cpp::namespace::name". Anonymous namespaces
// are elided; overloaded functions are not eligible for ambiguous registration.
// Explicit manifest is mandatory, every file must exist. Headers are audited
// as standalone C++ TUs. Included files must also be listed to own coverage.
CppSourceCensus scan_cpp_audit_sources(const std::filesystem::path& root,
    const std::vector<CppAuditSource>&,const CppAuditOptions& = {});
struct NativeAuditResult {
    bool ok=true;
    std::size_t n_files=0,n_constants=0,n_transforms=0;
    std::vector<std::string> absent,undeclared,buried,stale,problems,unregistered_quantization;
    std::string summary() const;
};
// Registry coverage is exact: a transform may contain raw quantization only
// within its named implementation function, never in an entire allowed file.
NativeAuditResult check_native_audits(const CppSourceCensus&,
    const NativeLedger&,const NativeQuantizations&);
// Production entry point: always re-reads and compiles the explicit manifest.
NativeAuditResult check_native_audits(const std::filesystem::path& root,
    const std::vector<CppAuditSource>& files,const NativeLedger&,
    const NativeQuantizations&,const CppAuditOptions& = {});
} // namespace schgen
