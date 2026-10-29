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
    assert client.get("/api/v1/raffles").status_code == 404  # ya no existe un listado público
    d = client.get(f"/api/v1/raffles/{r['id']}")
    assert d.json()["tickets_total"] == 10 and d.json()["tickets_sold"] == 0
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
    assert client.get("/api/v1/auth/config").status_code == 200  # la API no queda tapada por el mount estático


def test_board_is_compact_and_conditional(raffle, mkuser):
    r, b = raffle(n=10), mkuser()
    res = client.post(f"/api/v1/raffles/{r['id']}/reservations", headers=H(b),
                      json={"serials": [3, 4], "platform": "NEQUI", "external_ref": "X1", "amount_declared": 20000})
    assert res.status_code == 201, res.text
    g = client.get(f"/api/v1/raffles/{r['id']}/board", headers=H(b))
    j = g.json()
    assert j["states"] == "DDCCDDDDDD" and j["mine"] == [3, 4] and j["npt"] == 1 and j["total"] == 10
    assert len(g.content) < 200
    anon = client.get(f"/api/v1/raffles/{r['id']}/board").json()
    assert anon["mine"] == [] and anon["states"] == j["states"]
    etag = g.headers["etag"]
    assert client.get(f"/api/v1/raffles/{r['id']}/board", headers={**H(b), "If-None-Match": etag}).status_code == 304
    # un cambio de estado cambia el ETag
    tid = res.json()["transaction_id"]
    client.post(f"/api/v1/transactions/{tid}/approve", headers=H({"id": r["owner"], "role": "USER"}))
    g2 = client.get(f"/api/v1/raffles/{r['id']}/board", headers={**H(b), "If-None-Match": etag})
    assert g2.status_code == 200 and g2.json()["states"] == "DDPPDDDDDD"


def test_reservation_by_serial_conflicts_and_validation(raffle, mkuser):
    r, a, b = raffle(n=10), mkuser(), mkuser()
    url = f"/api/v1/raffles/{r['id']}/reservations"
    mk = lambda s, ref: {"serials": s, "platform": "NEQUI", "external_ref": ref, "amount_declared": 10000 * len(s)}
    assert client.post(url, json=mk([5], "A1"), headers=H(a)).status_code == 201
    clash = client.post(url, json=mk([5, 6], "B1"), headers=H(b))
    assert clash.status_code == 409 and clash.json()["detail"]["conflicts"] == [5]   # serial, no UUID
    assert client.post(url, json=mk([99], "B2"), headers=H(b)).status_code == 422     # no existe
    both = {**mk([7], "B3"), "ticket_ids": [str(r["tickets"][7])]}
    assert client.post(url, json=both, headers=H(b)).status_code == 422               # uno u otro, no ambos
    assert client.post(url, json={"platform": "NEQUI", "external_ref": "B4", "amount_declared": 0}, headers=H(b)).status_code == 422
