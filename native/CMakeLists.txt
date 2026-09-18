cmake_minimum_required(VERSION 3.18)
project(schgen_native LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)
set(CMAKE_POSITION_INDEPENDENT_CODE ON)
option(SCHGEN_BUILD_PYTHON "Build transitional Python bindings" ON)

# Compile one engine shared by the standalone CLI and transitional bindings.
add_library(schgen_core STATIC
    src/occupancy.cpp src/seat.cpp src/sexpr.cpp src/route.cpp src/emit.cpp
    src/legalize.cpp src/quantize.cpp src/turn.cpp src/pack.cpp
    src/pack_anchor.cpp src/place_search.cpp src/cc.cpp src/embed_fp.cpp
    src/pack_edges.cpp src/pcb_scan.cpp src/pack_refine.cpp src/place_geom.cpp
    src/catalog.cpp src/json.cpp src/circuit.cpp src/reorder.cpp)
target_include_directories(schgen_core PUBLIC "${CMAKE_CURRENT_SOURCE_DIR}/include")
target_compile_options(schgen_core PRIVATE -Wall -Wextra -Wpedantic -Werror)
set_source_files_properties(src/turn.cpp src/pack_anchor.cpp
                            src/pack_edges.cpp PROPERTIES
    COMPILE_OPTIONS "-ffp-contract=off")

if(SCHGEN_BUILD_PYTHON)
    find_package(Python REQUIRED COMPONENTS Interpreter Development.Module)
    execute_process(
        COMMAND "${Python_EXECUTABLE}" -m nanobind --cmake_dir
        OUTPUT_VARIABLE nanobind_ROOT
        OUTPUT_STRIP_TRAILING_WHITESPACE
        RESULT_VARIABLE nanobind_rv)
    if(nanobind_rv EQUAL 0 AND NOT nanobind_ROOT STREQUAL "")
        list(APPEND CMAKE_PREFIX_PATH "${nanobind_ROOT}")
        find_package(nanobind CONFIG REQUIRED)
    else()
        include(FetchContent)
        FetchContent_Declare(
            nanobind
            GIT_REPOSITORY https://github.com/wjakob/nanobind.git
            GIT_TAG v2.9.2)
        FetchContent_MakeAvailable(nanobind)
    endif()
    nanobind_add_module(_geom src/module.cpp)
    target_link_libraries(_geom PRIVATE schgen_core)
    target_compile_options(_geom PRIVATE -Wall -Wextra -Wpedantic -Werror)
    set_target_properties(_geom PROPERTIES
        LIBRARY_OUTPUT_DIRECTORY "${CMAKE_CURRENT_SOURCE_DIR}/../schgen"
        RUNTIME_OUTPUT_DIRECTORY "${CMAKE_CURRENT_SOURCE_DIR}/../schgen")
endif()

add_executable(schgen src/main.cpp)
target_link_libraries(schgen PRIVATE schgen_core)
target_compile_options(schgen PRIVATE -Wall -Wextra -Wpedantic -Werror)
set_target_properties(schgen PROPERTIES
    RUNTIME_OUTPUT_DIRECTORY "${CMAKE_CURRENT_SOURCE_DIR}/bin")

# JSON edits must regenerate catalogs even when the executable does not relink.
file(GLOB_RECURSE part_inputs CONFIGURE_DEPENDS
    "${CMAKE_CURRENT_SOURCE_DIR}/../parts/*.json")
file(GLOB_RECURSE circuit_inputs CONFIGURE_DEPENDS
    "${CMAKE_CURRENT_SOURCE_DIR}/../carrier/subsystems/*.json")
add_custom_command(OUTPUT "${CMAKE_CURRENT_SOURCE_DIR}/catalog.bin"
    COMMAND "$<TARGET_FILE:schgen>" catalog-compile
            "${CMAKE_CURRENT_SOURCE_DIR}/../parts"
            "${CMAKE_CURRENT_SOURCE_DIR}/catalog.bin"
    DEPENDS schgen ${part_inputs}
    VERBATIM)
add_custom_command(OUTPUT "${CMAKE_CURRENT_SOURCE_DIR}/circuits.bin"
    COMMAND "$<TARGET_FILE:schgen>" circuit-compile
            "${CMAKE_CURRENT_SOURCE_DIR}/../carrier/subsystems"
            "${CMAKE_CURRENT_SOURCE_DIR}/circuits.bin"
    DEPENDS schgen ${circuit_inputs}
    VERBATIM)
add_custom_target(schgen_catalogs ALL DEPENDS
    "${CMAKE_CURRENT_SOURCE_DIR}/catalog.bin"
    "${CMAKE_CURRENT_SOURCE_DIR}/circuits.bin")

include(CTest)
if(BUILD_TESTING)
    add_executable(schgen_kernel_contracts tests/kernel_contracts.cpp)
    target_link_libraries(schgen_kernel_contracts PRIVATE schgen_core)
    target_compile_options(schgen_kernel_contracts PRIVATE -Wall -Wextra -Wpedantic -Werror)
    foreach(contract rounding sexpr routing seating placement_limits)
        add_test(NAME native_${contract} COMMAND schgen_kernel_contracts ${contract})
    endforeach()
    add_test(NAME native_self_check COMMAND schgen self-check)
    add_test(NAME native_help COMMAND schgen --help)
    add_test(NAME native_reject_board COMMAND schgen board)
    add_test(NAME native_reject_self_check_args COMMAND schgen self-check extra)
    add_test(NAME native_reject_missing_catalog_args COMMAND schgen catalog-compile)
    set_tests_properties(native_reject_board native_reject_self_check_args
        native_reject_missing_catalog_args PROPERTIES WILL_FAIL TRUE)
endif()
