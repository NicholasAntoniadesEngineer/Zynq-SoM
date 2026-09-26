#pragma once
#include "schgen/authoring_purity.hpp"

namespace schgen {
struct AuthoringContext;
struct AuthoringPurityConfiguration {
    AuthoringPurityOptions toolchain;
    std::vector<AuthoringPurityCommand> commands;
};
// Configuration supplies evidence locations, never exemptions or scope edits.
// Strict schema: schema="schgen.authoring-purity.toolchain.v1", compiler,
// libclang, compile_commands, system_include_directories, production_targets.
// production_targets explicitly selects CMake object-output owners (normally
// schgen_core and schgen). Other targets are not inspected as production proof.
// Differing commands for one source across selected targets remain an error.
// Paths are absolute or
// relative to the configuration file. The compile database may use either
// arguments or a quoted command (tokenized only; never executed by a shell).
// Throws on malformed/ambiguous/opaque commands or untrusted compiler drivers.
AuthoringPurityConfiguration load_authoring_purity_configuration(
    const std::filesystem::path& repository, const std::filesystem::path& configuration);

// Fail-closed report on configuration/semantic errors. Parent must publish the
// report and abort on !ok() BEFORE invoking any circuit/project constructor.
// No disable switch, cached verdict, interpreter, or output-file side effect.
AuthoringPurityResult check_native_authoring_purity(
    const std::filesystem::path& repository, const std::filesystem::path& configuration,
    const AuthoringContext& context);
// Separate mandatory integration census, including unrelated native/src units.
AuthoringPurityResult check_native_authoring_purity_census(
    const std::filesystem::path& repository, const std::filesystem::path& configuration);
} // namespace schgen
