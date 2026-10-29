import os
from pathlib import Path

ROOT = Path(os.environ.get("SGRS_UPLOAD_DIR", "./uploads"))


def put(key: str, data: bytes) -> None:
    ROOT.mkdir(parents=True, exist_ok=True)
    (ROOT / key).write_bytes(data)  # nombre = hash del contenido: idempotente


def get(key: str) -> bytes:
    return (ROOT / key).read_bytes()
