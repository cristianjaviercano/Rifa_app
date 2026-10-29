"""Envío de SMS/WhatsApp. En desarrollo solo se registra en el log y en `outbox` (pruebas)."""
import logging

log = logging.getLogger("sgrs.sms")
outbox: list[tuple[str, str]] = []


def send(phone: str, text: str) -> None:
    outbox.append((phone, text))
    log.info("SMS a %s (proveedor no configurado)", phone[:-4] + "****")
