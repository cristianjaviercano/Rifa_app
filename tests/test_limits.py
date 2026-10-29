import uuid
from concurrent.futures import ThreadPoolExecutor

from tests.conftest import dsn
import pytest
from fastapi.testclient import TestClient

from app import db as appdb
from app.main import app
from tests.test_flow import H
from tests.test_images import payload

client = TestClient(app)


def phone():
    return "+57" + str(uuid.uuid4().int)[:10]


@pytest.fixture
def limits(monkeypatch, db):
    monkeypatch.setenv("SGRS_RATE_LIMITS", "on")
    db.execute("DELETE FROM rate_limits")


def test_otp_requests_limited_per_ip(limits, monkeypatch):
    monkeypatch.setenv("SGRS_OTP_IP_LIMIT", "10")
    codes = [client.post("/api/v1/auth/otp/request", json={"phone": phone()}).status_code for _ in range(11)]
    assert codes[:10] == [202] * 10 and codes[10] == 429


def test_otp_requests_limited_per_phone(limits, db):
    p = phone()
    assert client.post("/api/v1/auth/otp/request", json={"phone": p}).status_code == 202
    db.execute("UPDATE otp_codes SET created_at = now() - interval '2 minutes' WHERE phone_e164=%s", (p,))  # pasa el de 60 s
    for _ in range(4):
        r = client.post("/api/v1/auth/otp/request", json={"phone": p})
        db.execute("UPDATE otp_codes SET created_at = now() - interval '2 minutes' WHERE phone_e164=%s", (p,))
    assert r.status_code == 202
    assert client.post("/api/v1/auth/otp/request", json={"phone": p}).status_code == 429  # 6.º en una hora


def test_wrong_beta_key_locks_out_even_the_right_key(limits, db, monkeypatch):
    monkeypatch.setenv("SGRS_BETA_KEY", "clave-correcta-123")
    bad = [client.post("/api/v1/auth/otp/request", json={"phone": phone(), "invite": "mala"}).status_code for _ in range(10)]
    assert bad == [403] * 10
    assert db.execute("SELECT sum(hits) s FROM rate_limits WHERE bucket='invite_fail'").fetchone()["s"] == 10  # los fallos persisten
    ok = client.post("/api/v1/auth/otp/request", json={"phone": phone(), "invite": "clave-correcta-123"})
    assert ok.status_code == 429 and ok.json()["detail"]["code"] == "RATE_LIMITED"


def test_verify_attempts_limited_per_ip(limits):
    codes = [client.post("/api/v1/auth/otp/verify", json={"phone": phone(), "code": "000000"}).status_code for _ in range(31)]
    assert codes[:30] == [401] * 30 and codes[30] == 429


def test_raffle_creation_daily_cap(limits, mkuser, monkeypatch):
    monkeypatch.setenv("SGRS_MAX_RAFFLES_PER_DAY", "2")
    u = mkuser()
    codes = [client.post("/api/v1/raffles", json=payload(), headers=H(u)).status_code for _ in range(3)]
    assert codes == [201, 201, 429]
    assert client.post("/api/v1/raffles", json=payload(), headers=H(mkuser())).status_code == 201  # otro usuario no se afecta


def test_limits_off_by_default_in_tests(db):
    db.execute("DELETE FROM rate_limits")
    for _ in range(15):
        assert client.post("/api/v1/auth/otp/request", json={"phone": phone()}).status_code == 202
    assert db.execute("SELECT count(*) c FROM rate_limits").fetchone()["c"] == 0


def test_old_windows_are_purged(db):
    db.execute("INSERT INTO rate_limits VALUES ('x','y', now() - interval '3 days', 5), ('x','z', now(), 1)")
    import psycopg
    from psycopg.rows import dict_row
    with psycopg.connect(dsn(), row_factory=dict_row) as c:
        appdb.lazy_maintenance(c, force=True)
    keys = {r["key"] for r in db.execute("SELECT key FROM rate_limits WHERE bucket='x'")}
    assert keys == {"z"}


def test_connection_pool_serves_concurrent_requests(monkeypatch):
    monkeypatch.setenv("SGRS_POOL", "1")
    monkeypatch.setenv("SGRS_POOL_MAX", "3")
    try:
        with ThreadPoolExecutor(12) as ex:
            codes = list(ex.map(lambda _: client.get("/api/v1/resolve/R-AAAAAAA").status_code, range(40)))
        assert set(codes) == {404}           # CODE_NOT_FOUND: la consulta corrió
        assert appdb.DSN in appdb._pools
        assert client.get("/api/v1/auth/config").status_code == 200
        # una petición que falla (rollback) no deja la conexión en mal estado
        assert client.post("/api/v1/auth/otp/verify", json={"phone": "x", "code": "12"}).status_code == 422
        assert client.get("/api/v1/resolve/R-AAAAAAA").status_code == 404
    finally:
        p = appdb._pools.pop(appdb.DSN, None)
        if p:
            p.close()
