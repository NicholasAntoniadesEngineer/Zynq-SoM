"""Render KiCad schematics to PNG via ``kicad-cli`` + PyMuPDF.

The render is the supreme judge (see the repo Laws): this module turns a
``.kicad_sch`` into the exact raster KiCad itself would plot, so placement,
routing and label quality can be judged automatically against the pixels —
not merely against the in-memory geometric validators, which historically
diverged from the eye in the lenient direction.

Pipeline: ``kicad-cli sch export pdf`` produces a single-page PDF whose page
box is the schematic's paper size at exact scale; PyMuPDF rasterizes page 1
at a chosen DPI. The PDF page origin is the page's top-left corner with +Y
downward — identical to KiCad page coordinates — so the mm→pixel mapping is a
single uniform scale with no offset. :class:`PageRaster` carries that mapping
so an overlay (see :mod:`zynq_eda.core.render.overlay`) can draw a validator's
flagged bbox exactly where it sits on the rendered page.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

import fitz  # PyMuPDF

DEFAULT_DPI: int = 300
"""Render resolution. 300 DPI on A3 → ~4960×3508 px: fine enough that two
primitives 0.2 mm apart are ~1.6 px apart (visibly distinct), without
producing unwieldy files."""


@dataclass(frozen=True)
class PageRaster:
    """A rendered schematic page plus its mm→pixel transform.

    The scale is derived from the *actual* pixmap dimensions and the page's
    physical size (rather than assuming ``dpi/25.4``), so a drawn overlay
    lands exactly on the raster regardless of any rounding inside the
    rasterizer.
    """

    png_path: Path
    width_px: int
    height_px: int
    page_w_mm: float
    page_h_mm: float
    dpi: float

    def mm_to_px(self, x_mm: float, y_mm: float) -> tuple[float, float]:
        """Map a KiCad page coordinate (mm, +Y down) to a pixel coordinate."""
        sx = self.width_px / self.page_w_mm
        sy = self.height_px / self.page_h_mm
        return (x_mm * sx, y_mm * sy)


def _require_kicad_cli() -> str:
    kicad_cli = shutil.which("kicad-cli")
    if kicad_cli is None:
        raise RuntimeError(
            "kicad-cli not found on PATH; install KiCad 9+ to render schematics"
        )
    return kicad_cli


def render_sheet_to_png(
    schematic_path: Path,
    png_path: Path,
    *,
    dpi: int = DEFAULT_DPI,
) -> PageRaster:
    """Render ``schematic_path`` to ``png_path``; return its :class:`PageRaster`.

    Exports the page to a temporary PDF (the raster KiCad itself would plot)
    then rasterizes page 1 at ``dpi``. Raises if kicad-cli fails to produce a
    PDF — a missing render is never silently swallowed.
    """
    schematic_path = Path(schematic_path)
    if not schematic_path.exists():
        raise FileNotFoundError(f"schematic not found: {schematic_path}")
    png_path = Path(png_path)
    png_path.parent.mkdir(parents=True, exist_ok=True)

    kicad_cli = _require_kicad_cli()
    with tempfile.TemporaryDirectory(prefix="zynq_eda_render_") as temp_dir:
        pdf_path = Path(temp_dir) / (schematic_path.stem + ".pdf")
        command = [
            kicad_cli,
            "sch",
            "export",
            "pdf",
            "--output",
            str(pdf_path),
            str(schematic_path),
        ]
        try:
            completed = subprocess.run(
                command, capture_output=True, text=True, check=False
            )
        except OSError as exec_error:
            raise RuntimeError(
                f"Failed to execute kicad-cli sch export pdf: {exec_error}"
            ) from exec_error
        if not pdf_path.exists():
            raise RuntimeError(
                "kicad-cli sch export pdf produced no PDF: "
                f"exit={completed.returncode}, stderr={completed.stderr.strip()}"
            )

        doc = fitz.open(str(pdf_path))
        try:
            page = doc.load_page(0)
            rect = page.rect
            page_w_mm = rect.width / 72.0 * 25.4
            page_h_mm = rect.height / 72.0 * 25.4
            pix = page.get_pixmap(dpi=dpi)
            pix.save(str(png_path))
            width_px, height_px = pix.width, pix.height
        finally:
            doc.close()

    return PageRaster(
        png_path=png_path,
        width_px=width_px,
        height_px=height_px,
        page_w_mm=page_w_mm,
        page_h_mm=page_h_mm,
        dpi=float(dpi),
    )
