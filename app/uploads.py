import hashlib
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Request, Response

from . import storage
from .db import get_conn
from .raffles import err
from .security import current_user

router = APIRouter(prefix="/api/v1")
MAX_BYTES = 5 * 1024 * 1024
MAGIC = [(b"\x89PNG\r\n\x1a\n", "image/png"), (b"\xff\xd8\xff", "image/jpeg"), (b"%PDF-", "application/pdf")]


def sniff(data: bytes):
    """El tipo se deduce de los bytes, nunca del encabezado que envía el cliente."""
    for sig, mime in MAGIC:
        if data.startswith(sig):
            return mime
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


@router.put("/uploads/proof", status_code=201)
async def upload_proof(request: Request, user=Depends(current_user), conn=Depends(get_conn)):
    if int(request.headers.get("content-length", 0)) > MAX_BYTES:
        raise err(413, "FILE_TOO_LARGE", max=MAX_BYTES)
    data = await request.body()
    if not data or len(data) > MAX_BYTES:
        raise err(413 if data else 422, "FILE_TOO_LARGE" if data else "FILE_EMPTY", max=MAX_BYTES)
    mime = sniff(data)
    if not mime:
        raise err(415, "UNSUPPORTED_TYPE", allowed=["png", "jpeg", "webp", "pdf"])
    sha = hashlib.sha256(data).hexdigest()
    key = f"{sha}"
    storage.put(key, data)
    pid = uuid4()
    conn.execute("INSERT INTO proofs (id, uploader_id, sha256, mime, size, storage_key) VALUES (%s,%s,%s,%s,%s,%s)",
                 (pid, user["id"], sha, mime, len(data), key))
    return {"proof_id": pid, "sha256": sha, "mime": mime, "size": len(data)}


@router.get("/proofs/{pid}")
def get_proof(pid: UUID, user=Depends(current_user), conn=Depends(get_conn)):
    p = conn.execute("SELECT * FROM proofs WHERE id=%s", (pid,)).fetchone()
    if not p:
        raise err(404, "PROOF_NOT_FOUND")
    allowed = user["role"] == "SUPERUSER" or p["uploader_id"] == user["id"] or conn.execute(
        "SELECT 1 FROM payment_transactions pt JOIN raffles r ON r.id=pt.raffle_id"
        " WHERE pt.proof_id=%s AND r.owner_id=%s", (pid, user["id"])).fetchone()
    if not allowed:
        raise err(403, "FORBIDDEN")
    return Response(storage.get(p["storage_key"]), media_type=p["mime"], headers={
        "X-Content-Type-Options": "nosniff", "Cache-Control": "private, no-store",
        "Content-Disposition": "inline"})
