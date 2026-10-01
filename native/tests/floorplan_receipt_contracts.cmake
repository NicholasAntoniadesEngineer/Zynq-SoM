# Parent integration: include after schgen_core exists, inside BUILD_TESTING.
# No new production scalar, registry declaration or source-scope waiver.
add_library(schgen_floorplan_receipt_observed OBJECT
    ${CMAKE_CURRENT_SOURCE_DIR}/src/quantize.cpp
    ${CMAKE_CURRENT_SOURCE_DIR}/src/native_audit_quantize.cpp)
target_include_directories(schgen_floorplan_receipt_observed PRIVATE ${CMAKE_CURRENT_SOURCE_DIR}/include)
target_compile_options(schgen_floorplan_receipt_observed PRIVATE
    -Wall -Wextra -Wpedantic -Werror -ffp-contract=off)
set_property(TARGET schgen_floorplan_receipt_observed PROPERTY INTERPROCEDURAL_OPTIMIZATION FALSE)
if(CMAKE_CXX_COMPILER_ID MATCHES "Clang")
    target_compile_options(schgen_floorplan_receipt_observed PRIVATE -finstrument-functions-after-inlining)
else()
    target_compile_options(schgen_floorplan_receipt_observed PRIVATE -finstrument-functions -fno-inline)
endif()
add_executable(schgen_floorplan_receipt_contracts
    ${CMAKE_CURRENT_SOURCE_DIR}/tests/floorplan_receipt_contracts.cpp
    $<TARGET_OBJECTS:schgen_floorplan_receipt_observed>)
target_include_directories(schgen_floorplan_receipt_contracts PRIVATE ${CMAKE_CURRENT_SOURCE_DIR}/src)
target_link_libraries(schgen_floorplan_receipt_contracts PRIVATE schgen_core)
target_compile_options(schgen_floorplan_receipt_contracts PRIVATE
    -Wall -Wextra -Wpedantic -Werror -ffp-contract=off)
set_property(TARGET schgen_floorplan_receipt_contracts PROPERTY INTERPROCEDURAL_OPTIMIZATION FALSE)
add_test(NAME native_floorplan_receipt_contracts COMMAND schgen_floorplan_receipt_contracts)
