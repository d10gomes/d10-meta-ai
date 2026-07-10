"""
Media Library API
- Upload de imagens/vídeos para Supabase Storage
- Sincronização automática com Meta Ad Library
- Listagem com filtros e métricas de performance
"""
from __future__ import annotations

import mimetypes
import os
import uuid
from datetime import datetime
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from sqlalchemy import select, and_, or_, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import get_current_user, get_db
from app.core.config import settings
from app.core.logging import logger
from app.db.models import MediaAsset, MetaAccount, User

router = APIRouter(prefix="/media", tags=["media"])

# Supabase Storage REST endpoint
_STORAGE_URL = os.getenv("SUPABASE_URL", "").rstrip("/") + "/storage/v1"
_STORAGE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")
_BUCKET = "creatives"

ALLOWED_IMAGES = {"image/jpeg", "image/png", "image/gif", "image/webp"}
ALLOWED_VIDEOS = {"video/mp4", "video/quicktime", "video/webm"}
MAX_IMAGE_MB = 30
MAX_VIDEO_MB = 500


# ---------------------------------------------------------------------------
# Upload
# ---------------------------------------------------------------------------

@router.post("/upload")
async def upload_media(
    file: UploadFile = File(...),
    meta_account_id: Optional[str] = Form(None),
    offer_id: Optional[str] = Form(None),
    tags: Optional[str] = Form(None),          # comma-separated
    notes: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    mime = file.content_type or mimetypes.guess_type(file.filename or "")[0] or ""
    is_image = mime in ALLOWED_IMAGES
    is_video = mime in ALLOWED_VIDEOS

    if not is_image and not is_video:
        raise HTTPException(status_code=422, detail=f"Formato não suportado: {mime}")

    content = await file.read()
    file_size = len(content)
    max_bytes = (MAX_VIDEO_MB if is_video else MAX_IMAGE_MB) * 1024 * 1024
    if file_size > max_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"Arquivo muito grande. Máximo: {MAX_VIDEO_MB if is_video else MAX_IMAGE_MB}MB",
        )

    # Generate unique storage path
    ext = (file.filename or "file").rsplit(".", 1)[-1].lower()
    asset_id = str(uuid.uuid4())
    storage_path = f"{user.tenant_id}/{asset_id}.{ext}"

    # Upload to Supabase Storage
    public_url = await _upload_to_supabase(content, storage_path, mime)

    # Detect format from dimensions/aspect ratio
    width, height = _extract_dimensions(content, mime)
    fmt = _detect_format(width, height, is_video)

    # Save to DB
    asset = MediaAsset(
        id=asset_id,
        tenant_id=str(user.tenant_id),
        meta_account_id=meta_account_id,
        name=_clean_name(file.filename or "untitled"),
        original_name=file.filename or "untitled",
        file_type="video" if is_video else ("gif" if mime == "image/gif" else "image"),
        format=fmt,
        mime_type=mime,
        file_size_bytes=file_size,
        width_px=width,
        height_px=height,
        storage_bucket=_BUCKET,
        storage_path=storage_path,
        public_url=public_url,
        offer_id=offer_id,
        tags=[t.strip() for t in (tags or "").split(",") if t.strip()],
        notes=notes,
        status="ready",
        uploaded_by=str(user.id),
    )
    db.add(asset)
    await db.flush()

    # Fire-and-forget: sync to Meta if account provided
    if meta_account_id:
        try:
            await _sync_to_meta(asset, content, meta_account_id, db)
        except Exception as exc:
            logger.warning("media.meta_sync_failed", asset_id=asset_id, error=str(exc))

    await db.commit()
    await db.refresh(asset)
    return _serialize(asset)


# ---------------------------------------------------------------------------
# List / Search
# ---------------------------------------------------------------------------

@router.get("")
async def list_media(
    file_type: Optional[str] = Query(None),          # image|video|gif
    format: Optional[str] = Query(None),             # feed|story|reels|carousel
    status: Optional[str] = Query(None),
    meta_account_id: Optional[str] = Query(None),
    offer_id: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    sort: str = Query("created_at"),                 # created_at|avg_ctr|avg_roas|times_used
    limit: int = Query(50, le=200),
    offset: int = Query(0),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    filters = [
        MediaAsset.tenant_id == str(user.tenant_id),
        MediaAsset.status != "deleted",
    ]

    if file_type:
        filters.append(MediaAsset.file_type == file_type)
    if format:
        filters.append(MediaAsset.format == format)
    if status:
        filters.append(MediaAsset.status == status)
    if meta_account_id:
        filters.append(MediaAsset.meta_account_id == meta_account_id)
    if offer_id:
        filters.append(MediaAsset.offer_id == offer_id)
    if search:
        filters.append(
            or_(
                MediaAsset.name.ilike(f"%{search}%"),
                MediaAsset.notes.ilike(f"%{search}%"),
            )
        )

    order_col = {
        "avg_ctr": MediaAsset.avg_ctr.desc().nulls_last(),
        "avg_roas": MediaAsset.avg_roas.desc().nulls_last(),
        "times_used": MediaAsset.times_used.desc(),
    }.get(sort, MediaAsset.created_at.desc())

    result = await db.execute(
        select(MediaAsset)
        .where(and_(*filters))
        .order_by(order_col)
        .limit(limit)
        .offset(offset)
    )
    assets = result.scalars().all()

    # Total count
    count_result = await db.execute(
        select(func.count()).select_from(MediaAsset).where(and_(*filters))
    )
    total = count_result.scalar() or 0

    return {
        "total": total,
        "items": [_serialize(a) for a in assets],
    }


@router.get("/stats")
async def media_stats(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(
            func.count().label("total"),
            func.count().filter(MediaAsset.file_type == "image").label("images"),
            func.count().filter(MediaAsset.file_type == "video").label("videos"),
            func.count().filter(MediaAsset.status == "synced_meta").label("synced"),
            func.sum(MediaAsset.file_size_bytes).label("total_bytes"),
        ).where(
            MediaAsset.tenant_id == str(user.tenant_id),
            MediaAsset.status != "deleted",
        )
    )
    row = result.one()
    return {
        "total": row.total or 0,
        "images": row.images or 0,
        "videos": row.videos or 0,
        "synced_meta": row.synced or 0,
        "total_gb": round((row.total_bytes or 0) / (1024 ** 3), 3),
    }


@router.get("/{asset_id}")
async def get_media(
    asset_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(MediaAsset).where(
            MediaAsset.id == asset_id,
            MediaAsset.tenant_id == str(user.tenant_id),
        )
    )
    asset = result.scalar_one_or_none()
    if not asset:
        raise HTTPException(status_code=404, detail="Mídia não encontrada.")
    return _serialize(asset)


@router.delete("/{asset_id}")
async def delete_media(
    asset_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(MediaAsset).where(
            MediaAsset.id == asset_id,
            MediaAsset.tenant_id == str(user.tenant_id),
        )
    )
    asset = result.scalar_one_or_none()
    if not asset:
        raise HTTPException(status_code=404, detail="Mídia não encontrada.")
    asset.status = "deleted"
    await db.commit()
    return {"deleted": True}


@router.post("/{asset_id}/sync-meta")
async def sync_to_meta_manual(
    asset_id: str,
    meta_account_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Manually trigger sync of an asset to Meta Ad Library."""
    result = await db.execute(
        select(MediaAsset).where(
            MediaAsset.id == asset_id,
            MediaAsset.tenant_id == str(user.tenant_id),
        )
    )
    asset = result.scalar_one_or_none()
    if not asset:
        raise HTTPException(status_code=404, detail="Mídia não encontrada.")

    # Re-download from storage to sync
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(asset.public_url)
        resp.raise_for_status()
        content = resp.content

    await _sync_to_meta(asset, content, meta_account_id, db)
    await db.commit()
    return _serialize(asset)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

async def _upload_to_supabase(content: bytes, path: str, mime: str) -> str:
    if not _STORAGE_KEY:
        # Dev fallback: return placeholder
        return f"/storage/{path}"

    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(
            f"{_STORAGE_URL}/object/{_BUCKET}/{path}",
            content=content,
            headers={
                "Authorization": f"Bearer {_STORAGE_KEY}",
                "Content-Type": mime,
                "x-upsert": "true",
            },
        )
        if resp.status_code not in (200, 201):
            raise HTTPException(status_code=502, detail=f"Storage error: {resp.text[:200]}")

    supabase_url = os.getenv("SUPABASE_URL", "").rstrip("/")
    return f"{supabase_url}/storage/v1/object/public/{_BUCKET}/{path}"


async def _sync_to_meta(
    asset: MediaAsset,
    content: bytes,
    meta_account_id: str,
    db: AsyncSession,
) -> None:
    """Upload asset to Meta Ad Library and store the hash/video_id."""
    from app.infrastructure.meta_api.client import MetaAdsClient

    # Get account token
    result = await db.execute(
        select(MetaAccount).where(MetaAccount.id == meta_account_id)
    )
    account = result.scalar_one_or_none()
    if not account:
        return

    client = MetaAdsClient(account.access_token, account.ad_account_id)
    try:
        if asset.file_type == "image":
            meta_result = await client.upload_image(content, asset.original_name)
            asset.meta_image_hash = meta_result.get("hash")
            asset.meta_status = "ACTIVE"
        else:
            meta_result = await client.upload_video(content, asset.original_name)
            asset.meta_video_id = meta_result.get("video_id")
            asset.meta_status = "PROCESSING"

        asset.meta_account_id = meta_account_id
        asset.meta_synced_at = datetime.utcnow()
        asset.status = "synced_meta"
        logger.info("media.meta_synced", asset_id=str(asset.id), type=asset.file_type)
    finally:
        await client.close()


def _extract_dimensions(content: bytes, mime: str) -> tuple[int | None, int | None]:
    try:
        if mime.startswith("image/"):
            from PIL import Image
            import io
            img = Image.open(io.BytesIO(content))
            return img.width, img.height
    except Exception:
        pass
    return None, None


def _detect_format(w: int | None, h: int | None, is_video: bool) -> str:
    if not w or not h:
        return "unknown"
    ratio = w / h
    if abs(ratio - 1.0) < 0.05:
        return "feed"       # 1:1
    if ratio < 0.7:
        return "story"      # 9:16
    if ratio > 1.7:
        return "feed"       # 16:9 / 1.91:1
    return "carousel"       # mixed


def _clean_name(filename: str) -> str:
    return filename.rsplit(".", 1)[0].replace("_", " ").replace("-", " ").strip()


def _serialize(a: MediaAsset) -> dict:
    return {
        "id": str(a.id),
        "name": a.name,
        "original_name": a.original_name,
        "file_type": a.file_type,
        "format": a.format,
        "mime_type": a.mime_type,
        "file_size_bytes": a.file_size_bytes,
        "file_size_mb": round((a.file_size_bytes or 0) / (1024 * 1024), 2),
        "width_px": a.width_px,
        "height_px": a.height_px,
        "duration_secs": float(a.duration_secs) if a.duration_secs else None,
        "public_url": a.public_url,
        "meta_image_hash": a.meta_image_hash,
        "meta_video_id": a.meta_video_id,
        "meta_status": a.meta_status,
        "meta_synced_at": a.meta_synced_at.isoformat() if a.meta_synced_at else None,
        "offer_id": a.offer_id,
        "tags": a.tags or [],
        "notes": a.notes,
        "avg_ctr": float(a.avg_ctr) if a.avg_ctr else None,
        "avg_roas": float(a.avg_roas) if a.avg_roas else None,
        "avg_cpa": float(a.avg_cpa) if a.avg_cpa else None,
        "avg_frequency": float(a.avg_frequency) if a.avg_frequency else None,
        "times_used": a.times_used or 0,
        "performance_score": float(a.performance_score) if a.performance_score else None,
        "status": a.status,
        "created_at": a.created_at.isoformat() if a.created_at else None,
    }
