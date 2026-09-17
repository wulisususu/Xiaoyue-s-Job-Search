from __future__ import annotations

import hashlib
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
# Zip-bomb guards for DOCX containers.
MAX_ZIP_MEMBERS = 500
MAX_ZIP_UNCOMPRESSED = 100 * 1024 * 1024
MAX_ZIP_RATIO = 300


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


def _validate_pdf_file(path: Path) -> None:
    with path.open("rb") as handle:
        if handle.read(5) != b"%PDF-":
            raise InvalidResumeError("Invalid PDF signature")
    try:
        reader = pypdf.PdfReader(str(path))
        _ = len(reader.pages)
    except Exception as exc:
        raise InvalidResumeError("PDF cannot be opened") from exc


def _validate_docx_file(path: Path) -> None:
    with path.open("rb") as handle:
        if handle.read(2) != b"PK":
            raise InvalidResumeError("Invalid DOCX container")
    try:
        with zipfile.ZipFile(path) as archive:
            members = archive.infolist()
            if len(members) > MAX_ZIP_MEMBERS:
                raise InvalidResumeError("DOCX has too many ZIP members")
            names = {info.filename for info in members}
            if "[Content_Types].xml" not in names or "word/document.xml" not in names:
                raise InvalidResumeError("DOCX is missing required Word document members")
            if archive.testzip() is not None:
                raise InvalidResumeError("DOCX ZIP container is corrupt")
            total_uncompressed = 0
            total_compressed = 0
            for info in members:
                total_uncompressed += info.file_size
                total_compressed += max(info.compress_size, 1)
            if total_uncompressed > MAX_ZIP_UNCOMPRESSED:
                raise InvalidResumeError("DOCX decompresses to an implausible size")
            if total_compressed and total_uncompressed / total_compressed > MAX_ZIP_RATIO:
                raise InvalidResumeError("DOCX compression ratio is implausible (zip bomb?)")
        docx.Document(str(path))
    except InvalidResumeError:
        raise
    except Exception as exc:
        raise InvalidResumeError("DOCX cannot be opened") from exc


def validate_supported_content_file(ext: str, path: Path) -> None:
    if ext == ".pdf":
        _validate_pdf_file(path)
        return
    if ext == ".docx":
        _validate_docx_file(path)
        return
    raise UnsupportedResumeTypeError(f"Unsupported resume format: {ext or 'unknown'}")


def open_upload_spool(settings: AppSettings, filename: str) -> tuple[str, Path, "hashlib._Hash"]:
    """Create a temp spool file for a streaming upload.

    Returns (display_name, temp_path, hash). The caller streams chunks into
    temp_path while updating the hash, then calls finalize_streamed_upload.
    """
    display_name = _safe_display_name(filename)
    ext = Path(display_name).suffix.lower()
    if ext not in _MIME_BY_EXT:
        raise UnsupportedResumeTypeError("Only PDF and DOCX resumes are supported")
    spool_dir = settings.vault_dir / "incoming"
    spool_dir.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(dir=spool_dir, prefix=".upload-", suffix=".tmp", delete=False)
    handle.close()
    return display_name, Path(handle.name), hashlib.sha256()


def append_upload_chunk(temp_path: Path, hash_obj: "hashlib._Hash", chunk: bytes, received: int) -> int:
    """Append one chunk, enforcing the size cap before buffering more."""
    received += len(chunk)
    if received > MAX_RESUME_BYTES:
        temp_path.unlink(missing_ok=True)
        raise ResumeTooLargeError("Resume exceeds the 50 MiB limit")
    with temp_path.open("ab") as handle:
        handle.write(chunk)
    hash_obj.update(chunk)
    return received


def discard_upload_spool(temp_path: Path) -> None:
    temp_path.unlink(missing_ok=True)


def validate_and_store_resume(
    session: Session,
    settings: AppSettings,
    filename: str,
    content_type: str | None,
    data: bytes,
) -> tuple[ResumeVersion, bool]:
    """In-memory convenience wrapper around the streaming ingest primitives.
    The API route uses the streaming path directly; this keeps bytes-based
    callers (tests, scripts) on the same pipeline."""
    display_name, temp_path, hash_obj = open_upload_spool(settings, filename)
    append_upload_chunk(temp_path, hash_obj, data, 0)
    return finalize_streamed_upload(
        session, settings, display_name, temp_path, len(data), hash_obj.hexdigest()
    )


def finalize_streamed_upload(
    session: Session,
    settings: AppSettings,
    display_name: str,
    temp_path: Path,
    size_bytes: int,
    sha256: str,
) -> tuple[ResumeVersion, bool]:
    """Validate the streamed temp file and move it into the content-addressed
    vault, then commit the ResumeVersion row."""
    ext = Path(display_name).suffix.lower()
    validate_supported_content_file(ext, temp_path)
    existing = session.scalar(select(ResumeVersion).where(ResumeVersion.sha256 == sha256))
    if existing is not None:
        temp_path.unlink(missing_ok=True)
        return existing, True

    next_version = (session.scalar(select(func.max(ResumeVersion.version_number))) or 0) + 1
    relpath = Path("resumes") / sha256 / f"original{ext}"
    final_path = settings.vault_dir / relpath
    final_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        if final_path.exists():
            temp_path.unlink(missing_ok=True)
        else:
            os.replace(temp_path, final_path)

        resume = ResumeVersion(
            id=uuid.uuid4().hex,
            sha256=sha256,
            original_filename=display_name,
            file_ext=ext,
            mime_type=_MIME_BY_EXT[ext],
            size_bytes=size_bytes,
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
        temp_path.unlink(missing_ok=True)
        raise


def reconcile_vault(session: Session, settings: AppSettings) -> int:
    """Delete content-addressed vault files that no DB row references.

    A crash between writing the vault file and committing the ResumeVersion
    row can leave orphan files behind; this sweep removes them. Returns the
    number of removed content directories.
    """
    known_shas = set(session.scalars(select(ResumeVersion.sha256)).all())
    removed = 0
    resumes_root = settings.vault_dir / "resumes"
    if not resumes_root.is_dir():
        return 0
    for entry in resumes_root.iterdir():
        if not entry.is_dir() or entry.name in known_shas:
            continue
        for child in sorted(entry.rglob("*"), reverse=True):
            if child.is_file():
                child.unlink(missing_ok=True)
        entry.rmdir()
        removed += 1
    return removed
