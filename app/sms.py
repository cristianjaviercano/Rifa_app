"""Entrega del código OTP: WhatsApp si está configurado; en desarrollo solo se registra."""
import logging
import os

from . import whatsapp

log = logging.getLogger("sgrs.sms")
outbox: list[tuple[str, str]] = []  # solo desarrollo/pruebas


class DeliveryError(Exception):
    pass


def send_otp(phone: str, code: str) -> None:
    if whatsapp.config():
        res = whatsapp.send_otp_code(phone, code)
        if not res.ok:
            log.error("OTP no enviado a %s: %s", phone[:-4] + "****", res.error)
            raise DeliveryError(res.error)
        return
    if os.environ.get("SGRS_DEV_ECHO_OTP") == "1":  # beta: el código viaja en la respuesta, no por mensajería
        return
    if os.environ.get("SGRS_ENV") == "production":
        raise DeliveryError("proveedor de mensajería no configurado")
    outbox.append((phone, f"Tu código SGRS es {code}. Vence en 5 minutos."))
    log.warning("WhatsApp no configurado: código OTP solo disponible en desarrollo")
