#pragma once

#include <filesystem>
#include <string>
#include <vector>

namespace schgen {
struct AuthoringPurityCapability {
    // Exact compiler declaration/caller/target identities, never a signature-
    // wide callback exemption. Production additionally validates the actual
    // context with runtime_guard before construction.
    std::string field, caller, target, runtime_guard;
};
// A review manifest, not a snapshot of source text or a list of suppressed
// findings. Every body in units and every project header it includes is checked.
struct AuthoringPurityScope {
    std::vector<std::string> units;
    // Shared implementation units: only compiler-resolved reachable bodies are
    // in the constructor boundary. This is NOT an external-call allowlist.
    std::vector<std::string> providers;
    std::vector<std::string> headers;
    // Private provider implementation headers: forbidden in constructor-module
    // include closures and direct constructor references, but provider bodies
    // may use their checked declarations (e.g. symbol data -> pin-number set).
    std::vector<std::string> provider_headers;
    std::vector<AuthoringPurityCapability> capabilities;
    // Compiler identities: root-relative file + "::" + qualified name + " | "
    // + canonical function type. Overloads are distinct registrations.
    std::vector<std::string> constructors;
    // Non-authoring IR-returning/mutating APIs (parsers, transports, etc.) are
    // census classifications ONLY: calling one still requires its checked body.
    std::vector<std::string> infrastructure;
    // All C++ sources under these roots must have a compile command. This is
    // what prevents a new/renamed constructor file escaping the census.
    std::vector<std::string> census_roots;
};
struct AuthoringPurityCommand {
    std::string file;
    // Front-end arguments only, with absolute include paths: no compiler argv[0],
    // source, -c/-o, response files, PCH, modules or compiler plugins.
    std::vector<std::string> arguments;
};
struct AuthoringPurityOptions {
    // Explicit trusted toolchain dependency. No fallback to a source search.
    std::string libclang;
    // Reviewed toolchain headers, supplied as -isystem. Paths within the source
    // root are forbidden; #pragma system_header alone never grants trust.
    std::vector<std::string> system_include_directories;
};
struct AuthoringPurityFinding {
    std::string code, file, entity, detail;
    unsigned line = 0, column = 0;
};
struct AuthoringPurityResult {
    std::string compiler;
    std::size_t parsed_units = 0, checked_bodies = 0, checked_references = 0;
    std::vector<std::string> constructor_census, included_project_headers;
    std::vector<std::string> checked_capabilities;
    bool native_context_verified = false;
    std::vector<AuthoringPurityFinding> findings;
    bool ok() const { return parsed_units != 0 && findings.empty(); }
    std::string report() const;
};
// Read-only libclang semantic/preprocessor inspection. Parse errors, missing
// files/commands, unknown includes/callees and indirect dispatch fail closed.
// No compilation, execution of constructors, output files or Python runtime.
AuthoringPurityResult check_authoring_purity(const std::filesystem::path& root,
    const AuthoringPurityScope&, const std::vector<AuthoringPurityCommand>&,
    const AuthoringPurityOptions&);

// Production pre-construction check: all reviewed constructor modules and the
// compiler-resolved provider closure. The separate all-source census above is
// mandatory in integration tests; a board does not reparse unrelated pipelines.
AuthoringPurityResult check_authoring_purity_closure(const std::filesystem::path& root,
    const AuthoringPurityScope&, const std::vector<AuthoringPurityCommand>&,
    const AuthoringPurityOptions&);

// Explicit reviewed constructor/provider scope and named metadata capabilities.
// Neither constructor discovery nor a scanner-generated allowlist defines it.
AuthoringPurityScope native_authoring_purity_scope();
} // namespace schgen
