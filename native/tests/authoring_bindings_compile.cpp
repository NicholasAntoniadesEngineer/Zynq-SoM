#include "schgen/authoring_bindings.hpp"
// Compile this TU with Python + nanobind include paths before parent wiring.
void authoring_bindings_compile(nanobind::module_& module) {
    schgen::bind_authoring(module);
}
