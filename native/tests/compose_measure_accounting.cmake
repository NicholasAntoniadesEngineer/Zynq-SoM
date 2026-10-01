# Parent integration: include(tests/compose_measure_accounting.cmake) inside BUILD_TESTING.
add_executable(schgen_compose_measure_accounting_contracts tests/compose_measure_accounting_contracts.cpp)
target_include_directories(schgen_compose_measure_accounting_contracts PRIVATE src)
target_link_libraries(schgen_compose_measure_accounting_contracts PRIVATE schgen_core)
target_compile_options(schgen_compose_measure_accounting_contracts PRIVATE
    -Wall -Wextra -Wpedantic -Werror -ffp-contract=off)
add_test(NAME native_compose_measure_accounting_contracts
    COMMAND schgen_compose_measure_accounting_contracts "${CMAKE_CURRENT_SOURCE_DIR}/..")
set_tests_properties(native_compose_measure_accounting_contracts PROPERTIES TIMEOUT 120)
