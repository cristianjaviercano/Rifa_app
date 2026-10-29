import io
import uuid

from fastapi.testclient import TestClient
from PIL import Image

from app.main import app
from tests.test_flow import H

client = TestClient(app)


def test_share_page_has_open_graph_and_redirect(db, raffle, monkeypatch):
    monkeypatch.setenv("SGRS_PUBLIC_URL", "https://rifa.example")
    r = raffle()
    db.execute("UPDATE raffles SET title='Rifa Moto 2026' WHERE id=%s", (r["id"],))
    p = client.get(f"/r/{r['id']}")
    assert p.status_code == 200 and "text/html" in p.headers["content-type"]
    h = p.text
    assert 'property="og:title" content="Rifa Moto 2026 · Rifa App"' in h
    assert "Boleta a $10.000" in h and "0% vendido" in h
    assert f'property="og:image" content="https://rifa.example/r/{r["id"]}/og.png"' in h
    assert f'property="og:url" content="https://rifa.example/r/{r["id"]}"' in h
    assert 'name="twitter:card" content="summary_large_image"' in h
    assert f'http-equiv="refresh" content="0;url=/#/r/{r["id"]}"' in h


def test_share_page_escapes_title(db, raffle):
    r = raffle()
    db.execute("UPDATE raffles SET title=%s WHERE id=%s", ('<script>alert(1)</script>"><img src=x>', r["id"]))
    h = client.get(f"/r/{r['id']}").text
    assert "<script>alert" not in h and "<img src=x>" not in h and "&lt;script&gt;" in h


def test_draft_and_unknown_raffle_get_generic_card(db, mkuser):
    u = mkuser()
    rid = client.post("/api/v1/raffles", headers=H(u), json={
        "title": "Secreta", "terms_md": "x", "total_numbers": 10, "numbers_per_ticket": 1, "ticket_price": 1000,
        "sales_close_at": "2030-01-01T00:00:00+00:00", "draw_at": "2030-01-02T00:00:00+00:00", "draw_method": "INTERNAL_CSPRNG",
        "prizes": [{"kind": "MAIN", "description": "p"}]}).json()["id"]
    for target in (rid, str(uuid.uuid4())):
        h = client.get(f"/r/{target}")
        assert h.status_code == 200 and "Secreta" not in h.text and 'og:title" content="Rifa App"' in h.text
        assert client.get(f"/r/{target}/og.png").status_code == 200


def test_og_image_is_png_1200x630(raffle):
    r = raffle()
    img = client.get(f"/r/{r['id']}/og.png")
    assert img.status_code == 200 and img.headers["content-type"] == "image/png"
    assert Image.open(io.BytesIO(img.content)).size == (1200, 630)


def test_new_raffle_records_referrer(db, raffle, mkuser):
    src, u = raffle(), mkuser()
    body = {"title": "Hija", "terms_md": "x", "total_numbers": 10, "numbers_per_ticket": 1, "ticket_price": 1000,
            "sales_close_at": "2030-01-01T00:00:00+00:00", "draw_at": "2030-01-02T00:00:00+00:00", "draw_method": "INTERNAL_CSPRNG",
            "prizes": [{"kind": "MAIN", "description": "p"}]}
    ok = client.post("/api/v1/raffles", headers=H(u), json={**body, "referrer_raffle_id": str(src["id"])}).json()["id"]
    assert str(db.execute("SELECT referrer_raffle_id FROM raffles WHERE id=%s", (ok,)).fetchone()["referrer_raffle_id"]) == str(src["id"])
    bad = client.post("/api/v1/raffles", headers=H(u), json={**body, "referrer_raffle_id": str(uuid.uuid4())})
    assert bad.status_code == 201  # una referencia inexistente se ignora, no rompe la creación
    assert db.execute("SELECT referrer_raffle_id FROM raffles WHERE id=%s", (bad.json()["id"],)).fetchone()["referrer_raffle_id"] is None
