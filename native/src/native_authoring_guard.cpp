#include "schgen/native_authoring_guard.hpp"
#include "schgen/authoring_context.hpp"
#include "schgen/authoring_purity_config.hpp"
#include "schgen/project.hpp"

namespace schgen {
std::filesystem::path native_authoring_configuration(const std::filesystem::path& explicit_configuration) {
    if(!explicit_configuration.empty())return explicit_configuration;
#ifdef SCHGEN_AUTHORING_PURITY_CONFIGURATION
    return SCHGEN_AUTHORING_PURITY_CONFIGURATION;
#else
    return {};
#endif
}

AuthoringPurityResult require_native_authoring_guard(const std::filesystem::path& repository,
        const AuthoringContext& context,const std::filesystem::path& configuration,const NativeAuthoringReport& report) {
    const auto result=check_native_authoring_purity(repository,native_authoring_configuration(configuration),context);
    const bool accepted=result.ok() && result.native_context_verified;
    const auto diagnostic=result.report();
    if(report)report(result);
    if(!accepted)throw ProjectError(diagnostic);
    // No second compiler scan. Only recheck the exact callable identities and
    // private pin-library owner against mutation through an observer's alias.
    try { require_native_authoring_context(context); }
    catch(const CircuitAuthoringError& error) {
        throw ProjectError(std::string("native authoring context changed during reporting: ")+error.what());
    }
    return result;
}

AuthoringContext make_guarded_native_authoring_context(const std::filesystem::path& repository,
        const std::filesystem::path& configuration,const NativeAuthoringReport& report) {
    auto context=make_authoring_context(repository);
    require_native_authoring_guard(repository,context,configuration,report);
    return context;
}
} // namespace schgen
