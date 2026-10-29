"""Endpoint de mantenimiento para el Cron de Vercel (el worker en servidores propios hace lo mismo)."""
import hmac
import os

from fastapi import APIRouter, Depends, Header

from . import db
from .db import get_conn
from .raffles import err

router = APIRouter(prefix="/api/v1/cron")


@router.get("/tick")
def tick(authorization: str = Header(default=""), conn=Depends(get_conn)):
    secret = os.environ.get("CRON_SECRET")
    if not secret:
        raise err(503, "CRON_NOT_CONFIGURED")
    if not hmac.compare_digest(authorization.encode(), f"Bearer {secret}".encode()):
        raise err(401, "UNAUTHORIZED")
    return db.lazy_maintenance(conn, force=True)
