"""Límites de tasa respaldados en PostgreSQL (funcionan igual con varias instancias serverless)."""
import os

from .raffles import err


def enabled() -> bool:
    return os.environ.get("SGRS_RATE_LIMITS", "on") != "off"


def client_ip(request) -> str:
    """IP del cliente. En producción se confía en las cabeceras que fija la plataforma (Vercel)."""
    if os.environ.get("SGRS_ENV") == "production":
        for h in ("x-vercel-forwarded-for", "x-forwarded-for", "x-real-ip"):
            v = request.headers.get(h)
            if v:
                return v.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _window(window: int) -> str:
    return "to_timestamp(floor(extract(epoch from now()) / %s) * %s)"


def hit(conn, bucket: str, key: str, limit: int, window: int, persist: bool = False) -> None:
    """Cuenta una petición en la ventana actual y responde 429 al superar `limit`.
    persist=True confirma el contador de inmediato (para endpoints cuyo error normal revierte la transacción)."""
    if not enabled():
        return
    row = conn.execute(
        f"INSERT INTO rate_limits (bucket, key, window_start, hits) VALUES (%s, %s, {_window(window)}, 1)"
        " ON CONFLICT (bucket, key, window_start) DO UPDATE SET hits = rate_limits.hits + 1 RETURNING hits",
        (bucket, key, window, window)).fetchone()
    if persist:
        conn.commit()
    if row["hits"] > limit:
        raise err(429, "RATE_LIMITED", retry_after=window)


def blocked(conn, bucket: str, key: str, limit: int, window: int) -> None:
    """Responde 429 si ya hay `limit` fallos registrados en la ventana (no cuenta esta petición)."""
    if not enabled():
        return
    n = conn.execute("SELECT coalesce(sum(hits), 0) AS n FROM rate_limits WHERE bucket=%s AND key=%s"
                     " AND window_start >= now() - make_interval(secs => %s)", (bucket, key, window)).fetchone()["n"]
    if n >= limit:
        raise err(429, "RATE_LIMITED", retry_after=window)


def fail(conn, bucket: str, key: str, window: int) -> None:
    """Registra un fallo y lo confirma ya: la petición que sigue responde error y revertiría el contador."""
    if not enabled():
        return
    conn.execute(
        f"INSERT INTO rate_limits (bucket, key, window_start, hits) VALUES (%s, %s, {_window(window)}, 1)"
        " ON CONFLICT (bucket, key, window_start) DO UPDATE SET hits = rate_limits.hits + 1",
        (bucket, key, window, window))
    conn.commit()
