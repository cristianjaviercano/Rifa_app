"""Cliente de la API de WhatsApp Business (Cloud API de Meta).

Los mensajes iniciados por la empresa solo pueden enviarse con *plantillas* aprobadas
(ver docs/WHATSAPP.md). Aquí se arma el payload, se envía y se clasifica el error.
"""
import os
from dataclasses import dataclass
from typing import Optional

import httpx

TYPES = {  # tipo de notificación -> (variable de entorno, plantilla por defecto)
    "PAYMENT_APPROVED": ("WA_TPL_PAYMENT_APPROVED", "sgrs_pago_confirmado"),
    "WINNER": ("WA_TPL_WINNER", "sgrs_ganador"),
    "DRAW_FINISHED": ("WA_TPL_DRAW_FINISHED", "sgrs_sorteo_concluido"),
    "DRAW_REMINDER": ("WA_TPL_DRAW_REMINDER", "sgrs_recordatorio_sorteo"),
}
OTP_TEMPLATE = ("WA_TPL_OTP", "sgrs_codigo")
# Códigos de Meta que justifican reintentar (límites de tasa/capacidad); el resto es permanente.
RETRYABLE_CODES = {4, 80007, 130429, 131056, 131000, 2}


@dataclass
class Config:
    token: str
    phone_id: str
    version: str
    lang: str


def config() -> Optional[Config]:
    t, p = os.environ.get("WHATSAPP_TOKEN"), os.environ.get("WHATSAPP_PHONE_ID")
    if not (t and p):
        return None
    return Config(t, p, os.environ.get("WHATSAPP_API_VERSION", "v21.0"), os.environ.get("WHATSAPP_LANG", "es"))


def template_name(kind: str) -> str:
    var, default = OTP_TEMPLATE if kind == "OTP" else TYPES[kind]
    return os.environ.get(var, default)


@dataclass
class Result:
    ok: bool
    msg_id: Optional[str] = None
    retryable: bool = False
    error: Optional[str] = None


def _client() -> httpx.Client:  # sustituible en pruebas
    return httpx.Client(timeout=10)


def template_payload(to: str, name: str, lang: str, params: list[str], button_param: Optional[str] = None) -> dict:
    comps = [{"type": "body", "parameters": [{"type": "text", "text": str(p)[:1000]} for p in params]}]
    if button_param is not None:  # plantillas de autenticación: botón "copiar código"
        comps.append({"type": "button", "sub_type": "url", "index": "0",
                      "parameters": [{"type": "text", "text": button_param}]})
    return {"messaging_product": "whatsapp", "to": to.lstrip("+"), "type": "template",
            "template": {"name": name, "language": {"code": lang}, "components": comps}}


def send_payload(payload: dict) -> Result:
    cfg = config()
    if not cfg:
        return Result(False, error="whatsapp no configurado")
    url = f"https://graph.facebook.com/{cfg.version}/{cfg.phone_id}/messages"
    try:
        with _client() as c:
            r = c.post(url, json=payload, headers={"Authorization": f"Bearer {cfg.token}"})
    except httpx.HTTPError as e:
        return Result(False, retryable=True, error=f"red: {type(e).__name__}")
    if r.status_code < 300:
        try:
            return Result(True, msg_id=r.json()["messages"][0]["id"])
        except (KeyError, IndexError, ValueError):
            return Result(False, error="respuesta inesperada de Meta")
    try:
        e = r.json().get("error", {})
    except ValueError:
        e = {}
    code = e.get("code")
    msg = f"{r.status_code}/{code}: {e.get('message', '')}"[:300]
    return Result(False, retryable=r.status_code >= 500 or r.status_code == 429 or code in RETRYABLE_CODES, error=msg)


def send_template(to: str, kind: str, params: list[str]) -> Result:
    cfg = config()
    if not cfg:
        return Result(False, error="whatsapp no configurado")
    return send_payload(template_payload(to, template_name(kind), cfg.lang, params))


def send_otp_code(to: str, code: str) -> Result:
    cfg = config()
    if not cfg:
        return Result(False, error="whatsapp no configurado")
    return send_payload(template_payload(to, template_name("OTP"), cfg.lang, [code], button_param=code))
