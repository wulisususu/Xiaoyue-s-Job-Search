from __future__ import annotations

import hashlib
import io
import os
import tempfile
import uuid
import zipfile
from pathlib import Path

import docx
import pypdf
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import AppSettings
from ..models import ResumeVersion
from .parsers import extract_resume_text

MAX_RESUME_BYTES = 50 * 1024 * 1024


class ResumeVaultError(ValueError):
    pass


class ResumeTooLargeError(ResumeVaultError):
    pass


class UnsupportedResumeTypeError(ResumeVaultError):
    pass


class InvalidResumeError(ResumeVaultError):
    pass


_MIME_BY_EXT = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}


def _safe_display_name(filename: str) -> str:
    normalized = (filename or "resume").replace("\\", "/")
    name = normalized.rsplit("/", 1)[-1].strip()
    return name or "resume"


def _validate_pdf(data: bytes) -> None:
    if not data.startswith(b"%PDF-"):
        raise InvalidResumeError("Invalid PDF signature")
    try:
        reader = pypdf.PdfReader(io.BytesIO(data))
        _ = len(reader.pages)
    except Exception as exc:
        raise InvalidResumeError("PDF cannot be opened") from exc


def _validate_docx(data: bytes) -> None:
    if not data.startswith(b"PK"):
        raise InvalidResumeError("Invalid DOCX container")
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            names = set(archive.namelist())
            if "[Content_Types].xml" not in names or "word/document.xml" not in names:
                raise InvalidResumeError("DOCX is missing required Word document members")
            if archive.testzip() is not None:
                raise InvalidResumeError("DOCX ZIP container is corrupt")
        docx.Document(io.BytesIO(data))
    except InvalidResumeError:
        raise
    except Exception as exc:
        raise InvalidResumeError("DOCX cannot be opened") from exc


def _validate_supported_content(ext: str, data: bytes) -> None:
    if ext == ".pdf":
        _validate_pdf(data)
        return
    if ext == ".docx":
        _validate_docx(data)
        return
    raise UnsupportedResumeTypeError(f"Unsupported resume format: {ext or 'unknown'}")


def validate_and_store_resume(
    session: Session,
    settings: AppSettings,
    filename: str,
    content_type: str | None,
    data: bytes,
) -> tuple[ResumeVersion, bool]:
    display_name = _safe_display_name(filename)
    ext = Path(display_name).suffix.lower()
    if ext not in _MIME_BY_EXT:
        raise UnsupportedResumeTypeError("Only PDF and DOCX resumes are supported")
    if len(data) > MAX_RESUME_BYTES:
        raise ResumeTooLargeError("Resume exceeds the 50 MiB limit")

    _validate_supported_content(ext, data)
    sha256 = hashlib.sha256(data).hexdigest()
    existing = session.scalar(select(ResumeVersion).where(ResumeVersion.sha256 == sha256))
    if existing is not None:
        return existing, True

    next_version = (session.scalar(select(func.max(ResumeVersion.version_number))) or 0) + 1
    relpath = Path("resumes") / sha256 / f"original{ext}"
    final_path = settings.vault_dir / relpath
    final_path.parent.mkdir(parents=True, exist_ok=True)

    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(dir=final_path.parent, prefix=".upload-", suffix=".tmp", delete=False) as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
            temp_path = Path(handle.name)
        if final_path.exists():
            temp_path.unlink(missing_ok=True)
        else:
            os.replace(temp_path, final_path)
        temp_path = None

        resume = ResumeVersion(
            id=uuid.uuid4().hex,
            sha256=sha256,
            original_filename=display_name,
            file_ext=ext,
            mime_type=_MIME_BY_EXT[ext],
            size_bytes=len(data),
            vault_relpath=relpath.as_posix(),
            version_number=next_version,
            extraction_status="PENDING",
        )
        session.add(resume)
        session.flush()

        try:
            parsed = extract_resume_text(final_path, ext)
            resume.extraction_status = parsed.status
            resume.extracted_text = parsed.text or None
            resume.parser_name = parsed.parser_name
            resume.parser_version = parsed.parser_version
            resume.extraction_error = parsed.error
        except Exception as exc:
            resume.extraction_status = "FAILED"
            resume.extraction_error = str(exc)

        session.commit()
        session.refresh(resume)
        return resume, False
    except Exception:
        session.rollback()
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)
        raise


def read_upload_limited(file_obj, max_bytes: int = MAX_RESUME_BYTES) -> bytes:
    """Read an upload in chunks, refusing to buffer more than max_bytes.

    Unlike reading the whole upload into memory first, the size limit stops
    the transfer instead of merely rejecting after full ingestion.
    """
    chunks: list[bytes] = []
    received = 0
    while True:
        chunk = file_obj.read(1024 * 1024)
        if not chunk:
            break
        received += len(chunk)
        if received > max_bytes:
            raise ResumeTooLargeError("Resume exceeds the 50 MiB limit")
        chunks.append(chunk)
    return b"".join(chunks)


def reconcile_vault(session: Session, settings: AppSettings) -> int:
    """Delete content-addressed vault files that no DB row references.

    A crash between writing the vault file and committing the ResumeVersion
    row can leave orphan files behind; this sweep removes them. Returns the
    number of removed content directories.
    """
    known_shas = set(session.scalars(select(ResumeVersion.sha256)).all())
    resumes_root = settings.vault_dir / "resumes"
    if not resumes_root.is_dir():
        return 0
    removed = 0
    for entry in resumes_root.iterdir():
        if not entry.is_dir() or entry.name in known_shas:
            continue
        for child in sorted(entry.rglob("*"), reverse=True):
            if child.is_file():
                child.unlink(missing_ok=True)
        entry.rmdir()
        removed += 1
    return removed
