import json
from tests.conftest import dsn
import logging

import psycopg
import pytest
from fastapi.testclient import TestClient
from psycopg.rows import dict_row

from app import db as appdb
from app import observability
from app.audit import verify_chain, write_audit
from app.main import app

client = TestClient(app, raise_server_exceptions=False)


def test_health_ok(monkeypatch):
    monkeypatch.setenv("VERCEL_GIT_COMMIT_SHA", "abcdef1234567")
    r = client.get("/api/v1/health")
    j = r.json()
    assert r.status_code == 200 and j["status"] == "ok" and j["db"] is True
    assert j["commit"] == "abcdef1" and j["schema"].startswith("0002") and j["whatsapp"] is False


def test_health_degraded_when_database_is_down(monkeypatch):
    monkeypatch.setattr(appdb, "DSN", "postgresql://postgres@127.0.0.1:1/nada")
    r = client.get("/api/v1/health")
    assert r.status_code == 503 and r.json()["status"] == "degraded" and r.json()["db"] is False


def test_request_id_and_structured_access_log(caplog):
    with caplog.at_level(logging.INFO, logger="sgrs.access"):
        r = client.get("/api/v1/auth/config", headers={"x-vercel-id": "iad1::abc123"})
    assert r.headers["x-request-id"] == "iad1::abc123"
    line = next(json.loads(x.message) for x in caplog.records if x.name == "sgrs.access" and x.message.startswith("{"))
    assert line["ev"] == "req" and line["p"] == "/api/v1/auth/config" and line["s"] == 200 and line["rid"] == "iad1::abc123"
    assert "phone" not in json.dumps(line)


def test_access_log_has_no_query_string_or_body(caplog):
    with caplog.at_level(logging.INFO, logger="sgrs.access"):
        client.post("/api/v1/auth/otp/verify?x=secreto", json={"phone": "+573001112233", "code": "123456"})
    text = " ".join(x.message for x in caplog.records if x.name == "sgrs.access")
    assert "secreto" not in text and "3001112233" not in text and "123456" not in text


def test_unhandled_error_returns_reference(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("fallo inesperado con datos internos")
    monkeypatch.setattr("app.auth.sms.send_otp", boom)
    r = client.post("/api/v1/auth/otp/request", json={"phone": "+573001112299"})
    assert r.status_code == 500
    d = r.json()["detail"]
    assert d["code"] == "INTERNAL_ERROR" and d["request_id"] and r.headers["x-request-id"] == d["request_id"]
    assert "fallo inesperado" not in r.text  # sin filtrar detalles internos


def test_sentry_is_optional(monkeypatch):
    monkeypatch.delenv("SENTRY_DSN", raising=False)
    assert observability.init_sentry() is False
    monkeypatch.setenv("SENTRY_DSN", "http://public@127.0.0.1:1/1")
    try:
        assert observability.init_sentry() is True
    finally:
        import sentry_sdk
        sentry_sdk.init()  # desactiva


def test_windowed_audit_verification_detects_tampering(db):
    with psycopg.connect(dsn(), row_factory=dict_row) as c:
        for i in range(5):
            write_audit(c, None, "TEST", "x", None, {"i": i})
    with psycopg.connect(dsn(), row_factory=dict_row) as c:
        assert verify_chain(c) and verify_chain(c, last=3)
    db.execute("ALTER TABLE audit_log DISABLE TRIGGER audit_no_mutation")
    try:
        last_id = db.execute("SELECT max(id) m FROM audit_log").fetchone()["m"]
        db.execute("UPDATE audit_log SET action='ALTERADO' WHERE id=%s", (last_id,))
        with psycopg.connect(dsn(), row_factory=dict_row) as c:
            assert verify_chain(c, last=3) is False and verify_chain(c) is False
            assert verify_chain(c, last=1) is False
    finally:
        db.execute("UPDATE audit_log SET action='TEST' WHERE id=%s", (last_id,))
        db.execute("ALTER TABLE audit_log ENABLE TRIGGER audit_no_mutation")
