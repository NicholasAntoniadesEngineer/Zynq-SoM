// Standalone header compile contract; deliberately does not include module.cpp
// or execute Python while the parent's authoring/binding rebuild is in flight.
#include "schgen/native_render_bindings.hpp"

void schgen_native_render_bindings_compile_contract(nanobind::module_& module) {
    schgen::bind_native_render(module);
}
