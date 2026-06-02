"""
Gibson image storage service — Supabase Storage.
Falls back to local filesystem when Supabase is not configured (dev).
"""

import base64
import os
import uuid

import httpx

from api.config import settings


def _ext(content_type: str) -> str:
    if "jpeg" in content_type or "jpg" in content_type:
        return "jpg"
    return content_type.split("/")[-1]


BUCKET = "gibson-images"


async def upload_stock_image(image_base64: str, content_type: str = "image/jpeg") -> str:
    """
    Decode a base64 image and store it.
    Returns a public URL usable by the mobile app and marketplace listings.
    """
    image_bytes = base64.b64decode(image_base64)
    filename = f"{uuid.uuid4()}.{_ext(content_type)}"
    path = f"stock/{filename}"

    if settings.supabase_url and settings.supabase_service_role_key:
        upload_url = f"{settings.supabase_url}/storage/v1/object/{BUCKET}/{path}"
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                upload_url,
                content=image_bytes,
                headers={
                    "Authorization": f"Bearer {settings.supabase_service_role_key}",
                    "Content-Type": content_type,
                },
            )
            resp.raise_for_status()
        return f"{settings.supabase_url}/storage/v1/object/public/{BUCKET}/{path}"

    # Local fallback for development
    local_dir = os.path.join(settings.local_image_path, "stock")
    os.makedirs(local_dir, exist_ok=True)
    with open(os.path.join(local_dir, filename), "wb") as f:
        f.write(image_bytes)
    return f"/api/images/stock/{filename}"


async def delete_stock_image(url: str) -> None:
    """Best-effort delete. Does not raise on failure."""
    try:
        if settings.supabase_url and settings.supabase_service_role_key and BUCKET in url:
            # Extract path after /object/public/{bucket}/
            marker = f"/object/public/{BUCKET}/"
            if marker in url:
                path = url.split(marker, 1)[1]
                delete_url = f"{settings.supabase_url}/storage/v1/object/{BUCKET}/{path}"
                async with httpx.AsyncClient(timeout=10.0) as client:
                    await client.delete(
                        delete_url,
                        headers={"Authorization": f"Bearer {settings.supabase_service_role_key}"},
                    )
        elif url.startswith("/api/images/"):
            rel = url.replace("/api/images/", "")
            path = os.path.join(settings.local_image_path, rel)
            if os.path.exists(path):
                os.remove(path)
    except Exception:
        pass
