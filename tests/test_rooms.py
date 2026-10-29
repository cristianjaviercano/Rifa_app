import uuid

from fastapi.testclient import TestClient

from app import codes
from app.main import app
from tests.test_flow import H

client = TestClient(app)


def make(u, title="Rifa", visibility="PORTFOLIO", publish=True):
    r = client.post("/api/v1/raffles", headers=H(u), json={
        "title": title, "terms_md": "x", "total_numbers": 10, "numbers_per_ticket": 1, "ticket_price": 1000,
        "sales_close_at": "2031-01-01T00:00:00+00:00", "draw_at": "2031-01-02T00:00:00+00:00", "draw_method": "INTERNAL_CSPRNG",
        "prizes": [{"kind": "MAIN", "description": "p"}], "visibility": visibility})
    assert r.status_code == 201, r.text
    rid = r.json()["id"]
    if publish:
        assert client.post(f"/api/v1/raffles/{rid}/publish", headers=H(u)).status_code == 200
    return rid


def room(u):
    return client.get("/api/v1/me/room", headers=H(u)).json()


def test_codes_format_and_normalization():
    assert codes.CODE_RE.match("S" + "ABCDEFG") and not codes.CODE_RE.match("S0OIl1xx")
    assert codes.normalize(" s-ab cd.efg ") == "SABCDEFG" and codes.pretty("SABCDEFG") == "S-ABCDEFG"


def test_each_user_has_private_room_with_unique_code(mkuser):
    a, b = mkuser(), mkuser()
    ra, rb = room(a), room(b)
    assert codes.CODE_RE.match(ra["room_code"]) and ra["room_code"][0] == "S" and ra["room_code"] != rb["room_code"]
    assert room(a)["room_code"] == ra["room_code"]  # estable


def test_room_shows_only_that_owners_portfolio_raffles(mkuser):
    a, b, visitor = mkuser(), mkuser(), mkuser()
    pa1, pa2 = make(a, "A uno"), make(a, "A dos")
    make(a, "A solo enlace", visibility="LINK")
    make(a, "A borrador", publish=False)
    make(b, "B ajena")
    code = room(a)["room_code"]
    titles = {x["title"] for x in client.get(f"/api/v1/rooms/{code}").json()["raffles"]}
    assert titles == {"A uno", "A dos"}  # ni la de solo enlace, ni el borrador, ni la de otro organizador
    body = client.get(f"/api/v1/rooms/{code}").json()
    assert all("owner_id" not in x for x in body["raffles"]) and body["is_owner"] is False
    assert client.get(f"/api/v1/rooms/{code.lower()}").status_code == 200  # insensible a mayúsculas
    assert client.get("/api/v1/rooms/SAAAAAAA").status_code == 404


def test_no_public_listing_for_new_users():
    assert client.get("/api/v1/raffles").status_code == 404


def test_resolve_codes(mkuser):
    a = mkuser()
    rid = make(a, "Pública")
    draft = make(a, "Borrador", publish=False)
    sc = client.get(f"/api/v1/raffles/{rid}", headers=H(a)).json()["share_code"]
    rc = room(a)["room_code"]
    assert sc[0] == "R"
    assert client.get(f"/api/v1/resolve/{sc}").json() == {"type": "raffle", "id": rid}
    assert client.get(f"/api/v1/resolve/{codes.pretty(sc).lower()}").json()["id"] == rid
    assert client.get(f"/api/v1/resolve/{rc}").json() == {"type": "room", "code": rc}
    # el código de un borrador no abre nada
    dcode = next(x["share_code"] for x in client.get("/api/v1/me/room", headers=H(a)).json()["raffles"] if x["id"] == draft)
    assert client.get(f"/api/v1/resolve/{dcode}").status_code == 404
    for bad in ["", "hola", "R0000000", "S1111111", "RZZZZZZZ"]:
        assert client.get(f"/api/v1/resolve/{bad or 'x'}").status_code == 404


def test_visibility_toggle_is_owner_only_and_effective(mkuser):
    a, other = mkuser(), mkuser()
    rid = make(a, "Cambiante")
    code = room(a)["room_code"]
    assert any(x["id"] == rid for x in client.get(f"/api/v1/rooms/{code}").json()["raffles"])
    assert client.post(f"/api/v1/raffles/{rid}/visibility", json={"visibility": "LINK"}, headers=H(other)).status_code == 403
    assert client.post(f"/api/v1/raffles/{rid}/visibility", json={"visibility": "NADA"}, headers=H(a)).status_code == 422
    assert client.post(f"/api/v1/raffles/{rid}/visibility", json={"visibility": "LINK"}, headers=H(a)).status_code == 200
    assert not any(x["id"] == rid for x in client.get(f"/api/v1/rooms/{code}").json()["raffles"])
    assert client.get(f"/api/v1/raffles/{rid}").status_code == 200  # el enlace directo sigue funcionando


def test_link_only_raffle_does_not_reveal_the_room(mkuser):
    a, v = mkuser(), mkuser()
    solo, port = make(a, "Solo", "LINK"), make(a, "Portafolio")
    d = client.get(f"/api/v1/raffles/{solo}", headers=H(v)).json()
    assert d["room_code"] is None and d["room_name"] is None
    p = client.get(f"/api/v1/raffles/{port}", headers=H(v)).json()
    assert p["room_code"] == room(a)["room_code"] and p["owner_name"]
    assert client.get("/api/v1/me/rooms", headers=H(v)).json()[0]["room_code"] == room(a)["room_code"]  # solo se recordó la sala por la rifa de portafolio


def test_link_only_visit_does_not_create_membership(mkuser):
    a, v = mkuser(), mkuser()
    solo = make(a, "Solo", "LINK")
    client.get(f"/api/v1/raffles/{solo}", headers=H(v))
    assert client.get("/api/v1/me/rooms", headers=H(v)).json() == []


def test_entering_a_room_remembers_it_and_owner_is_not_a_member_of_self(mkuser):
    a, v = mkuser(), mkuser()
    make(a, "Una")
    code = room(a)["room_code"]
    client.get(f"/api/v1/rooms/{code}", headers=H(v))
    mine = client.get("/api/v1/me/rooms", headers=H(v)).json()
    assert len(mine) == 1 and mine[0]["open_raffles"] == 1
    client.get(f"/api/v1/rooms/{code}", headers=H(a))
    assert client.get("/api/v1/me/rooms", headers=H(a)).json() == []
    assert client.get(f"/api/v1/rooms/{code}", headers=H(a)).json()["is_owner"] is True


def test_rename_room(mkuser):
    a = mkuser()
    assert client.post("/api/v1/me/room", json={"room_name": ""}, headers=H(a)).status_code == 422
    assert client.post("/api/v1/me/room", json={"room_name": "Rifas de Carolina"}, headers=H(a)).status_code == 200
    r = room(a)
    assert r["room_name"] == "Rifas de Carolina" and r["has_custom_name"] is True
    assert client.get(f"/api/v1/rooms/{r['room_code']}").json()["room_name"] == "Rifas de Carolina"


def test_room_share_page_and_image(mkuser):
    a = mkuser()
    make(a, "Una"); make(a, "Dos")
    client.post("/api/v1/me/room", json={"room_name": '<b>Sala</b> "x"'}, headers=H(a))
    code = room(a)["room_code"]
    p = client.get(f"/s/{code}")
    assert p.status_code == 200 and "2 rifas activas" in p.text and "<b>Sala</b>" not in p.text and "&lt;b&gt;" in p.text
    assert f'content="0;url=/#/s/{code}"' in p.text and f"/s/{code}/og.png" in p.text
    img = client.get(f"/s/{code}/og.png")
    assert img.status_code == 200 and img.headers["content-type"] == "image/png"
    assert client.get("/s/SAAAAAAA").status_code == 200 and client.get("/s/SAAAAAAA/og.png").status_code == 200  # tarjeta genérica


def test_new_raffle_gets_share_code_and_owner_room(db, mkuser):
    a = mkuser()
    rid = make(a, "Nueva", publish=False)
    row = db.execute("SELECT r.share_code, u.room_code FROM raffles r JOIN users u ON u.id=r.owner_id WHERE r.id=%s", (rid,)).fetchone()
    assert row["share_code"][0] == "R" and row["room_code"][0] == "S"
