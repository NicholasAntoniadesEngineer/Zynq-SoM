# Explicit offline provisioning, never FetchContent, pip or a vendored binary.
# cmake -DSCHGEN_ZLIB_ARCHIVE=/verified/zlib-ng-2.3.3.tar.gz
#       -DSCHGEN_DEPENDENCY_WORK=/new/build/path
#       -DSCHGEN_DEPENDENCY_PREFIX=/new/install/path -P BootstrapZlib.cmake
cmake_minimum_required(VERSION 3.20)
foreach(_name SCHGEN_ZLIB_ARCHIVE SCHGEN_DEPENDENCY_WORK SCHGEN_DEPENDENCY_PREFIX)
    if(NOT DEFINED ${_name} OR NOT IS_ABSOLUTE "${${_name}}" OR "${${_name}}" MATCHES ";")
        message(FATAL_ERROR "${_name} must be an explicit absolute path without semicolons")
    endif()
endforeach()
if(NOT EXISTS "${SCHGEN_ZLIB_ARCHIVE}" OR IS_DIRECTORY "${SCHGEN_ZLIB_ARCHIVE}")
    message(FATAL_ERROR "Pinned zlib-ng source archive not found: ${SCHGEN_ZLIB_ARCHIVE}")
endif()
file(SHA256 "${SCHGEN_ZLIB_ARCHIVE}" _sha)
if(NOT _sha STREQUAL "f9c65aa9c852eb8255b636fd9f07ce1c406f061ec19a2e7d508b318ca0c907d1")
    message(FATAL_ERROR "zlib-ng 2.3.3 source archive checksum mismatch: ${_sha}; nothing extracted")
endif()
foreach(_name SCHGEN_DEPENDENCY_WORK SCHGEN_DEPENDENCY_PREFIX)
    if(EXISTS "${${_name}}" OR IS_SYMLINK "${${_name}}")
        message(FATAL_ERROR "${_name} already exists; bootstrap will not overwrite it: ${${_name}}")
    endif()
endforeach()
set(SCHGEN_DEPENDENCY_JOBS 4 CACHE STRING "Bounded dependency compile parallelism")
if(NOT SCHGEN_DEPENDENCY_JOBS MATCHES "^[1-9][0-9]*$")
    message(FATAL_ERROR "SCHGEN_DEPENDENCY_JOBS must be a positive integer")
endif()
file(MAKE_DIRECTORY "${SCHGEN_DEPENDENCY_WORK}")
file(ARCHIVE_EXTRACT INPUT "${SCHGEN_ZLIB_ARCHIVE}" DESTINATION "${SCHGEN_DEPENDENCY_WORK}/source")
set(_source "${SCHGEN_DEPENDENCY_WORK}/source/zlib-ng-2.3.3")
set(_build "${SCHGEN_DEPENDENCY_WORK}/build")
function(_checked)
    execute_process(COMMAND ${ARGV} RESULT_VARIABLE _result)
    if(NOT "${_result}" STREQUAL "0")
        message(FATAL_ERROR "Native dependency command failed (${_result}); partial output retained for diagnosis")
    endif()
endfunction()
_checked("${CMAKE_COMMAND}" -S "${_source}" -B "${_build}"
    -DCMAKE_BUILD_TYPE=Release -DZLIB_COMPAT=ON -DBUILD_SHARED_LIBS=OFF
    -DBUILD_TESTING=OFF -DWITH_GTEST=OFF -DCMAKE_POSITION_INDEPENDENT_CODE=ON
    -DWITH_NEW_STRATEGIES=ON -DWITH_RUNTIME_CPU_DETECTION=ON
    -DWITH_NATIVE_INSTRUCTIONS=OFF -DCMAKE_INSTALL_LIBDIR=lib
    "-DCMAKE_INSTALL_PREFIX=${SCHGEN_DEPENDENCY_PREFIX}")
_checked("${CMAKE_COMMAND}" --build "${_build}" --parallel "${SCHGEN_DEPENDENCY_JOBS}")
_checked("${CMAKE_COMMAND}" --install "${_build}")
message(STATUS "Installed pinned upstream source at ${SCHGEN_DEPENDENCY_PREFIX}. The consuming native configure must still pass its byte-compatibility probe.")
