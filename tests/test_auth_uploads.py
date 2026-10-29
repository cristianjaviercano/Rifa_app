import uuid

import pytest
from fastapi.testclient import TestClient

from app import sms
from app.main import app
from app.security import issue_token
from tests.test_flow import H, body

client = TestClient(app)
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


def last_code():
    import re
    return re.search(r"\d{6}", sms.outbox[-1][1]).group()


def phone():
    return "+57" + str(uuid.uuid4().int)[:10]


def login(p, code=None):
    client.post("/api/v1/auth/otp/request", json={"phone": p})
    code = code or last_code()
    return client.post("/api/v1/auth/otp/verify", json={"phone": p, "code": code, "name": "Ana"})


def test_otp_login_ok(db):
    p = phone()
    r = login(p)
    assert r.status_code == 200, r.text
    row = db.execute("SELECT phone_verified_at FROM users WHERE phone_e164=%s", (p,)).fetchone()
    assert row["phone_verified_at"] is not None
    assert db.execute("SELECT code_hash FROM otp_codes WHERE phone_e164=%s", (p,)).fetchone()["code_hash"] != sms.outbox[-1][1]
    # el token sirve
    assert client.put("/api/v1/uploads/proof", content=PNG,
                      headers={"Authorization": f"Bearer {r.json()['access_token']}"}).status_code == 201


def test_otp_wrong_code_locks_and_single_use(db):
    p = phone()
    client.post("/api/v1/auth/otp/request", json={"phone": p})
    good = last_code()
    bad = "000000" if good != "000000" else "111111"
    codes = [client.post("/api/v1/auth/otp/verify", json={"phone": p, "code": bad}).status_code for _ in range(5)]
    assert codes == [401] * 5
    assert client.post("/api/v1/auth/otp/verify", json={"phone": p, "code": good}).status_code == 429  # bloqueado


def test_otp_reuse_and_resend_limit(db):
    p = phone()
    assert login(p).status_code == 200
    code = last_code()
    assert client.post("/api/v1/auth/otp/verify", json={"phone": p, "code": code}).status_code == 401
    assert client.post("/api/v1/auth/otp/request", json={"phone": p}).status_code == 429


def test_otp_expired_and_bad_phone(db):
    p = phone()
    client.post("/api/v1/auth/otp/request", json={"phone": p})
    code = last_code()
    db.execute("UPDATE otp_codes SET expires_at = now() - interval '1 second' WHERE phone_e164=%s", (p,))
    assert client.post("/api/v1/auth/otp/verify", json={"phone": p, "code": code}).status_code == 401
    assert client.post("/api/v1/auth/otp/request", json={"phone": "3001234567"}).status_code == 422


def up(u, data=PNG):
    return client.put("/api/v1/uploads/proof", content=data, headers=H(u))


def test_upload_validation(mkuser):
    u = mkuser()
    assert up(u).status_code == 201
    assert up(u, b"<script>alert(1)</script>").status_code == 415
    assert up(u, PNG + b"0" * (5 * 1024 * 1024)).status_code == 413
    assert up(u, b"").status_code in (413, 422)


def test_proof_access_control_and_duplicate(db, raffle, mkuser):
    r, b, other = raffle(), mkuser(), mkuser()
    pid = up(b).json()["proof_id"]
    url = f"/api/v1/raffles/{r['id']}/reservations"
    assert client.get(f"/api/v1/proofs/{pid}", headers=H(other)).status_code == 403
    assert client.get(f"/api/v1/proofs/{pid}", headers=H({"id": r["owner"], "role": "USER"})).status_code == 403  # aún sin reserva
    bd = body(r["tickets"][:1]); bd.pop("external_ref"); bd["proof_id"] = pid
    assert client.post(url, json=bd, headers=H(b)).status_code == 201
    g = client.get(f"/api/v1/proofs/{pid}", headers=H({"id": r["owner"], "role": "USER"}))
    assert g.status_code == 200 and g.content == PNG and g.headers["x-content-type-options"] == "nosniff"
    # mismo archivo (otro upload, mismo hash) no respalda un segundo pago
    pid2 = up(mkuser_b := other).json()["proof_id"]
    bd2 = body(r["tickets"][1:2]); bd2.pop("external_ref"); bd2["proof_id"] = pid2
    assert client.post(url, json=bd2, headers=H(other)).status_code == 409
    # no se puede usar el comprobante de otro usuario
    bd3 = body(r["tickets"][2:3]); bd3.pop("external_ref"); bd3["proof_id"] = pid
    assert client.post(url, json=bd3, headers=H(other)).status_code == 422
