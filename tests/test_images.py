import uuid

from fastapi.testclient import TestClient

from app import db as appdb
from app.main import app
from tests.test_auth_uploads import PNG
from tests.test_flow import H

client = TestClient(app)


def payload(**kw):
    base = {"title": "Rifa con portada", "terms_md": "t", "total_numbers": 10, "numbers_per_ticket": 1, "ticket_price": 1000,
            "sales_close_at": "2030-01-01T00:00:00+00:00", "draw_at": "2030-01-02T00:00:00+00:00",
            "draw_method": "INTERNAL_CSPRNG", "prizes": [{"kind": "MAIN", "description": "p"}],
            "description": "Para recaudar fondos del viaje", "contact": "WhatsApp 300 111 2222"}
    return {**base, **kw}


def upload(u, data=PNG):
    return client.put("/api/v1/uploads/image", content=data, headers=H(u))


def test_image_upload_validation(mkuser):
    u = mkuser()
    ok = upload(u)
    assert ok.status_code == 201 and ok.json()["mime"] == "image/png"
    assert upload(u, b"%PDF-1.4 ...").status_code == 415      # los PDF no son imágenes de portada
    assert upload(u, b"<svg onload=alert(1)>").status_code == 415
    assert upload(u, b"").status_code == 422
    assert upload(u, PNG + b"0" * (4 * 1024 * 1024)).status_code == 413


def test_raffle_with_cover_gallery_description_and_contact(db, mkuser):
    u = mkuser()
    ids = [upload(u).json()["image_id"] for _ in range(3)]
    r = client.post("/api/v1/raffles", json=payload(image_ids=ids), headers=H(u))
    assert r.status_code == 201, r.text
    rid = r.json()["id"]
    # borrador: la imagen no es pública, solo del dueño
    assert client.get(f"/api/v1/raffle-images/{ids[0]}").status_code == 404
    assert client.get(f"/api/v1/raffle-images/{ids[0]}", headers=H(u)).status_code == 200
    assert client.post(f"/api/v1/raffles/{rid}/publish", headers=H(u)).status_code == 200
    pub = client.get(f"/api/v1/raffle-images/{ids[0]}")
    assert pub.status_code == 200 and pub.content == PNG and "immutable" in pub.headers["cache-control"]
    assert pub.headers["x-content-type-options"] == "nosniff"
    d = client.get(f"/api/v1/raffles/{rid}", headers=H(u)).json()
    assert d["images"] == ids and d["description"].startswith("Para recaudar") and d["contact"].startswith("WhatsApp")
    mine = client.get("/api/v1/me/raffles", headers=H(u)).json()
    assert next(x for x in mine if x["id"] == rid)["cover_id"] == ids[0]  # portada = primera imagen


def test_cannot_attach_someone_elses_or_reused_image(mkuser):
    a, b = mkuser(), mkuser()
    img = upload(a).json()["image_id"]
    assert client.post("/api/v1/raffles", json=payload(image_ids=[img]), headers=H(b)).status_code == 422
    assert client.post("/api/v1/raffles", json=payload(image_ids=[img]), headers=H(a)).status_code == 201
    assert client.post("/api/v1/raffles", json=payload(image_ids=[img]), headers=H(a)).status_code == 422  # ya usada


def test_max_five_images(mkuser):
    u = mkuser()
    ids = [upload(u).json()["image_id"] for _ in range(6)]
    assert client.post("/api/v1/raffles", json=payload(image_ids=ids), headers=H(u)).status_code == 422


def test_failed_creation_keeps_images_unattached(db, mkuser):
    u = mkuser()
    img = upload(u).json()["image_id"]
    bad = payload(image_ids=[img, str(uuid.uuid4())])  # la segunda no existe: revierte todo
    assert client.post("/api/v1/raffles", json=bad, headers=H(u)).status_code == 422
    assert db.execute("SELECT raffle_id FROM raffle_images WHERE id=%s", (img,)).fetchone()["raffle_id"] is None


def test_find_dsn_handles_custom_prefixes():
    f = appdb.find_dsn
    assert f({}) is None
    assert f({"DATABASE_URL": "postgresql://a"}) == "postgresql://a"
    assert f({"SGRS_DSN": "postgresql://x", "DATABASE_URL": "postgresql://a"}) == "postgresql://x"
    # integración con prefijo personalizado: prefiere el pooler, nunca el directo
    env = {"STORAGE_URL_NON_POOLING": "postgres://direct", "STORAGE_URL": "postgres://pooled", "OTRA": "no-es-url"}
    assert f(env) == "postgres://pooled"
    assert f({"STORAGE_URL_UNPOOLED": "postgres://direct"}) == "postgres://direct"  # mejor eso que nada


def test_missing_database_in_production_is_a_clear_503(monkeypatch):
    monkeypatch.setattr(appdb, "DSN_CONFIGURED", False)
    r = client.post("/api/v1/auth/otp/request", json={"phone": "+573001112233"})
    assert r.status_code == 503 and r.json()["detail"]["code"] == "DB_NOT_CONFIGURED"
