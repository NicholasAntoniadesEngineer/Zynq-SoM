#!/usr/bin/env bash
# Isolated contract build; never invokes CMake or writes shared native outputs.
set -euo pipefail
task_repo="${1:?usage: run_authoring_contracts.sh REPOSITORY [CORE_ARCHIVE]}"
task_archive="${2:-$task_repo/native/build/libschgen_core.a}"
test -d "$task_repo/native/include"
test -f "$task_archive"
task_build_dir="$(mktemp -d /private/tmp/schgen-authoring-XXXXXX)"
cp "$task_archive" "$task_build_dir/core.a"
task_flags=(-std=c++17 -Wall -Wextra -Wpedantic -Werror -ffp-contract=off -O1 -DNDEBUG -I "$task_repo/native/include")
if [[ "$(uname -s)" == Darwin ]]; then
    task_deployment="$(sed -n 's/^CMAKE_OSX_DEPLOYMENT_TARGET:STRING=//p' "$task_repo/native/build/CMakeCache.txt")"
    if [[ -n "$task_deployment" ]]; then task_flags+=("-mmacosx-version-min=$task_deployment"); fi
fi
if [[ "${AUTHORING_SANITIZE:-0}" == 1 ]]; then
    task_flags+=(-fsanitize=address,undefined -fno-omit-frame-pointer -g)
    if command -v pkg-config >/dev/null && pkg-config --exists libxml-2.0; then
        read -r -a task_xml_flags <<< "$(pkg-config --cflags libxml-2.0)"
        task_flags+=("${task_xml_flags[@]}")
    elif [[ "$(uname -s)" == Darwin ]]; then
        task_flags+=(-I "$(xcrun --show-sdk-path)/usr/include/libxml2")
    else
        task_flags+=(-I /usr/include/libxml2)
    fi
fi
task_sources=("$task_repo/native/src/circuit_helpers.cpp" "$task_repo/native/src/authoring.cpp"
    "$task_repo/native/src/authoring_ir.cpp" "$task_repo/native/src/authoring_gates.cpp"
    "$task_repo"/native/src/subsystem_authoring*.cpp "$task_repo"/native/src/project_authoring*.cpp)
if [[ "${AUTHORING_SANITIZE:-0}" == 1 ]]; then
    # libc++ vector annotations must agree across every TU sharing JsonNode/IR.
    # Recompile the 11 archive members reached by these contracts, read-only,
    # into this private directory. Link these before the copied archive; do not
    # disable ASan container checks or replace the user's shared archive.
    for task_dependency in json symbols circuit catalog atomic_file som_interface link sexpr occupancy turn quantize; do
        task_sources+=("$task_repo/native/src/$task_dependency.cpp")
    done
fi
task_objects=()
task_jobs=()
for task_source in "${task_sources[@]}"; do
    task_basename="${task_source##*/}"
    task_object="$task_build_dir/${task_basename%.cpp}.o"
    task_objects+=("$task_object")
    "${CXX:-c++}" "${task_flags[@]}" -c "$task_source" -o "$task_object" &
    task_jobs+=("$!")
    if [[ "${#task_jobs[@]}" -ge 4 ]]; then
        for task_pid in "${task_jobs[@]}"; do wait "$task_pid"; done
        task_jobs=()
    fi
done
for task_pid in "${task_jobs[@]}"; do wait "$task_pid"; done
for task_test in subsystem_authoring_contracts authoring_gates_contracts; do
    "${CXX:-c++}" "${task_flags[@]}" "$task_repo/native/tests/$task_test.cpp" \
        "${task_objects[@]}" "$task_build_dir/core.a" -lxml2 -lpthread -o "$task_build_dir/$task_test"
    "$task_build_dir/$task_test" "$task_repo"
done
printf 'Isolated build: %s\n' "$task_build_dir"
