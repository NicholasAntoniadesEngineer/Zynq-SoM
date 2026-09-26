cmake_minimum_required(VERSION 3.20)
project(schgen_ci_smoke LANGUAGES CXX)
include(CTest)
find_package(Threads REQUIRED)
add_executable(schgen_ci_smoke main.cpp ../../src/process.cpp)
target_include_directories(schgen_ci_smoke PRIVATE ../../include)
set_target_properties(schgen_ci_smoke PROPERTIES
    CXX_STANDARD 17 CXX_STANDARD_REQUIRED YES CXX_EXTENSIONS NO)
target_compile_options(schgen_ci_smoke PRIVATE
    -Wall -Wextra -Wpedantic -Werror -ffp-contract=off)
target_link_libraries(schgen_ci_smoke PRIVATE Threads::Threads)
add_test(NAME native_ci_smoke_contracts COMMAND schgen_ci_smoke --contracts)
add_test(NAME native_ci_bootstrap_rejections COMMAND schgen_ci_smoke --bootstrap-contracts
    "${CMAKE_COMMAND}" "${CMAKE_CURRENT_SOURCE_DIR}/../BootstrapZlib.cmake")
add_test(NAME native_ci_smoke_reject_arguments COMMAND schgen_ci_smoke --unknown)
set_tests_properties(native_ci_smoke_reject_arguments PROPERTIES WILL_FAIL TRUE)
