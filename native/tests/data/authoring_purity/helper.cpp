#if PURITY_CASE == 5 || PURITY_CASE == 45
#include "geometry.hpp"
int transitive_helper() { return geometry::innocent_name(); }
#else
int audited_unused_helper() { return 1; }
#endif
#if PURITY_CASE == 44
#include "geometry.hpp"
int transitive_helper() { return 2; }
int unrelated_pipeline_operation() { return geometry::innocent_name(); }
#endif
#if PURITY_CASE == 29
#include "api.hpp"
auto new_factory_in_existing_non_authoring_file() { return schgen::CircuitSheetIr{}; }
#endif
#if PURITY_CASE == 31
int external_counter = audited_unused_helper();
#endif
#if PURITY_CASE >= 46 && PURITY_CASE <= 56
#include "api.hpp"
#include <stdexcept>
#if PURITY_CASE == 49
#include "geometry.hpp"
#endif
namespace schgen {
#if PURITY_CASE != 50
int native_lookup(int value) {
#if PURITY_CASE == 49
    return value + geometry::innocent_name();
#else
    return value;
#endif
}
#endif
#if PURITY_CASE != 51
void require_context(const AuthoringContext& context) {
    const auto* target=context.part.target<int(*)(int)>();
    if (!target || *target!=&native_lookup) throw std::runtime_error("wrong target");
}
#endif
}
#endif
