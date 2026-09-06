cmake_minimum_required(VERSION 3.18)
project(schgen_native LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)
set(CMAKE_POSITION_INDEPENDENT_CODE ON)

if(NOT Python_EXECUTABLE)
    set(Python_EXECUTABLE "" CACHE FILEPATH "Python used to load schgen._geom")
endif()

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

nanobind_add_module(_geom src/module.cpp src/occupancy.cpp src/seat.cpp
                    src/sexpr.cpp src/route.cpp src/emit.cpp src/legalize.cpp
                    src/quantize.cpp src/turn.cpp src/pack.cpp
                    src/pack_anchor.cpp src/place_search.cpp src/cc.cpp
                    src/embed_fp.cpp src/pack_edges.cpp src/pcb_scan.cpp
                    src/pack_refine.cpp src/place_geom.cpp src/catalog.cpp
                    src/json.cpp src/circuit.cpp)
target_include_directories(_geom PRIVATE "${CMAKE_CURRENT_SOURCE_DIR}/include")
target_compile_options(_geom PRIVATE -Wall -Wextra -Wpedantic -Werror)
set_source_files_properties(src/turn.cpp src/pack_anchor.cpp
                            src/pack_edges.cpp PROPERTIES
    COMPILE_OPTIONS "-ffp-contract=off")

set(_geom_out "${CMAKE_CURRENT_SOURCE_DIR}/../schgen")
set_target_properties(_geom PROPERTIES
    LIBRARY_OUTPUT_DIRECTORY "${_geom_out}"
    RUNTIME_OUTPUT_DIRECTORY "${_geom_out}")

add_executable(schgen src/main.cpp src/occupancy.cpp src/seat.cpp
               src/sexpr.cpp src/route.cpp src/emit.cpp src/legalize.cpp
               src/quantize.cpp src/turn.cpp src/pack.cpp
               src/pack_anchor.cpp src/place_search.cpp src/cc.cpp
               src/embed_fp.cpp src/pack_edges.cpp src/pcb_scan.cpp
               src/pack_refine.cpp src/place_geom.cpp src/catalog.cpp
               src/json.cpp src/circuit.cpp)
add_custom_command(TARGET schgen POST_BUILD
    COMMAND "$<TARGET_FILE:schgen>" catalog-compile
            "${CMAKE_CURRENT_SOURCE_DIR}/../parts"
            "${CMAKE_CURRENT_SOURCE_DIR}/catalog.bin"
    COMMAND "$<TARGET_FILE:schgen>" circuit-compile
            "${CMAKE_CURRENT_SOURCE_DIR}/../carrier/subsystems"
            "${CMAKE_CURRENT_SOURCE_DIR}/circuits.bin"
    COMMENT "Compile parts and circuit JSON into native catalogs")
target_include_directories(schgen PRIVATE "${CMAKE_CURRENT_SOURCE_DIR}/include")
target_compile_options(schgen PRIVATE -Wall -Wextra -Wpedantic -Werror)
set_target_properties(schgen PROPERTIES
    RUNTIME_OUTPUT_DIRECTORY "${CMAKE_CURRENT_SOURCE_DIR}/../native/bin")
