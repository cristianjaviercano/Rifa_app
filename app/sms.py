"""Entrega del código OTP: WhatsApp si está configurado; en desarrollo solo se registra."""
import logging
import os

from . import whatsapp

log = logging.getLogger("sgrs.sms")
outbox: list[tuple[str, str]] = []  # solo desarrollo/pruebas


class DeliveryError(Exception):
    pass


def echo_allowed() -> bool:
    """El código en pantalla solo se permite en beta: sin WhatsApp real y, en producción, con clave de
    invitación (sin ella cualquiera podría iniciar sesión con el número de otra persona)."""
    if os.environ.get("SGRS_DEV_ECHO_OTP") != "1" or whatsapp.config():
        return False
    return os.environ.get("SGRS_ENV") != "production" or bool(os.environ.get("SGRS_BETA_KEY"))


def send_otp(phone: str, code: str) -> None:
    if whatsapp.config():
        res = whatsapp.send_otp_code(phone, code)
        if not res.ok:
            log.error("OTP no enviado a %s: %s", phone[:-4] + "****", res.error)
            raise DeliveryError(res.error)
        return
    if echo_allowed():  # beta: el código viaja en la respuesta, no por mensajería
        return
    if os.environ.get("SGRS_ENV") == "production":
        raise DeliveryError("proveedor de mensajería no configurado")
    outbox.append((phone, f"Tu código SGRS es {code}. Vence en 5 minutos."))
    log.warning("WhatsApp no configurado: código OTP solo disponible en desarrollo")
