"""Imágenes de portada y galería de una rifa."""
import hashlib
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Request, Response

from . import storage
from . import ratelimit
from .db import get_conn
from .raffles import err
from .security import current_user, optional_user
from .uploads import MAX_BYTES, sniff

router = APIRouter(prefix="/api/v1")
IMAGE_MIMES = {"image/png", "image/jpeg", "image/webp"}


@router.put("/uploads/image", status_code=201)
async def upload_image(request: Request, user=Depends(current_user), conn=Depends(get_conn)):
    ratelimit.hit(conn, "upload_user", str(user["id"]), limit=60, window=3600)
    if int(request.headers.get("content-length", 0)) > MAX_BYTES:
        raise err(413, "FILE_TOO_LARGE", max=MAX_BYTES)
    data = await request.body()
    if not data:
        raise err(422, "FILE_EMPTY")
    if len(data) > MAX_BYTES:
        raise err(413, "FILE_TOO_LARGE", max=MAX_BYTES)
    mime = sniff(data)
    if mime not in IMAGE_MIMES:
        raise err(415, "UNSUPPORTED_TYPE", allowed=["png", "jpeg", "webp"])
    sha = hashlib.sha256(data).hexdigest()
    storage.put(conn, sha, data)
    iid = uuid4()
    conn.execute("INSERT INTO raffle_images (id, uploader_id, sha256, mime, size, storage_key) VALUES (%s,%s,%s,%s,%s,%s)",
                 (iid, user["id"], sha, mime, len(data), sha))
    return {"image_id": iid, "mime": mime, "size": len(data)}


@router.get("/raffle-images/{iid}")
def get_image(iid: UUID, user=Depends(optional_user), conn=Depends(get_conn)):
    img = conn.execute(
        "SELECT i.*, r.status AS raffle_status, r.owner_id FROM raffle_images i LEFT JOIN raffles r ON r.id = i.raffle_id"
        " WHERE i.id=%s", (iid,)).fetchone()
    if not img:
        raise err(404, "IMAGE_NOT_FOUND")
    public = img["raffle_id"] is not None and img["raffle_status"] != "DRAFT"
    mine = user and (user["id"] in (img["uploader_id"], img["owner_id"]) or user["role"] == "SUPERUSER")
    if not (public or mine):
        raise err(404, "IMAGE_NOT_FOUND")  # no se revela que existe
    cache = "public, max-age=86400, immutable" if public else "private, no-store"
    return Response(storage.get(conn, img["storage_key"]), media_type=img["mime"],
                    headers={"X-Content-Type-Options": "nosniff", "Cache-Control": cache})
