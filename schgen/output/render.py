"""Transitional data transport for the native schematic renderer."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from schgen.core import native

DEFAULT_DPI: int = 300


@dataclass(frozen=True)
class PageRaster:
    png_path: Path
    width_px: int
    height_px: int
    page_w_mm: float
    page_h_mm: float
    dpi: float

    def mm_to_px(self, x_mm: float, y_mm: float) -> tuple[float, float]:
        return native.module().render_mm_to_px(
            self.width_px, self.height_px, self.page_w_mm, self.page_h_mm,
            x_mm, y_mm)


def render_sheet_to_png(
    schematic_path: Path,
    png_path: Path,
    *,
    dpi: int = DEFAULT_DPI,
) -> PageRaster:
    raw = native.module().render_sheet_to_png(
        str(schematic_path), str(png_path), dpi)
    return PageRaster(**{**raw, "png_path": Path(raw["png_path"])})
