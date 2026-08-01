from __future__ import annotations

import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

import fitz

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
    schematic_path = Path(schematic_path)
    if not schematic_path.exists():
        raise FileNotFoundError(f"schematic not found: {schematic_path}")
    png_path = Path(png_path)
    png_path.parent.mkdir(parents=True, exist_ok=True)

    kicad_cli = _require_kicad_cli()
    with tempfile.TemporaryDirectory(prefix="schgen_render_") as temp_dir:
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
