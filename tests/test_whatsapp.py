import hashlib
from tests.conftest import dsn
import hmac
import json
import types
import uuid

import httpx
import pytest
from fastapi.testclient import TestClient

from app import notify, sms, whatsapp
from app.main import app
from scripts.simulate import run as simulate
from tests.test_flow import H, body

client = TestClient(app)
SECRET = "appsecret"


@pytest.fixture
def wa(monkeypatch, db):
    db.execute("DELETE FROM notifications")
    monkeypatch.setenv("SGRS_FLUSH_ON_COMMIT", "0")  # las pruebas de la cola verifican el estado QUEUED
    for k, v in {"WHATSAPP_TOKEN": "tok", "WHATSAPP_PHONE_ID": "123", "WHATSAPP_APP_SECRET": SECRET,
                 "WHATSAPP_VERIFY_TOKEN": "vt", "SGRS_PUBLIC_URL": "https://rifa.example"}.items():
        monkeypatch.setenv(k, v)
    calls, st = [], {}
    st["h"] = lambda req: httpx.Response(200, json={"messages": [{"id": f"wamid.{len(calls)}"}]})

    def handler(req):
        calls.append(req)
        return st["h"](req)
    monkeypatch.setattr(whatsapp, "_client", lambda: httpx.Client(transport=httpx.MockTransport(handler)))
    return types.SimpleNamespace(calls=calls, st=st)


def approved_notification(r, b):
    tid = client.post(f"/api/v1/raffles/{r['id']}/reservations", json=body(r["tickets"][:1]), headers=H(b)).json()["transaction_id"]
    assert client.post(f"/api/v1/transactions/{tid}/approve", headers=H({"id": r["owner"], "role": "USER"})).status_code == 200
    return tid


def row(db, tid):
    return db.execute("SELECT * FROM notifications WHERE ref_id=%s", (tid,)).fetchone()


def test_approved_payment_is_sent_as_template(pg, db, wa, raffle, mkuser):
    r, b = raffle(), mkuser()
    tid = approved_notification(r, b)
    assert row(db, tid)["status"] == "QUEUED"
    assert notify.process_queue(pg) == 1
    n = row(db, tid)
    assert n["status"] == "SENT" and n["provider_msg_id"].startswith("wamid.")
    req = wa.calls[0]
    assert str(req.url) == "https://graph.facebook.com/v21.0/123/messages"
    assert req.headers["authorization"] == "Bearer tok"
    p = json.loads(req.content)
    assert p["messaging_product"] == "whatsapp" and p["type"] == "template" and not p["to"].startswith("+")
    assert p["template"]["name"] == "sgrs_pago_confirmado" and p["template"]["language"]["code"] == "es"
    texts = [x["text"] for x in p["template"]["components"][0]["parameters"]]
    assert texts == ["t", "1", f"https://rifa.example/#/r/{r['id']}"]


def test_retry_with_backoff_then_success(pg, db, wa, raffle, mkuser):
    r, b = raffle(), mkuser()
    tid = approved_notification(r, b)
    wa.st["h"] = lambda req: httpx.Response(503, json={"error": {"code": 2, "message": "temporal"}})
    notify.process_queue(pg)
    n = row(db, tid)
    assert n["status"] == "QUEUED" and n["attempts"] == 1 and "503" in n["last_error"]
    assert notify.process_queue(pg) == 0  # aún no vence el backoff
    wa.st["h"] = lambda req: httpx.Response(200, json={"messages": [{"id": "wamid.ok"}]})
    db.execute("UPDATE notifications SET scheduled_at = now() WHERE ref_id=%s", (tid,))
    assert notify.process_queue(pg) == 1
    assert row(db, tid)["status"] == "SENT"


def test_permanent_error_and_attempt_limit(pg, db, wa, raffle, mkuser):
    r, b = raffle(), mkuser()
    tid = approved_notification(r, b)
    wa.st["h"] = lambda req: httpx.Response(400, json={"error": {"code": 131026, "message": "Message undeliverable"}})
    notify.process_queue(pg)
    n = row(db, tid)
    assert n["status"] == "FAILED" and n["attempts"] == 1 and "131026" in n["last_error"]
    # reintentable pero agotó intentos
    db.execute("UPDATE notifications SET status='QUEUED', attempts=4, scheduled_at=now() WHERE ref_id=%s", (tid,))
    wa.st["h"] = lambda req: httpx.Response(500, json={})
    notify.process_queue(pg)
    assert row(db, tid)["status"] == "FAILED"


def test_network_error_is_retryable(pg, db, wa, raffle, mkuser):
    r, b = raffle(), mkuser()
    tid = approved_notification(r, b)

    def boom(req):
        raise httpx.ConnectError("sin red")
    wa.st["h"] = boom
    notify.process_queue(pg)
    assert row(db, tid)["status"] == "QUEUED" and row(db, tid)["attempts"] == 1


def test_optout_is_skipped(pg, db, wa, raffle, mkuser):
    r, b = raffle(), mkuser()
    db.execute("UPDATE users SET notify_optout=true WHERE id=%s", (b["id"],))
    tid = approved_notification(r, b)
    notify.process_queue(pg)
    assert row(db, tid)["status"] == "SKIPPED" and not wa.calls


def test_unconfigured_keeps_queue(pg, db, wa, monkeypatch, raffle, mkuser):
    r, b = raffle(), mkuser()
    tid = approved_notification(r, b)
    monkeypatch.delenv("WHATSAPP_TOKEN")
    assert notify.process_queue(pg) == 0
    assert row(db, tid)["status"] == "QUEUED"


def test_otp_sent_as_authentication_template(db, wa):
    phone = "+57" + str(uuid.uuid4().int)[:10]
    assert client.post("/api/v1/auth/otp/request", json={"phone": phone}).status_code == 202
    p = json.loads(wa.calls[0].content)
    code = p["template"]["components"][0]["parameters"][0]["text"]
    assert p["template"]["name"] == "sgrs_codigo" and len(code) == 6
    btn = p["template"]["components"][1]
    assert btn["type"] == "button" and btn["sub_type"] == "url" and btn["parameters"][0]["text"] == code
    assert client.post("/api/v1/auth/otp/verify", json={"phone": phone, "code": code}).status_code == 200


def test_otp_delivery_failure_leaves_no_code(db, wa):
    phone = "+57" + str(uuid.uuid4().int)[:10]
    wa.st["h"] = lambda req: httpx.Response(400, json={"error": {"code": 131030, "message": "no permitido"}})
    assert client.post("/api/v1/auth/otp/request", json={"phone": phone}).status_code == 502
    assert db.execute("SELECT count(*) c FROM otp_codes WHERE phone_e164=%s", (phone,)).fetchone()["c"] == 0


def test_otp_not_logged_in_production_without_provider(monkeypatch):
    monkeypatch.setenv("SGRS_ENV", "production")
    monkeypatch.delenv("WHATSAPP_TOKEN", raising=False)
    with pytest.raises(sms.DeliveryError):
        sms.send_otp("+573001112233", "123456")


def sign(raw: bytes) -> dict:
    return {"X-Hub-Signature-256": "sha256=" + hmac.new(SECRET.encode(), raw, hashlib.sha256).hexdigest()}


def test_webhook_handshake(wa):
    ok = client.get("/api/v1/webhooks/whatsapp", params={"hub.mode": "subscribe", "hub.verify_token": "vt", "hub.challenge": "42"})
    assert ok.status_code == 200 and ok.text == "42"
    assert client.get("/api/v1/webhooks/whatsapp", params={"hub.mode": "subscribe", "hub.verify_token": "x", "hub.challenge": "42"}).status_code == 403


def test_webhook_rejects_bad_signature(wa):
    raw = json.dumps({"entry": []}).encode()
    assert client.post("/api/v1/webhooks/whatsapp", content=raw).status_code == 403
    assert client.post("/api/v1/webhooks/whatsapp", content=raw, headers={"X-Hub-Signature-256": "sha256=00"}).status_code == 403


def test_webhook_updates_delivery_and_optout(pg, db, wa, raffle, mkuser):
    r, b = raffle(), mkuser()
    tid = approved_notification(r, b)
    notify.process_queue(pg)
    mid = row(db, tid)["provider_msg_id"]

    def post(value):
        raw = json.dumps({"entry": [{"changes": [{"value": value}]}]}).encode()
        return client.post("/api/v1/webhooks/whatsapp", content=raw, headers=sign(raw))

    assert post({"statuses": [{"id": mid, "status": "delivered"}]}).status_code == 200
    assert row(db, tid)["delivery_status"] == "delivered" and row(db, tid)["status"] == "SENT"
    post({"statuses": [{"id": mid, "status": "failed", "errors": [{"code": 131026, "title": "Undeliverable"}]}]})
    assert row(db, tid)["status"] == "FAILED" and "131026" in row(db, tid)["last_error"]
    phone = db.execute("SELECT phone_e164 FROM users WHERE id=%s", (b["id"],)).fetchone()["phone_e164"]
    post({"messages": [{"from": phone.lstrip("+"), "type": "text", "text": {"body": " BAJA "}}]})
    assert db.execute("SELECT notify_optout FROM users WHERE id=%s", (b["id"],)).fetchone()["notify_optout"] is True


def test_draw_reminder_is_enqueued_once(db, wa, raffle, mkuser):
    r, b = raffle(), mkuser()
    tid = approved_notification(r, b)
    db.execute("UPDATE raffles SET sales_close_at = now() + interval '1 hour', draw_at = now() + interval '5 hours' WHERE id=%s", (r["id"],))
    import psycopg
    from psycopg.rows import dict_row
    with psycopg.connect(dsn(), row_factory=dict_row) as c:
        assert notify.enqueue_draw_reminders(c) == 1
    with psycopg.connect(dsn(), row_factory=dict_row) as c:
        assert notify.enqueue_draw_reminders(c) == 0
    p = db.execute("SELECT payload FROM notifications WHERE type='DRAW_REMINDER'").fetchone()["payload"]["params"]
    assert p[0] == "t" and p[2] == f"https://rifa.example/#/r/{r['id']}"


def test_winner_does_not_also_get_generic_notice(pg, db, wa):
    simulate(pg, buyers=30, seed=5)
    assert db.execute("SELECT count(*) c FROM notifications w JOIN notifications g ON g.user_id=w.user_id"
                      " AND g.raffle_id=w.raffle_id AND w.type='WINNER' AND g.type='DRAW_FINISHED'").fetchone()["c"] == 0
    assert db.execute("SELECT count(*) c FROM notifications WHERE type='WINNER'").fetchone()["c"] >= 1
    notify.process_queue(pg, limit=200)
    assert not db.execute("SELECT 1 FROM notifications WHERE status='QUEUED'").fetchall()
    names = {json.loads(c.content)["template"]["name"] for c in wa.calls}
    assert {"sgrs_pago_confirmado", "sgrs_ganador", "sgrs_sorteo_concluido"} <= names


def test_approval_sends_immediately_without_waiting_for_cron(db, wa, monkeypatch, raffle, mkuser):
    monkeypatch.setenv("SGRS_FLUSH_ON_COMMIT", "1")
    r, b = raffle(), mkuser()
    tid = approved_notification(r, b)
    n = row(db, tid)
    assert n["status"] == "SENT" and n["provider_msg_id"] and len(wa.calls) == 1


def test_immediate_send_failure_keeps_notification_queued(db, wa, monkeypatch, raffle, mkuser):
    monkeypatch.setenv("SGRS_FLUSH_ON_COMMIT", "1")
    wa.st["h"] = lambda req: httpx.Response(503, json={"error": {"code": 2, "message": "temporal"}})
    r, b = raffle(), mkuser()
    tid = approved_notification(r, b)           # la aprobación no falla aunque WhatsApp sí
    n = row(db, tid)
    assert n["status"] == "QUEUED" and n["attempts"] == 1


def test_owner_can_flush_and_see_summary(db, wa, monkeypatch, raffle, mkuser):
    r, b, other = raffle(), mkuser(), mkuser()
    approved_notification(r, b)
    own = {"id": r["owner"], "role": "USER"}
    s = client.get(f"/api/v1/raffles/{r['id']}/notifications", headers=H(own)).json()
    assert s["counts"]["QUEUED"] == 1 and s["whatsapp"] is True
    monkeypatch.setenv("SGRS_FLUSH_ON_COMMIT", "1")
    f = client.post(f"/api/v1/raffles/{r['id']}/notifications/flush", headers=H(own)).json()
    assert f == {"processed": 1, "queued": 0}
    assert client.get(f"/api/v1/raffles/{r['id']}/notifications", headers=H(other)).status_code == 403
