# Include inside BUILD_TESTING after schgen_core. No production observer hook.
# Unsupported ABIs fail configuration explicitly; never silently skip coverage.
if(NOT CMAKE_CXX_COMPILER_ID MATCHES "^(AppleClang|Clang|GNU)$" OR MSVC)
    message(FATAL_ERROR "fallback scope contracts require GNU/Clang Itanium C++ ABI")
endif()
add_library(schgen_floorplan_fallback_observed OBJECT src/floorplan_geometry.cpp)
target_include_directories(schgen_floorplan_fallback_observed PRIVATE include src)
target_compile_options(schgen_floorplan_fallback_observed PRIVATE
    -Wall -Wextra -Wpedantic -Werror -ffp-contract=off -finstrument-functions -fno-inline)
set_property(TARGET schgen_floorplan_fallback_observed PROPERTY INTERPROCEDURAL_OPTIMIZATION FALSE)
add_executable(schgen_floorplan_fallback_scope_contracts
    tests/floorplan_fallback_scope_contracts.cpp
    $<TARGET_OBJECTS:schgen_floorplan_fallback_observed>)
target_include_directories(schgen_floorplan_fallback_scope_contracts PRIVATE src)
target_link_libraries(schgen_floorplan_fallback_scope_contracts PRIVATE schgen_core)
target_compile_options(schgen_floorplan_fallback_scope_contracts PRIVATE
    -Wall -Wextra -Wpedantic -Werror -ffp-contract=off)
set_property(TARGET schgen_floorplan_fallback_scope_contracts PROPERTY INTERPROCEDURAL_OPTIMIZATION FALSE)
add_test(NAME native_floorplan_fallback_scope_contracts
    COMMAND schgen_floorplan_fallback_scope_contracts ${CMAKE_CURRENT_SOURCE_DIR}/..)
add_executable(schgen_floorplan_fixed_choice_contracts tests/floorplan_fixed_choice_contracts.cpp)
target_include_directories(schgen_floorplan_fixed_choice_contracts PRIVATE src)
target_link_libraries(schgen_floorplan_fixed_choice_contracts PRIVATE schgen_core)
target_compile_options(schgen_floorplan_fixed_choice_contracts PRIVATE
    -Wall -Wextra -Wpedantic -Werror -ffp-contract=off)
add_test(NAME native_floorplan_fixed_choice_contracts COMMAND schgen_floorplan_fixed_choice_contracts)
