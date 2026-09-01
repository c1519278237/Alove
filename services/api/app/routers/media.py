from pathlib import Path

from cryptography.fernet import InvalidToken
from fastapi import APIRouter, Depends, File, UploadFile
from fastapi.responses import Response
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..database import get_db
from ..deps import get_current_user
from ..errors import AppError, not_found
from ..models import FamilyMessage, MediaObject, User
from ..schemas import MediaObjectOut
from ..security import decrypt_bytes, encrypt_bytes, new_id

router = APIRouter(prefix="/media", tags=["media"])

_IMAGE_SIGNATURES: tuple[tuple[str, bytes], ...] = (
    ("image/png", b"\x89PNG\r\n\x1a\n"),
    ("image/jpeg", b"\xff\xd8\xff"),
    ("image/gif", b"GIF8"),
)


def _storage_root() -> Path:
    root = Path(get_settings().media_storage_dir).resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def media_path(storage_key: str) -> Path:
    root = _storage_root()
    candidate = (root / storage_key).resolve()
    if root != candidate and root not in candidate.parents:
        raise AppError("INVALID_MEDIA_KEY", "媒体文件路径无效", 500)
    return candidate


def _detected_image_type(payload: bytes) -> str | None:
    for mime_type, signature in _IMAGE_SIGNATURES:
        if payload.startswith(signature):
            return mime_type
    if len(payload) >= 12 and payload.startswith(b"RIFF") and payload[8:12] == b"WEBP":
        return "image/webp"
    return None


@router.post("/audio", response_model=MediaObjectOut, status_code=201)
async def upload_audio(
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> MediaObject:
    settings = get_settings()
    content_type = (file.content_type or "application/octet-stream").lower()
    if not content_type.startswith("audio/"):
        raise AppError("INVALID_AUDIO", "只能上传音频文件", 415)
    payload = await file.read(settings.media_max_bytes + 1)
    if not payload:
        raise AppError("INVALID_AUDIO", "音频文件不能为空", 422)
    if len(payload) > settings.media_max_bytes:
        raise AppError("MEDIA_TOO_LARGE", "语音留言不能超过 10MB", 413)
    media_id = new_id()
    storage_key = f"audio/{media_id}.bin"
    destination = media_path(storage_key)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(encrypt_bytes(payload))
    media = MediaObject(
        id=media_id,
        owner_user_id=user.id,
        storage_key=storage_key,
        mime_type=content_type,
        original_name=(file.filename or "voice-message")[:255],
        size_bytes=len(payload),
    )
    db.add(media)
    db.commit()
    return media


@router.post("/image", response_model=MediaObjectOut, status_code=201)
async def upload_image(
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> MediaObject:
    settings = get_settings()
    max_bytes = min(settings.media_max_bytes, 5 * 1024 * 1024)
    payload = await file.read(max_bytes + 1)
    if not payload:
        raise AppError("INVALID_IMAGE", "图片文件不能为空", 422)
    if len(payload) > max_bytes:
        raise AppError("MEDIA_TOO_LARGE", "图片不能超过5MB", 413)
    detected_type = _detected_image_type(payload)
    if detected_type is None:
        raise AppError("INVALID_IMAGE", "仅支持PNG、JPEG、WebP或GIF图片", 415)
    media_id = new_id()
    storage_key = f"image/{media_id}.bin"
    destination = media_path(storage_key)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(encrypt_bytes(payload))
    media = MediaObject(
        id=media_id,
        owner_user_id=user.id,
        storage_key=storage_key,
        mime_type=detected_type,
        original_name=(file.filename or "ai-image")[:255],
        size_bytes=len(payload),
    )
    db.add(media)
    db.commit()
    return media


def read_owned_image(db: Session, media_id: str, user_id: str) -> tuple[str, bytes]:
    media = db.get(MediaObject, media_id)
    if (
        media is None
        or media.status != "active"
        or media.owner_user_id != user_id
        or not media.mime_type.startswith("image/")
    ):
        raise not_found("图片")
    try:
        payload = decrypt_bytes(media_path(media.storage_key).read_bytes())
    except (FileNotFoundError, InvalidToken) as exc:
        raise not_found("图片") from exc
    return media.mime_type, payload


def _can_read_media(db: Session, media: MediaObject, user_id: str) -> bool:
    if media.owner_user_id == user_id:
        return True
    message = db.scalar(
        select(FamilyMessage.id).where(
            FamilyMessage.audio_object_key == media.id,
            or_(
                FamilyMessage.sender_user_id == user_id,
                FamilyMessage.recipient_user_id == user_id,
            ),
        )
    )
    return message is not None


@router.get("/{media_id}")
def download_media(
    media_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    media = db.get(MediaObject, media_id)
    if media is None or media.status != "active" or not _can_read_media(db, media, user.id):
        raise not_found("媒体文件")
    try:
        payload = decrypt_bytes(media_path(media.storage_key).read_bytes())
    except (FileNotFoundError, InvalidToken) as exc:
        raise not_found("媒体文件") from exc
    return Response(
        content=payload,
        media_type=media.mime_type,
        headers={
            "Content-Disposition": f'inline; filename="{media.id}"',
            "Cache-Control": "private, no-store",
        },
    )
