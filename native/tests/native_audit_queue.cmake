# Independent original implementation, copied verbatim from ffe6a470. Only the
# public entry-point names change in this test object; production uses the core.
file(SHA256 "${CMAKE_CURRENT_SOURCE_DIR}/tests/data/native_audit_queue/before-native_cpp_audits.cpp.txt" reference_hash)
if(NOT reference_hash STREQUAL "baa73e9181cd02ba9770de3dba85bf3125ac5aafd466007a9dc559335e195fc2")
    message(FATAL_ERROR "Original auditor reference changed")
endif()
configure_file(tests/data/native_audit_queue/before-native_cpp_audits.cpp.txt
    "${CMAKE_CURRENT_BINARY_DIR}/audit_queue_reference.cpp" COPYONLY)
add_library(schgen_audit_queue_reference OBJECT "${CMAKE_CURRENT_BINARY_DIR}/audit_queue_reference.cpp")
target_include_directories(schgen_audit_queue_reference PRIVATE include src)
target_compile_definitions(schgen_audit_queue_reference PRIVATE
    scan_cpp_audit_sources=scan_cpp_audit_sources_reference
    check_native_audits=check_native_audits_reference
    NativeAuditResult=NativeAuditResultReference)
target_compile_options(schgen_audit_queue_reference PRIVATE -Wall -Wextra -Wpedantic -Werror)
add_executable(schgen_native_audit_queue_contracts tests/native_audit_queue_contracts.cpp
    $<TARGET_OBJECTS:schgen_audit_queue_reference>)
target_link_libraries(schgen_native_audit_queue_contracts PRIVATE schgen_core)
target_compile_options(schgen_native_audit_queue_contracts PRIVATE -Wall -Wextra -Wpedantic -Werror)
add_test(NAME native_audit_queue_contracts COMMAND schgen_native_audit_queue_contracts
    "${CMAKE_CURRENT_BINARY_DIR}/audit-queue-proof")
set_tests_properties(native_audit_queue_contracts PROPERTIES RUN_SERIAL TRUE TIMEOUT 180)
