"""PDF and image preprocessing — convert input files to base64 PNG pages."""

import base64
from io import BytesIO
from pathlib import Path

import pymupdf
from PIL import Image

from notes2latex.config import Settings


def load_pages(file_paths: list[Path], settings: Settings) -> list[str]:
    """Convert input files (PDFs or images) into a list of base64-encoded PNG strings."""
    pages: list[str] = []
    for file_path in file_paths:
        suffix = file_path.suffix.lower()
        if suffix == ".pdf":
            pages.extend(_pdf_to_base64_pages(file_path, settings))
        elif suffix in {".png", ".jpg", ".jpeg", ".tiff", ".bmp", ".webp"}:
            pages.append(_image_to_base64(file_path))
        else:
            raise ValueError(f"Unsupported file type: {suffix}")
    return pages


def _pdf_to_base64_pages(pdf_path: Path, settings: Settings) -> list[str]:
    pages: list[str] = []
    doc = pymupdf.open(str(pdf_path))
    zoom = settings.dpi / 72.0
    matrix = pymupdf.Matrix(zoom, zoom)
    for page in doc:
        pix = page.get_pixmap(matrix=matrix)
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        pages.append(_pil_to_base64(img))
    doc.close()
    return pages


def _image_to_base64(image_path: Path) -> str:
    img = Image.open(image_path).convert("RGB")
    return _pil_to_base64(img)


def _pil_to_base64(img: Image.Image) -> str:
    buffer = BytesIO()
    img.save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode("utf-8")
