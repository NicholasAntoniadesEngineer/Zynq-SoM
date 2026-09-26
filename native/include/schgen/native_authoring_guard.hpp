#pragma once

#include "schgen/authoring.hpp"
#include "schgen/authoring_purity.hpp"
#include <functional>

namespace schgen {
class ExecutionTimings;
using NativeAuthoringReport = std::function<void(const AuthoringPurityResult&)>;

// An explicit evidence configuration takes precedence over this binary's CMake
// configuration. An unconfigured binary returns an empty path, which FAILS the
// gate: no environment search, default success, cached verdict or skip switch.
std::filesystem::path native_authoring_configuration(
    const std::filesystem::path& explicit_configuration = {});

// One production-boundary check, before any constructor/factory invocation.
// Checks actual context targets and real configured compiler closure. Reports
// exactly once before throwing ProjectError on failure. The observer supplies
// no verdict; exceptions from it abort construction. Rechecks actual targets
// after the observer, which might hold a mutable alias to the caller's context.
// Callers must use this same context without subsequent mutation. Pure public
// authoring/custom-provider APIs and already-authored IR consumers stay intact.
AuthoringPurityResult require_native_authoring_guard(
    const std::filesystem::path& repository, const AuthoringContext& context,
    const std::filesystem::path& configuration = {}, const NativeAuthoringReport& report = {});

// Preferred direct CLI entry: the context is created privately, checked once,
// then returned by value with exactly the checked targets/owner. The reporting
// observer cannot replace a caller-held context before constructor entry.
AuthoringContext make_guarded_native_authoring_context(
    const std::filesystem::path& repository, const std::filesystem::path& configuration = {},
    const NativeAuthoringReport& report = {});
// Observational overload; exactly the same mandatory guard and reporting.
AuthoringContext make_guarded_native_authoring_context(
    const std::filesystem::path& repository, const std::filesystem::path& configuration,
    const NativeAuthoringReport& report, ExecutionTimings* timing);
} // namespace schgen
