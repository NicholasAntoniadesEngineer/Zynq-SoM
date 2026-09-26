cmake_minimum_required(VERSION 3.18)
project(schgen_native LANGUAGES CXX)
set_source_files_properties(src/legalize.cpp PROPERTIES COMPILE_OPTIONS "-ffp-contract=off")
set_source_files_properties(src/part_import_symbol.cpp src/part_import_footprint.cpp
    PROPERTIES COMPILE_OPTIONS "-ffp-contract=off")

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)
set(CMAKE_POSITION_INDEPENDENT_CODE ON)
option(SCHGEN_BUILD_PYTHON "Build transitional Python bindings" OFF)

# Compile one engine shared by the standalone CLI and transitional bindings.
add_library(schgen_core STATIC
    src/occupancy.cpp src/seat.cpp src/sexpr.cpp src/route.cpp src/emit.cpp
    src/legalize.cpp src/quantize.cpp src/precision_ops.cpp src/turn.cpp src/pack.cpp
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
    src/power_checks.cpp src/thermal_checks.cpp src/part_checks.cpp
    src/bom_values.cpp src/footprint_pads.cpp src/pin_completeness.cpp src/symbol_law.cpp
    src/spice.cpp src/spice_process.cpp src/process.cpp
    src/bringup_facts.cpp src/firmware_docs.cpp src/firmware_docs_manual.cpp src/firmware_provenance.cpp
    src/firmware_docs_testplan.cpp src/firmware_docs_scfw.cpp src/firmware_docs_power_sequence.cpp
    src/pcb_checks_model.cpp src/pcb_checks_connectors.cpp src/pcb_checks_placement.cpp
    src/pcb_checks_return_path.cpp src/pcb_checks_ampacity.cpp src/pcb_checks_escape.cpp src/pcb_checks_stitch.cpp)
set(SCHGEN_FLOORPLAN_SOURCES
    src/floorplan_spec.cpp src/floorplan_geometry.cpp src/floorplan_cross.cpp
    src/floorplan_pack.cpp src/floorplan_compose.cpp src/floorplan_build.cpp
    src/floorplan_ledger.cpp src/floorplan_json.cpp src/floorplan_notes.cpp
    src/floorplan_svg.cpp src/floorplan_md.cpp src/floorplan_output.cpp src/floorplan_export.cpp)
set(SCHGEN_PCB_EMIT_SOURCES
    src/pcb_model.cpp src/pcb_embed.cpp src/pcb_emit.cpp src/pcb_project.cpp src/pcb_silk.cpp)
target_sources(schgen_core PRIVATE ${SCHGEN_FLOORPLAN_SOURCES} ${SCHGEN_PCB_EMIT_SOURCES})
set(SCHGEN_SELFTEST_SOURCES
    src/selftest_full.cpp src/selftest_full_fixtures.cpp src/selftest_full_models.cpp
    src/selftest_full_json.cpp src/selftest_full_worker.cpp src/ratsnest_gate.cpp
    src/circuit_helpers.cpp)
target_sources(schgen_core PRIVATE ${SCHGEN_SELFTEST_SOURCES})
set(SCHGEN_MANUFACTURING_SOURCES
    src/manufacturing_assembly_plan.cpp src/manufacturing_assembly_documents.cpp
    src/manufacturing_assembly_images.cpp src/manufacturing_checks.cpp
    src/manufacturing_exports_manifest.cpp src/manufacturing_exports_si.cpp
    src/manufacturing_pipeline.cpp src/manufacturing_runs.cpp)
include(cmake/ManufacturingCompression.cmake)
schgen_require_manufacturing_compression()
target_sources(schgen_core PRIVATE ${SCHGEN_MANUFACTURING_SOURCES})
target_link_libraries(schgen_core PUBLIC schgen::manufacturing_compression)
include(cmake/native_audits.cmake)
schgen_add_native_audits(schgen_core)
target_sources(schgen_core PRIVATE src/procurement.cpp)
target_sources(schgen_core PRIVATE src/gallery.cpp src/diagram.cpp)
target_sources(schgen_core PRIVATE src/pcb_verification.cpp)
target_sources(schgen_core PRIVATE src/pcb_drc.cpp)
target_sources(schgen_core PRIVATE src/subsystem_build.cpp)
target_sources(schgen_core PRIVATE src/example_devkit.cpp)
target_sources(schgen_core PRIVATE src/net_contract.cpp)
target_sources(schgen_core PRIVATE src/doc_consistency.cpp)
target_sources(schgen_core PRIVATE src/regression_cli.cpp)
target_sources(schgen_core PRIVATE src/geometry_cli.cpp src/audit_ast_projection.cpp)
set_source_files_properties(src/geometry_cli.cpp src/audit_ast_projection.cpp
    PROPERTIES COMPILE_OPTIONS "-Wall;-Wextra;-Wpedantic;-Werror;-ffp-contract=off")
set_source_files_properties(src/regression_cli.cpp
    PROPERTIES COMPILE_OPTIONS "-Wall;-Wextra;-Wpedantic;-Werror;-ffp-contract=off")
set_source_files_properties(src/precision_ops.cpp
    PROPERTIES COMPILE_OPTIONS "-Wall;-Wextra;-Wpedantic;-Werror;-ffp-contract=off")
set_source_files_properties(src/doc_consistency.cpp
    PROPERTIES COMPILE_OPTIONS "-Wall;-Wextra;-Wpedantic;-Werror;-ffp-contract=off")
set_source_files_properties(src/net_contract.cpp src/example_devkit.cpp
    PROPERTIES COMPILE_OPTIONS "-Wall;-Wextra;-Wpedantic;-Werror;-ffp-contract=off")
target_sources(schgen_core PRIVATE src/experiment_tools_json.cpp src/experiment_tools_board.cpp
    src/experiment_tools_probe.cpp src/experiment_tools_catalog.cpp)
target_sources(schgen_core PRIVATE src/board_policy.cpp src/board_policy_metadata.cpp)
target_sources(schgen_core PRIVATE src/experiment_observers.cpp
    src/experiment_floorplan_probe.cpp src/pcb_placement_observer.cpp)
set_source_files_properties(src/experiment_observers.cpp src/experiment_floorplan_probe.cpp
    src/pcb_placement_observer.cpp src/experiment_tools_json.cpp src/experiment_tools_board.cpp
    src/experiment_tools_probe.cpp src/experiment_tools_catalog.cpp
    PROPERTIES COMPILE_OPTIONS "-Wall;-Wextra;-Wpedantic;-Werror;-ffp-contract=off")
target_sources(schgen_core PRIVATE src/part_import.cpp src/part_import_symbol.cpp
    src/part_import_footprint.cpp src/part_import_io.cpp src/part_import_cli.cpp)
target_sources(schgen_core PRIVATE
    src/board_pipeline.cpp src/board_pipeline_authoring.cpp src/board_pipeline_audits.cpp
    src/board_pipeline_cc.cpp src/board_pipeline_checks.cpp src/board_pipeline_coverage.cpp
    src/board_pipeline_documents.cpp src/board_pipeline_golden.cpp
    src/board_pipeline_pcb.cpp src/board_pipeline_schematic.cpp)
target_sources(schgen_core PRIVATE src/compose_repair_json.cpp src/compose_repair_edits.cpp
    src/compose_repair_measure.cpp src/compose_repair_driver.cpp)
set_source_files_properties(src/compose_repair_json.cpp src/compose_repair_edits.cpp
    src/compose_repair_measure.cpp src/compose_repair_driver.cpp
    PROPERTIES COMPILE_OPTIONS "-Wall;-Wextra;-Wpedantic;-Werror;-ffp-contract=off")
target_sources(schgen_core PRIVATE src/subsystem_scaffold_templates.cpp src/subsystem_scaffold_publish.cpp
    src/subsystem_registration.cpp src/subsystem_package_checks.cpp)
set_source_files_properties(src/subsystem_scaffold_templates.cpp src/subsystem_scaffold_publish.cpp
    src/subsystem_registration.cpp src/subsystem_package_checks.cpp
    PROPERTIES COMPILE_OPTIONS "-Wall;-Wextra;-Wpedantic;-Werror;-ffp-contract=off")
include(cmake/NativeRendering.cmake)
target_sources(schgen_core PRIVATE src/model3d_gate.cpp src/model3d_assets.cpp src/native_render.cpp)
target_link_libraries(schgen_core PUBLIC schgen_poppler_cpp PNG::PNG)
set_source_files_properties(src/model3d_gate.cpp src/model3d_assets.cpp src/native_render.cpp
    PROPERTIES COMPILE_OPTIONS "-Wall;-Wextra;-Wpedantic;-Werror;-ffp-contract=off")
target_sources(schgen_core PRIVATE src/component_basis.cpp src/component_basis_registry.cpp src/copper_debt.cpp)
set_source_files_properties(src/component_basis.cpp src/component_basis_registry.cpp src/copper_debt.cpp
    PROPERTIES COMPILE_OPTIONS "-Wall;-Wextra;-Wpedantic;-Werror;-ffp-contract=off")
set_source_files_properties(src/pcb_verification.cpp PROPERTIES COMPILE_OPTIONS "-ffp-contract=off")
target_sources(schgen_core PRIVATE src/pcb_placement_contract_gate.cpp src/pcb_placement_flow_gate.cpp src/pcb_placement_compose_gate.cpp)
set_source_files_properties(src/pcb_placement_contract_gate.cpp src/pcb_placement_flow_gate.cpp src/pcb_placement_compose_gate.cpp
    PROPERTIES COMPILE_OPTIONS "-ffp-contract=off")
set_source_files_properties(src/gallery.cpp src/diagram.cpp PROPERTIES COMPILE_OPTIONS "-ffp-contract=off")
target_sources(schgen_core PRIVATE src/ratsnest_documents.cpp src/ratsnest_images.cpp src/ratsnest_raster.cpp)
set_source_files_properties(src/ratsnest_documents.cpp src/ratsnest_images.cpp src/ratsnest_raster.cpp
    PROPERTIES COMPILE_OPTIONS "-ffp-contract=off")
set_source_files_properties(src/procurement.cpp PROPERTIES COMPILE_OPTIONS "-ffp-contract=off")
set(SCHGEN_PCB_PLACEMENT_SOURCES
    src/pcb_escape_model.cpp src/pcb_escape_triage.cpp src/pcb_escape_plan.cpp
    src/pcb_escape_copper.cpp src/pcb_escape_json.cpp
    src/pcb_stage_geometry.cpp src/pcb_stage_search.cpp src/pcb_stage_power.cpp src/pcb_stage_zone.cpp
    src/pcb_placement_inputs.cpp src/pcb_placement_pack.cpp src/pcb_placement_variants.cpp
    src/pcb_placement_zones.cpp src/pcb_placement_model.cpp src/pcb_placement_moves.cpp
    src/pcb_placement_breathe.cpp src/pcb_placement_build.cpp src/board_inputs.cpp src/board_pcb.cpp)
target_sources(schgen_core PRIVATE ${SCHGEN_PCB_PLACEMENT_SOURCES})
set_source_files_properties(${SCHGEN_PCB_PLACEMENT_SOURCES} PROPERTIES COMPILE_OPTIONS "-ffp-contract=off")
set_source_files_properties(${SCHGEN_MANUFACTURING_SOURCES} PROPERTIES COMPILE_OPTIONS "-ffp-contract=off")
file(GLOB authoring_builders CONFIGURE_DEPENDS
    "${CMAKE_CURRENT_SOURCE_DIR}/src/subsystem_authoring*.cpp"
    "${CMAKE_CURRENT_SOURCE_DIR}/src/project_authoring*.cpp")
set(authoring_sources src/authoring.cpp src/authoring_ir.cpp src/authoring_gates.cpp ${authoring_builders})
target_sources(schgen_core PRIVATE ${authoring_sources})
set_source_files_properties(${authoring_sources} PROPERTIES COMPILE_OPTIONS "-ffp-contract=off")
set_source_files_properties(${SCHGEN_SELFTEST_SOURCES} PROPERTIES COMPILE_OPTIONS "-ffp-contract=off")
set_source_files_properties(${SCHGEN_FLOORPLAN_SOURCES} ${SCHGEN_PCB_EMIT_SOURCES}
    PROPERTIES COMPILE_OPTIONS "-ffp-contract=off")
find_package(Threads REQUIRED)
find_package(LibXml2 REQUIRED)
target_link_libraries(schgen_core PUBLIC LibXml2::LibXml2 Threads::Threads)
target_include_directories(schgen_core PUBLIC "${CMAKE_CURRENT_SOURCE_DIR}/include")
target_compile_options(schgen_core PRIVATE -Wall -Wextra -Wpedantic -Werror)
set_source_files_properties(src/turn.cpp src/pack_anchor.cpp src/symbols.cpp
                            src/schematic_route.cpp src/schematic_place_core.cpp
                            src/schematic_place_fanout.cpp src/schematic_place_templates.cpp
                            src/schematic_place_chain.cpp src/schematic_place_pages.cpp src/board_schematic.cpp
                            src/pack_edges.cpp src/power_checks.cpp src/thermal_checks.cpp src/part_checks.cpp
                            src/bom_values.cpp src/spice.cpp src/spice_process.cpp
                            src/pcb_checks_model.cpp src/pcb_checks_connectors.cpp src/pcb_checks_placement.cpp
                            src/pcb_checks_return_path.cpp src/pcb_checks_ampacity.cpp src/pcb_checks_escape.cpp src/pcb_checks_stitch.cpp PROPERTIES
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
include(cmake/SubsystemPackages.cmake)
schgen_configure_subsystem_packages(schgen_core "${CMAKE_CURRENT_SOURCE_DIR}/..")
if(BUILD_TESTING)
    foreach(compose_test compose_repair compose_kernel)
        add_executable(schgen_${compose_test}_contracts tests/${compose_test}_contracts.cpp)
        target_include_directories(schgen_${compose_test}_contracts PRIVATE src)
        target_link_libraries(schgen_${compose_test}_contracts PRIVATE schgen_core)
        target_compile_options(schgen_${compose_test}_contracts PRIVATE -Wall -Wextra -Wpedantic -Werror -ffp-contract=off)
        add_test(NAME native_${compose_test}_contracts COMMAND schgen_${compose_test}_contracts "${CMAKE_CURRENT_SOURCE_DIR}/..")
    endforeach()
    add_executable(schgen_legalize_precision_contracts tests/legalize_precision_contracts.cpp)
    target_include_directories(schgen_legalize_precision_contracts PRIVATE src)
    target_link_libraries(schgen_legalize_precision_contracts PRIVATE schgen_core)
    target_compile_options(schgen_legalize_precision_contracts PRIVATE -Wall -Wextra -Wpedantic -Werror -ffp-contract=off)
    add_test(NAME native_legalize_precision_contracts COMMAND schgen_legalize_precision_contracts
        "${CMAKE_CURRENT_SOURCE_DIR}/tests/data/compose_repair/kernel_regressions.json")
    add_executable(schgen_subsystem_scaffold_contracts tests/subsystem_scaffold_contracts.cpp)
    target_link_libraries(schgen_subsystem_scaffold_contracts PRIVATE schgen_core Threads::Threads)
    target_compile_options(schgen_subsystem_scaffold_contracts PRIVATE -Wall -Wextra -Wpedantic -Werror -ffp-contract=off)
    add_test(NAME native_subsystem_scaffold_contracts COMMAND schgen_subsystem_scaffold_contracts "${CMAKE_CURRENT_SOURCE_DIR}/..")
    add_executable(schgen_subsystem_scaffold_build_contracts tests/subsystem_scaffold_build_contracts.cpp)
    target_link_libraries(schgen_subsystem_scaffold_build_contracts PRIVATE schgen_core)
    target_compile_options(schgen_subsystem_scaffold_build_contracts PRIVATE -Wall -Wextra -Wpedantic -Werror -ffp-contract=off)
    add_test(NAME native_subsystem_scaffold_build_contracts COMMAND schgen_subsystem_scaffold_build_contracts
        "${CMAKE_CURRENT_SOURCE_DIR}/.." "$<TARGET_FILE:schgen_core>" "${CMAKE_COMMAND}")
    add_executable(schgen_render_models_contracts tests/render_models_contracts.cpp)
    target_include_directories(schgen_render_models_contracts PRIVATE src)
    target_link_libraries(schgen_render_models_contracts PRIVATE schgen_core)
    target_compile_options(schgen_render_models_contracts PRIVATE -Wall -Wextra -Wpedantic -Werror -ffp-contract=off)
    add_test(NAME native_render_models_contracts COMMAND schgen_render_models_contracts
        "${CMAKE_CURRENT_SOURCE_DIR}/.." "${CMAKE_CURRENT_BINARY_DIR}/render-models-contract-output")
    add_test(NAME native_render_models_live_contracts COMMAND schgen_render_models_contracts
        "${CMAKE_CURRENT_SOURCE_DIR}/.." "${CMAKE_CURRENT_BINARY_DIR}/render-models-live-output" --live)
    set_tests_properties(native_render_models_live_contracts PROPERTIES LABELS live-kicad)
    foreach(audit component_basis copper_debt)
        add_executable(schgen_${audit}_contracts tests/${audit}_contracts.cpp)
        target_link_libraries(schgen_${audit}_contracts PRIVATE schgen_core)
        target_compile_options(schgen_${audit}_contracts PRIVATE -Wall -Wextra -Wpedantic -Werror -ffp-contract=off)
        add_test(NAME native_${audit}_contracts COMMAND schgen_${audit}_contracts "${CMAKE_CURRENT_SOURCE_DIR}/..")
    endforeach()
    add_library(schgen_observed_quantization OBJECT src/quantize.cpp src/native_audit_quantize.cpp)
    target_include_directories(schgen_observed_quantization PRIVATE include src)
    target_compile_options(schgen_observed_quantization PRIVATE -Wall -Wextra -Wpedantic -Werror
        -ffp-contract=off -finstrument-functions -fno-inline)
    add_executable(schgen_producer_accounting_contracts tests/producer_accounting_contracts.cpp
        $<TARGET_OBJECTS:schgen_observed_quantization>)
    target_include_directories(schgen_producer_accounting_contracts PRIVATE src)
    target_compile_options(schgen_producer_accounting_contracts PRIVATE -Wall -Wextra -Wpedantic -Werror -ffp-contract=off)
    target_link_libraries(schgen_producer_accounting_contracts PRIVATE schgen_core)
    add_test(NAME native_producer_accounting_contracts COMMAND schgen_producer_accounting_contracts "${CMAKE_CURRENT_SOURCE_DIR}/..")
    add_executable(schgen_pcb_drc_contracts tests/pcb_drc_contracts.cpp)
    target_link_libraries(schgen_pcb_drc_contracts PRIVATE schgen_core)
    target_compile_options(schgen_pcb_drc_contracts PRIVATE -Wall -Wextra -Wpedantic -Werror)
    add_test(NAME native_pcb_drc_contracts COMMAND schgen_pcb_drc_contracts)
    add_executable(schgen_manufacturing_contracts tests/manufacturing_contracts.cpp)
    add_executable(schgen_pcb_placement_gates_contracts tests/pcb_placement_gates_contracts.cpp)
    target_link_libraries(schgen_pcb_placement_gates_contracts PRIVATE schgen_core)
    target_compile_options(schgen_pcb_placement_gates_contracts PRIVATE -Wall -Wextra -Wpedantic -Werror -ffp-contract=off)
    add_test(NAME native_pcb_placement_gates_contracts COMMAND schgen_pcb_placement_gates_contracts "${CMAKE_CURRENT_SOURCE_DIR}/..")
    add_executable(schgen_gallery_diagram_contracts tests/gallery_diagram_contracts.cpp)
    target_link_libraries(schgen_gallery_diagram_contracts PRIVATE schgen_core)
    target_compile_options(schgen_gallery_diagram_contracts PRIVATE -Wall -Wextra -Wpedantic -Werror -ffp-contract=off)
    add_test(NAME native_gallery_diagram_contracts COMMAND schgen_gallery_diagram_contracts
        "${CMAKE_CURRENT_SOURCE_DIR}/tests/data/gallery_diagram"
        "${CMAKE_CURRENT_BINARY_DIR}/gallery-diagram-contract-output" "${CMAKE_CURRENT_SOURCE_DIR}/..")
    add_executable(schgen_ratsnest_documents_contracts tests/ratsnest_documents_contracts.cpp)
    target_include_directories(schgen_ratsnest_documents_contracts PRIVATE "${CMAKE_CURRENT_SOURCE_DIR}/src")
    target_link_libraries(schgen_ratsnest_documents_contracts PRIVATE schgen_core)
    target_compile_options(schgen_ratsnest_documents_contracts PRIVATE -Wall -Wextra -Wpedantic -Werror -ffp-contract=off)
    add_test(NAME native_ratsnest_documents_contracts COMMAND schgen_ratsnest_documents_contracts
        "${CMAKE_CURRENT_SOURCE_DIR}/.." "${CMAKE_CURRENT_BINARY_DIR}/ratsnest-document-results")
    add_executable(schgen_procurement_contracts tests/procurement_contracts.cpp)
    target_link_libraries(schgen_procurement_contracts PRIVATE schgen_core)
    target_compile_options(schgen_procurement_contracts PRIVATE -Wall -Wextra -Wpedantic -Werror -ffp-contract=off)
    add_test(NAME native_procurement_contracts COMMAND schgen_procurement_contracts)
    add_executable(schgen_native_audits_contracts tests/native_audits_contracts.cpp tests/native_accounting_contracts.cpp)
    target_link_libraries(schgen_native_audits_contracts PRIVATE schgen_core)
    target_include_directories(schgen_native_audits_contracts PRIVATE "${CMAKE_CURRENT_SOURCE_DIR}/src")
    target_compile_options(schgen_native_audits_contracts PRIVATE -Wall -Wextra -Wpedantic -Werror -ffp-contract=off)
    add_test(NAME native_policy_audits_contracts COMMAND schgen_native_audits_contracts "${CMAKE_CURRENT_SOURCE_DIR}/..")
    add_executable(schgen_pack_silk_contracts tests/pack_silk_contracts.cpp)
    target_link_libraries(schgen_pack_silk_contracts PRIVATE schgen_core)
    target_compile_options(schgen_pack_silk_contracts PRIVATE -Wall -Wextra -Wpedantic -Werror -ffp-contract=off)
    add_test(NAME native_pack_silk_contracts COMMAND schgen_pack_silk_contracts
        "${CMAKE_CURRENT_SOURCE_DIR}/tests/data/pack_silk/cases.json")
    add_executable(schgen_board_live_contracts tests/board_live_contracts.cpp)
    target_link_libraries(schgen_board_live_contracts PRIVATE schgen_core)
    target_compile_options(schgen_board_live_contracts PRIVATE -Wall -Wextra -Wpedantic -Werror -ffp-contract=off)
    add_test(NAME native_board_live_contracts COMMAND schgen_board_live_contracts
        "${CMAKE_CURRENT_SOURCE_DIR}/.." "${CMAKE_CURRENT_BINARY_DIR}/board-live-contract-results")
    set_tests_properties(native_board_live_contracts PROPERTIES LABELS "live-kicad")
    foreach(family pcb_escape pcb_stage pcb_placement board_inputs)
        add_executable(schgen_${family}_contracts tests/${family}_contracts.cpp)
        target_link_libraries(schgen_${family}_contracts PRIVATE schgen_core)
        target_compile_options(schgen_${family}_contracts PRIVATE -Wall -Wextra -Wpedantic -Werror -ffp-contract=off)
        add_test(NAME native_${family}_contracts COMMAND schgen_${family}_contracts "${CMAKE_CURRENT_SOURCE_DIR}/..")
    endforeach()
    target_link_libraries(schgen_manufacturing_contracts PRIVATE schgen_core)
    target_compile_options(schgen_manufacturing_contracts PRIVATE -Wall -Wextra -Wpedantic -Werror -ffp-contract=off)
    add_test(NAME native_manufacturing_contracts COMMAND schgen_manufacturing_contracts
        "${CMAKE_CURRENT_SOURCE_DIR}/.." "${CMAKE_CURRENT_BINARY_DIR}/manufacturing-contract-results")
    add_executable(schgen_json_unicode_contracts tests/json_unicode_contracts.cpp)
    target_link_libraries(schgen_json_unicode_contracts PRIVATE schgen_core)
    target_compile_options(schgen_json_unicode_contracts PRIVATE -Wall -Wextra -Wpedantic -Werror)
    add_test(NAME native_json_unicode_contracts COMMAND schgen_json_unicode_contracts)
    foreach(family subsystem_authoring authoring_gates)
        add_executable(schgen_${family}_contracts tests/${family}_contracts.cpp)
        target_link_libraries(schgen_${family}_contracts PRIVATE schgen_core)
        target_compile_options(schgen_${family}_contracts PRIVATE -Wall -Wextra -Wpedantic -Werror -ffp-contract=off)
        add_test(NAME native_${family}_contracts COMMAND schgen_${family}_contracts "${CMAKE_CURRENT_SOURCE_DIR}/..")
    endforeach()
    add_executable(schgen_selftest_full_contracts tests/selftest_full_contracts.cpp)
    target_link_libraries(schgen_selftest_full_contracts PRIVATE schgen_core)
    target_include_directories(schgen_selftest_full_contracts PRIVATE "${CMAKE_CURRENT_SOURCE_DIR}/src")
    target_compile_options(schgen_selftest_full_contracts PRIVATE -Wall -Wextra -Wpedantic -Werror -ffp-contract=off)
    find_file(SCHGEN_TEST_RESISTOR_FOOTPRINT R_0603_1608Metric.kicad_mod
        PATHS /Applications/KiCad/KiCad.app/Contents/SharedSupport/footprints
              /usr/share/kicad/footprints /usr/local/share/kicad/footprints
        PATH_SUFFIXES Resistor_SMD.pretty)
    if(SCHGEN_TEST_RESISTOR_FOOTPRINT)
        add_test(NAME native_selftest_full_contracts COMMAND schgen_selftest_full_contracts
            "${CMAKE_CURRENT_SOURCE_DIR}/.." "${SCHGEN_TEST_RESISTOR_FOOTPRINT}")
        set_tests_properties(native_selftest_full_contracts PROPERTIES LABELS "live-kicad")
    endif()
    add_executable(schgen_floorplan_contracts tests/floorplan_contracts.cpp)
    target_link_libraries(schgen_floorplan_contracts PRIVATE schgen_core)
    target_compile_options(schgen_floorplan_contracts PRIVATE -Wall -Wextra -Wpedantic -Werror -ffp-contract=off)
    add_test(NAME native_floorplan_contracts COMMAND schgen_floorplan_contracts
        "${CMAKE_CURRENT_SOURCE_DIR}/tests/data/floorplan")
    add_executable(schgen_pcb_emit_contracts tests/pcb_emit_contracts.cpp)
    target_link_libraries(schgen_pcb_emit_contracts PRIVATE schgen_core)
    target_compile_options(schgen_pcb_emit_contracts PRIVATE -Wall -Wextra -Wpedantic -Werror -ffp-contract=off)
    add_test(NAME native_pcb_emit_contracts COMMAND schgen_pcb_emit_contracts
        "${CMAKE_CURRENT_SOURCE_DIR}/tests/data/pcb_emit" "${CMAKE_CURRENT_BINARY_DIR}/pcb-emit-contract-output")
    add_executable(schgen_pcb_checks_contracts tests/pcb_checks_contracts.cpp)
    target_link_libraries(schgen_pcb_checks_contracts PRIVATE schgen_core)
    target_compile_options(schgen_pcb_checks_contracts PRIVATE -Wall -Wextra -Wpedantic -Werror -ffp-contract=off)
    add_test(NAME native_pcb_checks_contracts COMMAND schgen_pcb_checks_contracts "${CMAKE_CURRENT_SOURCE_DIR}/..")
    add_executable(schgen_firmware_docs_contracts tests/firmware_docs_contracts.cpp)
    add_executable(schgen_process_contracts tests/process_contracts.cpp)
    add_executable(schgen_render_project_base_contracts tests/render_project_base_contracts.cpp)
    target_include_directories(schgen_render_project_base_contracts PRIVATE src)
    target_link_libraries(schgen_render_project_base_contracts PRIVATE schgen_core)
    target_compile_options(schgen_render_project_base_contracts PRIVATE -Wall -Wextra -Wpedantic -Werror -ffp-contract=off)
    add_test(NAME native_render_project_base_contracts COMMAND schgen_render_project_base_contracts "${CMAKE_CURRENT_SOURCE_DIR}/..")
    set_tests_properties(native_render_project_base_contracts PROPERTIES LABELS live-kicad)
    target_link_libraries(schgen_process_contracts PRIVATE schgen_core)
    target_compile_options(schgen_process_contracts PRIVATE -Wall -Wextra -Wpedantic -Werror)
    add_test(NAME native_process_contracts COMMAND schgen_process_contracts)
    add_executable(schgen_part_import_contracts tests/part_import_contracts.cpp)
    target_link_libraries(schgen_part_import_contracts PRIVATE schgen_core)
    target_compile_options(schgen_part_import_contracts PRIVATE -Wall -Wextra -Wpedantic -Werror)
    add_test(NAME native_part_import_contracts COMMAND schgen_part_import_contracts
        "${CMAKE_CURRENT_SOURCE_DIR}/tests/data/part_gen" "$<TARGET_FILE:schgen>")
    add_executable(schgen_board_pipeline_contracts tests/board_pipeline_contracts.cpp)
    add_executable(schgen_net_contract_contracts tests/net_contract_contracts.cpp)
    add_executable(schgen_doc_consistency_contracts tests/doc_consistency_contracts.cpp)
    add_executable(schgen_geometry_cli_contracts tests/geometry_cli_contracts.cpp)
    target_link_libraries(schgen_geometry_cli_contracts PRIVATE schgen_core)
    target_compile_options(schgen_geometry_cli_contracts PRIVATE
        -Wall -Wextra -Wpedantic -Werror -ffp-contract=off)
    add_test(NAME native_geometry_cli_contracts COMMAND schgen_geometry_cli_contracts
        "${CMAKE_CURRENT_SOURCE_DIR}/.." --system-temp)
    add_test(NAME native_geometry_cli_live_contracts COMMAND schgen_geometry_cli_contracts
        "${CMAKE_CURRENT_SOURCE_DIR}/.." --system-temp --live-kicad)
    add_test(NAME native_geometry_cli_apply_contracts COMMAND schgen_geometry_cli_contracts
        "${CMAKE_CURRENT_SOURCE_DIR}/.." --system-temp --live-apply)
    set_tests_properties(native_geometry_cli_live_contracts native_geometry_cli_apply_contracts
        PROPERTIES LABELS "live-kicad" TIMEOUT 1200)
    add_executable(schgen_audit_ast_projection_contracts tests/audit_ast_projection_contracts.cpp)
    target_link_libraries(schgen_audit_ast_projection_contracts PRIVATE schgen_core)
    target_compile_options(schgen_audit_ast_projection_contracts PRIVATE
        -Wall -Wextra -Wpedantic -Werror -ffp-contract=off)
    add_test(NAME native_audit_ast_projection_contracts COMMAND schgen_audit_ast_projection_contracts)
    # Includes the actual visitor once; the ordinary archive is not force-loaded.
    add_executable(schgen_audit_ast_projection_census tests/audit_ast_projection_census.cpp)
    target_include_directories(schgen_audit_ast_projection_census PRIVATE src)
    target_link_libraries(schgen_audit_ast_projection_census PRIVATE schgen_core)
    target_compile_options(schgen_audit_ast_projection_census PRIVATE
        -Wall -Wextra -Wpedantic -Werror -ffp-contract=off)
    add_test(NAME native_audit_ast_projection_census COMMAND schgen_audit_ast_projection_census
        --selftest "${CMAKE_CURRENT_SOURCE_DIR}/..")
    foreach(family precision_ops native_cpp_enum)
        add_executable(schgen_${family}_contracts tests/${family}_contracts.cpp)
        target_link_libraries(schgen_${family}_contracts PRIVATE schgen_core)
        target_compile_options(schgen_${family}_contracts PRIVATE
            -Wall -Wextra -Wpedantic -Werror -ffp-contract=off)
        add_test(NAME native_${family}_contracts COMMAND schgen_${family}_contracts)
    endforeach()
    # Only the private operation object is instrumented. Its actual function
    # entries independently verify producer counters; production stays untouched.
    add_library(schgen_precision_observed OBJECT src/precision_ops.cpp)
    target_include_directories(schgen_precision_observed PRIVATE include)
    target_compile_options(schgen_precision_observed PRIVATE
        -Wall -Wextra -Wpedantic -Werror -ffp-contract=off -finstrument-functions -fno-inline)
    add_executable(schgen_precision_accounting_contracts tests/precision_accounting_contracts.cpp
        $<TARGET_OBJECTS:schgen_precision_observed>)
    target_include_directories(schgen_precision_accounting_contracts PRIVATE src)
    target_link_libraries(schgen_precision_accounting_contracts PRIVATE schgen_core)
    target_compile_options(schgen_precision_accounting_contracts PRIVATE
        -Wall -Wextra -Wpedantic -Werror -ffp-contract=off)
    add_test(NAME native_precision_accounting_contracts COMMAND schgen_precision_accounting_contracts
        "${CMAKE_CURRENT_SOURCE_DIR}/..")
    foreach(family regression_cli regression_rc_smoke)
        add_executable(schgen_${family}_contracts tests/${family}_contracts.cpp)
        target_link_libraries(schgen_${family}_contracts PRIVATE schgen_core)
        target_compile_options(schgen_${family}_contracts PRIVATE
            -Wall -Wextra -Wpedantic -Werror -ffp-contract=off)
    endforeach()
    add_test(NAME native_regression_cli_contracts
        COMMAND schgen_regression_cli_contracts "${CMAKE_COMMAND}" "${CMAKE_CTEST_COMMAND}")
    set_tests_properties(native_regression_cli_contracts PROPERTIES TIMEOUT 120)
    add_test(NAME native_regression_rc_smoke
        COMMAND schgen_regression_rc_smoke_contracts "${CMAKE_CURRENT_SOURCE_DIR}/..")
    set_tests_properties(native_regression_rc_smoke PROPERTIES TIMEOUT 120 LABELS "live-kicad")
    target_link_libraries(schgen_doc_consistency_contracts PRIVATE schgen_core)
    target_compile_options(schgen_doc_consistency_contracts PRIVATE -Wall -Wextra -Wpedantic -Werror -ffp-contract=off)
    add_test(NAME native_doc_consistency_contracts COMMAND schgen_doc_consistency_contracts "${CMAKE_CURRENT_SOURCE_DIR}/.." "${CMAKE_CURRENT_BINARY_DIR}/doc-consistency-contract-output")
    target_link_libraries(schgen_net_contract_contracts PRIVATE schgen_core)
    target_compile_options(schgen_net_contract_contracts PRIVATE -Wall -Wextra -Wpedantic -Werror -ffp-contract=off)
    add_test(NAME native_net_contract_contracts COMMAND schgen_net_contract_contracts "${CMAKE_CURRENT_SOURCE_DIR}/.." "${CMAKE_CURRENT_BINARY_DIR}/net-contract-contract-output")
    add_executable(schgen_example_devkit_contracts tests/example_devkit_contracts.cpp)
    target_link_libraries(schgen_example_devkit_contracts PRIVATE schgen_core)
    target_compile_options(schgen_example_devkit_contracts PRIVATE -Wall -Wextra -Wpedantic -Werror -ffp-contract=off)
    add_test(NAME native_example_devkit_contracts COMMAND schgen_example_devkit_contracts "${CMAKE_CURRENT_SOURCE_DIR}/..")
    add_test(NAME native_example_devkit_live_contracts COMMAND schgen_example_devkit_contracts "${CMAKE_CURRENT_SOURCE_DIR}/.." --live)
    set_tests_properties(native_example_devkit_live_contracts PROPERTIES LABELS live-kicad)
    add_executable(schgen_board_policy_contracts tests/board_policy_contracts.cpp)
    target_include_directories(schgen_board_policy_contracts PRIVATE src)
    add_executable(schgen_board_policy_migration_contracts tests/board_policy_migration_contracts.cpp)
    target_include_directories(schgen_board_policy_migration_contracts PRIVATE src)
    target_link_libraries(schgen_board_policy_migration_contracts PRIVATE schgen_core)
    target_compile_options(schgen_board_policy_migration_contracts PRIVATE -Wall -Wextra -Wpedantic -Werror -ffp-contract=off)
    add_test(NAME native_board_policy_migration_contracts COMMAND schgen_board_policy_migration_contracts "${CMAKE_CURRENT_SOURCE_DIR}/..")
    add_executable(schgen_native_cpp_auditor_contracts tests/native_cpp_auditor_contracts.cpp)
    target_link_libraries(schgen_native_cpp_auditor_contracts PRIVATE schgen_core)
    target_compile_options(schgen_native_cpp_auditor_contracts PRIVATE -Wall -Wextra -Wpedantic -Werror -ffp-contract=off)
    add_test(NAME native_cpp_auditor_contracts COMMAND schgen_native_cpp_auditor_contracts "${CMAKE_CURRENT_SOURCE_DIR}/..")
    target_link_libraries(schgen_board_policy_contracts PRIVATE schgen_core)
    target_compile_options(schgen_board_policy_contracts PRIVATE -Wall -Wextra -Wpedantic -Werror -ffp-contract=off)
    add_test(NAME native_board_policy_contracts COMMAND schgen_board_policy_contracts "${CMAKE_CURRENT_SOURCE_DIR}/.." --compiler)
    add_executable(schgen_experiment_observer_contracts tests/experiment_observer_contracts.cpp)
    add_executable(schgen_experiment_tools_contracts tests/experiment_tools_contracts.cpp)
    target_link_libraries(schgen_experiment_tools_contracts PRIVATE schgen_core)
    target_compile_options(schgen_experiment_tools_contracts PRIVATE -Wall -Wextra -Wpedantic -Werror -ffp-contract=off)
    add_test(NAME native_experiment_tools_contracts COMMAND schgen_experiment_tools_contracts "${CMAKE_CURRENT_SOURCE_DIR}/.." --live)
    target_include_directories(schgen_experiment_observer_contracts PRIVATE src)
    target_link_libraries(schgen_experiment_observer_contracts PRIVATE schgen_core)
    target_compile_options(schgen_experiment_observer_contracts PRIVATE -Wall -Wextra -Wpedantic -Werror -ffp-contract=off)
    add_test(NAME native_experiment_observer_contracts COMMAND schgen_experiment_observer_contracts "${CMAKE_CURRENT_SOURCE_DIR}/.." --live)
    target_include_directories(schgen_board_pipeline_contracts PRIVATE src)
    target_link_libraries(schgen_board_pipeline_contracts PRIVATE schgen_core PNG::PNG)
    target_compile_options(schgen_board_pipeline_contracts PRIVATE -Wall -Wextra -Wpedantic -Werror)
    add_test(NAME native_board_pipeline_contracts COMMAND schgen_board_pipeline_contracts
        "${CMAKE_CURRENT_SOURCE_DIR}/..")
    add_test(NAME native_board_pipeline_live_contracts COMMAND schgen_board_pipeline_contracts
        "${CMAKE_CURRENT_SOURCE_DIR}/.." --live-kicad)
    add_test(NAME native_single_sheet_live COMMAND schgen build pd_input
        --repo "${CMAKE_CURRENT_SOURCE_DIR}/.." --project devkit_mini --no-render
        -o "${CMAKE_CURRENT_BINARY_DIR}/single-sheet-live")
    set_tests_properties(native_board_pipeline_live_contracts native_single_sheet_live
        PROPERTIES LABELS "live-kicad")
    add_executable(schgen_firmware_provenance_contracts tests/firmware_provenance_contracts.cpp)
    target_link_libraries(schgen_firmware_provenance_contracts PRIVATE schgen_core)
    target_compile_options(schgen_firmware_provenance_contracts PRIVATE -Wall -Wextra -Wpedantic -Werror)
    add_test(NAME native_firmware_provenance_contracts COMMAND schgen_firmware_provenance_contracts
        "${CMAKE_CURRENT_SOURCE_DIR}/..")
    target_link_libraries(schgen_firmware_docs_contracts PRIVATE schgen_core)
    target_compile_options(schgen_firmware_docs_contracts PRIVATE -Wall -Wextra -Wpedantic -Werror)
    add_test(NAME native_firmware_docs_contracts COMMAND schgen_firmware_docs_contracts
        "${CMAKE_CURRENT_SOURCE_DIR}/.." "${CMAKE_CURRENT_BINARY_DIR}/firmware-docs-contract-output")
    foreach(family verification spice)
        add_executable(schgen_${family}_contracts tests/${family}_contracts.cpp)
        target_link_libraries(schgen_${family}_contracts PRIVATE schgen_core)
        target_compile_options(schgen_${family}_contracts PRIVATE -Wall -Wextra -Wpedantic -Werror -ffp-contract=off)
        add_test(NAME native_${family}_contracts COMMAND schgen_${family}_contracts
            "${CMAKE_CURRENT_SOURCE_DIR}/tests/data/${family}")
    endforeach()
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
    add_test(NAME native_subsystem_check_cli COMMAND schgen subsystem-check --repo "${CMAKE_CURRENT_SOURCE_DIR}/..")
    add_test(NAME native_carrier_check_cli COMMAND schgen carrier-check --repo "${CMAKE_CURRENT_SOURCE_DIR}/..")
    add_test(NAME native_devkit_check_cli COMMAND schgen carrier-check --project devkit_mini --repo "${CMAKE_CURRENT_SOURCE_DIR}/..")
    foreach(command board build devkit nets chir-rung w11-sweep w12-bound w12-stageprobe dump-circuits
            selftest project-check circuit-check som-interface xdc vivado fpga bom link devicetree
            design-rules testpoints board-schematic pcb-stage pcb-drc subsystem-new render3d board-step
            model3d-check assembly ratsnest gallery diagram si-constraints fab-profile manifest preflight
            constraints powertree thermal part-rules bom-values footprint-pads pin-completeness symbol-law
            spice firmware manual scfw testplan power-sequence subsystem-check carrier-check check floorplan compose)
        add_test(NAME native_${command}_help COMMAND schgen ${command} --help --repo /nonexistent/schgen-help-must-not-read)
    endforeach()
    add_test(NAME native_part_import_help COMMAND schgen part-import --help
        --parts-root /nonexistent/schgen-help-must-not-write --from-json /nonexistent/schgen-help-must-not-read)
    add_test(NAME native_reject_board COMMAND schgen board --skip-audits)
    add_test(NAME native_reject_self_check_args COMMAND schgen self-check extra)
    add_test(NAME native_reject_missing_catalog_args COMMAND schgen catalog-compile)
    set_tests_properties(native_reject_board native_reject_self_check_args
        native_reject_missing_catalog_args PROPERTIES WILL_FAIL TRUE)
endif()
