import re
import uuid

import psycopg
import pytest
from fastapi.testclient import TestClient
from psycopg.rows import dict_row

from app import db as appdb
from app import security
from app.main import app
from tests.test_flow import H, body
from tests.test_auth_uploads import PNG

client = TestClient(app)


def phone():
    return "+57" + str(uuid.uuid4().int)[:10]


def test_config_and_beta_gate(monkeypatch):
    assert client.get("/api/v1/auth/config").json() == {"beta": False, "otp_on_screen": False}
    monkeypatch.setenv("SGRS_BETA_KEY", "clave-beta-123")
    monkeypatch.setenv("SGRS_DEV_ECHO_OTP", "1")
    assert client.get("/api/v1/auth/config").json() == {"beta": True, "otp_on_screen": True}
    p = phone()
    assert client.post("/api/v1/auth/otp/request", json={"phone": p}).status_code == 403
    assert client.post("/api/v1/auth/otp/request", json={"phone": p, "invite": "otra"}).status_code == 403
    ok = client.post("/api/v1/auth/otp/request", json={"phone": p, "invite": "clave-beta-123"})
    assert ok.status_code == 202 and re.fullmatch(r"\d{6}", ok.json()["dev_code"])
    v = client.post("/api/v1/auth/otp/verify", json={"phone": p, "code": ok.json()["dev_code"], "name": "Tester"})
    assert v.status_code == 200 and v.json()["access_token"]


def test_code_never_echoed_when_whatsapp_configured(monkeypatch):
    monkeypatch.setenv("SGRS_DEV_ECHO_OTP", "1")
    monkeypatch.setenv("WHATSAPP_TOKEN", "t")
    monkeypatch.setenv("WHATSAPP_PHONE_ID", "1")
    assert client.get("/api/v1/auth/config").json()["otp_on_screen"] is False


def test_beta_in_production_without_whatsapp(monkeypatch):
    monkeypatch.setenv("SGRS_ENV", "production")
    monkeypatch.setenv("SGRS_DEV_ECHO_OTP", "1")
    monkeypatch.setenv("SGRS_BETA_KEY", "clave-beta-123")
    monkeypatch.delenv("WHATSAPP_TOKEN", raising=False)
    r = client.post("/api/v1/auth/otp/request", json={"phone": phone(), "invite": "clave-beta-123"})
    assert r.status_code == 202 and "dev_code" in r.json()


def test_code_on_screen_requires_beta_key_in_production(monkeypatch):
    """Sin clave de invitación, el código en pantalla permitiría tomar la cuenta de cualquier número."""
    monkeypatch.setenv("SGRS_ENV", "production")
    monkeypatch.setenv("SGRS_DEV_ECHO_OTP", "1")
    monkeypatch.delenv("SGRS_BETA_KEY", raising=False)
    monkeypatch.delenv("WHATSAPP_TOKEN", raising=False)
    assert client.get("/api/v1/auth/config").json() == {"beta": False, "otp_on_screen": False}
    r = client.post("/api/v1/auth/otp/request", json={"phone": phone()})
    assert r.status_code == 502 and "dev_code" not in r.text


def test_storage_in_database(db, monkeypatch, tmp_path, mkuser):
    monkeypatch.setenv("SGRS_STORAGE", "db")
    monkeypatch.setenv("SGRS_UPLOAD_DIR", str(tmp_path / "no-usar"))
    u = mkuser()
    r = client.put("/api/v1/uploads/proof", content=PNG, headers=H(u))
    assert r.status_code == 201
    assert db.execute("SELECT count(*) c FROM proof_blobs WHERE storage_key=%s", (r.json()["sha256"],)).fetchone()["c"] == 1
    g = client.get(f"/api/v1/proofs/{r.json()['proof_id']}", headers=H(u))
    assert g.status_code == 200 and g.content == PNG
    assert not (tmp_path / "no-usar").exists()  # nada escrito en disco


def test_upload_limit_is_below_platform_limit():
    from app.uploads import MAX_BYTES
    assert MAX_BYTES < 4.5 * 1024 * 1024


def test_cron_requires_secret(monkeypatch):
    assert client.get("/api/v1/cron/tick").status_code == 503
    monkeypatch.setenv("CRON_SECRET", "s3cr3t")
    assert client.get("/api/v1/cron/tick").status_code == 401
    assert client.get("/api/v1/cron/tick", headers={"Authorization": "Bearer mal"}).status_code == 401
    r = client.get("/api/v1/cron/tick", headers={"Authorization": "Bearer s3cr3t"})
    assert r.status_code == 200 and set(r.json()) == {"expiradas", "cerradas", "recordatorios"}


def test_lazy_maintenance_expires_without_worker(db, monkeypatch, raffle, mkuser):
    r, b = raffle(), mkuser()
    tid = client.post(f"/api/v1/raffles/{r['id']}/reservations", json=body(r["tickets"][:1]), headers=H(b)).json()["transaction_id"]
    db.execute("UPDATE payment_transactions SET expires_at = now() - interval '1 minute' WHERE id=%s", (tid,))
    monkeypatch.setenv("SGRS_LAZY_MAINTENANCE", "1")
    monkeypatch.setattr(appdb, "_last_maintenance", 0.0)
    assert client.get(f"/api/v1/raffles/{r['id']}").status_code == 200  # cualquier petición dispara el mantenimiento
    assert db.execute("SELECT status FROM payment_transactions WHERE id=%s", (tid,)).fetchone()["status"] == "EXPIRED"
    assert db.execute("SELECT status FROM tickets WHERE id=%s", (r["tickets"][0],)).fetchone()["status"] == "DISPONIBLE"


def test_schema_is_created_on_empty_database(pg, monkeypatch):
    admin = pg.rsplit("/", 1)[0] + "/postgres"
    name = "vacia_" + uuid.uuid4().hex[:8]
    with psycopg.connect(admin, autocommit=True) as c:
        c.execute(f"CREATE DATABASE {name}")
    dsn = pg.rsplit("/", 1)[0] + "/" + name
    monkeypatch.setattr(appdb, "_schema_ok", False)
    with psycopg.connect(dsn, row_factory=dict_row) as c:
        appdb.ensure_schema(c)
    monkeypatch.setattr(appdb, "_schema_ok", False)
    with psycopg.connect(dsn, row_factory=dict_row) as c:
        appdb.ensure_schema(c)  # idempotente
        n = c.execute("SELECT count(*) n FROM information_schema.tables WHERE table_schema='public'").fetchone()["n"]
    assert n >= 15


def test_jwt_secret_derived_in_production(monkeypatch):
    monkeypatch.delenv("SGRS_JWT_SECRET", raising=False)
    assert security._secret() == "dev-only-change-me"
    monkeypatch.setenv("SGRS_ENV", "production")
    s = security._secret()
    assert s == appdb.secret_fallback() and s != "dev-only-change-me" and len(s) == 64
