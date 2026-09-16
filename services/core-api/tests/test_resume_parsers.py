from __future__ import annotations

import io
import zipfile

from app.resumes.parsers import extract_resume_text


def build_pdf(text: str) -> bytes:
    escaped = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    stream = f"BT /F1 12 Tf 72 720 Td ({escaped}) Tj ET".encode("latin-1") if text else b""
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream",
    ]
    data = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for index, obj in enumerate(objects, start=1):
        offsets.append(len(data))
        data.extend(f"{index} 0 obj\n".encode())
        data.extend(obj)
        data.extend(b"\nendobj\n")
    xref_offset = len(data)
    data.extend(f"xref\n0 {len(objects) + 1}\n".encode())
    data.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        data.extend(f"{offset:010d} 00000 n \n".encode())
    data.extend(f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF\n".encode())
    return bytes(data)


def build_docx() -> bytes:
    content_types = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
</Types>"""
    rels = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>"""
    document = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>
  <w:p><w:r><w:t>Resume paragraph name@example.com</w:t></w:r></w:p>
  <w:tbl><w:tr><w:tc><w:p><w:r><w:t>Table cell 13800138000</w:t></w:r></w:p></w:tc></w:tr></w:tbl>
  <w:sectPr/>
</w:body></w:document>"""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", content_types)
        archive.writestr("_rels/.rels", rels)
        archive.writestr("word/document.xml", document)
    return buffer.getvalue()


def test_pdf_text_layer_is_extracted(tmp_path):
    path = tmp_path / "resume.pdf"
    path.write_bytes(build_pdf("hello@example.com 13800138000 resume text"))

    result = extract_resume_text(path, ".pdf")

    assert result.status == "EXTRACTED"
    assert "hello@example.com" in result.text
    assert "13800138000" in result.text
    assert result.parser_name == "pypdf"


def test_blank_pdf_is_marked_ocr_required(tmp_path):
    path = tmp_path / "scan.pdf"
    path.write_bytes(build_pdf(""))

    result = extract_resume_text(path, ".pdf")

    assert result.status == "OCR_REQUIRED"
    assert result.text == ""
    assert result.error is None


def test_docx_paragraphs_and_table_cells_are_extracted(tmp_path):
    path = tmp_path / "resume.docx"
    path.write_bytes(build_docx())

    result = extract_resume_text(path, ".docx")

    assert result.status == "EXTRACTED"
    assert "Resume paragraph name@example.com" in result.text
    assert "Table cell 13800138000" in result.text
    assert result.parser_name == "python-docx"
