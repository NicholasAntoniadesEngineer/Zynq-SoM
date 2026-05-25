"""Top-level entry point for the carrier_template schematic generator.

Thin shim around the hierarchical pipeline::

    python scripts/create_carrier_template_schematic.py
    python -m scripts.carrier
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.carrier.pipeline import main


if __name__ == "__main__":
    raise SystemExit(main())
