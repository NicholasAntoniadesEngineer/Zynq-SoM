cmake_minimum_required(VERSION 3.18)
project(schgen_native LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)
set(CMAKE_POSITION_INDEPENDENT_CODE ON)
option(SCHGEN_BUILD_PYTHON "Build transitional Python bindings" OFF)

# Compile one engine shared by the standalone CLI and transitional bindings.
add_library(schgen_core STATIC
    src/occupancy.cpp src/seat.cpp src/sexpr.cpp src/route.cpp src/emit.cpp
    src/legalize.cpp src/quantize.cpp src/turn.cpp src/pack.cpp
    src/pack_anchor.cpp src/place_search.cpp src/cc.cpp src/embed_fp.cpp
    src/pack_edges.cpp src/pcb_scan.cpp src/pack_refine.cpp src/place_geom.cpp
    src/catalog.cpp src/json.cpp src/circuit.cpp src/reorder.cpp src/atomic_file.cpp
    src/ratsnest.cpp src/footprint_library.cpp src/xdc.cpp src/vivado.cpp
    src/bom.cpp src/project.cpp src/project_catalog.cpp src/project_outputs.cpp src/som_interface.cpp
    src/link.cpp src/devicetree.cpp src/symbols.cpp src/validation.cpp
    src/schematic.cpp src/schematic_route.cpp src/netlist_gate.cpp src/design_rules.cpp
    src/schematic_place_core.cpp src/schematic_place_fanout.cpp
    src/schematic_place_templates.cpp src/schematic_place_chain.cpp src/schematic_place_pages.cpp
    src/selftest.cpp src/board_schematic.cpp src/mirror.cpp src/constraints.cpp
    src/power_checks.cpp src/thermal_checks.cpp src/part_checks.cpp)
find_package(Threads REQUIRED)
find_package(LibXml2 REQUIRED)
target_link_libraries(schgen_core PUBLIC LibXml2::LibXml2 Threads::Threads)
target_include_directories(schgen_core PUBLIC "${CMAKE_CURRENT_SOURCE_DIR}/include")
target_compile_options(schgen_core PRIVATE -Wall -Wextra -Wpedantic -Werror)
set_source_files_properties(src/turn.cpp src/pack_anchor.cpp src/symbols.cpp
                            src/schematic_route.cpp src/schematic_place_core.cpp
                            src/schematic_place_fanout.cpp src/schematic_place_templates.cpp
                            src/schematic_place_chain.cpp src/schematic_place_pages.cpp src/board_schematic.cpp
                            src/pack_edges.cpp src/power_checks.cpp src/thermal_checks.cpp src/part_checks.cpp PROPERTIES
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

add_executable(schgen src/main.cpp src/project_cli.cpp)
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
    add_executable(schgen_model_checks_contracts tests/model_checks_contracts.cpp)
    target_link_libraries(schgen_model_checks_contracts PRIVATE schgen_core)
    target_compile_options(schgen_model_checks_contracts PRIVATE -Wall -Wextra -Wpedantic -Werror -ffp-contract=off)
    add_test(NAME native_model_checks_contracts COMMAND schgen_model_checks_contracts
        "${CMAKE_CURRENT_SOURCE_DIR}/..")
    add_executable(schgen_constraints_contracts tests/constraints_contracts.cpp)
    target_link_libraries(schgen_constraints_contracts PRIVATE schgen_core)
    target_compile_options(schgen_constraints_contracts PRIVATE -Wall -Wextra -Wpedantic -Werror)
    add_test(NAME native_constraints_contracts COMMAND schgen_constraints_contracts
        "${CMAKE_CURRENT_SOURCE_DIR}/.." "${CMAKE_CURRENT_SOURCE_DIR}/tests/data/constraints")
    add_executable(schgen_mirror_contracts tests/mirror_contracts.cpp)
    target_link_libraries(schgen_mirror_contracts PRIVATE schgen_core)
    target_compile_options(schgen_mirror_contracts PRIVATE -Wall -Wextra -Wpedantic -Werror)
    add_test(NAME native_mirror_contracts COMMAND schgen_mirror_contracts
        "${CMAKE_CURRENT_SOURCE_DIR}/tests/data/mirror")
    add_executable(schgen_board_schematic_contracts tests/board_schematic_contracts.cpp)
    target_link_libraries(schgen_board_schematic_contracts PRIVATE schgen_core)
    target_compile_options(schgen_board_schematic_contracts PRIVATE -Wall -Wextra -Wpedantic -Werror -ffp-contract=off)
    add_test(NAME native_board_schematic_contracts COMMAND schgen_board_schematic_contracts
        "${CMAKE_CURRENT_SOURCE_DIR}/tests/data/board_schematic")
    add_test(NAME native_board_schematic_requires_output COMMAND schgen board-schematic --project devkit_mini)
    set_tests_properties(native_board_schematic_requires_output PROPERTIES WILL_FAIL TRUE)
    add_executable(schgen_selftest_contracts tests/selftest_contracts.cpp)
    target_link_libraries(schgen_selftest_contracts PRIVATE schgen_core)
    target_compile_options(schgen_selftest_contracts PRIVATE -Wall -Wextra -Wpedantic -Werror -ffp-contract=off)
    add_test(NAME native_selftest_contracts COMMAND schgen_selftest_contracts
        "${CMAKE_CURRENT_SOURCE_DIR}/tests/data/selftest")
    foreach(stage fanout templates chain)
        add_executable(schgen_schematic_place_${stage}_contracts tests/schematic_place_${stage}_contracts.cpp)
        target_link_libraries(schgen_schematic_place_${stage}_contracts PRIVATE schgen_core)
        target_compile_options(schgen_schematic_place_${stage}_contracts PRIVATE
            -Wall -Wextra -Wpedantic -Werror -ffp-contract=off)
        add_test(NAME native_schematic_place_${stage}_contracts COMMAND schgen_schematic_place_${stage}_contracts
            "${CMAKE_CURRENT_SOURCE_DIR}/tests/data/schematic_place_${stage}")
    endforeach()
    add_executable(schgen_schematic_place_pages_contracts tests/schematic_place_pages_contracts.cpp)
    target_link_libraries(schgen_schematic_place_pages_contracts PRIVATE schgen_core)
    target_compile_options(schgen_schematic_place_pages_contracts PRIVATE
        -Wall -Wextra -Wpedantic -Werror -ffp-contract=off)
    add_test(NAME native_schematic_place_pages_contracts COMMAND schgen_schematic_place_pages_contracts
        "${CMAKE_CURRENT_SOURCE_DIR}/..")
    add_executable(schgen_schematic_place_core_contracts tests/schematic_place_core_contracts.cpp)
    target_link_libraries(schgen_schematic_place_core_contracts PRIVATE schgen_core)
    target_compile_options(schgen_schematic_place_core_contracts PRIVATE
        -Wall -Wextra -Wpedantic -Werror -ffp-contract=off)
    add_test(NAME native_schematic_place_core_contracts COMMAND schgen_schematic_place_core_contracts
        "${CMAKE_CURRENT_SOURCE_DIR}/..")
    add_executable(schgen_design_rules_contracts tests/design_rules_contracts.cpp)
    target_link_libraries(schgen_design_rules_contracts PRIVATE schgen_core)
    target_compile_options(schgen_design_rules_contracts PRIVATE -Wall -Wextra -Wpedantic -Werror)
    add_test(NAME native_design_rules_contracts COMMAND schgen_design_rules_contracts
        "${CMAKE_CURRENT_SOURCE_DIR}/tests/data/design_rules")
    add_test(NAME native_design_rules_reject_missing_pullups COMMAND schgen design-rules
        --repo "${CMAKE_CURRENT_SOURCE_DIR}/.." --project devkit_mini power_mon)
    set_tests_properties(native_design_rules_reject_missing_pullups PROPERTIES WILL_FAIL TRUE)
    add_test(NAME native_design_rules_reject_som_option COMMAND schgen design-rules --som ignored)
    set_tests_properties(native_design_rules_reject_som_option PROPERTIES WILL_FAIL TRUE)
    add_executable(schgen_netlist_gate_contracts tests/netlist_gate_contracts.cpp)
    target_link_libraries(schgen_netlist_gate_contracts PRIVATE schgen_core)
    target_compile_options(schgen_netlist_gate_contracts PRIVATE -Wall -Wextra -Wpedantic -Werror)
    add_test(NAME native_netlist_gate_contracts COMMAND schgen_netlist_gate_contracts
        "${CMAKE_CURRENT_SOURCE_DIR}/tests/data/netlist_gate")
    add_executable(schgen_schematic_route_contracts tests/schematic_route_contracts.cpp)
    target_link_libraries(schgen_schematic_route_contracts PRIVATE schgen_core)
    target_compile_options(schgen_schematic_route_contracts PRIVATE -Wall -Wextra -Wpedantic -Werror)
    add_test(NAME native_schematic_route_contracts COMMAND schgen_schematic_route_contracts
        "${CMAKE_CURRENT_SOURCE_DIR}/tests/data/schematic_route" "${CMAKE_CURRENT_SOURCE_DIR}/..")
    add_executable(schgen_schematic_contracts tests/schematic_contracts.cpp)
    target_link_libraries(schgen_schematic_contracts PRIVATE schgen_core)
    target_compile_options(schgen_schematic_contracts PRIVATE -Wall -Wextra -Wpedantic -Werror)
    add_test(NAME native_schematic_contracts COMMAND schgen_schematic_contracts
        "${CMAKE_CURRENT_SOURCE_DIR}/tests/data/schematic")
    foreach(stage symbols validation devkit_design)
        add_executable(schgen_${stage}_contracts tests/${stage}_contracts.cpp)
        target_link_libraries(schgen_${stage}_contracts PRIVATE schgen_core)
        target_compile_options(schgen_${stage}_contracts PRIVATE -Wall -Wextra -Wpedantic -Werror)
        add_test(NAME native_${stage}_contracts COMMAND schgen_${stage}_contracts
            "${CMAKE_CURRENT_SOURCE_DIR}/..")
    endforeach()
    add_executable(schgen_project_outputs_contracts tests/project_outputs_contracts.cpp)
    target_link_libraries(schgen_project_outputs_contracts PRIVATE schgen_core)
    target_compile_options(schgen_project_outputs_contracts PRIVATE -Wall -Wextra -Wpedantic -Werror)
    add_test(NAME native_project_outputs_contracts COMMAND schgen_project_outputs_contracts
        "${CMAKE_CURRENT_SOURCE_DIR}/..")
    add_executable(schgen_devicetree_contracts tests/devicetree_contracts.cpp)
    target_link_libraries(schgen_devicetree_contracts PRIVATE schgen_core)
    target_compile_options(schgen_devicetree_contracts PRIVATE -Wall -Wextra -Wpedantic -Werror)
    add_test(NAME native_devicetree_contracts COMMAND schgen_devicetree_contracts
        "${CMAKE_CURRENT_SOURCE_DIR}/tests/data" "${CMAKE_CURRENT_SOURCE_DIR}/..")
    add_executable(schgen_link_contracts tests/link_contracts.cpp)
    target_link_libraries(schgen_link_contracts PRIVATE schgen_core)
    target_compile_options(schgen_link_contracts PRIVATE -Wall -Wextra -Wpedantic -Werror)
    add_test(NAME native_link_contracts COMMAND schgen_link_contracts)
    add_executable(schgen_project_contracts tests/project_contracts.cpp)
    target_link_libraries(schgen_project_contracts PRIVATE schgen_core)
    target_compile_options(schgen_project_contracts PRIVATE -Wall -Wextra -Wpedantic -Werror)
    add_test(NAME native_project_contracts COMMAND schgen_project_contracts
        "${CMAKE_CURRENT_SOURCE_DIR}/..")
    add_executable(schgen_som_interface_contracts tests/som_interface_contracts.cpp)
    target_link_libraries(schgen_som_interface_contracts PRIVATE schgen_core)
    target_compile_options(schgen_som_interface_contracts PRIVATE -Wall -Wextra -Wpedantic -Werror)
    add_test(NAME native_som_interface_contracts COMMAND schgen_som_interface_contracts
        "${CMAKE_CURRENT_SOURCE_DIR}/tests/data")
    add_executable(schgen_project_catalog_contracts tests/project_catalog_contracts.cpp)
    target_link_libraries(schgen_project_catalog_contracts PRIVATE schgen_core)
    target_compile_options(schgen_project_catalog_contracts PRIVATE -Wall -Wextra -Wpedantic -Werror)
    add_test(NAME native_project_catalog_contracts COMMAND schgen_project_catalog_contracts
        "${CMAKE_CURRENT_SOURCE_DIR}/..")
    add_executable(schgen_vivado_contracts tests/vivado_contracts.cpp)
    target_link_libraries(schgen_vivado_contracts PRIVATE schgen_core)
    target_compile_options(schgen_vivado_contracts PRIVATE -Wall -Wextra -Wpedantic -Werror)
    add_test(NAME native_vivado_contracts COMMAND schgen_vivado_contracts
        "${CMAKE_CURRENT_SOURCE_DIR}/tests/data/vivado_golden.tcl")
    add_executable(schgen_bom_contracts tests/bom_contracts.cpp)
    target_link_libraries(schgen_bom_contracts PRIVATE schgen_core)
    target_compile_options(schgen_bom_contracts PRIVATE -Wall -Wextra -Wpedantic -Werror)
    add_test(NAME native_bom_contracts COMMAND schgen_bom_contracts
        "${CMAKE_CURRENT_SOURCE_DIR}/..")
    foreach(project carrier devkit_mini)
        add_test(NAME native_project_${project} COMMAND schgen project-check
            --repo "${CMAKE_CURRENT_SOURCE_DIR}/.." --project ${project})
        add_test(NAME native_electrical_${project} COMMAND schgen circuit-check
            --repo "${CMAKE_CURRENT_SOURCE_DIR}/.." --project ${project})
        add_test(NAME native_design_rules_${project} COMMAND schgen design-rules
            --repo "${CMAKE_CURRENT_SOURCE_DIR}/.." --project ${project})
        add_test(NAME native_testpoints_${project} COMMAND schgen testpoints
            --repo "${CMAKE_CURRENT_SOURCE_DIR}/.." --project ${project})
    endforeach()
    add_executable(schgen_circuit_semantic_contracts tests/circuit_semantic_contracts.cpp)
    target_link_libraries(schgen_circuit_semantic_contracts PRIVATE schgen_core)
    target_compile_options(schgen_circuit_semantic_contracts PRIVATE
        -Wall -Wextra -Wpedantic -Werror)
    add_test(NAME native_circuit_semantic_contracts COMMAND schgen_circuit_semantic_contracts
        "${CMAKE_CURRENT_SOURCE_DIR}/../carrier/subsystems")
    add_executable(schgen_xdc_contracts tests/xdc_contracts.cpp)
    target_link_libraries(schgen_xdc_contracts PRIVATE schgen_core)
    target_compile_options(schgen_xdc_contracts PRIVATE -Wall -Wextra -Wpedantic -Werror)
    add_test(NAME native_xdc_contracts COMMAND schgen_xdc_contracts
        "${CMAKE_CURRENT_SOURCE_DIR}/tests/data/xdc_golden.xdc")
    foreach(contract numeric_contracts placement_search)
        add_executable(schgen_${contract} tests/${contract}.cpp)
        target_link_libraries(schgen_${contract} PRIVATE schgen_core)
        target_compile_options(schgen_${contract} PRIVATE -Wall -Wextra -Wpedantic -Werror)
        add_test(NAME native_${contract} COMMAND schgen_${contract})
    endforeach()
    add_executable(schgen_catalog_lifecycle tests/catalog_lifecycle.cpp)
    target_link_libraries(schgen_catalog_lifecycle PRIVATE schgen_core)
    target_compile_options(schgen_catalog_lifecycle PRIVATE -Wall -Wextra -Wpedantic -Werror)
    add_test(NAME native_catalog_lifecycle COMMAND schgen_catalog_lifecycle
        "${CMAKE_CURRENT_SOURCE_DIR}/..")
    add_executable(schgen_kernel_contracts tests/kernel_contracts.cpp)
    target_link_libraries(schgen_kernel_contracts PRIVATE schgen_core)
    target_compile_options(schgen_kernel_contracts PRIVATE -Wall -Wextra -Wpedantic -Werror)
    foreach(contract rounding sexpr routing seating placement_limits ratsnest)
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
