#pragma once

#include "schgen/authoring.hpp"
#include <memory>

namespace schgen {
class SymbolLibrary;

// Named native input provider, not a placement or circuit factory. The private
// owner can only be created by make_authoring_context; it retains the same live
// library/snapshot lifetime and lazy resolution as the former captured lambda.
class NativeAuthoringPinResolver final {
public:
    std::optional<std::set<std::string>> operator()(const std::string& lib_id) const;
private:
    explicit NativeAuthoringPinResolver(std::shared_ptr<SymbolLibrary> library);
    std::shared_ptr<SymbolLibrary> library_;
    friend AuthoringContext make_authoring_context(const std::filesystem::path& repository);
    friend void require_native_authoring_context(const AuthoringContext& context);
};

// Native-policy host precondition, checked on the actual context that will be
// passed to authoring. Rejects empty/foreign/wrapped callbacks and a moved-from
// pin owner without executing any callback. Recheck after any context mutation;
// a caller assertion, type name or previously accepted copy is not evidence.
// This does not restrict the separate public custom-provider authoring API.
void require_native_authoring_context(const AuthoringContext& context);
} // namespace schgen
