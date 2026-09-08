from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from schgen.core.link import all_subsystem_paths, exec_subsystem_py
from schgen.core.model import Circuit


def circuit_json_path(py_path: Path) -> Path:
    if py_path.parent.name == py_path.stem:
        return py_path.parent / "circuit.json"
    return py_path.parent / py_path.stem / "circuit.json"


def dump_sheet(py_path: Path) -> Path:
    loaded = exec_subsystem_py(str(py_path))
    ir = loaded.circuit.to_ir()
    roundtrip = Circuit.from_ir(ir)
    if roundtrip.to_ir() != ir:
        raise SystemExit(f"circuit IR roundtrip drifted: {py_path}")
    out_path = circuit_json_path(py_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(ir, indent=2, ensure_ascii=False) + "\n")
    return out_path


def main() -> int:
    paths = all_subsystem_paths()
    if not paths:
        raise SystemExit("no subsystems found")
    written = []
    for py_path in paths:
        written.append(dump_sheet(py_path))
    for out_path in written:
        print(out_path.relative_to(REPO_ROOT))
    print(f"dumped {len(written)} circuit.json files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
