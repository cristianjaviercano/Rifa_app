import hashlib
import hmac
import os
import re
import secrets

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from . import sms
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


class OtpVerify(BaseModel):
    phone: str
    code: str = Field(pattern=r"^\d{6}$")
    name: str = Field(default="Usuario", min_length=1, max_length=80)


@router.post("/otp/request", status_code=202)
def otp_request(b: OtpRequest, conn=Depends(get_conn)):
    if not PHONE.match(b.phone):
        raise err(422, "PHONE_INVALID")
    if conn.execute("SELECT 1 FROM otp_codes WHERE phone_e164=%s AND created_at > now() - make_interval(secs => %s)",
                    (b.phone, RESEND_SECONDS)).fetchone():
        raise err(429, "OTP_TOO_SOON", retry_after=RESEND_SECONDS)
    code = f"{secrets.randbelow(10**6):06d}"  # CSPRNG
    conn.execute("INSERT INTO otp_codes (phone_e164, code_hash, expires_at)"
                 " VALUES (%s,%s, now() + make_interval(secs => %s))", (b.phone, _hash(b.phone, code), TTL_SECONDS))
    sms.send(b.phone, f"Tu código SGRS es {code}. Vence en 5 minutos.")
    out = {"expires_in": TTL_SECONDS}  # no se revela si el usuario existe
    if os.environ.get("SGRS_DEV_ECHO_OTP") == "1":  # SOLO desarrollo/E2E; nunca en producción
        out["dev_code"] = code
    return out


@router.post("/otp/verify")
def otp_verify(b: OtpVerify, conn=Depends(get_conn)):
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
    conn.execute("UPDATE otp_codes SET consumed_at = now() WHERE id=%s", (row["id"],))
    u = conn.execute(
        "INSERT INTO users (phone_e164, name, phone_verified_at) VALUES (%s,%s, now())"
        " ON CONFLICT (phone_e164) DO UPDATE SET phone_verified_at = coalesce(users.phone_verified_at, now())"
        " RETURNING id, role", (b.phone, b.name)).fetchone()
    return {"access_token": issue_token(u["id"], u["role"]), "token_type": "bearer", "expires_in": TOKEN_TTL}
