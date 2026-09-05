#!/usr/bin/env bash
# Build schgen._geom (C++ occupancy kernel) into schgen/.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
if [ -z "${PYTHON:-}" ]; then
    if [ -x "${REPO_ROOT}/.venv/bin/python" ]; then
        PYTHON="${REPO_ROOT}/.venv/bin/python"
    elif [ -x "${REPO_ROOT}/../Zynq-SoM/.venv/bin/python" ]; then
        PYTHON="${REPO_ROOT}/../Zynq-SoM/.venv/bin/python"
    else
        PYTHON="python3"
    fi
fi
if ! "${PYTHON}" -c "import nanobind" >/dev/null 2>&1; then
    "${PYTHON}" -m pip install 'nanobind>=2.0'
fi
cmake -S "${REPO_ROOT}/native" -B "${REPO_ROOT}/native/build" \
    -DPython_EXECUTABLE="$(${PYTHON} -c 'import sys; print(sys.executable)')" \
    -DCMAKE_BUILD_TYPE=Release
cmake --build "${REPO_ROOT}/native/build" --parallel
"${PYTHON}" -c "from schgen import _geom; print('schgen._geom', _geom.__file__)"
