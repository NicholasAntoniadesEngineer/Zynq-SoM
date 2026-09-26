# Separate native CI entry point: no edits/hooks in the parent-owned engine build.
cmake_minimum_required(VERSION 3.28)
project(schgen_native_ci LANGUAGES CXX)
include(CTest)
if(DEFINED SCHGEN_BUILD_PYTHON AND SCHGEN_BUILD_PYTHON)
    message(FATAL_ERROR "Native CI must not enable SCHGEN_BUILD_PYTHON; use a separate parity build")
endif()
if(NOT BUILD_TESTING)
    message(FATAL_ERROR "Native CI requires BUILD_TESTING=ON; an empty test suite is not a pass")
endif()
set(SCHGEN_BUILD_PYTHON OFF CACHE BOOL "Native CI never builds transitional bindings" FORCE)
set(CMAKE_EXPORT_COMPILE_COMMANDS ON)
find_program(SCHGEN_CI_KICAD_EXECUTABLE kicad-cli REQUIRED)
set(SCHGEN_CI_KICAD_VERSION "10.0.2" CACHE STRING "KiCad release used by immutable live fixtures")
set(_kicad_roots /Applications/KiCad/KiCad.app/Contents/SharedSupport
    /usr/share/kicad /usr/local/share/kicad)
find_path(SCHGEN_CI_FOOTPRINTS Resistor_SMD.pretty/R_0603_1608Metric.kicad_mod
    PATHS ${_kicad_roots} PATH_SUFFIXES footprints REQUIRED)
find_path(SCHGEN_CI_SYMBOLS Device.kicad_sym
    PATHS ${_kicad_roots} PATH_SUFFIXES symbols REQUIRED)
find_path(SCHGEN_CI_MODELS Resistor_SMD.3dshapes/R_0603_1608Metric.step
    PATHS ${_kicad_roots} PATH_SUFFIXES 3dmodels REQUIRED)
# The engine conditionally registers full selftests if this footprint resolves.
# Make that prerequisite explicit so a missing default search path cannot silently
# omit the test when a caller supplied a different installed library directory.
set(SCHGEN_TEST_RESISTOR_FOOTPRINT
    "${SCHGEN_CI_FOOTPRINTS}/Resistor_SMD.pretty/R_0603_1608Metric.kicad_mod"
    CACHE FILEPATH "Required native CI selftest footprint" FORCE)
# Keep both graphs intact: the normal native contracts and this entry point's
# bootstrap smoke executable. They share no Python test collector or runtime.
add_subdirectory(.. engine)
add_subdirectory(smoke)
get_property(_engine_tests DIRECTORY "${CMAKE_CURRENT_SOURCE_DIR}/.." PROPERTY TESTS)
foreach(_required native_selftest_full_contracts native_board_live_contracts
    native_render_models_live_contracts native_manufacturing_contracts native_policy_audits_contracts)
    if(NOT _required IN_LIST _engine_tests)
        message(FATAL_ERROR "Native CI is missing required contract registration: ${_required}")
    endif()
endforeach()
add_test(NAME native_ci_cache COMMAND schgen_ci_smoke --cache "${CMAKE_BINARY_DIR}/CMakeCache.txt")
add_test(NAME native_ci_environment COMMAND schgen_ci_smoke --environment
    "${SCHGEN_CI_KICAD_EXECUTABLE}" "${SCHGEN_CI_KICAD_VERSION}"
    "${SCHGEN_CI_FOOTPRINTS}" "${SCHGEN_CI_SYMBOLS}" "${SCHGEN_CI_MODELS}")
add_test(NAME native_ci_cli COMMAND schgen_ci_smoke --cli "$<TARGET_FILE:schgen>" "${CMAKE_CURRENT_SOURCE_DIR}/../..")
set_tests_properties(native_ci_cache native_ci_environment PROPERTIES
    FIXTURES_SETUP native_ci_ready TIMEOUT 120)
set_tests_properties(native_ci_cli PROPERTIES FIXTURES_REQUIRED native_ci_ready TIMEOUT 180)
function(schgen_ci_require_environment directory)
    get_property(_tests DIRECTORY "${directory}" PROPERTY TESTS)
    if(_tests)
        set_property(TEST ${_tests} DIRECTORY "${directory}" APPEND PROPERTY FIXTURES_REQUIRED native_ci_ready)
    endif()
    get_property(_children DIRECTORY "${directory}" PROPERTY SUBDIRECTORIES)
    foreach(_child IN LISTS _children)
        schgen_ci_require_environment("${_child}")
    endforeach()
endfunction()
schgen_ci_require_environment("${CMAKE_CURRENT_SOURCE_DIR}/..")
