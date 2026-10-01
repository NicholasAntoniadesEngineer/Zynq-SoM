add_library(schgen_model_failure_observed OBJECT
    src/stage_precision.cpp src/placement_precision.cpp src/precision_ops.cpp
    src/pack_geometry_precision.cpp src/pack_precision.cpp src/output_precision.cpp)
target_include_directories(schgen_model_failure_observed PRIVATE include)
target_compile_options(schgen_model_failure_observed PRIVATE -Wall -Wextra -Wpedantic -Werror)
set_property(TARGET schgen_model_failure_observed PROPERTY INTERPROCEDURAL_OPTIMIZATION FALSE)
if(CMAKE_CXX_COMPILER_ID MATCHES "Clang")
    target_compile_options(schgen_model_failure_observed PRIVATE -finstrument-functions-after-inlining)
else()
    target_compile_options(schgen_model_failure_observed PRIVATE -finstrument-functions -fno-inline)
endif()
add_executable(schgen_model_failure_receipt_contracts tests/model_failure_receipt_contracts.cpp
    $<TARGET_OBJECTS:schgen_model_failure_observed>)
target_include_directories(schgen_model_failure_receipt_contracts PRIVATE src)
target_compile_options(schgen_model_failure_receipt_contracts PRIVATE -Wall -Wextra -Wpedantic -Werror -ffp-contract=off)
target_link_libraries(schgen_model_failure_receipt_contracts PRIVATE schgen_core)
add_test(NAME native_model_failure_receipt_contracts COMMAND schgen_model_failure_receipt_contracts
    "${CMAKE_CURRENT_SOURCE_DIR}/..")
