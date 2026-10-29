"""Webhook de WhatsApp: estados de entrega (sent/delivered/read/failed) y bajas voluntarias."""
import hashlib
import hmac
import json
import os
import re

from fastapi import APIRouter, Depends, Request
from fastapi.responses import PlainTextResponse

from .db import get_conn
from .raffles import err

router = APIRouter(prefix="/api/v1/webhooks")
OPTOUT = re.compile(r"^\s*(baja|stop|parar|cancelar|no m[aá]s)\s*$", re.I)


@router.get("/whatsapp")
def verify(request: Request):
    """Handshake de suscripción de Meta."""
    q = request.query_params
    token = os.environ.get("WHATSAPP_VERIFY_TOKEN")
    if token and q.get("hub.mode") == "subscribe" and hmac.compare_digest(q.get("hub.verify_token", ""), token):
        return PlainTextResponse(q.get("hub.challenge", ""))
    raise err(403, "FORBIDDEN")


@router.post("/whatsapp")
async def receive(request: Request, conn=Depends(get_conn)):
    secret = os.environ.get("WHATSAPP_APP_SECRET")
    raw = await request.body()
    sig = request.headers.get("x-hub-signature-256", "")
    expected = "sha256=" + hmac.new((secret or "").encode(), raw, hashlib.sha256).hexdigest()
    if not secret or not hmac.compare_digest(sig, expected):  # sin firma válida no se procesa nada
        raise err(403, "BAD_SIGNATURE")
    try:
        data = json.loads(raw)
    except ValueError:
        raise err(400, "BAD_JSON") from None
    for entry in data.get("entry", []):
        for ch in entry.get("changes", []):
            v = ch.get("value", {})
            for st in v.get("statuses", []):
                error = (st.get("errors") or [{}])[0]
                conn.execute(
                    "UPDATE notifications SET delivery_status=%s,"
                    " status = CASE WHEN %s = 'failed' THEN 'FAILED' ELSE status END,"
                    " last_error = CASE WHEN %s = 'failed' THEN left(%s, 300) ELSE last_error END"
                    " WHERE provider_msg_id=%s",
                    (st.get("status"), st.get("status"), st.get("status"),
                     f"{error.get('code')}: {error.get('title', '')}", st.get("id")))
            for m in v.get("messages", []):
                if m.get("type") == "text" and OPTOUT.match(m.get("text", {}).get("body", "")):
                    conn.execute("UPDATE users SET notify_optout=true WHERE phone_e164=%s", ("+" + m.get("from", ""),))
    return {}
