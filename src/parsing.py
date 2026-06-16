"""Extract plain text from résumé files (PDF and DOCX)."""

from __future__ import annotations

from pathlib import Path
from typing import List

from . import config


def extract_text(path: Path) -> str:
    """Return the plain text of a résumé file.

    Supports .pdf (via pdfplumber) and .docx (via python-docx).
    Raises ValueError for unsupported extensions.
    """
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return _extract_pdf(path)
    if suffix == ".docx":
        return _extract_docx(path)
    raise ValueError(
        f"Unsupported file type '{suffix}' for {path.name}. "
        f"Supported: {', '.join(sorted(config.SUPPORTED_EXTENSIONS))}"
    )


def _extract_pdf(path: Path) -> str:
    import pdfplumber

    parts: List[str] = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            if text.strip():
                parts.append(text)
    return "\n\n".join(parts).strip()


def _extract_docx(path: Path) -> str:
    from docx import Document

    document = Document(str(path))
    parts = [p.text for p in document.paragraphs if p.text.strip()]

    # Include table cell text — résumés often use tables for layout.
    for table in document.tables:
        for row in table.rows:
            cells = [cell.text.strip() for cell in row.cells if cell.text.strip()]
            if cells:
                parts.append(" | ".join(cells))

    return "\n".join(parts).strip()


def list_resumes(role: str) -> List[Path]:
    """All parseable résumé files for a role, sorted by name."""
    folder = config.role_resume_dir(role)
    if not folder.exists():
        return []
    return sorted(
        p
        for p in folder.iterdir()
        if p.is_file() and p.suffix.lower() in config.SUPPORTED_EXTENSIONS
    )
