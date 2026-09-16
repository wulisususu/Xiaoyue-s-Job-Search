from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import docx
import pypdf
from docx.document import Document as DocumentObject
from docx.oxml.table import CT_Tbl
from docx.oxml.text.paragraph import CT_P
from docx.table import Table
from docx.text.paragraph import Paragraph


@dataclass(frozen=True, slots=True)
class ResumeParseResult:
    status: str
    text: str
    parser_name: str
    parser_version: str
    error: str | None = None


def _normalize_text(text: str) -> str:
    lines: list[str] = []
    for raw_line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        line = re.sub(r"[ \t\f\v]+", " ", raw_line).strip()
        if line:
            lines.append(line)
    return "\n".join(lines)


def _iter_docx_blocks(document: DocumentObject):
    body = document.element.body
    for child in body.iterchildren():
        if isinstance(child, CT_P):
            yield Paragraph(child, document)
        elif isinstance(child, CT_Tbl):
            yield Table(child, document)


def _extract_pdf(path: Path) -> ResumeParseResult:
    reader = pypdf.PdfReader(str(path))
    raw = "\n".join((page.extract_text() or "") for page in reader.pages)
    normalized = _normalize_text(raw)
    meaningful_chars = len(re.sub(r"\s+", "", normalized))
    if meaningful_chars < 20:
        return ResumeParseResult(
            status="OCR_REQUIRED",
            text="",
            parser_name="pypdf",
            parser_version=getattr(pypdf, "__version__", "unknown"),
        )
    return ResumeParseResult(
        status="EXTRACTED",
        text=normalized,
        parser_name="pypdf",
        parser_version=getattr(pypdf, "__version__", "unknown"),
    )


def _extract_docx(path: Path) -> ResumeParseResult:
    document = docx.Document(str(path))
    lines: list[str] = []
    for block in _iter_docx_blocks(document):
        if isinstance(block, Paragraph):
            if block.text.strip():
                lines.append(block.text)
            continue
        for row in block.rows:
            for cell in row.cells:
                for paragraph in cell.paragraphs:
                    if paragraph.text.strip():
                        lines.append(paragraph.text)
    return ResumeParseResult(
        status="EXTRACTED",
        text=_normalize_text("\n".join(lines)),
        parser_name="python-docx",
        parser_version=getattr(docx, "__version__", "unknown"),
    )


def extract_resume_text(path: Path, ext: str) -> ResumeParseResult:
    normalized_ext = ext.lower()
    if normalized_ext == ".pdf":
        return _extract_pdf(path)
    if normalized_ext == ".docx":
        return _extract_docx(path)
    raise ValueError(f"Unsupported resume extension: {ext}")
