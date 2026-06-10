"""Render-truthful feedback loop: rasterize schematics + overlay findings.

See the repo Laws — "the render is the supreme judge." This package makes
that real and automatic: :mod:`raster` turns a ``.kicad_sch`` into the exact
PNG KiCad plots; :mod:`overlay` draws a validator's flagged bboxes onto that
PNG; :mod:`reconcile` ties the two together per sheet so every finding can be
confirmed against the rendered pixels (and any visible crowd confirmed to
carry a finding).
"""

from __future__ import annotations

from zynq_eda.core.render.raster import (
    DEFAULT_DPI,
    PageRaster,
    render_sheet_to_png,
)

__all__ = ["DEFAULT_DPI", "PageRaster", "render_sheet_to_png"]
