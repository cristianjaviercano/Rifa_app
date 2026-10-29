import hashlib
import logging
import os
import time
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

log = logging.getLogger("sgrs.db")


def _dsn() -> str:
    return (os.environ.get("SGRS_DSN") or os.environ.get("DATABASE_URL") or os.environ.get("POSTGRES_URL")
            or "postgresql://postgres@localhost:5433/sgrs")


DSN = _dsn()
SCHEMA = Path(__file__).resolve().parent.parent / "schema.sql"
_schema_ok = False
_last_maintenance = 0.0


def secret_fallback() -> str:
    """Secreto derivado de la cadena de conexión (que solo existe en el entorno del servidor)."""
    return hashlib.sha256(("sgrs-jwt:" + DSN).encode()).hexdigest()


def ensure_schema(conn) -> None:
    """Crea el esquema si la base está vacía (primer arranque en la nube). Seguro ante concurrencia."""
    global _schema_ok
    if _schema_ok:
        return
    conn.execute("SELECT pg_advisory_xact_lock(727274)")
    if conn.execute("SELECT to_regclass('public.users') AS t").fetchone()["t"] is None:
        log.warning("Base vacía: aplicando schema.sql")
        conn.execute(SCHEMA.read_text())
    _schema_ok = True


def lazy_maintenance(conn, force: bool = False) -> dict:
    """Sin worker (entornos serverless): expira reservas, cierra rifas y programa recordatorios
    aprovechando las propias peticiones, como máximo cada 20 s por instancia."""
    global _last_maintenance
    now = time.monotonic()
    if not force and now - _last_maintenance < 20:
        return {}
    _last_maintenance = now
    from .main import expire_holds
    from .notify import enqueue_draw_reminders
    from .raffles import auto_close
    out = {}
    try:
        with conn.transaction():  # punto de guardado: un fallo aquí no rompe la petición
            out = {"expiradas": expire_holds(conn), "cerradas": auto_close(conn), "recordatorios": enqueue_draw_reminders(conn)}
    except Exception:
        log.exception("mantenimiento falló")
    return out


def get_conn():
    """Una conexión por petición; commit al terminar, rollback ante excepción."""
    # prepare_threshold=None: compatible con pooler de transacciones (Neon/pgbouncer)
    with psycopg.connect(DSN, row_factory=dict_row, prepare_threshold=None, connect_timeout=10) as conn:
        if os.environ.get("SGRS_AUTO_SCHEMA") == "1":
            ensure_schema(conn)
        if os.environ.get("SGRS_LAZY_MAINTENANCE") == "1":
            lazy_maintenance(conn)
        yield conn
