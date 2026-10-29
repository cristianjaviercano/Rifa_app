import uuid

from fastapi.testclient import TestClient

from app.main import app
from tests.test_flow import H, body

client = TestClient(app)


def mk_tx(r, b, n=1, ref=None):
    res = client.post(f"/api/v1/raffles/{r['id']}/reservations", json=body(r["tickets"][:n], ref=ref), headers=H(b))
    assert res.status_code == 201, res.text
    return res.json()["transaction_id"]


def test_public_list_and_detail_hide_private_data(db, raffle, mkuser):
    r, b = raffle(), mkuser()
    rows = client.get("/api/v1/raffles").json()
    mine = next(x for x in rows if x["id"] == str(r["id"]))
    assert mine["tickets_total"] == 10 and mine["tickets_sold"] == 0
    d = client.get(f"/api/v1/raffles/{r['id']}")
    assert d.status_code == 200 and "owner_id" not in d.json() and d.json()["is_owner"] is False
    own = client.get(f"/api/v1/raffles/{r['id']}", headers=H({"id": r["owner"], "role": "USER"})).json()
    assert own["is_owner"] is True


def test_draft_is_not_public(db, mkuser):
    u = mkuser()
    now = "2030-01-01T00:00:00+00:00"
    rid = client.post("/api/v1/raffles", headers=H(u), json={
        "title": "x", "terms_md": "x", "total_numbers": 10, "numbers_per_ticket": 1, "ticket_price": 1000,
        "sales_close_at": now, "draw_at": "2030-01-02T00:00:00+00:00", "draw_method": "INTERNAL_CSPRNG",
        "prizes": [{"kind": "MAIN", "description": "p"}], "payment_accounts": {"Nequi": "300"}}).json()["id"]
    assert client.get(f"/api/v1/raffles/{rid}").status_code == 404
    assert client.get(f"/api/v1/raffles/{rid}", headers=H(u)).json()["payment_accounts"] == {"Nequi": "300"}


def test_tickets_mark_mine(raffle, mkuser):
    r, b, o = raffle(), mkuser(), mkuser()
    mk_tx(r, b)
    mine = [t for t in client.get(f"/api/v1/raffles/{r['id']}/tickets", headers=H(b)).json() if t["mine"]]
    assert len(mine) == 1
    assert not any(t["mine"] for t in client.get(f"/api/v1/raffles/{r['id']}/tickets", headers=H(o)).json())


def test_my_transactions_and_review_queue_access(raffle, mkuser):
    r, b, other = raffle(), mkuser(), mkuser()
    tid = mk_tx(r, b, n=2)
    mine = client.get("/api/v1/me/transactions", headers=H(b)).json()
    assert mine[0]["id"] == tid and len(mine[0]["tickets"]) == 2 and "buyer_phone" not in mine[0]
    owner = {"id": r["owner"], "role": "USER"}
    q = client.get(f"/api/v1/raffles/{r['id']}/transactions?status=PENDING", headers=H(owner)).json()
    assert q[0]["buyer_phone"].startswith("+57")
    assert client.get(f"/api/v1/raffles/{r['id']}/transactions", headers=H(other)).status_code == 403
    assert client.get(f"/api/v1/raffles/{r['id']}/transactions").status_code in (401, 403)


def test_static_app_and_security_headers():
    r = client.get("/")
    assert r.status_code == 200 and "Rifa" in r.text
    assert "default-src 'self'" in r.headers["content-security-policy"]
    assert r.headers["cache-control"] == "no-cache"
    assert client.get("/sw.js").status_code == 200
    assert client.get("/api/v1/raffles").status_code == 200  # la API no queda tapada por el mount estático
