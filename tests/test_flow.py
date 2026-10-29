import uuid
from concurrent.futures import ThreadPoolExecutor

from tests.conftest import dsn
import psycopg
from fastapi.testclient import TestClient

from app.main import app, expire_holds
from app.security import issue_token

client = TestClient(app)


def H(u, key=None):
    return {"Authorization": f"Bearer {issue_token(u['id'], str(u['role']))}",
            "Idempotency-Key": key or str(uuid.uuid4())}


def body(tickets, ref=None, price=10000):
    return {"ticket_ids": [str(t) for t in tickets], "platform": "NEQUI",
            "external_ref": ref or uuid.uuid4().hex[:10], "amount_declared": price * len(tickets)}


def test_reserve_approve_flow(db, raffle, mkuser):
    r, b = raffle(), mkuser()
    res = client.post(f"/api/v1/raffles/{r['id']}/reservations", json=body(r["tickets"][:2]), headers=H(b))
    assert res.status_code == 201, res.text
    assert {t["status"] for t in res.json()["tickets"]} == {"CONGELADO"}
    tid = res.json()["transaction_id"]
    owner = {"id": r["owner"], "role": "USER"}
    ap = client.post(f"/api/v1/transactions/{tid}/approve", headers=H(owner))
    assert ap.status_code == 200 and {t["status"] for t in ap.json()["tickets"]} == {"PAGADO"}
    assert client.post(f"/api/v1/transactions/{tid}/approve", headers=H(owner)).status_code == 409
    assert db.execute("SELECT count(*) c FROM notifications").fetchone()["c"] >= 1


def test_only_raffle_admin_can_approve(raffle, mkuser):
    r, b = raffle(), mkuser()
    tid = client.post(f"/api/v1/raffles/{r['id']}/reservations", json=body(r["tickets"][:1]), headers=H(b)).json()["transaction_id"]
    assert client.post(f"/api/v1/transactions/{tid}/approve", headers=H(b)).status_code == 403


def test_reject_releases(db, raffle, mkuser):
    r, b = raffle(), mkuser()
    tid = client.post(f"/api/v1/raffles/{r['id']}/reservations", json=body(r["tickets"][:1]), headers=H(b)).json()["transaction_id"]
    rj = client.post(f"/api/v1/transactions/{tid}/reject", json={"reason": "monto no coincide"},
                     headers=H({"id": r["owner"], "role": "USER"}))
    assert rj.status_code == 200
    assert db.execute("SELECT status FROM tickets WHERE id=%s", (r["tickets"][0],)).fetchone()["status"] == "DISPONIBLE"


def test_validations(raffle, mkuser):
    r, b = raffle(), mkuser()
    url = f"/api/v1/raffles/{r['id']}/reservations"
    bad = body(r["tickets"][:1]); bad["amount_declared"] = 1
    assert client.post(url, json=bad, headers=H(b)).status_code == 422
    ok = body(r["tickets"][:1], ref="DUP1")
    assert client.post(url, json=ok, headers=H(b)).status_code == 201
    other = body(r["tickets"][1:2], ref="DUP1")
    assert client.post(url, json=other, headers=H(b)).status_code == 409


def test_idempotency(raffle, mkuser):
    r, b = raffle(), mkuser()
    h, bd = H(b, "same-key"), body(r["tickets"][:1])
    url = f"/api/v1/raffles/{r['id']}/reservations"
    a, c = client.post(url, json=bd, headers=h), client.post(url, json=bd, headers=h)
    assert a.status_code == 201 == c.status_code and a.json()["transaction_id"] == c.json()["transaction_id"]


def test_sales_closed(db, raffle, mkuser):
    r, b = raffle(), mkuser()
    db.execute("UPDATE raffles SET sales_close_at = now() - interval '1 second', draw_at = now() + interval '1 day' WHERE id=%s", (r["id"],))
    assert client.post(f"/api/v1/raffles/{r['id']}/reservations", json=body(r["tickets"][:1]), headers=H(b)).status_code == 423


def test_expiry(db, raffle, mkuser):
    r, b = raffle(), mkuser()
    tid = client.post(f"/api/v1/raffles/{r['id']}/reservations", json=body(r["tickets"][:1]), headers=H(b)).json()["transaction_id"]
    db.execute("UPDATE payment_transactions SET expires_at = now() - interval '1 minute' WHERE id=%s", (tid,))
    assert client.post(f"/api/v1/transactions/{tid}/approve", headers=H({"id": r["owner"], "role": "USER"})).status_code == 410
    with psycopg.connect(dsn()) as c:  # misma BD
        from psycopg.rows import dict_row
        c.row_factory = dict_row
        assert expire_holds(c) == 1
    assert db.execute("SELECT status FROM tickets WHERE id=%s", (r["tickets"][0],)).fetchone()["status"] == "DISPONIBLE"


def test_concurrent_reservation_single_winner(db, raffle, mkuser):
    """30 compradores compiten por la misma boleta: exactamente 1 obtiene 201."""
    r = raffle()
    users = [mkuser() for _ in range(30)]
    url = f"/api/v1/raffles/{r['id']}/reservations"

    def go(u):
        return TestClient(app).post(url, json=body(r["tickets"][:1]), headers=H(u)).status_code

    with ThreadPoolExecutor(30) as ex:
        codes = list(ex.map(go, users))
    assert codes.count(201) == 1 and codes.count(409) == 29, codes
    assert db.execute("SELECT count(*) c FROM tickets WHERE raffle_id=%s AND status='CONGELADO'", (r["id"],)).fetchone()["c"] == 1


def test_audit_append_only(db):
    try:
        db.execute("UPDATE audit_log SET action='x'")
        assert False
    except psycopg.errors.RaiseException:
        pass
