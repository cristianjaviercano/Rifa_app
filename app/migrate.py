"""Migraciones de esquema versionadas: archivos migrations/NNNN_nombre.sql aplicados en orden.

Reglas: nunca se edita una migración ya publicada; todo cambio de esquema es un archivo nuevo.
Todo se aplica en una sola transacción bajo un bloqueo consultivo (seguro con varias instancias).
Uso manual: python -m app.migrate  (usa SGRS_DSN / DATABASE_URL)
"""
import logging
from pathlib import Path

log = logging.getLogger("sgrs.migrate")
DIR = Path(__file__).resolve().parent.parent / "migrations"
BASELINE = "0001_baseline"


def files() -> list[Path]:
    return sorted(DIR.glob("[0-9][0-9][0-9][0-9]_*.sql"))


def apply_all(conn) -> list[str]:
    """Aplica las migraciones pendientes y devuelve sus nombres."""
    conn.execute("SELECT pg_advisory_xact_lock(727274)")
    conn.execute("CREATE TABLE IF NOT EXISTS schema_migrations "
                 "(version text PRIMARY KEY, applied_at timestamptz NOT NULL DEFAULT now())")
    done = {r["version"] for r in conn.execute("SELECT version FROM schema_migrations").fetchall()}
    if not done and conn.execute("SELECT to_regclass('public.users') AS t").fetchone()["t"] is not None:
        # base creada antes de existir este sistema: ya contiene la línea base
        conn.execute("INSERT INTO schema_migrations (version) VALUES (%s)", (BASELINE,))
        done.add(BASELINE)
    applied = []
    for f in files():
        if f.stem in done:
            continue
        log.warning("aplicando migración %s", f.stem)
        conn.execute(f.read_text())
        conn.execute("INSERT INTO schema_migrations (version) VALUES (%s)", (f.stem,))
        applied.append(f.stem)
    return applied


def current(conn) -> str | None:
    row = conn.execute("SELECT max(version) AS v FROM schema_migrations").fetchone()
    return row["v"] if row else None


if __name__ == "__main__":
    import psycopg
    from psycopg.rows import dict_row

    from .db import DSN
    with psycopg.connect(DSN, row_factory=dict_row, prepare_threshold=None) as c:
        print("aplicadas:", apply_all(c) or "ninguna (al día)")
