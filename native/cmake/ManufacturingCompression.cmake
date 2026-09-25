# Exact assembly PNG compression, without Python, downloads or system fallback.
# Usage (after project(... LANGUAGES CXX)):
#   include(cmake/ManufacturingCompression.cmake)
#   schgen_require_manufacturing_compression()
#   target_link_libraries(schgen_core PUBLIC schgen::manufacturing_compression)
# Configure with -DSCHGEN_MANUFACTURING_ZLIB_PREFIX=/absolute/installed/prefix.
# The prefix must contain a PIC static zlib-ng 2.3.3, built ZLIB_COMPAT=ON.
# This deliberately does not define/replace ZLIB::ZLIB or change global searches.
include_guard(GLOBAL)

function(schgen_require_manufacturing_compression)
    set(SCHGEN_MANUFACTURING_ZLIB_PREFIX "" CACHE PATH
        "Installed PIC static zlib-ng 2.3.3 prefix (ZLIB_COMPAT=ON); no automatic download")
    if(NOT IS_ABSOLUTE "${SCHGEN_MANUFACTURING_ZLIB_PREFIX}" OR
       NOT IS_DIRECTORY "${SCHGEN_MANUFACTURING_ZLIB_PREFIX}" OR
       "${SCHGEN_MANUFACTURING_ZLIB_PREFIX}" MATCHES ";")
        message(FATAL_ERROR
            "Manufacturing PNGs require an explicit installed zlib-ng 2.3.3 prefix. "
            "Set SCHGEN_MANUFACTURING_ZLIB_PREFIX to an existing absolute directory "
            "containing include/zlib.h and a PIC static library built with ZLIB_COMPAT=ON. "
            "See native/tests/data/manufacturing/README.md; no Python/system fallback is used.")
    endif()
    get_filename_component(_prefix "${SCHGEN_MANUFACTURING_ZLIB_PREFIX}" REALPATH)
    if(TARGET schgen_manufacturing_compression)
        get_target_property(_previous schgen_manufacturing_compression SCHGEN_ZLIB_PREFIX)
        if(NOT "${_previous}" STREQUAL "${_prefix}")
            message(FATAL_ERROR "Manufacturing compression target already exists with a different prefix")
        endif()
        return()
    endif()
    if(NOT CMAKE_CXX_COMPILER_LOADED)
        message(FATAL_ERROR "ManufacturingCompression.cmake requires the CXX language to be enabled")
    endif()
    if(CMAKE_CROSSCOMPILING AND NOT CMAKE_CROSSCOMPILING_EMULATOR)
        message(FATAL_ERROR
            "Manufacturing compression must run its byte-compatibility probe. "
            "Cross builds require a working CMAKE_CROSSCOMPILING_EMULATOR; there is no skip/waiver option.")
    endif()
    set(_include "${_prefix}/include")
    foreach(_header zlib.h zconf.h)
        if(NOT EXISTS "${_include}/${_header}")
            message(FATAL_ERROR "Manufacturing compression prefix is missing include/${_header}: ${_prefix}")
        endif()
    endforeach()
    file(READ "${_include}/zlib.h" _header_text)
    foreach(_definition ZLIBNG_VERSION ZLIB_VERSION)
        string(REGEX MATCH "#[ \t]*define[ \t]+${_definition}[ \t]+\"([^\"]+)\"" _match "${_header_text}")
        set(_${_definition} "${CMAKE_MATCH_1}")
    endforeach()
    if(NOT "${_ZLIBNG_VERSION}" STREQUAL "2.3.3" OR
       NOT "${_ZLIB_VERSION}" STREQUAL "1.3.1.zlib-ng")
        message(FATAL_ERROR
            "Manufacturing PNG bytes require zlib-ng 2.3.3 in ZLIB_COMPAT mode "
            "(ZLIB_VERSION=1.3.1.zlib-ng). Found ZLIBNG_VERSION='${_ZLIBNG_VERSION}', "
            "ZLIB_VERSION='${_ZLIB_VERSION}' in ${_include}/zlib.h. "
            "Stock zlib and other releases are not interchangeable.")
    endif()
    # Explicit filenames avoid accidentally selecting a shared import library or
    # changing FindZLIB/global CMAKE_FIND_LIBRARY_SUFFIXES for unrelated targets.
    if(MSVC)
        set(_archive_name zlibstatic.lib)
    else()
        set(_archive_name libz.a)
    endif()
    set(_library_dirs "${_prefix}/lib" "${_prefix}/lib64")
    if(CMAKE_LIBRARY_ARCHITECTURE)
        list(APPEND _library_dirs "${_prefix}/lib/${CMAKE_LIBRARY_ARCHITECTURE}")
    endif()
    unset(_schgen_compression_archive)
    unset(_schgen_compression_archive CACHE)
    find_file(_schgen_compression_archive NAMES "${_archive_name}"
        PATHS ${_library_dirs} NO_DEFAULT_PATH NO_CMAKE_FIND_ROOT_PATH)
    set(_archive "${_schgen_compression_archive}")
    unset(_schgen_compression_archive CACHE)
    if(NOT _archive)
        message(FATAL_ERROR
            "Manufacturing compression requires ${_archive_name} under ${_prefix}/lib, lib64 "
            "or lib/<architecture>. Install with BUILD_SHARED_LIBS=OFF and "
            "CMAKE_POSITION_INDEPENDENT_CODE=ON; a shared-only installation is not accepted.")
    endif()

    # A version label alone cannot prove deflate byte identity. This known-answer
    # probe was independently run against the reference zlib-ng library. It uses
    # the exact PNG deflate settings but synthetic data, not board-output fixtures.
    # The complete manufacturing contract still checks all 52 actual PNG hashes.
    set(_probe_dir "${CMAKE_CURRENT_BINARY_DIR}/CMakeFiles/schgen-manufacturing-compression")
    file(MAKE_DIRECTORY "${_probe_dir}")
    file(WRITE "${_probe_dir}/probe.cpp" [=[
#include <zlib.h>
#include <array>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <vector>

int main() {
    if (std::strcmp(zlibVersion(), "1.3.1.zlib-ng") != 0) {
        std::fprintf(stderr, "expected 1.3.1.zlib-ng, loaded %s\n", zlibVersion());
        return 1;
    }
    // Synthetic filter-like bytes: repetitive bands, gradients and noise, across
    // a 32 KiB history boundary. This is not a stored manufacturing image.
    std::vector<unsigned char> input(196613);
    std::uint32_t state = 0x12345678U;
    for (std::size_t i = 0; i < input.size(); ++i) {
        state ^= state << 13;
        state ^= state >> 17;
        state ^= state << 5;
        const auto row = i / 769;
        const auto col = i % 769;
        input[i] = static_cast<unsigned char>(col == 0 ? row % 5 :
            col < 640 ? (col / 17 + row / 7) % 256 : state % 256);
    }
    z_stream stream{};
    if (deflateInit2(&stream, 9, Z_DEFLATED, 15, 9, Z_FILTERED) != Z_OK) return 2;
    stream.next_in = input.data();
    stream.avail_in = static_cast<uInt>(input.size());
    std::array<unsigned char, 65536> buffer{};
    std::vector<unsigned char> compressed;
    int result;
    do {
        stream.next_out = buffer.data();
        stream.avail_out = static_cast<uInt>(buffer.size());
        result = deflate(&stream, Z_FINISH);
        compressed.insert(compressed.end(), buffer.begin(),
            buffer.begin() + (buffer.size() - stream.avail_out));
    } while (result == Z_OK);
    const auto end_result = deflateEnd(&stream);
    if (result != Z_STREAM_END || end_result != Z_OK) return 3;
    std::vector<unsigned char> restored(input.size());
    uLongf restored_size = static_cast<uLongf>(restored.size());
    if (uncompress(restored.data(), &restored_size, compressed.data(),
                   static_cast<uLong>(compressed.size())) != Z_OK ||
        restored_size != input.size() || restored != input) return 4;
    for (const auto byte : compressed) std::printf("%02x", static_cast<unsigned int>(byte));
    return std::ferror(stdout) ? 5 : 0;
}
]=])
    if(MSVC)
        set(_probe_options /W4 /WX /fp:strict)
    else()
        set(_probe_options -Wall -Wextra -Wpedantic -Werror -ffp-contract=off)
    endif()
    # Re-run on every configure, including when an archive changes in place.
    # Do not trust user-supplied cached try_run success or cross-compile answers.
    unset(_schgen_compression_compiled)
    unset(_schgen_compression_compiled CACHE)
    unset(_schgen_compression_ran)
    unset(_schgen_compression_ran CACHE)
    set(CMAKE_TRY_COMPILE_TARGET_TYPE EXECUTABLE)
    try_run(_schgen_compression_ran _schgen_compression_compiled
        "${_probe_dir}/build" "${_probe_dir}/probe.cpp"
        CMAKE_FLAGS "-DINCLUDE_DIRECTORIES:STRING=${_include}"
        COMPILE_DEFINITIONS ${_probe_options}
        LINK_LIBRARIES "${_archive}"
        CXX_STANDARD 17 CXX_STANDARD_REQUIRED ON CXX_EXTENSIONS OFF
        COMPILE_OUTPUT_VARIABLE _compile_output
        RUN_OUTPUT_VARIABLE _run_output)
    set(_compiled "${_schgen_compression_compiled}")
    set(_ran "${_schgen_compression_ran}")
    unset(_schgen_compression_compiled CACHE)
    unset(_schgen_compression_ran CACHE)
    if(NOT _compiled)
        message(FATAL_ERROR "Manufacturing zlib-ng header/archive compile or link check failed:\n${_compile_output}")
    endif()
    if(NOT "${_ran}" STREQUAL "0")
        message(FATAL_ERROR "Manufacturing zlib-ng runtime/round-trip check failed (${_ran}):\n${_run_output}")
    endif()
    string(SHA256 _fingerprint "${_run_output}")
    if(NOT _fingerprint STREQUAL "03c433e6dad439ba633dd5e1cf22897379c8530ffaf4a9e0564655f00aafe576")
        message(FATAL_ERROR
            "Manufacturing zlib-ng deflate bytes differ from the independent reference "
            "(fingerprint ${_fingerprint}). Use the documented 2.3.3 compatibility build; "
            "do not update golden PNG hashes to accommodate another compressor.")
    endif()
    add_library(schgen_manufacturing_compression STATIC IMPORTED GLOBAL)
    set_target_properties(schgen_manufacturing_compression PROPERTIES
        IMPORTED_LOCATION "${_archive}"
        INTERFACE_INCLUDE_DIRECTORIES "${_include}"
        SCHGEN_ZLIB_PREFIX "${_prefix}")
    add_library(schgen::manufacturing_compression ALIAS schgen_manufacturing_compression)
    message(STATUS "Manufacturing compression: zlib-ng 2.3.3 / 1.3.1.zlib-ng; byte probe passed (${_archive})")
endfunction()
