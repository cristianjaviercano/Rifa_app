"""Registros estructurados, referencia de error para el usuario y captura opcional con Sentry."""
import json
import logging
import os
import sys
import time
import uuid

log = logging.getLogger("sgrs.access")


def setup_logging() -> None:
    """Una línea JSON por evento en stdout (lo recoge Vercel). No se registran datos personales."""
    root = logging.getLogger()
    if not root.handlers:
        h = logging.StreamHandler(sys.stdout)
        h.setFormatter(logging.Formatter("%(message)s"))
        root.addHandler(h)
    root.setLevel(os.environ.get("SGRS_LOG_LEVEL", "INFO"))


def init_sentry() -> bool:
    dsn = os.environ.get("SENTRY_DSN")
    if not dsn:
        return False
    try:
        import sentry_sdk
        sentry_sdk.init(dsn=dsn, environment=os.environ.get("SGRS_ENV", "dev"), send_default_pii=False,
                        max_request_body_size="never",  # los cuerpos traen celulares y comprobantes
                        traces_sample_rate=float(os.environ.get("SENTRY_TRACES", "0")),
                        release=os.environ.get("VERCEL_GIT_COMMIT_SHA"))
        return True
    except Exception:  # un fallo de observabilidad nunca debe tumbar la app
        logging.getLogger("sgrs").exception("no se pudo iniciar Sentry")
        return False


def request_id(request) -> str:
    return request.headers.get("x-vercel-id") or request.headers.get("x-request-id") or uuid.uuid4().hex[:12]


async def access_log(request, call_next):
    rid = request_id(request)
    request.state.rid = rid
    t0 = time.perf_counter()
    try:
        resp = await call_next(request)
    except Exception:
        log.error(json.dumps({"ev": "error", "rid": rid, "m": request.method, "p": request.url.path,
                              "ms": round((time.perf_counter() - t0) * 1000)}), exc_info=True)
        raise
    path = request.url.path
    if path.startswith("/api/"):  # el estático no aporta
        log.info(json.dumps({"ev": "req", "rid": rid, "m": request.method, "p": path, "s": resp.status_code,
                             "ms": round((time.perf_counter() - t0) * 1000)}))
    resp.headers["X-Request-Id"] = rid
    return resp
