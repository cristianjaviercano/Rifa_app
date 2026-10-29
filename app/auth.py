import hashlib
import hmac
import os
import re
import secrets
from typing import Optional

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from . import sms
from . import legal, ratelimit
from .audit import write_audit
from .db import get_conn
from .raffles import err
from .security import SECRET, TOKEN_TTL, issue_token

router = APIRouter(prefix="/api/v1/auth")
PHONE = re.compile(r"^\+[1-9]\d{7,14}$")
TTL_SECONDS, MAX_ATTEMPTS, RESEND_SECONDS = 300, 5, 60


def _hash(phone: str, code: str) -> str:
    return hmac.new(SECRET.encode(), f"{phone}:{code}".encode(), hashlib.sha256).hexdigest()


class OtpRequest(BaseModel):
    phone: str
    invite: Optional[str] = None


class OtpVerify(BaseModel):
    phone: str
    code: str = Field(pattern=r"^\d{6}$")
    name: str = Field(default="Usuario", min_length=1, max_length=80)
    accept_terms: bool = False


def _echo() -> bool:
    """El código se muestra en pantalla solo en beta y mientras no haya WhatsApp real configurado."""
    return sms.echo_allowed()


@router.get("/config")
def public_config():
    return {"beta": bool(os.environ.get("SGRS_BETA_KEY")), "otp_on_screen": _echo(),
            "terms_required": legal.required(), "terms_version": legal.TERMS_VERSION}


@router.post("/otp/request", status_code=202)
def otp_request(b: OtpRequest, request: Request, conn=Depends(get_conn)):
    ip = ratelimit.client_ip(request)
    beta_key = os.environ.get("SGRS_BETA_KEY")
    if beta_key:
        ratelimit.blocked(conn, "invite_fail", ip, limit=10, window=900)  # 10 claves erróneas / 15 min / IP
        if not (b.invite and hmac.compare_digest(b.invite.encode(), beta_key.encode())):
            ratelimit.fail(conn, "invite_fail", ip, 900)
            raise err(403, "INVITE_INVALID")
    # por IP: configurable porque varios testers pueden compartir la misma red (NAT)
    ratelimit.hit(conn, "otp_ip", ip, limit=int(os.environ.get("SGRS_OTP_IP_LIMIT", "20")), window=3600)
    ratelimit.hit(conn, "otp_phone", b.phone, limit=5, window=3600)  # 5 códigos / hora / número
    if not PHONE.match(b.phone):
        raise err(422, "PHONE_INVALID")
    if conn.execute("SELECT 1 FROM otp_codes WHERE phone_e164=%s AND created_at > now() - make_interval(secs => %s)",
                    (b.phone, RESEND_SECONDS)).fetchone():
        raise err(429, "OTP_TOO_SOON", retry_after=RESEND_SECONDS)
    code = f"{secrets.randbelow(10**6):06d}"  # CSPRNG
    conn.execute("INSERT INTO otp_codes (phone_e164, code_hash, expires_at)"
                 " VALUES (%s,%s, now() + make_interval(secs => %s))", (b.phone, _hash(b.phone, code), TTL_SECONDS))
    try:
        sms.send_otp(b.phone, code)
    except sms.DeliveryError:
        raise err(502, "OTP_SEND_FAILED") from None  # la transacción se revierte: no queda un código inútil
    out = {"expires_in": TTL_SECONDS}  # no se revela si el usuario existe
    if _echo():  # beta/E2E sin WhatsApp; con WhatsApp configurado nunca se devuelve
        out["dev_code"] = code
    return out


@router.post("/otp/verify")
def otp_verify(b: OtpVerify, request: Request, conn=Depends(get_conn)):
    ratelimit.hit(conn, "verify_ip", ratelimit.client_ip(request), limit=30, window=3600, persist=True)
    row = conn.execute(
        "SELECT * FROM otp_codes WHERE phone_e164=%s AND consumed_at IS NULL AND expires_at > now()"
        " ORDER BY created_at DESC LIMIT 1 FOR UPDATE", (b.phone,)).fetchone()
    if not row:
        raise err(401, "OTP_INVALID")
    if row["attempts"] >= MAX_ATTEMPTS:
        raise err(429, "OTP_LOCKED")
    if not hmac.compare_digest(row["code_hash"], _hash(b.phone, b.code)):
        conn.execute("UPDATE otp_codes SET attempts = attempts + 1 WHERE id=%s", (row["id"],))
        conn.commit()  # el intento fallido debe persistir aunque se responda error
        raise err(401, "OTP_INVALID")
    known = conn.execute("SELECT terms_version FROM users WHERE phone_e164=%s", (b.phone,)).fetchone()
    already = bool(known and known["terms_version"] == legal.TERMS_VERSION)
    if legal.required() and not already and not b.accept_terms:
        raise err(422, "TERMS_REQUIRED")  # antes de consumir el código: puede reintentar marcando la casilla
    accepting = b.accept_terms and not already
    conn.execute("UPDATE otp_codes SET consumed_at = now() WHERE id=%s", (row["id"],))
    u = conn.execute(
        "INSERT INTO users (phone_e164, name, phone_verified_at, terms_accepted_at, terms_version)"
        " VALUES (%s,%s, now(), CASE WHEN %s THEN now() END, CASE WHEN %s THEN %s END)"
        " ON CONFLICT (phone_e164) DO UPDATE SET phone_verified_at = coalesce(users.phone_verified_at, now()),"
        " terms_accepted_at = CASE WHEN %s THEN now() ELSE users.terms_accepted_at END,"
        " terms_version = CASE WHEN %s THEN %s ELSE users.terms_version END"
        " RETURNING id, role", (b.phone, b.name, accepting, accepting, legal.TERMS_VERSION,
                                accepting, accepting, legal.TERMS_VERSION)).fetchone()
    if accepting:
        write_audit(conn, u["id"], "ACCEPT_TERMS", "user", u["id"], {"version": legal.TERMS_VERSION})
    return {"access_token": issue_token(u["id"], u["role"]), "token_type": "bearer", "expires_in": TOKEN_TTL}
