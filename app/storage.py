"""Almacenamiento de comprobantes: disco local (SGRS_STORAGE=file, por defecto) o la propia base (db)."""
import os
from pathlib import Path


def _backend() -> str:
    return os.environ.get("SGRS_STORAGE", "file")


def _root() -> Path:
    return Path(os.environ.get("SGRS_UPLOAD_DIR", "./uploads"))


def put(conn, key: str, data: bytes) -> None:
    if _backend() == "db":
        conn.execute("INSERT INTO proof_blobs (storage_key, data) VALUES (%s,%s) ON CONFLICT DO NOTHING", (key, data))
        return
    _root().mkdir(parents=True, exist_ok=True)
    (_root() / key).write_bytes(data)  # nombre = hash del contenido: idempotente


def get(conn, key: str) -> bytes:
    if _backend() == "db":
        return bytes(conn.execute("SELECT data FROM proof_blobs WHERE storage_key=%s", (key,)).fetchone()["data"])
    return (_root() / key).read_bytes()
