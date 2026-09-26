# Final native path. No tree-sitter, Python grammar, .py inputs or interpreter.
include_guard(GLOBAL)
set(SCHGEN_NATIVE_AUDIT_DIR "${CMAKE_CURRENT_LIST_DIR}/..")
function(schgen_add_native_audits target)
    target_sources(${target} PRIVATE
        "${SCHGEN_NATIVE_AUDIT_DIR}/src/native_audit_state.cpp"
        "${SCHGEN_NATIVE_AUDIT_DIR}/src/native_audit_accounting.cpp"
        "${SCHGEN_NATIVE_AUDIT_DIR}/src/native_audit_registry.cpp"
        "${SCHGEN_NATIVE_AUDIT_DIR}/src/native_audit_quantize.cpp"
        "${SCHGEN_NATIVE_AUDIT_DIR}/src/native_cpp_audits.cpp"
        "${SCHGEN_NATIVE_AUDIT_DIR}/src/verification_audits_counts.cpp")
    target_compile_features(${target} PUBLIC cxx_std_17)
    set_source_files_properties(
        "${SCHGEN_NATIVE_AUDIT_DIR}/src/native_audit_state.cpp"
        "${SCHGEN_NATIVE_AUDIT_DIR}/src/native_audit_accounting.cpp"
        "${SCHGEN_NATIVE_AUDIT_DIR}/src/native_audit_registry.cpp"
        "${SCHGEN_NATIVE_AUDIT_DIR}/src/native_audit_quantize.cpp"
        "${SCHGEN_NATIVE_AUDIT_DIR}/src/native_cpp_audits.cpp"
        "${SCHGEN_NATIVE_AUDIT_DIR}/src/verification_audits_counts.cpp"
        PROPERTIES COMPILE_OPTIONS "-ffp-contract=off;-Wall;-Wextra;-Wpedantic;-Werror")
endfunction()
