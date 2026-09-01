from __future__ import annotations

import csv
import io
import json
from pathlib import Path

from fastapi import UploadFile

from .errors import AppError

TEXT_EXTENSIONS = {".txt", ".md", ".markdown", ".csv", ".json"}
DOCUMENT_EXTENSIONS = TEXT_EXTENSIONS | {".pdf", ".docx"}


async def read_uploaded_document(file: UploadFile, *, max_bytes: int) -> str:
    name = (file.filename or "document.txt")[:255]
    suffix = Path(name).suffix.lower()
    if suffix not in DOCUMENT_EXTENSIONS:
        raise AppError(
            "UNSUPPORTED_DOCUMENT",
            "仅支持 TXT、Markdown、CSV、JSON、PDF 和 DOCX 文件",
            415,
        )
    payload = await file.read(max_bytes + 1)
    if not payload:
        raise AppError("EMPTY_DOCUMENT", "资料文件不能为空", 422)
    if len(payload) > max_bytes:
        raise AppError("DOCUMENT_TOO_LARGE", "资料文件不能超过 10MB", 413)
    try:
        if suffix in {".txt", ".md", ".markdown"}:
            return _decode_text(payload)
        if suffix == ".csv":
            return _csv_text(payload)
        if suffix == ".json":
            return json.dumps(json.loads(_decode_text(payload)), ensure_ascii=False, indent=2)
        if suffix == ".pdf":
            from pypdf import PdfReader

            reader = PdfReader(io.BytesIO(payload))
            return "\n".join((page.extract_text() or "").strip() for page in reader.pages).strip()
        if suffix == ".docx":
            from docx import Document

            document = Document(io.BytesIO(payload))
            return "\n".join(paragraph.text.strip() for paragraph in document.paragraphs).strip()
    except (UnicodeDecodeError, ValueError, KeyError, OSError) as exc:
        raise AppError("DOCUMENT_PARSE_FAILED", "无法读取该资料文件", 422) from exc
    raise AppError("DOCUMENT_PARSE_FAILED", "无法读取该资料文件", 422)


def _decode_text(payload: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "gb18030"):
        try:
            return payload.decode(encoding).strip()
        except UnicodeDecodeError:
            continue
    raise UnicodeDecodeError("utf-8", payload, 0, 1, "unsupported text encoding")


def _csv_text(payload: bytes) -> str:
    source = io.StringIO(_decode_text(payload))
    return "\n".join(" | ".join(cell.strip() for cell in row) for row in csv.reader(source))
