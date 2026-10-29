"""Endpoint de mantenimiento para el Cron de Vercel (el worker en servidores propios hace lo mismo)."""
import hmac
import logging
import os

from fastapi import APIRouter, Depends, Header
from fastapi.responses import JSONResponse

from . import db
from .audit import verify_chain
from .db import get_conn
from .raffles import err

router = APIRouter(prefix="/api/v1/cron")


health = APIRouter(prefix="/api/v1")


@health.get("/health")
def health_check():
    """Para monitores externos (UptimeRobot, Better Stack…): 200 si la base responde, 503 si no."""
    import psycopg
    from psycopg.rows import dict_row

    from . import migrate, whatsapp
    out = {"status": "ok", "commit": (os.environ.get("VERCEL_GIT_COMMIT_SHA") or "dev")[:7],
           "whatsapp": whatsapp.config() is not None, "beta": bool(os.environ.get("SGRS_BETA_KEY"))}
    try:
        with psycopg.connect(db.DSN, row_factory=dict_row, connect_timeout=5, prepare_threshold=None) as c:
            c.execute("SELECT 1")
            if os.environ.get("SGRS_AUTO_SCHEMA") == "1":
                db.ensure_schema(c)  # primer arranque: crea/actualiza el esquema antes de informar
            out["schema"] = migrate.current(c)
    except Exception:
        return JSONResponse({**out, "status": "degraded", "db": False}, status_code=503)
    return {**out, "db": True}


@router.get("/tick")
def tick(authorization: str = Header(default=""), conn=Depends(get_conn)):
    secret = os.environ.get("CRON_SECRET")
    if not secret:
        raise err(503, "CRON_NOT_CONFIGURED")
    if not hmac.compare_digest(authorization.encode(), f"Bearer {secret}".encode()):
        raise err(401, "UNAUTHORIZED")
    out = db.lazy_maintenance(conn, force=True)
    out["auditoria_ok"] = verify_chain(conn, last=5000)
    if not out["auditoria_ok"]:
        logging.getLogger("sgrs").error("CADENA DE AUDITORÍA ROTA: revisar audit_log")
    return out
