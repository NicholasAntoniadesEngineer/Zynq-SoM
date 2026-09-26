#include "schgen/authoring_context.hpp"
#include "schgen/symbols.hpp"
#include <memory>

namespace schgen {
NativeAuthoringPinResolver::NativeAuthoringPinResolver(std::shared_ptr<SymbolLibrary> library)
    :library_(std::move(library)) {}

std::optional<std::set<std::string>> NativeAuthoringPinResolver::operator()(const std::string& lib_id) const {
    if(!library_)throw CircuitAuthoringError("native pin resolver: empty library owner");
    try{return library_->pin_numbers(lib_id);}catch(const SymbolError&){return std::nullopt;}
}

void require_native_authoring_context(const AuthoringContext& context) {
    using CatalogLookup = CatalogPart (*)(const std::string&);
    const auto catalog = context.part.target<CatalogLookup>();
    if(!catalog || *catalog != &lookup_part_catalog)
        throw CircuitAuthoringError("native authoring context: catalog target must be lookup_part_catalog");
    const auto pins = context.pins.target<NativeAuthoringPinResolver>();
    if(!pins || !pins->library_)
        throw CircuitAuthoringError("native authoring context: pins target must own a NativeAuthoringPinResolver");
}

// Host-side setup only: authoring receives the existing resolver context; it
// does not create a symbol library or acquire geometry through a helper include.
AuthoringContext make_authoring_context(const std::filesystem::path& repository) {
    auto library=std::make_shared<SymbolLibrary>(repository);
    AuthoringContext context;
    context.pins=NativeAuthoringPinResolver(std::move(library));
    return context;
}
} // namespace schgen
