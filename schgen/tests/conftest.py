"""Pytest bootstrap: guarantee the repo root (which contains the ``schgen``
package) is importable no matter the invocation cwd.

The fast unit suite under ``schgen/tests/`` imports the engine as
``import schgen.model`` etc. pytest already inserts the rootdir on sys.path
for this package layout, but pinning it here makes the suite robust when run
from a sub-directory or by an IDE that sets a different rootdir. No engine
code is touched; this only adjusts the import path.
"""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = str(Path(__file__).resolve().parents[2])   # schgen/tests/ -> repo root
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
