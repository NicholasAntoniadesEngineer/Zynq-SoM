# Search9: the production archive is uninstrumented; only the test scalar object
# observes real calls. Never publish these observers into schgen_core.
add_library(schgen_pack_search_observed OBJECT src/pack_search_precision.cpp)
target_include_directories(schgen_pack_search_observed PRIVATE include)
target_compile_options(schgen_pack_search_observed PRIVATE -Wall -Wextra -Wpedantic -Werror)
set_property(TARGET schgen_pack_search_observed PROPERTY INTERPROCEDURAL_OPTIMIZATION FALSE)
if(CMAKE_CXX_COMPILER_ID MATCHES "Clang")
    target_compile_options(schgen_pack_search_observed PRIVATE -finstrument-functions-after-inlining)
else()
    target_compile_options(schgen_pack_search_observed PRIVATE -finstrument-functions -fno-inline)
endif()
foreach(probe helper defined_edge board negative)
    add_executable(schgen_pack_search_${probe} tests/pack_search/${probe}_contracts.cpp
        $<TARGET_OBJECTS:schgen_pack_search_observed>)
    target_include_directories(schgen_pack_search_${probe} PRIVATE tests src)
    target_compile_definitions(schgen_pack_search_${probe} PRIVATE SEARCH_CANDIDATE)
    target_compile_options(schgen_pack_search_${probe} PRIVATE -Wall -Wextra -Wpedantic -Werror)
    set_property(TARGET schgen_pack_search_${probe} PROPERTY INTERPROCEDURAL_OPTIMIZATION FALSE)
    target_link_libraries(schgen_pack_search_${probe} PRIVATE schgen_core)
endforeach()
set(search9_fixture_dir "${CMAKE_CURRENT_SOURCE_DIR}/tests/data/pack_search_precision")
set(search9_runner "${CMAKE_CURRENT_SOURCE_DIR}/tests/pack_search/verify_output.cmake")
foreach(probe helper defined_edge board)
    add_test(NAME native_pack_search_${probe} COMMAND "${CMAKE_COMMAND}"
        "-DPROGRAM=$<TARGET_FILE:schgen_pack_search_${probe}>"
        "-DROOT=${CMAKE_CURRENT_SOURCE_DIR}/.." "-DPROBE=${probe}"
        "-DFIXTURES=${search9_fixture_dir}" "-DOUTPUT_DIR=${CMAKE_CURRENT_BINARY_DIR}/search9-proof"
        -P "${search9_runner}")
endforeach()
add_test(NAME native_pack_search_negative COMMAND schgen_pack_search_negative)
add_executable(schgen_pack_search_header tests/pack_search/header_contracts.cpp)
target_include_directories(schgen_pack_search_header PRIVATE include)
target_compile_options(schgen_pack_search_header PRIVATE -Wall -Wextra -Wpedantic -Werror)
add_test(NAME native_pack_search_header COMMAND schgen_pack_search_header)
add_executable(schgen_pack_search_adapters tests/pack_search/adapter_contracts.cpp)
target_include_directories(schgen_pack_search_adapters PRIVATE tests src)
target_link_libraries(schgen_pack_search_adapters PRIVATE schgen_core)
target_compile_options(schgen_pack_search_adapters PRIVATE -Wall -Wextra -Wpedantic -Werror)
add_test(NAME native_pack_search_adapters COMMAND schgen_pack_search_adapters)
add_executable(schgen_pack_search_source tests/pack_search/audit_contracts.cpp)
target_include_directories(schgen_pack_search_source PRIVATE tests)
target_link_libraries(schgen_pack_search_source PRIVATE schgen_core)
target_compile_options(schgen_pack_search_source PRIVATE -Wall -Wextra -Wpedantic -Werror)
add_test(NAME native_pack_search_source COMMAND "${CMAKE_COMMAND}"
    "-DPROGRAM=$<TARGET_FILE:schgen_pack_search_source>" "-DROOT=${CMAKE_CURRENT_SOURCE_DIR}/.."
    "-DFIXTURES=${search9_fixture_dir}" "-DOUTPUT_DIR=${CMAKE_CURRENT_BINARY_DIR}/search9-proof"
    -P "${CMAKE_CURRENT_SOURCE_DIR}/tests/pack_search/verify_source.cmake")
set_tests_properties(native_pack_search_source PROPERTIES RUN_SERIAL TRUE TIMEOUT 600)
add_test(NAME native_pack_search_fixture_mutation COMMAND "${CMAKE_COMMAND}"
    "-DFIXTURES=${search9_fixture_dir}" "-DOUTPUT_DIR=${CMAKE_CURRENT_BINARY_DIR}/search9-proof"
    "-DRUNNER=${search9_runner}" -P "${CMAKE_CURRENT_SOURCE_DIR}/tests/pack_search/fixture_mutation.cmake")

# Optional targeted UBSan proof. Historical UB probes are evidence, not normal
# tests; never run the original overflowing allocation without its sanitizer.
option(SCHGEN_SEARCH9_SANITIZERS "Build targeted Search9 UBSan proof executables" OFF)
if(SCHGEN_SEARCH9_SANITIZERS AND CMAKE_CXX_COMPILER_ID MATCHES "Clang|GNU")
    add_library(schgen_pack_search_san_ops OBJECT src/pack_search_precision.cpp)
    target_include_directories(schgen_pack_search_san_ops PRIVATE include)
    target_compile_options(schgen_pack_search_san_ops PRIVATE -fsanitize=undefined,float-cast-overflow -fno-sanitize-recover=all)
    set_property(TARGET schgen_pack_search_san_ops PROPERTY INTERPROCEDURAL_OPTIMIZATION FALSE)
    if(CMAKE_CXX_COMPILER_ID MATCHES "Clang")
        target_compile_options(schgen_pack_search_san_ops PRIVATE -finstrument-functions-after-inlining)
    else()
        target_compile_options(schgen_pack_search_san_ops PRIVATE -finstrument-functions -fno-inline)
    endif()
    foreach(probe helper negative)
        add_executable(schgen_pack_search_san_${probe} tests/pack_search/${probe}_contracts.cpp
            src/pack.cpp $<TARGET_OBJECTS:schgen_pack_search_san_ops>)
        target_include_directories(schgen_pack_search_san_${probe} PRIVATE tests src)
        target_compile_definitions(schgen_pack_search_san_${probe} PRIVATE SEARCH_CANDIDATE)
        target_compile_options(schgen_pack_search_san_${probe} PRIVATE -fsanitize=undefined,float-cast-overflow -fno-sanitize-recover=all)
        target_link_options(schgen_pack_search_san_${probe} PRIVATE -fsanitize=undefined,float-cast-overflow)
        target_link_libraries(schgen_pack_search_san_${probe} PRIVATE schgen_core)
        set_property(TARGET schgen_pack_search_san_${probe} PROPERTY INTERPROCEDURAL_OPTIMIZATION FALSE)
    endforeach()
    add_test(NAME native_pack_search_san_negative COMMAND schgen_pack_search_san_negative)
    add_test(NAME native_pack_search_san_helper COMMAND "${CMAKE_COMMAND}"
        "-DPROGRAM=$<TARGET_FILE:schgen_pack_search_san_helper>" "-DPROBE=helper"
        "-DROOT=${CMAKE_CURRENT_SOURCE_DIR}/.." "-DFIXTURES=${search9_fixture_dir}"
        "-DOUTPUT_DIR=${CMAKE_CURRENT_BINARY_DIR}/search9-proof/sanitized" -P "${search9_runner}")
endif()
